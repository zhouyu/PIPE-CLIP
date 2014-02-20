#!/usr/bin/python
# Programmer : beibei.chen@utsouthwestern.edu
# Usage: generate clusters with reads count for cluster enrichment analysis
# Input: BAM
# Output: BED
# Last modified: 19 Dec. 2013


import sys
import string
from pysam import *
from pybedtools import BedTool



def main():
	try:
		mapped_bam = BedTool(sys.argv[1])
	except IOError,message:
		print >> sys.stderr,"Cannot open BAM file.",message
		sys.exit(1)
	
	mapped_bed = mapped_bam.bam_to_bed()
	bed_merge = mapped_bed.merge(s=True, n=True)
	
	count = 1
	for item in bed_merge:
		name = "cluster_"+str(count)
		count += 1
		print "%s\t%s\t%s\t%s\t%s\t%s" % (item[0],item[1],item[2],name,item[3],item[4])

if __name__=="__main__":
	main()