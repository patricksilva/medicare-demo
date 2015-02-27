import time
import sys

MAX_NPI_ID = 880643
MAX_CPT_CODE = 5948
MAX_SPECIALTY_ID = 175

folder = sys.argv[1]
path = "hdfs://"+folder+"/"

print "Reading specialty"
# specialty:  specialty-id <tab> description
# Specialty table maps specialty id to its description. 
specialty_file = path+"specialty"
`Specialty(int specialty:0..$MAX_SPECIALTY_ID, String descr) indexby descr.
 Specialty(spec, descr) :- l=$read($specialty_file), 
                           (descr, _spec) = $split(l, "\t"),
                           spec=$toInt(_spec).`

specialties = []
# These are the specialties we will use as source nodes in the PageRank algorithm.
specialtyDescrs = ["Dermatology", "Otolaryngology", "Plastic Surgery", "Ophthalmology",
                   "Radiology", "Optometrist", "Pathology",  "Physical Therapist" ] 

for descr in specialtyDescrs:
    num, _ = `Specialty(num, $descr)`.next()
    specialties.append(num)

# Build a map of similar specialties. This is used to find false-positives.
similarSpecialtyDescrs = [("Dentist", "Oral & Maxillofacial Surgery"),
                          ("Radiology", "Radiologic Technologist"),
                          ("Assistant, Podiatric", "Podiatrist"),
                          ("Optometrist", "Ophthalmology"),
                          ("Massage Therapist", "Physical Therapist", "Physical Therapy Assistant",\
                           "Mechanotherapist", "Rehabilitation Practitioner", "Rehabilitation Hospital", "Chiropractor"),
                          ("Psychiatric Unit", "Psychoanalyst", "Psychiatric Hospital", "Psychiatry & Neurology", "Psychologist", "Behavioral Analyst"),
                          ("Pathology", "Technician, Pathology", "Spec/Tech, Pathology"),
                          ("Pain Medicine", "Nurse Anesthetist, Certified Registered",\
                           "Anesthesiologist Assistant", "Anesthesiology"),
                          ]
similarSpecialties = []
for simGroup in similarSpecialtyDescrs:
    g = []
    for descr in simGroup:
      try:
        num, _ = `Specialty(num, $descr)`.next()
        g.append(num)
      except: continue 
    similarSpecialties.append(g)

similarSpecialtyMap = {}
for specialtyGroup in similarSpecialties:
    for s in specialtyGroup:
        similarSpecialtyMap[s] = specialtyGroup

print "Reading the graph"

import time
# graph: npi1 <tab> npi2
# This represents a graph of NPIs whose prescriptions are similar.
# If the prescription of an NPI is similiar enough to another NPI, then there is an edge between the NPIs.
# This file graph can be generated by running run1.sh, which preprocess the Medicare data set and 
# computes cosine similarity between NPIs.
graph_file = path+"graph"
s = time.time()
`Graph(int npi:0..$MAX_NPI_ID, (int npi2)) multiset.
 Graph(npi1, npi2) :- l=$read($graph_file), 
                       (_npi1, _npi2)=$split(l, "\t"),
                        npi1=$toInt(_npi1),
                        npi2=$toInt(_npi2). `

# This is an undirected graph, and we represent an undirected edge between n1 and n2 by 
# having two directed edges (n1 -> n2 and n2 -> n1).
`Graph(npi2, npi1) :- Graph(npi1, npi2). `
print "Loading time:%.2f sec."%(time.time()-s)
 
# EdgeCnt table stores the number of edges for each node (node id, neighbor count)
`EdgeCnt(int npi:0..$MAX_NPI_ID, int cnt).
 EdgeCnt(npi, $inc(1)) :- Graph(npi, npi2).`

print "Reading npi-cpt-code"

# npi-cpt-code: NPI <tab> NPI specialty <tab> CPT code <tab> CPT code frequency
# NPI table stores the information (NPI, specialty, CPT code, frequency)
npi_cpt_file = path+"npi-cpt-code"
`NPI(int npi:0..$MAX_NPI_ID, int specialty, (int code, int freq)).
 NPI(npi, specialty, code, freq) :- l=$read($npi_cpt_file), 
                                       (_npi, _spec, _code, _freq) = $split(l, "\t"),
                                       npi = $toInt(_npi),
                                       specialty = $toInt(_spec),
                                       code = $toInt(_code),
                                       freq = $toInt(_freq).`

print "Reading hcpcs-code"
# hcpcs_code: CPT code <tab> description
# Specialty table maps specialty id to its description.
cpt_file = path+"hcpcs-code"
`Code(int code:0..$MAX_CPT_CODE, String descr).
 Code(code, descr) :- l=$read($cpt_file), 
                           (_, descr, _code) = $split(l, "\t"),
                           code = $toInt(_code).`

