#!/usr/bin/env python2

import bootstrap
import os
import datetime
table_path = "./tables/"
results_path = "./results/"


bootstrap.cutoff = 1e-10

dim = 3
k_max = 20
l_max = 14
n_max = 4
m_max = 2
odd_spins = False
delta_12 = 0 
delta_34 = 0

threshold = 0.01
channel = 0

log_name = results_path + "single_bound_epsprime_" + datetime.datetime.now().strftime("%b_%d_%H_%M") + ".txt"
log = open(log_name, 'w')
log.write("\"\n")
log.write("threshold = " + str(threshold) + "\n")
log.write("channel = " + str(channel) + "\n\n")
log.write("bootstrap cutoff = " + str(bootstrap.cutoff) + "\n")
log.write("d = " + str(dim) + "\n")
log.write("k_max = " + str(k_max) + "\n")
log.write("L_max = " + str(l_max) + "\n")
log.write("m_max = " + str(m_max) + "\n")
log.write("n_max = " + str(n_max) + "\n")
log.write("odd L = " + str(odd_spins) + "\n\"\n\n")
log.close()

# bounds from a previous run on eps
points = [[0.501, 1.059375], [0.5042222222222222, 1.153125], [0.5074444444444445, 1.2234375], [0.5106666666666667, 1.29375], [0.513888888888889, 1.3640625], [0.5171111111111111, 1.4109375], [0.5203333333333333, 1.434375], [0.5235555555555556, 1.45], [0.5267777777777778, 1.4734375], [0.53, 1.4890625]]

table_name = "d" + str(dim) + "_k" + str(k_max) + "_L" + str(l_max) + "_m"+ str(m_max) + "_n" + str(n_max) + "_delta12_" + str(delta_12) + "_delta34_" + str(delta_34) + "_oddL_" + str(odd_spins) 
if os.path.isfile(table_path + table_name):
    table = bootstrap.ConformalBlockTable(0,0,0,0,0,0,0,0,table_path + table_name)
else:    
    table = bootstrap.ConformalBlockTable(dim, k_max, l_max, m_max, n_max, delta_12, delta_34, odd_spins)
    table.dump(table_path + table_name)

table_convolved = bootstrap.ConvolvedBlockTable(table)

for eps_bound in points:
    dim_phi = eps_bound[0]
    dim_eps = eps_bound[1]
    print("Evaluating phi = " + str(dim_phi))
    sdp = bootstrap.SDP(dim_phi, table_convolved)
    sdp.add_point(channel, dim_eps)
    result = sdp.bisect(dim_eps + threshold, 8, threshold, channel)
    log = open(log_name, 'a')
    log.write("{" + str(dim_phi) + ", " + str(result) + "}\n")
    log.close()
    print("Bound found: (" + str(dim_phi) + ", " + str(result) + ")\n")

log = open(log_name, 'a')
log.write("\n\n\"\nFinished " + datetime.datetime.now().strftime("%b %d, %H:%M") + "\n\"")
log.close()
print("Done, results printed to " + log_name + "\n")
