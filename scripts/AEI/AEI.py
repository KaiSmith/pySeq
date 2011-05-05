""" Gets the read bases at each position specified by the first argument, which
is a VCF/BED/GFF/GTF file, from an indexed BAMfile/s or pileup/s:  
    1. Whether the loci is heterzygous or homozygous if the genotyping is not
    known
    2. The p-value of the loci exhibiting allelic imbalance if the loci is
    heterzygous.  

Usage: 
    python getReads.py bedfile/vcf bamfile1 [bamfile2 ...] -o OUTPUT


:TODO Add VCF support. Had it in originally  
:TODO Do comparison with reference allele
:TODO Account for mis-alignments of the minor allele
:TODO Need to be able to handle insertion/deletions in the sequence as compared
to reference. This will be hard to do 
:TODO add an option that includes a gene annotation file

:TODO Output the results into a VCF file

Written by Jeffrey Hsu
"""


import pysam, optparse, csv, sys, operator, re
from pySeq.formats.VCF import VCFfile
import numpy as np
import pySeq.stats.likelihood_funcs as lf


class lociInformation():
    """ Contains information about a given position in a BAM file

    :TODO subclass this to locations
    """

    BASE_INDEX = {'A':0, 'a':0, 'C':1, 'c':1, 'G':2, 'g':2, 'T':3, "t":3}
    def __init__(self, region, position, samples,phredThreshold=0):
	""" Location is one-based.  Internally this will get changed to zero
	base by pysam.  
	"""
	self.region = region
	self.position = int(position)
	# Find a better less convuluted way to do this
	# allele_counts is a dictionary of dictionaries
	# the key is the read group ID.  Values is a dictionary of the allele
	# and the number of counts for that allele in a read group.  This is
	# done so that a bam file with multiple read groups is able to be
	# parsed
	# Samples and genotypes should be another Class
	self.allele_counts = {}
	self.strand_bias = {}  
	self.samples = samples
	self.phredThreshold=phredThreshold
	#self.genotype = genotype
	for i in self.samples:
	    self.allele_counts[i] = np.zeros(4, dtype=np.int) 


    def __call__(self, pileups, position=None, samples=None,
	    phredThreshold=None, genotype=None):
	""" Genotype file contains the infromation the actualy genotyping
	calls.  
	"""
	if position == None: position = self.position
	else:  pass
	if samples == None: n = self.samples
	else: pass
	if phredThreshold == None: qualT = self.phredThreshold
	# Hmm somewhere the possition got converted into zero base
	if pileups.pos != position-1: pass
	else:
	    for read in pileups.pileups:
		# checks first to see if the read is a duplicate
		if read.alignment.is_duplicate or read.alignment.mapq <= 50: pass
		else:
		    qpos = read.qpos
		    base_quality = read.alignment.qual[qpos]
		    if ord(base_quality)-33 > qualT:
			try:
			    read_group = read.alignment.opt('RG')
			except:
			    read_group = self.samples[0] 
			base = read.alignment.seq[qpos]
			base = self.BASE_INDEX[base]	
			#strand = read.alignment.is_reverse
			self.allele_counts[read_group][base]+=1
		    else: pass
		    # print(qpos, read.alignment.qname, read.alignment.is_proper_pair)



def thresholdCounts(counts, threshold=30, number=1):
    """
    Makes sure that at least one of the samples meet a read count threshold 
    """
    counter = 0
    for i in counts:
	if sum(i) > threshold: counter += 1 
    if counter >= number:
	return True
    else:
	return False
	

