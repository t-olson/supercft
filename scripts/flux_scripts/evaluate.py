#!/usr/bin/env python 2

import os
from sys import argv
from random import randint
from time import sleep
from fractions import Fraction

script, point = argv

print "now evaluating: " + str(point)

def convertStringToList(strng, typ):
	return map(typ, strng.lstrip('[').rstrip(']').replace(',',' ').split())

def pointToString(point):
	return '[[' + str(map(str, point[0][0])).replace("'", "") + ', ' + str(point[0][1]) + '], ' + str(point[1]) + ']'	

def readPoint(strng):
	split_point = strng.index('],')+1
	return [[convertStringToList(strng[2:split_point], Fraction), int(strng[split_point+1])], convertStringToList(strng[(split_point+4):-1],int)]

pointStr = point	

point = readPoint(point)	

x = point[0][0][0]
y = point[0][0][1]

if y < -4*((x-.5)**2) + .99:
	pointEval = [[point[0][0], 1], point[1]]
else:
	pointEval = [[point[0][0], 0], point[1]]

f = open('points.txt', 'a')
f.write(pointToString(pointEval).replace(" ", "") + "\n")
f.close()

f = open('in_progress.txt','r')
work = f.read()
f.close()
work = work.replace(pointStr, "")
f = open('in_progress.txt', 'w')
f.write(work)
f.close()

os.system('python scheduler.py')