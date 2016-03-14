#!/usr/bin/env python2

import bootstrap
import os
import datetime
table_path = "../tables/"
results_path = "../results/"

bootstrap.cutoff = 1e-10

dim = 3
k_max = 40
l_max = 30
n_max = 11
m_max = 1
odd_spins = False
delta_12 = 0 
delta_34 = 0

dim_phi_range = [0.501,0.53]
number_of_points = 10
lower_eps = 0.7
upper_eps = 1.7
threshold = 0.01
channel = 0

log_name = results_path + "single_bound_" + datetime.datetime.now().strftime("%b_%d_%H_%M") + ".txt"
log = open(log_name, 'w')
log.write("\"\n")
log.write("dim_phi range = " + str(dim_phi_range) + "\n")
log.write("number of points = " + str(number_of_points) + "\n")
log.write("lower_eps = " + str(lower_eps) + "\n")
log.write("upper_eps = " + str(upper_eps) + "\n")
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

points = [dim_phi_range[0] + x*(dim_phi_range[1]-dim_phi_range[0])/(number_of_points-1) for x in range(0,number_of_points)]

table_name = "d" + str(dim) + "_k" + str(k_max) + "_L" + str(l_max) + "_m"+ str(m_max) + "_n" + str(n_max) + "_delta12_" + str(delta_12) + "_delta34_" + str(delta_34) + "_oddL_" + str(odd_spins) 
if os.path.isfile(table_path + table_name):
    table = bootstrap.ConformalBlockTable(0,0,0,0,0,0,0,0,table_path + table_name)
else:    
    table = bootstrap.ConformalBlockTable(dim, k_max, l_max, m_max, n_max, delta_12, delta_34, odd_spins)
    table.dump(table_path + table_name)

table_convolved = bootstrap.ConvolvedBlockTable(table)

for dim_phi in points:
    print("Evaluating phi = " + str(dim_phi))
    sdp = bootstrap.SDP(dim_phi, table_convolved)
    result = sdp.bisect(lower_eps, upper_eps, threshold, channel)
    log = open(log_name, 'a')
    log.write("{" + str(dim_phi) + ", " + str(result) + "}\n")
    log.close()
    print("Bound found: (" + str(dim_phi) + ", " + str(result) + ")\n")

log = open(log_name, 'a')
log.write("\n\n\"\nFinished " + datetime.datetime.now().strftime("%b %d, %H:%M") + "\n\"")
log.close()
print("Done, results printed to " + log_name + "\n")