# We go over selected specialties, 
# and run PageRank algorithm with the NPIs having the selected specialty as the source nodes.
for i in range(len(specialties)):
    clusterSpecialty = specialty = specialties[i]
    specialty_descr = specialtyDescrs[i]
    print "Running Personalized PageRank... (source specialty:"+specialty_descr+")"

    `Source(int npi) indexby npi.
     Source(npi) :- NPI(npi, specialty, _, _), specialty==$specialty.`
 
    # NPIs with similar specialties are also considered as source nodes.
    if clusterSpecialty in similarSpecialtyMap:
        for s in similarSpecialtyMap[clusterSpecialty]:
            if s == clusterSpecialty: continue
            `Source(npi) :- NPI(npi, specialty, _, _), specialty==$s.`

    `SourceCnt(int n:0..0, int cnt) groupby(1).
     SourceCnt(0, $inc(1)) :- Source(npi). `

    _, N = `SourceCnt(0, N)`.next()

    # Rank table stores PageRank values for NPIs.
    # (npi, iteration #, rank value)
    # The table only stores the values for the recent two iterations.
    `Rank(int npi:0..$MAX_NPI_ID, int i:iter, float rank).`
    #sys.stdout.write("..")

    # Initially we assign the PageRank value of 1/N to source nodes, where N is the number of source nodes.
    `Rank(source_npi, 0, pr) :- Source(source_npi), pr=1.0f/$N.`
    for i in range(10):
        `Rank(node, $i+1, $sum(pr)) :- Source(node), pr = 0.2f*1.0f/$N ;
                                  :- Rank(src, $i, pr1), pr1>1e-8, EdgeCnt(src, cnt), pr = 0.8f*pr1/cnt, Graph(src, node).`

        # The first body represents the jump to one of source nodes with probability 0.2.
        # The second body computes the random walk from src NPI to target NPI.
        # For efficiency, we ignore random walks from the nodes whose PageRank values are smaller than 1e-8.
        # This approximates the computation.

        sys.stdout.write("..")
        sys.stdout.flush()
    print
    
    `MinRank(int i:0..0, float rank) groupby(1).
     MinRank(0, $min(r)) :- Rank(npi, $i, r), NPI(npi, specialty, _, _),
                            specialty == $specialty.`
    _, minRank = `MinRank(0, r)`.next()
    threshold = minRank
    `MaxRank(int i:0..0, float rank) groupby(1).
     MaxRank(0, $max(rank)) :- Rank(npi, $i, rank).`
    _, maxRank = `MaxRank(0, rank)`.next()
    if threshold == 0: 
        threshold = maxRank*0.01

    # Anomaly candidates are NPIs whose specialty is different from the selected specialty, but has high PageRank value.
    `AnomalyCandidate(int npi, float rank) multiset.
     AnomalyCandidate(npi, rank) :- Rank(npi, $i, rank), NPI(npi, specialty, _, _),
                                specialty != $specialty, rank>=$threshold.`

    # We sort anomalies by their PageRank values
    anomalies=[]
    from heapq import *
    for npi, rank in `AnomalyCandidate(npi, rank)`:
        heappush(anomalies, (1-rank, npi))   

    # and pick top anomaly candidates with high PageRank values
    topAnomalies = []
    while anomalies:
        priority, npi = heappop(anomalies)
        rank = 1-priority
        topAnomalies.append((npi, rank))
        if len(topAnomalies) > 1000:
            break


    # Specialties occuring more than threshold(10) or part of the fpRole list are considered false-positives.
    falsePositives=set()
    fpRole = ["Specialist", "Physician Assistant", "Family Medicine", "Nurse Practitioner", "Student in an Organized Health Care Education/Training Program",
              "Emergency Medicine", "Registered Nurse", "Skilled Nursing Facility", "Nurse's aid", "Legal Medicine", "Clinicians Nurse Specialist",
             "Nursing Care", "Nurse's Aide", "Clinical Nurse Specialist", "General Practice"]
    specialtyCount={}
    for npi, rank in topAnomalies:
        _, specialty, _, _ = `NPI($npi, specialty, _, _)`.next()
        try:
          _, sp_desc = `Specialty($specialty, sp_desc)`.next()
          if sp_desc in fpRole:
            falsePositives.add(specialty)
          specialtyCount[specialty] += 1
        except: specialtyCount[specialty] = 1
        if specialtyCount[specialty] >= 10:
            falsePositives.add(specialty)
 
    if clusterSpecialty in similarSpecialtyMap:
        for similarSpecialty in similarSpecialtyMap[clusterSpecialty]:
            falsePositives.add(similarSpecialty)

    print "+------------------------------------------+"
    print " Anomaly analysis with specialty ", specialty_descr
    print "   Number of NPIs with this specialty: ", N
    print "   Max PageRank value:", maxRank
    print "   Some of unexpected specialties having high PageRank values:"
    for specialty, cnt in specialtyCount.items():
        if specialty in falsePositives:
            continue
        _, descr = `Specialty($specialty, descr)`.next()
        print "     %s:%d"%(descr, cnt)

    # We print top 5 anomalies and their prescribed CPT codes.
    print "   Top 5 Anomalies:"
    anomalyCount = 0
    while topAnomalies:
        npi, rank = topAnomalies.pop(0)
        _, specialty, _, _ = `NPI($npi, specialty, _, _)`.next()
        if specialty == clusterSpecialty:
            continue
        if specialty in falsePositives:
            continue
        _, descr = `Specialty($specialty, descr)`.next()
        print "      %d.NPI:%s, Specialty:%s, PageRank:%f" % (anomalyCount+1, npi, descr, rank)
        for _, specialty, code, freq in `NPI($npi, specialty, code, freq)`:
            _, descr = `Code($code, descr)`.next()
            print "\t\t", descr, ":", freq

        anomalyCount += 1
        if anomalyCount==5: break

    print "-----------------------------\n"
    specialtyCount.clear()

    # We clear the tables for the next iteration.
    `clear Rank.
     clear AnomalyCandidate.
     clear Source.
     clear SourceCnt.
     clear MaxRank.
     clear MinRank.`
