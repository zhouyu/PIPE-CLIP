#!/usr/bin/python
# Programmer : beibei.chen@utsouthwestern.edu
# Usage: Get reliable mutations using binomial distribution
# Input: Filtered BAM, reads coverage (generated by SAMFilter.py), mutation file
# Output: BED 
# Last modified: 19 Dec.2013


import sys
import re
import random
import string
import logging
import pysam
from pysam import *
import argparse as ap
from pybedtools import BedTool
import copy
import rpy2.robjects as robject
from rpy2.robjects.packages import importr
from rpy2.robjects import FloatVector
import math
from collections import Counter
import subprocess
import OptValidator

OptValidator.opt_validate()

stats = importr('stats')

def freqRank(readCount,rev=False):
	key = sorted(readCount.keys(),reverse=rev)
	r_rank = {}
	rank = 0
	for i in key:
		rank += readCount[i]
		r_rank[i] =rank
	return r_rank

def BH(pvalue,pRank,N):
	a = N/float(pRank)
	q = a * pvalue
	qva = max(pvalue, q)
	return qva

def KMvalue(mapfile,mufile):
		'''
		Calculate K(coverage) value for each mutation location
		Mutations are already unique.
		'''
		km = []#store mutations with updated k value
		km_pair = {}#Dic of count tuples of (k,m),key:"K_M"
		count = 0
		for item in mufile:
			count += 1
			if count % 5000 == 0:
				logging.info("Counting K-M for %d mutation sites" % count)
			st = []
			strand = item.strand 
			M = item.score
			K = 0
			for pileupColumn in mapfile.pileup(item.chr,int(item.start),int(item.stop)):
				if pileupColumn.pos == int(item.start): #find the mutation site
					K = 0 #pileupColumn.n #edited 1023
					for pileupRead in pileupColumn.pileups:
						if pileupRead.alignment.is_reverse:
							if strand == "-":
								K += 1
						else: #pileup alignment is on plus strand
							if strand == "+": #changed - into +
								K += 1
			if K>=M:
				item.updateK(K)
				pair_name = str(K)+"_"+str(M)
				if km_pair.has_key(pair_name):
					km_pair[pair_name] += 1
				else:
					km_pair[pair_name] = 1
				#km.append(item)
		return km_pair


def uniq(b): #b is a list
	uniqElements = []
	for i in b:
		if uniqElements.count(i)==0:
			uniqElements.append(i)
	uniqElements.sort()
	return uniqElements


def mutationEnrich(clip,threshold=0.01):
	coverage = clip.coverage *1.0
	totalMuCount = clip.mutationCount
	#(original_KM,KM_test) = KMvalue(clip.originalBAM, clip.mutations)
	KM_test = KMvalue(clip.originalBAM, clip.mutations.values())#check after doing KM, if clip.mutations changed
	logging.info("Finished K-M counting, starting fitting.")
	R = robject.r
	reliableList = []
	P = totalMuCount/coverage
	km_p = {}#store km and corresponding p value
	pvalues = []
	for k in KM_test:
		parameters = k.split("_")
		p = R.pbinom(int(parameters[1])-1,int(parameters[0]),P,False)[0]	
		pvalues.append(p)
		km_p[k]=p
	pCount = dict(Counter(pvalues))
	pRank = freqRank(pCount,True)
	total_test = len(clip.mutations.keys())
	pqDic={}
	for i in pRank.keys():
		try:
			p_rank = pRank[i]
			q_value = BH(i,p_rank,total_test)
			pqDic[i]=q_value
		except:
			print >> sys.stderr,"Cannot find p value in dictionary"
			continue
	count = 0
	for mu in clip.mutations.values():
		name = str(mu.kvalue)+"_"+str(mu.score)
		mu.pvalue = km_p[name]
		mu.qvalue = pqDic[mu.pvalue]
		if mu.qvalue <= threshold:
			count += 1
			new_mutationName = "Mutation_"+str(count)
			mu.name = new_mutationName
			mu.sig = True
			clip.sigMutationCount += 1
			clip.addSigToDic(clip.sigMutations,mu)
	logging.info("There are %d reliable mutations" % clip.sigMutationCount)



