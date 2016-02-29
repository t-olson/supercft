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

dim_phi_range = [0.501,0.53]
dim_eps_range = [1,1.5]
eps_gap = float(3)
number_of_points = 10 # makes an n x n grid
lower_eps = 0.7
upper_eps = 1.7
threshold = 0.01
channel = 0

log_name = results_path + "single_bound_eps_gap_" + datetime.datetime.now().strftime("%b_%d_%H_%M") + ".txt"
log = open(log_name, 'w')
log.write("\"\n")
log.write("dim_phi range = " + str(dim_phi_range) + "\n")
log.write("dim_eps range = " + str(dim_phi_range) + "\n")
log.write("eps_gap = " + str(eps_gap) + "\n")
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

phi_points = [dim_phi_range[0] + x*(dim_phi_range[1]-dim_phi_range[0])/(number_of_points-1) for x in range(0,number_of_points)]
eps_points = [dim_eps_range[0] + x*(dim_eps_range[1]-dim_eps_range[0])/(number_of_points-1) for x in range(0,number_of_points)]

table_name = "d" + str(dim) + "_k" + str(k_max) + "_L" + str(l_max) + "_m"+ str(m_max) + "_n" + str(n_max) + "_delta12_" + str(delta_12) + "_delta34_" + str(delta_34) + "_oddL_" + str(odd_spins) 
if os.path.isfile(table_path + table_name):
    table = bootstrap.ConformalBlockTable(0,0,0,0,0,0,0,0,table_path + table_name)
else:    
    table = bootstrap.ConformalBlockTable(dim, k_max, l_max, m_max, n_max, delta_12, delta_34, odd_spins)
    table.dump(table_path + table_name)

table_convolved = bootstrap.ConvolvedBlockTable(table)

final_results = []

for dim_phi in phi_points:
    sdp = bootstrap.SDP(dim_phi, table_convolved)
    sdp.set_bound(channel, eps_gap)
    for dim_eps in eps_points:
        print("Evaluating (" + str(dim_phi)[0:4] + ", " + str(dim_eps)[0:4] + ")")
        sdp.add_point(channel, dim_eps)
        result = sdp.iterate()
        sdp.add_point(channel)
        log = open(log_name, 'a')
        log.write("{" + str(dim_phi) + ", " + str(dim_eps) + ", " + str(result) + "}\n")
        log.close()
        if (result):
            print("Yes")
        else:
            print("No")


log = open(log_name, 'a')
log.write("\n\"\nFinished " + datetime.datetime.now().strftime("%b %d, %H:%M") + "\n\"")
log.close()
print("Done, results printed to " + log_name + "\n")













































