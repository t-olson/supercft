#!/usr/bin/env python 2

import os
from fractions import Fraction

def flatten(lst):
	return [x for sublist in lst for x in sublist]

def convertTrianglesToPoints(triangles):
	pointsTemp = []
	points = []
	for point in flatten(triangles):
		if point not in pointsTemp:
			pointsTemp.append(point)
	for point in pointsTemp:
		points.append([point,[x for x in range(len(triangles)) if point in triangles[x]]])
	return points

def convertPointsToTriangles(points):
	triangleIndex = list(set(flatten([point[1] for point in points])))
	triangles = []
	for indice in triangleIndex:
		triangles.append([point[0] for point in points if indice in point[1]])
	return triangles

def convertStringToList(strng, typ):
	return map(typ, strng.lstrip('[').rstrip(']').replace(',',' ').split())

def pointToString(point):
	return '[[' + str(map(str, point[0][0])).replace("'", "") + ', ' + str(point[0][1]) + '], ' + str(point[1]) + ']'

def readPoint(strng):
	split_point = strng.index('],')+1
	return [[convertStringToList(strng[2:split_point], Fraction), int(strng[split_point+1])], convertStringToList(strng[(split_point+4):-1],int)]

with open('log.txt') as f:
    log = f.read().splitlines()
    iter_current = int(log[0][-1])
    iter_total = int(log[1][-1])

# read in points

with open('points.txt') as f:
    points = f.read().splitlines()
		
#convert strings to lists of floats and ints

points = map(readPoint, points)		

# check to see if any points still need to be evaluated

nextPoint = next((point for point in points if point[0][1] == 2), 0)

def splitTriangle(triangle):
	p1 = triangle[0][0]
	p2 = triangle[1][0]
	p3 = triangle[2][0]
	val1 = triangle[0][1]
	val2 = triangle[1][1]
	val3 = triangle[2][1]
	c = [(a + b + c)/3 for a, b, c in zip(p1, p2, p3)]
	lst = []
	if val1 != val2:
		p1p2 = [(a + b)/2 for a, b in zip(p1, p2)]
		lst.append([[c, 2], [p1, val1], [p1p2, 2]])
		lst.append([[c, 2], [p2, val2], [p1p2, 2]])
	if val2 != val3:
		p2p3 = [(a + b)/2 for a, b in zip(p2, p3)]
		lst.append([[c, 2], [p2, val2], [p2p3, 2]])
		lst.append([[c, 2], [p3, val3], [p2p3, 2]])
	if val3 != val1:
		p1p3 = [(a + b)/2 for a, b in zip(p1, p3)]
		lst.append([[c, 2], [p1, val1], [p1p3, 2]])
		lst.append([[c, 2], [p3, val3], [p1p3, 2]])
	return lst

if nextPoint != 0:
	inProgress = open('in_progress.txt','a')
	inProgress.write(pointToString(points.pop(points.index(nextPoint))).replace(" ", "") + "\n")
	inProgress.close()
	f = open('points.txt', 'w')
	for point in points:
		f.write(pointToString(point).replace(" ", "") + "\n")
	f.close()
	os.system('python evaluate.py ' + pointToString(nextPoint).replace(" ", ""))
else:
	if iter_current < iter_total:
		print("calculating new points")
		iter_current += 1
		triangles = convertPointsToTriangles(points)
		newTriangles = flatten(map(splitTriangle, triangles))
		newPoints = convertTrianglesToPoints(newTriangles)
		for point in points:
			if point[0] not in [x[0] for x in newPoints]:
				newPoints.append([point[0],[]])
		f = open('points.txt', 'w')
		for point in newPoints:
			f.write(pointToString(point).replace(" ", "") + "\n")
		f.close()
		f = open('log.txt', 'w')
		f.write("current iteration = " + str(iter_current) + "\n")
		f.write("total iterations = " + str(iter_total) + "\n")
		f.close()
		os.system('python scheduler.py')
	else:
		quit()













