def clusterEnrich(clip,threshold=0.01):
	#write temp file
	#temp_filename = "test.merge"#clip.filepath.split("/")[-1].split(".")[0]
	#fh = open(temp_filename,"w")
	#for i in clip.clusters:
	#	print >> fh, "\t".join(i)


	#Call R code and get result
	epsilon = [0.01,0.15,0.1]
	step = [0.1,0.08,0.05]
	for index in range(3):
		e = epsilon[index]
		s = step[index]
		r_args = ['Rscript','ZTNB.R','test.merge',threshold,e,s]
		p = subprocess.Popen(args)
		stdout_value = p.communicate()[0]
		#output = subprocess.check_output['ls','-l','test.merge.ztnb']
		#output_log = subprocess.check_output['ls','-l','test.merge.ztnblog']
		#If regression converged, there is no need to try other epsilon or step,check log file flag: Y means coverged, N means not converged 
		try:
			r_output_log = open("test.merge.ztnblog","r")
			flag = r_outpu_log.read(1)
			if flag == "Y":#converged
				break
			elif flag=="N":
				continue
			else:
				logging.info("No log file was produced by R code, continue regression using other parameters anyway.")
				continue

	#check ztnb file

	r_output = subprocess.check_output['ls','-l','test.merge.ztnb']
	if True:#int(r_output.split()[4])>100: #more than header,file OK
		enrich_parameter = open("../test/test.merge.ztnb","r")
		nbDic = {}
		for item in enrich_parameter:
			buf = item.rstrip().split("\t")
			nb_key = "_".join(buf[0:2]) #reads_length as key
			#logging.debug("NB_key %s" % nb_key)
			if not nbDic.has_key(nb_key):
				nbDic[nb_key]=(buf[2],buf[3])#pvalue and qvalue
		logging.info("There are %d read-length pairs" % (len(nbDic.keys())))
		for i in range(len(clip.clusters)):
			r_key = str(clip.clusters[i].score)+"_"+str(clip.clusters[i].stop-clip.clusters[i].start)
			#logging.debug("Keys from clip.clusters,%s" % r_key)
			if nbDic.has_key(r_key):
				clip.clusters[i].pvalue = nbDic[r_key][0]
				clip.clusters[i].qvalue = nbDic[r_key][1]
				clip.clusters[i].sig = True
				clip.sigClusterCount += 1
				#clip.addSigToDic(clip.sigClusters,clip.clusters[i])

def fisherTest(clusterp,mutationp):
	R = robject.r
	min_mp = min(mutationp)
	#logging.debug("clusterP %f,%s" % (clusterp, type(clusterp)))
	#logging.debug("mutationP %f,%s" % (min_mp, type(min_mp)))
	xsq = -2*math.log(clusterp * min_mp)
	fp = R.pchisq(xsq,**{'df':4,'lower.tail':False,'log.p':True})[0]
	fps = -1.0*fp
	return fps


def mutationEnrich_ignore(clip):
		coverage = clip.coverage


		if self.isPar: #input is a par,no need to split the file
			filename = self.outputRoot+".bed"
			outputfile = open(filename,"wa")
			print >> outputfile,"#chr\tstart\tend\tname\tp\tstrand\ttype\tk\tm"
			for reliable_mu in self.muEvaluate(self.bamFile,self.mutationFile,coverage,self.fdr):
				print >>outputfile,'\t'.join(reliable_mu)
		else: #splitfile to insertion, deletion, substitution
			insertion = []
			deletion = []
			substitution = []
			for item in self.mutationFile:
				if item[-1].count("Deletion")>0:
					deletion.append(item)
				elif item[-1].count("Insertion")>0:
					insertion.append(item)
				else:
					substitution.append(item)
			del_name = self.outputRoot+"_deletion.bed"
			ins_name = self.outputRoot+"_insertion.bed"
			sub_name = self.outputRoot+"_substitution.bed"

			outfile_del = open(del_name,"wa")
			outfile_ins = open(ins_name,"wa")
			outfile_sub = open(sub_name,"wa")
			print >> outfile_ins,"#chr\tstart\tend\tname\t-log(q)\tstrand\ttype\tk\tm"
			print >> outfile_del,"#chr\tstart\tend\tname\t-log(q)\tstrand\ttype\tk\tm"
			print >> outfile_sub,"#chr\tstart\tend\tname\t-log(q)\tstrand\ttype\tk\tm"
			for reliable_mu in self.muEvaluate(self.bamFile,insertion,coverage,self.fdr):
				print >> outfile_ins,'\t'.join(reliable_mu)
			for reliable_mu in self.muEvaluate(self.bamFile,deletion,coverage,self.fdr):
				print >> outfile_del,'\t'.join(reliable_mu)
			for reliable_mu in self.muEvaluate(self.bamFile,substitution,coverage,self.fdr):
				print >> outfile_sub,'\t'.join(reliable_mu)


# mutationFilter.mutationFilterMain(outputPrefix+".filter.bam",outputPrefix+".filter.mutation.bed",outputPrefix+".filter.reliable",clipType,fdrReliableMutation,outputPrefix+".filter.coverage")
def mutationFilterMain(saminputPath,bedinputPath,outputRoot,par,fdr,coveragefilePath):
  try:
    bamFile = pysam.Samfile(saminputPath,"rb")
  except IOError,message:
    print >> sys.stderr, "cannot open mapping BAM file",message
    sys.exit(1)

  try:
    mutationFile = BedTool(bedinputPath)
  except IOError,message:
    print >> sys.stderr, "cannot open mutation BED file",message
    sys.exit(1)
  
  try:
    coverageFile = open(coveragefilePath,"r")
  except IOError,message:
    print >> sys.stderr, "cannot open coverage file",message
    sys.exit(1)

