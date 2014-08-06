#!/usr/bin/python
# programmer: beibei.chen@utsouthwestern.edu
# Usage: definition of utilities to handel pysam classes

import sys

def is_sorted(header):
	'''Get a BAM header, and check if this file is sorted or not
	   Return: True: sorted, False: unsorted
	   Header variable is a list
	'''
	for row in header:
		buf = row.rstrip().split("\t")
		if buf[0]=="@HD":
			if buf[2] in ["SO:unsorted","SO:unknown"] :
				return False
			elif buf[2] in ["SO:coordinate","SO:queryname"]:
				return True
	#If no HD header contains SO info, return False
	return False 



