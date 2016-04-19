#!/usr/bin/env python2

import bootstrap
import os
import datetime
table_path = "../tables/"
results_path = "../results/"

#Cut-off for dropping poles with small residues
bootstrap.cutoff = 1e-10

#Can't do exactly dim = 4, since double poles start to appear there.
#Approximate with dim = 3.99.
dim = 3.99

#Range of dim_phi values, and number of points to take along the range
dim_phi_range = [1.01, 1.4]
number_of_points = 10

#Upper and lower bounds on what dimensions to bisect on
lower_eps = 2.01
upper_eps = 4.0

#The threshold for stopping the bisection 
threshold = 0.01

#Channel we're bisecting on
channel = 0

#SDPB parameters
k_max = 25
l_max = 26
n_max = 7
m_max = 1
odd_spins = True
delta_12 = 0
delta_34 = 0

#Write to the log file with SDPB information
log_name = results_path + "super_single_bound_4d_" + datetime.datetime.now().strftime("%b_%d_%H_%M") + ".txt"
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

#points = [dim_phi_range[0] + x*(dim_phi_range[1]-dim_phi_range[0])/(number_of_points-1) for x in range(0,number_of_points)]
points = [1.4,1.2]

table_name = "d" + str(dim) + "_k" + str(k_max) + "_L" + str(l_max) + "_m"+ str(m_max) + "_n" + str(n_max) + "_delta12_" + str(delta_12) + "_delta34_" + str(delta_34) + "_oddL_" + str(odd_spins) 

#Ordinarily, we'd store tables and load them as needed.  
#I'd rather not right now, just to make sure that everything is working correctly

#if os.path.isfile(table_path + table_name):
#    print("Found previously existing table.\n")
#    table = bootstrap.ConformalBlockTable(0,0,0,0,0,0,0,0,table_path + table_name)
#else:    
#    print("No previous table - generating one.\n")
#    table = bootstrap.ConformalBlockTable(dim, k_max, l_max, m_max, n_max, delta_12, delta_34, odd_spins)
#    table.dump(table_path + table_name)

print("Setting up table...")
table = bootstrap.ConformalBlockTable(dim, k_max, l_max, m_max, n_max, delta_12, delta_34, odd_spins)
print("Done.\n")

#What we're going to have to do is:
#
#1. Generate the tables corresponding to delta_12 and delta_34
#2. Convolve with different values of delta and spin as appropriate for superconformal blocks
#3. Write to SDPB with all of the combinations, depending on the c_i coefficients

delta = bootstrap.delta
spin = bootstrap.ell

print("Getting superconformal coefficients...")

#The naive coefficients listed by Miguel et. al. in [1503.02081] are
#c1 = 1
#c2 = ((delta + delta_12 + spin) * (delta + delta_34 + spin)) / (2 * (delta + spin) * (delta + spin + 1))
#c3 = (spin * (spin + dim - 3) * (delta + delta_12 - spin - dim + 2) * (delta + delta_34 - spin - dim + 2)) / (2 * #( (2 * spin) + dim - 4) * ( (2 * spin) + dim - 2) * (delta - spin - dim + 2) * (delta - spin - dim + 3))
#c4 = (delta * (delta - dim + 3) * (delta + delta_12 + spin) * (delta + delta_34 + spin) * (delta + delta_12 - spin - dim + 2) * (delta + delta_34 - spin - dim + 2)) / (4 * ( (2 * delta) - dim + 4) * ( (2 * delta) - dim + 2) * (delta + spin) * (delta + spin + 1 ) * (delta - spin - dim + 2) * (delta - spin - dim + 3))

#With delta_12 = delta_34 = 0 and multiplying out by a common denominator, the coefficients in 4D become:
c1 = 16 * (delta + spin + 1) * (delta - spin - 1)
c2 = -8 * (delta + spin) * (delta - spin - 1)
c3 = -2 * (delta - spin - 2) * (delta + spin + 1)
c4 = (delta + spin) * (delta - spin - 2)

#Connor's conventions give them to be:
#c1 = (delta + spin + 1) * (delta - spin - 1) * (spin + 1)
#c2 = -(delta + spin) * (delta - spin - 1) * (spin + 2)
#c3 = -(delta - spin - 2) * (delta + spin + 1) * spin
#c4 = (delta + spin) * (delta - spin - 2) * (spin + 1)

combo1 = [[c1, 0, 0], [c2, 1, 1], [c3, 1, -1], [c4, 2, 0]]
combo2 = combo1
combo2[1][0] *= -1
combo2[2][0] *= -1

print("Done.\n")

print("Convolving all of the relevant tables for superconformal purposes...")
convtab_1a = bootstrap.ConvolvedBlockTable(table)
convtab_1s = bootstrap.ConvolvedBlockTable(table, symmetric = True)
convtab_2a = bootstrap.ConvolvedBlockTable(table, content = combo1)
convtab_2s = bootstrap.ConvolvedBlockTable(table, content = combo1, symmetric = True)
convtab_3 = bootstrap.ConvolvedBlockTable(table, content = combo2)

tab_list = [convtab_1a, convtab_1s, convtab_2a, convtab_2s, convtab_3]

vec1 = [[1, 4], [1, 2], [1, 3]]
vec2 = [[-1, 4], [1, 2], [1, 3]]
vec3 = [[0, 0], [1, 0], [-1, 1]]

#Give these vectors labels for their spin (even, odd, even, respectively) and their representations
info = [[vec1, 0, "singlet"], [vec2, 1, "antisymmetric"], [vec3, 0, "symmetric"]]
print("Done.\n")

print("Now, time to bisect on values of dim_phi.\n")
for dim_phi in points:
    
    print("Setting up SDP for dim_phi = " + str(dim_phi) + "...")
    sdp = bootstrap.SDP(dim_phi, tab_list, vector_types = info)
    sdp.set_option("dualErrorThreshold", 1e-22)

    # Goes through all spins, tells the symmetric channel to contain a BPS operator and then a gap.
    for l in range(0, l_max + 1, 2):
        sdp.add_point([l, "symmetric"], 2 * dim_phi + l)
        sdp.set_bound([l, "symmetric"], abs(2 * dim_phi - dim + 1) + dim - 1 + l)
        
    # Need to also account for the antichiral case for the phi-phi OPE
    if dim_phi < dim/4.0:
        sdp.add_point([0, "symmetric"], dim - 2 * dim_phi)
    print("Done. Now, bisect on dim_eps values.\n")

    #Bisect on the first non-identity operator in the phi-phibar OPE
    #i.e. means bisecting on the [0, "singlet"] vector
    result = sdp.bisect(lower_eps, upper_eps, threshold, [0, "singlet"])

    #Punch in the result to the log file
    log = open(log_name, 'a')
    log.write("{" + str(dim_phi) + ", " + str(result) + "}\n")
    log.write("\n\n Finished " + datetime.datetime.now().strftime("%b %d, %H:%M") + "\n")
    log.close()
    print("Bound found: (" + str(dim_phi) + ", " + str(result) + "}\n")