def main():
    #################################################################
    # Argument and Options Parsing
    #################################################################
    
    p = optparse.OptionParser(__doc__)
    p.add_option("-o", "--output", dest="filename", help="write \
	    report to FILE")
    # :TODO These options do nothing right now?
    p.add_option("-v",  "--vcf_file",action="store_true", dest="inputisvcfile", help="the input \
	    is a VCF file")
    p.add_option("-q", "--quality_threshold",type="int", dest="qual", help="base quality \
	    threshold to take allele counts from")
    p.add_option("-D", "--debug", action="store_true", dest="D", help="debug") 
    p.add_option("-V", "--output_vcf", action="store_true", dest="outputVCF",\
	    help="Output the results to a VCF file")

    options, args = p.parse_args()
    if options.qual: pass
    else: options.qual=20
    # Open the bedfile/vcf file
    # file_a = csv.reader(open(args[0], "rU"), delimiter="\t")
    # Right now defaulting to VCF file
    """
    if options.inputisvcfile:
	file_a = VCFfile(args[0])
    else: 
	file_a = BEDfile(args[0])
    """
    file_a = open(args[0],"rb")

    # Handling of multiple BAM/SAM inputs
    bam_Names = args[1:]
    bam_Files = []
    for filename in bam_Names:
	bam_Files.append(pysam.Samfile(filename,"rb"))
        
    # Creates a dictionary with the bam_file name as the key, and the samples
    # by readgroup as the value i.e. {"bamfile":[RG1, RG2, RG3]
    # "bamfile2":[RG4,RG5]"

    # Also creates a read group sample dictionary
    readGroup_sample = {}
    bam_ReadGroups = {}
    for bamFile, bamName in map(None, bam_Files, bam_Names):
	samples = []
	# Grab only the header information
	header=bamFile.text
	m = re.compile('@RG.*')
	readGroups = m.findall(header)
	for r in readGroups:
	    r=r.split('\t')
	    for i in r:
		if i[0:3] == "ID:": ID = i[3:]
		elif i[0:3] == "SM:": SM = i[3:]
		else : pass
	    readGroup_sample[ID] = SM
	    samples.append(ID)
	bam_ReadGroups[bamName] = samples	
    # For testing purposes
    x=1
    
    # Print the Header
    header = ["chr", "pos", "rsID"]
    for i in bam_Names:
	ReadGroupsinBam = bam_ReadGroups[i]
	for t in ReadGroupsinBam:
	    header.append(readGroup_sample[t])
	    header.append("Genotype(Maj/Min)")
	    header.append("Ratio")
    print("\t".join(header))

    INDEX_BASE = ['A','C','G','T']
    count_threshold=30
    for line in file_a:
	line=line.strip('\n').split('\t')
	
	counts = []
	for bamFile, bamNames in map(None, bam_Files, bam_Names):
	    # :TODO in the VCF and bed files make sure to type the attributes
	    variant = lociInformation(str(line[0]), int(line[2]),\
		    samples=bam_ReadGroups[bamNames],\
		    phredThreshold=options.qual)
	    # Method Call
	    bamFile.pileup(variant.region, variant.position, variant.position,callback=variant)
	    for i in variant.samples:
		counts.append(variant.allele_counts[i])
	# First determines if any of the samples meet the read threshold
	# Secondly determines if there are any heterozygotes in the sample (if
	# there aren't any it skips printing that line.  
	# There are several ways it calculates this, if imputed genotyeps are given it will
	# use that, otherwise the posterior probability of being a heterozygote
	# given the data is calculated.  
	if thresholdCounts(counts, threshold=count_threshold):
	    p_values = []
	    for sample_c in counts:
		ind = sample_c.argsort()[::-1]
		"""
		ind = sample_c.argsort()[::-1]
		p_values.append(binom_test(sample_c[ind[0:2]]))
		"""
		any_hets=[]
		if sample_c.sum() >=count_threshold:
		    if lf.isHet(sample_c):
			p_values.append(lf.ratioLik(sample_c))
			p_values.append("%s:%s" % (INDEX_BASE[ind[0]],
			    INDEX_BASE[ind[1]]))
			any_hets.append(True)
		    else: 
			p_values.append("HOMO")
			p_values.append(str(INDEX_BASE[ind[0]]))
			any_hets.append(False)
		    p_values.append("%s:%s" % (sample_c[ind[0]],
			sample_c[ind[1]]))
		else:
		    p_values.append("NA")
		    p_values.append(str(INDEX_BASE[ind[0]]))
		    p_values.append("%s:%s" % (sample_c[ind[0]],
			sample_c[ind[1]]))
		    any_hets.append(False)
	    if any(any_hets):

		    print("\t".join([variant.region, str(variant.position), line[3]])+"\t" +
			    "\t".join(map(str, list(p_values))))
	    else: pass

	# For testing purposes
	if options.D:
	    if x > 2000: break
	    else: x += 1
	else:pass

if __name__ == '__main__':
    main()