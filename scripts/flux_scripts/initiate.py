#!/usr/bin/env python 2

import os
from fractions import Fraction

xMin = 0.
xMax = 1.
yMin = 0.
yMax = 1.
gridSize = 6

xMin = Fraction(str(xMin))
xMax = Fraction(str(xMax))
yMin = Fraction(str(yMin))
yMax = Fraction(str(yMax))
xGrid = (xMax - xMin) / gridSize
yGrid = (yMax - yMin) / gridSize

iterations = 3

def isGoodTriangle(triangle):
	return all([xMin <= point[0] <= xMax for point in triangle]) and all([yMin <= point[1] <= yMax for point in triangle])

def flatten(lst):
	return [x for sublist in lst for x in sublist]

triangles = []

if yGrid > xGrid:
	b = yMin - xMax
	while b < yMax - xMin:
		x = xMin
		while x < xMax:
			triangles.append([[x, x + b], [x + xGrid, x + xGrid + b], [x, x + b + yGrid]])
			triangles.append([[x + xGrid, x + xGrid + b], [x, x + b + yGrid], [x + xGrid, x + xGrid + yGrid + b]])
			x += xGrid
		b += yGrid
else:
	b = yMin - xMax
	while b < yMax - xMin:
		x = yMin - b
		while x < yMax - b:
			triangles.append([[x, x + b], [x + yGrid, x + yGrid + b], [x + xGrid, x + b]])
			triangles.append([[x + yGrid, x + yGrid + b], [x + xGrid, x + b], [x + xGrid + yGrid, x + yGrid + b]])
			x += yGrid
		b += xGrid

triangles = [x for x in triangles if isGoodTriangle(x)]

triangles = [[[point,2] for point in triangle] for triangle in triangles] #append a 2 to the end of all points to indicate that they have not been evaluated


def convertTrianglesToPoints(triangles):
	pointsTemp = []
	points = []
	for point in flatten(triangles):
		if point not in pointsTemp:
			pointsTemp.append(point)
	for point in pointsTemp:
		points.append([point,[x for x in range(len(triangles)) if point in triangles[x]]])
	return points

### points are stored as: [[[x,y], val], [triangles]], where [x,y] are the coordinates, val = 0 if false, 1 if true, and 2 if unevaluated, and [triangles] is a list of the triangles that the point is a member of

points = convertTrianglesToPoints(triangles)

f = open("points.txt", 'w')

def pointToString(point):
	return '[[' + str(map(str, point[0][0])).replace("'", "") + ', ' + str(point[0][1]) + '], ' + str(point[1]) + ']'

for point in points:
	f.write(pointToString(point).replace(" ", "") + "\n")

f.close()

f = open("log.txt", 'w')

f.write("current iteration = 1\n")
f.write("total iterations = " + str(iterations) + "\n")

f.close()

#os.system('python scheduler.py')


		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
		
