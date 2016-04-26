#!/usr/bin/env python2

import bootstrap
import os
import datetime
table_path = "../tables/"
results_path = "../results/"

#Cut-off for dropping poles with small residues
#I set this to 1e-10, but that seemed to rule out everything
bootstrap.cutoff = 0

#Make sure 2 < dim < 4, since double poles appear at even dimensions
#Approximate endpoints with 2.01 and 3.99
dim = 3
print("Doing bootstrap with dim = " + str(dim) + "\n")

#Upper and lower bounds on what dimensions to bisect on
#In Bobev et. al.'s results, dim_eps is roughly somewhere between dim - 2 and dim + 0.5.
lower_eps = 1.51
upper_eps = 3.5

#Channel we're bisecting on
channel = 0

#SDPB parameters
k_max = 35
l_max = 36
n_max = 7
m_max = 1
odd_spins = True
delta_12 = 0
delta_34 = 0

#Generate table with the given SDPB parameters
print("Setting up table...")
table = bootstrap.ConformalBlockTable(dim, k_max, l_max, m_max, n_max, delta_12, delta_34, odd_spins)
print("Done.\n")

delta = bootstrap.delta
spin = bootstrap.ell

print("Getting superconformal coefficients...")

#Connor's conventions give them to be, in 4D:
#c1 = (delta + spin + 1) * (delta - spin - 1) * (spin + 1)
#c2 = -(delta + spin) * (delta - spin - 1) * (spin + 2)
#c3 = -(delta - spin - 2) * (delta + spin + 1) * spin
#c4 = (delta + spin) * (delta - spin - 2) * (spin + 1)

#These should be the general coefficients in arbitrary dimensions
#They reduce to Connor's (up to an overall positive constant) in the 4D case
c1 = (dim + 2*spin - 2)*(delta - spin + 3 - dim)*(delta + spin + 1)*(2*delta + 2 - dim)*(2*delta + 4 - dim)
c2 = -2*(dim + spin - 2)*(delta - spin + 3 - dim)*(delta + spin)*(2*delta + 2 - dim)*(2*delta + 4 - dim)
c3 = -2*spin*(delta - spin + 2 - dim)*(delta + spin + 1)*(2*delta + 2 - dim)*(2*delta + 4 - dim)
c4 = 4*(dim + 2*spin - 2)*(delta + 3 - dim)*(delta - spin + 2 - dim)*delta*(delta+spin)

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

#Set up the [delta_phi, delta_eps] points that you want to test
#Right now code is only implemented for pair1, but that's easily modified
pair1 = [0.9, 3.3]
#pair2 = [0.9, 2.0]

print("Initialize the sdp...")
sdp1 = bootstrap.SDP(pair1[0], tab_list, vector_types = info)
#sdp2 = bootstrap.SDP(pair2[0], tab_list, vector_types = info)
print("Done.\n")

print("Setting bounds on the sdp...")
# Goes through all spins, tells the symmetric channel to contain a BPS operator and then a gap.
for l in range(0, l_max + 1, 2):
    sdp1.add_point([l, "symmetric"], 2 * pair1[0] + l)
    sdp1.set_bound([l, "symmetric"], abs(2 * pair1[0] - dim + 1) + dim - 1 + l)
    #sdp2.add_point([l, "symmetric"], 2 * pair2[0] + l)
    #sdp2.set_bound([l, "symmetric"], abs(2 * pair2[0] - dim + 1) + dim - 1 + l)
        
# Need to also account for the antichiral case for the phi-phi OPE
if pair1[0] < dim/4.0:
    sdp1.add_point([0, "symmetric"], dim - 2 * pair1[0])

#if pair2[0] < dim/4.0:
#    sdp2.add_point([0, "symmetric"], dim - 2 * pair2[0])

#Tells sdp that we want to look at the dim_eps value in pair1
sdp1.set_bound([0, "singlet"],pair1[1])

#Sets the dualErrorThreshold
#I'm not sure if this is where we need to crank up the accuracy to get results
sdp1.set_option("dualErrorThreshold", 1e-20)
print("Done.\n")

print("Now, iterate!  Is (" + str(pair1[0]) + ", " + str(pair1[1]) + ") allowed?")
allowed = sdp1.iterate()
if (allowed):
    print("Yes!")
else:
    print("No...")
