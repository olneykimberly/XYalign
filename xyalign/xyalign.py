# To-do list
# 1) Add ploidy estimation
# 		- need to add likelihood analyses (model fitting)
# 2) Compartmentalize all steps of analysis
# 		- Add flags to make each part of the pipeline optional
# 		- Allow users to call specific parts of the pipeline
# 					(e.g. only vcf plotting)
# 		- Add checkpointing
# 5) Generalize mapping and calling (perhaps by allowing users to
# 		add command lines as  strings)
# 6) Add plotting of high-quality windows (depth, mapq), also after remapping
# 7) Check for behavior when files already exist (e.g., overwrite, quit, etc.?)
# 8) Incorporate mask integration on the fly
# 9) Check with Python 3 and for any incompatibilities
# 				- division updated
# 				- printing updated

from __future__ import division
from __future__ import print_function
import argparse
import csv
import os
import subprocess
import sys
import numpy as np
import pandas as pd
import pybedtools
import pysam
# Setting the matplotlib display variable requires importing
# 	in exactly the following order:
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
import seaborn as sns


def main():
	""" Main program"""

	args = parse_args()

	# Setup output paths
	fastq_path = os.path.join(args.output_dir, "fastq")
	bam_path = os.path.join(args.output_dir, "bam")
	reference_path = os.path.join(args.output_dir, "reference")
	bed_path = os.path.join(args.output_dir, "bed")
	vcf_path = os.path.join(args.output_dir, "vcf")
	plots_path = os.path.join(args.output_dir, "plots")
	results_path = os.path.join(args.output_dir, "results")
	logfile_path = os.path.join(args.output_dir, "logfiles")

	# Create paths for output files
	if args.logfile is not None:
		logfile = os.path.join(
			logfile_path, args.logfile)
	else:
		logfile = os.path.join(
			logfile_path, "{}_xyalign.log".format(
				args.sample_id))
	noprocessing_vcf = os.path.join(
		vcf_path, "{}.noprocessing.vcf".format(
			args.sample_id))
	postprocessing_vcf = os.path.join(
		vcf_path, "{}.postprocessing.vcf".format(
			args.sample_id))
	if args.platypus_logfile is not None:
		plat_log = args.platypus_logfile
	else:
		plat_log = args.sample_id
	noprocessing_vcf_log = os.path.join(
		logfile_path, "{}_noprocessing_platypus.log".format(
			plat_log))
	postprocessing_vcf_log = os.path.join(
		logfile_path, "{}_postprocessing_platypus.log".format(
			plat_log))
	readbalance_prefix_noprocessing = os.path.join(
		plots_path, "{}_noprocessing".format(args.sample_id))
	readbalance_prefix_postprocessing = os.path.join(
		plots_path, "{}_postprocessing".format(args.sample_id))
	depth_mapq_prefix = os.path.join(
		plots_path, "{}_noprocessing".format(args.sample_id))
	if args.high_quality_bed_out is not None:
		high_prefix = args.high_quality_bed_out
	else:
		high_prefix = "{}_highquality".format(args.sample_id)
	output_bed_high = os.path.join(
		bed_path, "{}.bed".format(high_prefix))
	if args.low_quality_bed_out is not None:
		low_prefix = args.low_quality_bed_out
	else:
		low_prefix = "{}_lowquality".format(args.sample_id)
	output_bed_low = os.path.join(
		bed_path, "{}.bed".format(low_prefix))

	# First round of Platypus calling and plotting
	if args.platypus_calling == "both" or "before":
		if args.bam is not None:
			a = platypus_caller(
				args.platypus_path, noprocessing_vcf_log, args.bam, args.ref,
				args.chromosomes, args.cpus, noprocessing_vcf, None)
			if a != 0:
				print("Error in initial Platypus calling.")
				sys.exit(1)
			if args.no_variant_plots is not True:
				plot_variants_per_chrom(
					args.chromosomes, noprocessing_vcf,
					args.sample_id, readbalance_prefix_noprocessing,
					args.variant_quality_cutoff, args.marker_size,
					args.marker_transparency, args.bam)
		else:
			a = platypus_caller(
				args.platypus_path, noprocessing_vcf_log, args.cram, args.ref,
				args.chromosomes, args.cpus, noprocessing_vcf, None)
			if a != 0:
				print("Error in initial Platypus calling.")
				sys.exit(1)
			if args.no_variant_plots is not True:
				plot_variants_per_chrom(
					args.chromosomes, noprocessing_vcf,
					args.sample_id, readbalance_prefix_noprocessing,
					args.variant_quality_cutoff, args.marker_size,
					args.marker_transparency, args.cram)

	# Analyze bam for depth and mapq
	if args.no_bam_analysis is not True:
		if args.bam is not None:
			samfile = pysam.AlignmentFile(args.bam, "rb")
		else:
			samfile = pysam.AlignmentFile(args.cram, "rc")
		pass_df = []
		fail_df = []
		for chromosome in args.chromosomes:
			data = traverse_bam_fetch(samfile, chromosome, args.window_size)
			tup = make_region_lists(
				data["windows"], args.mapq_cutoff, args.depth_filter)
			pass_df.append(tup[0])
			fail_df.append(tup[1])
			plot_depth_mapq(
				data, depth_mapq_prefix, args.sample_id,
				get_length(samfile, chromosome), args.marker_size,
				args.marker_transparency)
		output_bed(output_bed_high, *pass_df)
		output_bed(output_bed_low, *fail_df)

	# Infer ploidy (needs to be finished)

	# Replace this with code to infer ploidy, etc.
	# Permutation tests
	if args.no_perm_test is not True:
		sex_chromosomes = args.x_chromosome + args.y_chromosome
		autosomes = [x for x in args.chromosomes if x not in sex_chromosomes]
		perm_res_x = []
		perm_res_y = []
		for c in autosomes:
			perm_res_x.append(permutation_test_chromosomes(
				pd.concat(pass_df), c, str(args.x_chromosome[0]), "chrom",
				"depth", args.num_permutations,
				results_path + "/{}_{}_permutation_results.txt".format(
					c, str(args.x_chromosome[0]))))
			perm_res_y.append(permutation_test_chromosomes(
				pd.concat(pass_df), c, str(args.y_chromosome[0]), "chrom",
				"depth", args.num_permutations,
				results_path + "/{}_{}_permutation_results.txt".format(
					c, str(args.y_chromosome[0]))))
		sex_perm_res = permutation_test_chromosomes(
			pd.concat(pass_df), str(args.x_chromosome[0]), str(args.y_chromosome[0]),
			"chrom", "depth", args.num_permutations,
			results_path + "/{}_{}_permutation_results.txt".format(
				str(args.x_chromosome[0]), str(args.y_chromosome[0])))
		# Right now this implements a simple and rather inelegant test for
		# 	a Y chromosome that assumes approximately equal depth on the
		# 	X and the Y in XY individuals.
		if 0.025 < sex_perm_res[2] < 0.95:
			y_present_perm = True
		else:
			y_present_perm = False

	if args.y_present is True:
		y_present = True
	elif args.y_absent is True:
		y_present = False
	else:
		y_present = y_present_perm

	# Likelihood analyses

	# Remapping
	if args.no_remapping is not True:
		if y_present is True:
			# Isolate sex chromosomes from reference and index new reference
			new_reference = isolate_chromosomes_reference(
				args.samtools_path, args.ref, "{}/{}.sex_chroms".format(
					reference_path, args.sample_id),
				args.x_chromosome + args.y_chromosome, args.reference_mask)
			# Strip reads from sex chromosomes
			if args.bam is not None:
				new_fastqs = bam_to_fastq(
					args.samtools_path, args.repairsh_path, args.bam,
					args.single_end, fastq_path, args.sample_id,
					args.x_chromosome + args.y_chromosome)
			else:
				new_fastqs = bam_to_fastq(
					args.samtools_path, args.repairsh_path, args.cram,
					args.single_end, fastq_path, args.sample_id,
					args.x_chromosome + args.y_chromosome)
			# Remap
			with open(new_fastqs[0]) as f:
				read_group_and_fastqs = [line.split() for line in f]
			with open(new_fastqs[1]) as f:
				read_group_headers = [line.split() for line in f]
			temp_bam_list = []
			for i in read_group_and_fastqs:
				if i != [""]:
					rg_id = i[0]
					fastq_files = i[1:]
					for j in read_group_headers:
						for k in j:
							if k[0:2] == 'ID':
								if k[3:] == rg_id:
									rg_tag = "\t".join(j)
								break
					temp_bam = bwa_mem_mapping_sambamba(
						args.bwa_path, args.samtools_path, args.sambamba_path,
						new_reference, "{}/{}.sex_chroms.{}.".format(
							bam_path, args.sample_id, rg_id),
						fastq_files, args.cpus, rg_tag)
					temp_bam_list.append(temp_bam)
			if len(temp_bam_list) < 2:
				new_bam = temp_bam_list[0]
			else:
				new_bam = sambamba_merge(
					args.sambamba_path, temp_bam_list, "{}/{}.sex_chroms".format(
						bam_path, args.sample_id), args.cpus)
			# Merge bam files
			if args.bam is not None:
				merged_bam = switch_sex_chromosomes_bam_sambamba(
					args.samtools_path, args.sambamba_path, args.bam, new_bam,
					args.x_chromosome + args.y_chromosome,
					bam_path, args.sample_id, args.cpus)
			else:
				merged_bam = switch_sex_chromosomes_bam_sambamba(
					args.samtools_path, args.sambamba_path, args.cram, new_bam,
					args.x_chromosome + args.y_chromosome,
					bam_path, args.sample_id, args.cpus)

		else:
			# Isolate sex chromosomes from reference and index new reference
			new_reference = isolate_chromosomes_reference(
				args.samtools_path, args.ref, "{}/{}.sex_chroms".format(
					reference_path, args.sample_id),
				args.x_chromosome, args.reference_mask)
			# Strip reads from sex chromosomes
			if args.bam is not None:
				new_fastqs = bam_to_fastq(
					args.samtools_path, args.repairsh_path, args.bam,
					args.single_end, fastq_path, args.sample_id,
					args.x_chromosome)
			else:
				new_fastqs = bam_to_fastq(
					args.samtools_path, args.repairsh_path, args.cram,
					args.single_end, fastq_path, args.sample_id,
					args.x_chromosome)
			# Remap
			with open(new_fastqs[0]) as f:
				read_group_and_fastqs = [line.split() for line in f]
			with open(new_fastqs[1]) as f:
				read_group_headers = [line.split() for line in f]
			temp_bam_list = []
			for i in read_group_and_fastqs:
				if i != [""]:
					rg_id = i[0]
					fastq_files = i[1:]
					for j in read_group_headers:
						for k in j:
							if k[0:2] == 'ID':
								if k[3:] == rg_id:
									rg_tag = "\t".join(j)
								break
					temp_bam = bwa_mem_mapping_sambamba(
						args.bwa_path, args.samtools_path, args.sambamba_path,
						new_reference, "{}/{}.sex_chroms.{}.".format(
							bam_path, args.sample_id, rg_id),
						fastq_files, args.cpus, rg_tag)
					temp_bam_list.append(temp_bam)
			if len(temp_bam_list) < 2:
				new_bam = temp_bam_list[0]
			else:
				new_bam = sambamba_merge(
					args.sambamba_path, temp_bam_list, "{}/{}.sex_chroms".format(
						bam_path, args.sample_id), args.cpus)
			# Merge bam files
			if args.bam is not None:
				merged_bam = switch_sex_chromosomes_bam_sambamba(
					args.samtools_path, args.sambamba_path, args.bam, new_bam,
					args.x_chromosome + args.y_chromosome,
					bam_path, args.sample_id, args.cpus)
			else:
				merged_bam = switch_sex_chromosomes_bam_sambamba(
					args.samtools_path, args.sambamba_path, args.cram, new_bam,
					args.x_chromosome + args.y_chromosome,
					bam_path, args.sample_id, args.cpus)

	# Final round of calling and plotting
	include_bed = output_bed_high

	if args.platypus_calling == "both" or "after":
		a = platypus_caller(
			args.platypus_path, postprocessing_vcf_log, merged_bam, args.ref,
			args.chromosomes, args.cpus, postprocessing_vcf, include_bed)
		if a != 0:
			print("Error in second round of Platypus calling.")
			sys.exit(1)
		if args.no_variant_plots is not True:
			plot_variants_per_chrom(
				args.chromosomes,
				postprocessing_vcf,
				args.sample_id, readbalance_prefix_postprocessing,
				args.variant_quality_cutoff, args.marker_size,
				args.marker_transparency, merged_bam)


def parse_args():
	"""Parse command-line arguments"""
	parser = argparse.ArgumentParser(description="XYalign")

	parser.add_argument(
		"--ref", required=True,
		help="Path to reference sequence (including file name).")

	parser.add_argument(
		"--output_dir", "-o",
		help="Output directory")

	parser.add_argument(
		"--chromosomes", "-c", nargs="+", default=["chrX", "chrY", "chr19"],
		help="Chromosomes to analyze.")

	parser.add_argument(
		"--x_chromosome", "-x", nargs="+", default=["chrX"],
		help="Names of y-linked scaffolds in reference fasta.")

	parser.add_argument(
		"--y_chromosome", "-y", nargs="+", default=["chrY"],
		help="Names of y-linked scaffolds in reference fasta.")

	parser.add_argument(
		"--sample_id", "-id", default="sample",
		help="Name/ID of sample - for use in plot titles and file naming.")

	parser.add_argument(
		"--cpus", type=int, default=1,
		help="Number of cores/threads to use.")

	parser.add_argument(
		"--logfile", default=None,
		help="Name of logfile.  Will overwrite if exists.  Default is "
		"sample_xyalign.log")

	parser.add_argument(
		"--single_end", action="store_true", default=False,
		help="Include flag if reads are single-end and NOT paired-end.")

	# Program paths
	parser.add_argument(
		"--platypus_path", default="platypus",
		help="Path to platypus.  Default is 'platypus'")

	parser.add_argument(
		"--bwa_path", default="bwa",
		help="Path to bwa. Default is 'bwa'")

	parser.add_argument(
		"--samtools_path", default="samtools",
		help="Path to samtools. Default is 'samtools'")

	parser.add_argument(
		"--repairsh_path", default="repair.sh",
		help="Path to bbmap's repair.sh script. Default is 'repair.sh'")

	parser.add_argument(
		"--sambamba_path", default="sambamba",
		help="Path to sambamba. Default is 'sambamba'")

	# Options for turning on/off parts of the pipeline
	parser.add_argument(
		"--no_remapping", action="store_true", default=False,
		help="Include this flag to prevent remapping sex chromosome reads.")

	parser.add_argument(
		"--platypus_calling", default="both",
		help="Platypus calling withing the pipeline "
		"(before processing, after processing, both, "
		"or neither). Options: both, none, before, after.")

	parser.add_argument(
		"--no_variant_plots", action="store_true", default=False,
		help="Include flag to prevent plotting read balance from VCF files.")

	parser.add_argument(
		"--no_bam_analysis", action="store_true", default=False,
		help="Include flag to prevent depth/mapq analysis of bam file")

	# Variant Calling Flags
	parser.add_argument(
		"--variant_quality_cutoff", "-vqc", type=int, default=20,
		help="Consider all SNPs with a quality greater than or "
		"equal to this value. Default is 20.")

	parser.add_argument(
		"--platypus_logfile", default=None,
		help="Prefix to use for Platypus log files.  Will default to the "
		"sample name")

	# Mapping/remapping Flags
	parser.add_argument(
		"--reference_mask", default=None,
		help="Bed file containing regions to replace with Ns in the sex "
		"chromosome reference.  Examples might include the pseudoautosomal "
		"regions on the Y to force all mapping/calling on those regions of the "
		"X chromosome.  Default is none.")

	# Bam Analysis Flags
	parser.add_argument(
		"--window_size", "-w", type=int, default=50000,
		help="Window size (integer) for sliding window calculations.")

	parser.add_argument(
		"--mapq_cutoff", "-mq", type=int, default=20,
		help="Minimum mean mapq threshold for a window to be "
		"considered high quality.")

	parser.add_argument(
		"--depth_filter", "-df", type=float, default=4.0,
		help="Filter for depth (f), where the threshold used is mean_depth +- "
		"(f * square_root(mean_depth)).")

	parser.add_argument(
		"--high_quality_bed_out", "-hq", default=None,
		help="Prefix of output file for high quality regions. Defaults to "
		"samplename_highquality")

	parser.add_argument(
		"--low_quality_bed_out", "-lq", default=None,
		help="Prefix of output file for low quality regions. Defaults to "
		"samplename_lowquality")

	parser.add_argument(
		"--num_permutations", type=int, default=10000,
		help="Number of permutations to use for permutation analyses. "
		"Default is 10,000")

	# Plotting flags
	parser.add_argument(
		"--marker_size", type=float, default=10.0,
		help="Marker size for genome-wide plots in matplotlib.")

	parser.add_argument(
		"--marker_transparency", "-mt", type=float, default=0.5,
		help="Transparency of markers in genome-wide plots.  "
		"Alpha in matplotlib.")

	# Mutually exclusive group 1 - bam or cram file
	group = parser.add_mutually_exclusive_group(required=True)

	group.add_argument(
		"--bam", help="Input bam file.")

	group.add_argument(
		"--cram", help="Input cram file.")

	# Mutally exclusive group 2 - overriding ploidy estimation with declaration
	# 		that Y is present or Y is absent.  --no_perm_test explicitly
	# 		requires one of either --y_present or --y_absent, but the reverse
	# 		is not true (i.e., if you don't run tests, you need to tell
	# 		XY align what the ploidy is, however you can tell XY align what
	# 		the ploidy is and still run the permutation analyses, the results
	# 		of which will be ignored)

	parser.add_argument(
		"--no_perm_test", action="store_true", default=False,
		help="Include flag to turn off permutation tests. Requires either "
		"--y_present or --y_absent to also be called")

	group2 = parser.add_mutually_exclusive_group(required=False)

	group2.add_argument(
		"--y_present", action="store_true", default=False,
		help="Overrides sex chr estimation by XYalign and remaps with Y present.")

	group2.add_argument(
		"--y_absent", action="store_true", default=False,
		help="Overrides sex chr estimation by XY align and remaps with Y absent.")

	args = parser.parse_args()

	# Validate arguments
	if args.no_perm_test is True:
		if args.y_present is False and args.y_absent is False:
			print("Error. Either --y_present or --y_absent needs to be "
									"included with --no_perm_test")
		sys.exit(1)
	if args.platypus_calling not in ["both", "none", "before", "after"]:
		print("Error. Platypus calling must be both, none, before, or after. "
								"Default is both.")
		sys.exit(1)

	# Create directory structure if not already in place
	if not os.path.exists(os.path.join(args.output_dir, "fastq")):
		os.makedirs(os.path.join(args.output_dir, "fastq"))
	if not os.path.exists(os.path.join(args.output_dir, "bam")):
		os.makedirs(os.path.join(args.output_dir, "bam"))
	if not os.path.exists(os.path.join(args.output_dir, "reference")):
		os.makedirs(os.path.join(args.output_dir, "reference"))
	if not os.path.exists(os.path.join(args.output_dir, "bed")):
		os.makedirs(os.path.join(args.output_dir, "bed"))
	if not os.path.exists(os.path.join(args.output_dir, "vcf")):
		os.makedirs(os.path.join(args.output_dir, "vcf"))
	if not os.path.exists(os.path.join(args.output_dir, "plots")):
		os.makedirs(os.path.join(args.output_dir, "plots"))
	if not os.path.exists(os.path.join(args.output_dir, "results")):
		os.makedirs(os.path.join(args.output_dir, "results"))
	if not os.path.exists(os.path.join(args.output_dir, "logfiles")):
		os.makedirs(os.path.join(args.output_dir, "logfiles"))

	# Return arguments namespace
	return args


def get_length(bamfile, chrom):
	""" Extract chromosome length from BAM header.

	args:
		bamfile: pysam AlignmentFile object
			- can be bam, cram, or sam, needs to be declared
				in pysam.AlignmentFile call before passing to function
		chrom: chromosome name (string)

	returns:
		Length (int)

	"""
	lengths = dict(zip(bamfile.references, bamfile.lengths))
	return lengths[chrom]


def permutation_test_chromosomes(
	data_frame, first_chrom, second_chrom, chrom_column,
	value_column, num_perms, output_file=None):
	""" Takes a dataframe and runs a permutation test comparing mean values
	of two chromosomes.
	"""
	first_vals = data_frame[
		data_frame[chrom_column] == first_chrom][value_column]
	second_vals = data_frame[
		data_frame[chrom_column] == second_chrom][value_column]
	combined = np.append(first_vals, second_vals)

	first_mean = np.mean(first_vals)
	second_mean = np.mean(second_vals)

	observed = first_mean / second_mean
	perms = []
	for i in range(0, num_perms):
		np.random.shuffle(combined)
		first = np.mean(combined[:len(first_vals)])
		second = np.mean(combined[-len(second_vals):])
		perms.append(first / second)
	perms = np.asarray(perms)
	sig = len(np.where(perms > observed)) / num_perms
	if output_file is not None:
		a = [
			"{}_mean".format(first_chrom),
			"{}_mean".format(second_chrom),
			"{}_{}_diff".format(first_chrom, second_chrom),
			"p_val_({}_/_{})".format(first_chrom, second_chrom),
			"perm_2.5",
			"perm_50",
			"perm_97.5"]
		b = [
			"{}".format(first_mean),
			"{}".format(second_mean),
			"{}".format(observed),
			"{}".format(sig),
			"{}".format(np.percentile(perms, 2.5)),
			"{}".format(np.percentile(perms, 50)),
			"{}".format(np.percentile(perms, 97.5))]
		with open(output_file, "w") as f:
			w = csv.writer(f, dialect="excel-tab")
			w.writerows([a, b])
	return (first_mean, second_mean, sig)


def bwa_mem_mapping_sambamba(
	bwa_path, samtools_path, sambamba_path, reference, output_prefix, fastqs,
	threads, read_group_line, cram=False):
	""" Maps reads to a reference genome using bwa mem.
	"""
	fastqs = ' '.join(fastqs)
	subprocess.call("{} index {}".format(bwa_path, reference), shell=True)
	if cram is False:
		command_line = "{} mem -t {} -R {} {} {} | {} fixmate -O bam - - | "\
			"{} sort -t {} -o {}_sorted.bam /dev/stdin".format(
				bwa_path, threads, repr(read_group_line), reference, fastqs, samtools_path,
				sambamba_path, threads, output_prefix)
		subprocess.call(command_line, shell=True)
		subprocess.call(
			"{} index -t {} {}_sorted.bam".format(
				sambamba_path, threads, output_prefix), shell=True)
		return "{}_sorted.bam".format(output_prefix)
	else:
		command_line = "{} mem -t {} -R {} {} {} | {} fixmate -O cram - - | "\
			"{} sort -O cram -o {}_sorted.cram -".format(
				bwa_path, threads, repr(read_group_line), reference, fastqs, samtools_path,
				samtools_path, output_prefix)
		subprocess.call(command_line, shell=True)
		subprocess.call(
			"{} index {}_sorted.cram".format(
				samtools_path, output_prefix), shell=True)
		return "{}_sorted.cram".format(output_prefix)


def sambamba_merge(sambamba_path, bam_list, output_prefix, threads):
	"""
	Takes a list of bam files, e.g., [bam1,bam2,bam3,...], and merges them
	using sambamba
	"""
	subprocess.call(
		"{} merge -t {} {}.merged.bam {}".format(
			sambamba_path, threads, output_prefix, " ".join(bam_list)))
	subprocess.call(
		"{} index {}.merged.bam".format(
			sambamba_path, output_prefix))
	return "{}.merged.bam".format(output_prefix)


def switch_sex_chromosomes_bam_sambamba(
	samtools_path, sambamba_path, bam_orig, bam_new, sex_chroms,
	output_directory, output_prefix, threads, cram=False):
	""" Removes sex chromosomes from original bam and merges in remmapped
	sex chromosomes, while retaining the original bam header
	"""
	# Grab original header
	subprocess.call(
		"{} view -H {} > {}/header.sam".format(
			samtools_path, bam_orig, output_directory), shell=True)
	if cram is False:
		# Remove sex chromosomes from original bam and merge
		samfile = pysam.AlignmentFile(bam_orig, "rb")
		non_sex_scaffolds = filter(
			lambda x: x not in sex_chroms, list(samfile.references))
		subprocess.call(
			"{} view -h -t {} -f bam -o /dev/stdout {} {} | "
			"{} merge -t {} {}/{}.merged.bam /dev/stdin {}".format(
				sambamba_path, threads, bam_orig, " ".join(non_sex_scaffolds),
				sambamba_path, threads, output_directory, output_prefix,
				bam_new), shell=True)

		return "{}/{}.merged.bam".format(output_directory, output_prefix)

	else:
		# Remove sex chromosomes from original bam
		samfile = pysam.AlignmentFile(bam_orig, "rc")
		non_sex_scaffolds = filter(
			lambda x: x not in sex_chroms, list(samfile.references))
		subprocess.call(
			"{} view -h -b {} {} > {}/no_sex.cram".format(
				samtools_path, bam_orig, " ".join(non_sex_scaffolds),
				output_directory),
			shell=True)
		subprocess.call(
			"{} index {}/no_sex.cram".format(
				samtools_path, output_directory), shell=True)

		# Merge bam files
		subprocess.call(
			"{} merge -h {}/header.sam {}/{}.cram {}/no_sex.cram {}".format(
				samtools_path, output_directory, output_directory,
				output_prefix, output_directory, bam_new), shell=True)
		subprocess.call("{} index {}/{}.cram".format(
			samtools_path, output_directory, output_prefix), shell=True)

		return "{}/{}.cram".format(output_directory, output_prefix)


def platypus_caller(
	platypus_path, log_path, bam, ref, chroms, cpus, output_file,
	regions_file=None):
	""" Uses platypus to make variant calls on provided bam file

	bam is input bam (or cram) file
	ref is path to reference sequence
	chroms is a list of chromosomes to call on, e.g., ["chrX", "chrY", "chr19"]
	cpus is the number of threads/cores to use
	output_file is the name of the output vcf
	"""
	if regions_file is None:
		regions = ','.join(map(str, chroms))
	else:
		regions = regions_file
	command_line = "{} callVariants --bamFiles {} -o {} --refFile {} "\
		"--nCPU {} --regions {} --assemble 1 --logFileName {}".format(
			platypus_path, bam, output_file, ref, cpus, regions, log_path)
	return_code = subprocess.call(command_line, shell=True)
	return return_code


def isolate_chromosomes_reference(
	samtools_path, reference_fasta, new_ref_prefix, chroms, bed_mask):
	""" Takes a reference fasta file and a list of chromosomes to include
	and outputs a new, indexed reference fasta.
	"""
	outpath = "{}.fa".format(new_ref_prefix)
	if type(chroms) != list:
		chroms = list(chroms)
	if bed_mask is not None:
		maskedpath = "{}.masked.fa".format(new_ref_prefix)
		command_line = "{} faidx {} {} > {}".format(
			samtools_path, reference_fasta, " ".join(chroms), outpath)
		subprocess.call(command_line, shell=True)
		subprocess.call("{} faidx {}".format(
			samtools_path, outpath), shell=True)
		b_fasta = pybedtools.BedTool(outpath)
		b_tool = pybedtools.BedTool(bed_mask)
		b = b_tool.mask_fasta(fi=b_fasta, fo=maskedpath)
		subprocess.call(
			"{} faidx {}".format(samtools_path, maskedpath), shell=True)
	else:
		command_line = "{} faidx {} {} > {}".format(
			samtools_path, reference_fasta, " ".join(chroms), outpath)
		subprocess.call(command_line, shell=True)
		subprocess.call("{} faidx {}".format(samtools_path, outpath), shell=True)
		return outpath


def bam_to_fastq(
	samtools_path, repairsh_path, bamfile, single, output_directory,
	output_prefix, regions):
	""" Strips reads from a bam or cram file in provided regions and outputs
	sorted fastqs containing reads.
	"""
	# Collect RGs
	rg_list = output_directory + "/" + "full_rg.list"
	command_line = """{} view -H {} | awk '$1=="\x40RG"' | """\
		"""awk {} """\
		"""| cut -d':' -f 2 > {}""".format(
			samtools_path, bamfile,
			repr('{for(i=1;i<=NF;i++){if (substr($i,1,2) ~ /ID/){print $i}}}'),
			rg_list)
	subprocess.call(command_line, shell=True)
	rg_header_lines = output_directory + "/" + "header_lines_rg.list"
	command_line = """{} view -H {} | awk '$1=="\x40RG"' > {}""".format(
		samtools_path, bamfile, rg_header_lines)
	subprocess.call(command_line, shell=True)
	with open(rg_list, "r") as f:
		out_rg_table = output_directory + "/" + "rg_fastq_key.list"
		with open(out_rg_table, "w") as ortab:
			for line in f:
				rg = line.strip()
				if rg != "":
					with open("{}/{}.txt".format(output_directory, rg), "w") as o:
						o.write(rg)
					if single is False:
						command_line = "{} view -b {} {} | {} bam2fq -1 {}/temp_1.fastq "\
							"-2 {}/temp_2.fastq -t -n - ".format(
								samtools_path, bamfile, ' '.join(map(str, regions)),
								samtools_path, output_directory, output_directory)
						subprocess.call(command_line, shell=True)
						command_line = "{} in1={} in2={} out1={} out2={} overwrite=true".format(
							repairsh_path,
							output_directory + "/temp_1.fastq",
							output_directory + "/temp_2.fastq",
							output_directory + "/" + output_prefix + "_" + rg + "_1.fastq",
							output_directory + "/" + output_prefix + "_" + rg + "_2.fastq")
						subprocess.call(command_line, shell=True)
						ortab.write("{}\t{}\t{}".format(
							rg,
							output_directory + "/" + output_prefix + "_" + rg + "_1.fastq",
							output_directory + "/" + output_prefix + "_" + rg + "_2.fastq"))
					else:
						command_line = "{} view -b {} {} | {} bam2fq -t -n - > "\
							"{}/temp.fastq".format(samtools_path, bamfile, ' '.join(map(
								str, regions)), samtools_path, output_directory)
						subprocess.call(command_line, shell=True)
						command_line = "{} in={} out={} overwrite=true".format(
							repairsh_path,
							output_directory + "/temp.fastq",
							output_directory + "/" + output_prefix + "_" + rg + ".fastq")
						# write line
						ortab.write("{}\t{}".format(
							rg,
							output_directory + "/" + output_prefix + "_" + rg + ".fastq"))
	return [out_rg_table, rg_header_lines]


def parse_platypus_VCF(filename, qualCutoff, chrom):
	""" Parse vcf generated by Platypus """
	infile = open("{}".format(filename), 'r')
	positions = []
	quality = []
	readBalance = []
	for line in infile:
		cols = line.strip('\n').split('\t')
		if cols[0] != chrom:
			continue
		pos = int(cols[1])
		qual = float(cols[5])
		if qual < qualCutoff:
			continue
		TR = cols[7].split(';')[17].split('=')[1]
		TC = cols[7].split(';')[14].split('=')[1]
		if ',' in TR or ',' in TC:
			continue
		if (float(TR) == 0) or (float(TC) == 0):
			continue
		ReadRatio = float(TR) / float(TC)

		# Add to arrays
		readBalance.append(ReadRatio)
		positions.append(pos)
		quality.append(qual)

	return (positions, quality, readBalance)


def plot_read_balance(
	chrom, positions, readBalance, sampleID, output_prefix, MarkerSize,
	MarkerAlpha, bamfile):
	""" Plots read balance at each SNP along a chromosome """
	if bamfile[-3] == "bam" or bamfile[-3] == "BAM":
		chrom_len = get_length(pysam.AlignmentFile(bamfile, "rb"), chrom)
	else:
		chrom_len = get_length(pysam.AlignmentFile(bamfile, "rc"), chrom)
	if "x" in chrom.lower():
		Color = "green"
	elif "y" in chrom.lower():
		Color = "blue"
	else:
		Color = "red"
	fig = plt.figure(figsize=(15, 5))
	axes = fig.add_subplot(111)
	axes.scatter(
		positions, readBalance, c=Color, alpha=MarkerAlpha, s=MarkerSize, lw=0)
	axes.set_xlim(0, chrom_len)
	axes.set_title(sampleID)
	axes.set_xlabel("Chromosomal Coordinate")
	axes.set_ylabel("Read Balance")
	# print(len(positions))
	plt.savefig("{}_{}_ReadBalance_GenomicScatter.svg".format(
		output_prefix, chrom))
	plt.savefig("{}_{}_ReadBalance_GenomicScatter.png".format(
		output_prefix, chrom))
	# plt.show()


def hist_read_balance(chrom, readBalance, sampleID, output_prefix):
	""" Plot a histogram of read balance """
	if "x" in chrom.lower():
		Color = "green"
	elif "y" in chrom.lower():
		Color = "blue"
	else:
		Color = "red"
	fig = plt.figure(figsize=(8, 8))
	axes = fig.add_subplot(111)
	axes.set_title(sampleID)
	axes.set_xlabel("Read Balance")
	axes.set_ylabel("Frequency")
	axes.hist(readBalance, bins=50, color=Color)
	plt.savefig("{}_{}_ReadBalance_Hist.svg".format(output_prefix, chrom))
	plt.savefig("{}_{}_ReadBalance_Hist.png".format(output_prefix, chrom))
	# plt.show()


def plot_variants_per_chrom(
	chrom_list, vcf_file, sampleID, output_prefix, qualCutoff,
	MarkerSize, MarkerAlpha, bamfile):
	""" Parses a vcf file and plots read balance in separate plots
	for each chromosome in the input list
	"""
	for i in chrom_list:
		parse_results = parse_platypus_VCF(vcf_file, qualCutoff, i)
		plot_read_balance(
			i, parse_results[0], parse_results[2],
			sampleID, output_prefix, MarkerSize, MarkerAlpha, bamfile)
		hist_read_balance(
			i, parse_results[2], sampleID, output_prefix)
	pass


def traverse_bam_fetch(samfile, chrom, window_size):
	"""Analyze the `samfile` BAM (or CRAM) file for various metrics.
	Currently, this function looks at the following metrics across genomic
	windows:
	- Read depth
	- Mapping quality
	The average of each metric will be calculated for each window of
	size `window_size` and stored altogether in a pandas data frame.
	Returns a dictionary of pandas data frames with the following key:
	- windows: The averages for each metric for each window
	"""
	chr_len = get_length(samfile, chrom)
	num_windows = chr_len // window_size + 1
	if chr_len % num_windows == 0:
		last_window_len = window_size
	else:
		last_window_len = chr_len % num_windows

	window_id = 0

	chr_list = [chrom] * num_windows
	start_list = []
	stop_list = []
	depth_list = []
	mapq_list = []

	start = 0
	end = window_size
	for window in range(0, num_windows):
		mapq = []
		total_read_length = 0
		for read in samfile.fetch(chrom, start, end):
			if read.is_secondary is False:
				if read.is_supplementary is False:
					total_read_length += read.infer_query_length()
					mapq.append(read.mapping_quality)
		start_list.append(start)
		stop_list.append(end)
		depth_list.append(total_read_length / window_size)
		mapq_list.append(np.mean(np.asarray(mapq)))

		window_id += 1
		if window_id == num_windows - 1:
			start += window_size
			end += last_window_len
		else:
			start += window_size
			end += window_size

		# Print progress
		print("{} out of {} windows processed on {}".format(
			window_id, num_windows, chrom))

	# Convert data into pandas data frames
	windows_df = pd.DataFrame({
		"chrom": np.asarray(chr_list),
		"start": np.asarray(start_list),
		"stop": np.asarray(stop_list),
		"depth": np.asarray(depth_list),
		"mapq": np.asarray(mapq_list)
	})[["chrom", "start", "stop", "depth", "mapq"]]

	results = {"windows": windows_df}
	return results


def make_region_lists(depthAndMapqDf, mapqCutoff, sd_thresh):
	"""
	(pandas.core.frame.DataFrame, int, float) -> (list, list)
	return two lists of regions (keepList, excludeList) based on
	cutoffs for depth and mapq
	"""
	depth_mean = depthAndMapqDf["depth"].mean()
	depth_sd = depthAndMapqDf["depth"].std()

	depthMin = depth_mean - (sd_thresh * (depth_sd ** 0.5))
	depthMax = depth_mean + (sd_thresh * (depth_sd ** 0.5))

	good = (
		(depthAndMapqDf.mapq > mapqCutoff) &
		(depthAndMapqDf.depth > depthMin) &
		(depthAndMapqDf.depth < depthMax))
	dfGood = depthAndMapqDf[good]
	dfBad = depthAndMapqDf[~good]

	return (dfGood, dfBad)


def output_bed(outBed, *regionDfs):
	'''
	(list, list, str) -> bedtoolsObject
	Take two sorted lists.  Each list is a list of tuples
	(chrom[str], start[int], end[int])
	Return a pybedtools object and output a bed file.
	'''
	dfComb = pd.concat(regionDfs)
	regionList = dfComb.ix[:, "chrom":"stop"].values.tolist()
	merge = pybedtools.BedTool(regionList).sort().merge()
	with open(outBed, 'w') as output:
		output.write(str(merge))
	pass


def chromosome_wide_plot(
	chrom, positions, y_value, measure_name, sampleID, output_prefix,
	MarkerSize, MarkerAlpha, Xlim, Ylim):
	'''
	Plots values across a chromosome, where the x axis is the position along the
	chromosome and the Y axis is the value of the measure of interest.
	positions is an array of coordinates
	y_value is an array of the values of the measure of interest
	measure_name is the name of the measure of interest (y axis title)
	chromosome is the name of the chromosome being plotted
	sampleID is the name of the sample
	MarkerSize is the size in points^2
	MarkerAlpha is the transparency (0 to 1)
	Xlim is the maximum X value
	Ylim is the maximum Y value
	'''
	if "x" in chrom.lower():
		Color = "green"
	elif "y" in chrom.lower():
		Color = "blue"
	else:
		Color = "red"
	fig = plt.figure(figsize=(15, 5))
	axes = fig.add_subplot(111)
	axes.scatter(
		positions, y_value, c=Color, alpha=MarkerAlpha, s=MarkerSize, lw=0)
	axes.set_xlim(0, Xlim)
	axes.set_ylim(0, Ylim)
	axes.set_title("%s - %s" % (sampleID, chrom))
	axes.set_xlabel("Chromosomal Position")
	axes.set_ylabel(measure_name)
	plt.savefig("{}_{}_{}_GenomicScatter.svg".format(
		output_prefix, chrom, measure_name))
	plt.savefig("{}_{}_{}_GenomicScatter.png".format(
		output_prefix, chrom, measure_name))
	# plt.show()


def plot_depth_mapq(
	data_dict, output_prefix, sampleID, chrom_length, MarkerSize, MarkerAlpha):
	"""
	Takes a dictionary (output from traverseBam) and outputs histograms and
	genome-wide plots of various metrics.
	Args:
		data_dict: Dictionary of pandas data frames
		output_prefix: Path and prefix of output files to create
		sampleID: name/ID of sample
		chrom_length: length of chromosome
	Returns:
		None
	"""

	window_df = None if "windows" not in data_dict else data_dict[
		"windows"]
	depth_hist = None if "depth_freq" not in data_dict else data_dict[
		"depth_freq"]
	readbal_hist = None if "readbal_freq" not in data_dict else data_dict[
		"readbal_freq"]
	mapq_hist = None if "mapq_freq" not in data_dict else data_dict[
		"mapq_freq"]

	chromosome = window_df["chrom"][1]

	# Create genome-wide plots based on window means
	if window_df is not None:
		# depth plot
		# depth_genome_plot_path = os.path.join(
		# 	output_dir, "depth_windows." + chromosome + ".png")
		# depth_genome_plot = sns.lmplot(
		# 	'start', 'depth', data=window_df, fit_reg=False,
		# 	scatter_kws={'alpha': 0.3})
		# depth_genome_plot.savefig(depth_genome_plot_path)
		chromosome_wide_plot(
			chromosome, window_df["start"].values, window_df["depth"].values,
			"Depth", sampleID, output_prefix,
			MarkerSize, MarkerAlpha,
			chrom_length, 100)

		# mapping quality plot
		# mapq_genome_plot_path = os.path.join(
		# 	output_dir, "mapq_windows." + chrom + ".png")
		# mapq_genome_plot = sns.lmplot(
		# 	'start', 'mapq', data=window_df, fit_reg=False)
		# mapq_genome_plot.savefig(mapq_genome_plot_path)
		chromosome_wide_plot(
			chromosome, window_df["start"].values, window_df["mapq"].values,
			"Mapq", sampleID, output_prefix,
			MarkerSize, MarkerAlpha, chrom_length, 80)

	# Create histograms
	# TODO: update filenames dynamically like window_df above
	# TODO: update Count column name
	if depth_hist is not None:
		depth_bar_plot = sns.countplot(
			x='depth', y='Count', data=depth_hist)
		depth_bar_plot.savefig("depth_hist.png")
	if readbal_hist is not None:
		balance_bar_plot = sns.countplot(
			x='ReadBalance', y='Count', data=readbal_hist)
		balance_bar_plot.savefig("readbalance_hist.png")
	if mapq_hist is not None:
		mapq_bar_plot = sns.countplot(
			x='Mapq', y='Count', data=mapq_hist)
		mapq_bar_plot.savefig("mapq_hist.png")


# Legacy functions (keeping them so they remain callable if needed later)
def bwa_mem_mapping(
	bwa_path, samtools_path, reference, output_prefix, fastqs,
	threads, cram=False):
	""" Maps reads to a reference genome using bwa mem.
	"""
	fastqs = ' '.join(fastqs)
	subprocess.call("{} index {}".format(bwa_path, reference), shell=True)
	if cram is False:
		command_line = "{} mem -t {} {} {} | {} fixmate -O bam - - | "\
			"{} sort -O bam -o {}_sorted.bam -".format(
				bwa_path, threads, reference, fastqs, samtools_path,
				samtools_path, output_prefix)
		subprocess.call(command_line, shell=True)
		subprocess.call(
			"{} index {}_sorted.bam".format(
				samtools_path, output_prefix), shell=True)
		return "{}_sorted.bam".format(output_prefix)
	else:
		command_line = "{} mem -t {} {} {} | {} fixmate -O cram - - | "\
			"{} sort -O cram -o {}_sorted.cram -".format(
				bwa_path, threads, reference, fastqs, samtools_path,
				samtools_path, output_prefix)
		subprocess.call(command_line, shell=True)
		subprocess.call(
			"{} index {}_sorted.cram".format(
				samtools_path, output_prefix), shell=True)
		return "{}_sorted.cram".format(output_prefix)


def switch_sex_chromosomes_bam(
	samtools_path, bam_orig, bam_new, sex_chroms, output_directory,
	output_prefix, cram=False):
	""" Removes sex chromosomes from original bam and merges in remmapped
	sex chromosomes, while retaining the original bam header
	"""
	# Grab original header
	subprocess.call(
		"{} view -H {} > {}/header.sam".format(
			samtools_path, bam_orig, output_directory), shell=True)
	if cram is False:
		# Remove sex chromosomes from original bam
		samfile = pysam.AlignmentFile(bam_orig, "rb")
		non_sex_scaffolds = filter(
			lambda x: x not in sex_chroms, list(samfile.references))
		subprocess.call(
			"{} view -h -b {} {} > {}/no_sex.bam".format(
				samtools_path, bam_orig, " ".join(non_sex_scaffolds),
				output_directory),
			shell=True)
		subprocess.call(
			"{} index {}/no_sex.bam".format(
				samtools_path, output_directory), shell=True)

		# Merge bam files
		subprocess.call(
			"{} merge -h {}/header.sam {}/{}.bam {}/no_sex.bam {}".format(
				samtools_path, output_directory, output_directory,
				output_prefix, output_directory, bam_new), shell=True)
		subprocess.call("{} index {}/{}.bam".format(
			samtools_path, output_directory, output_prefix), shell=True)

		return "{}/{}.bam".format(output_directory, output_prefix)

	else:
		# Remove sex chromosomes from original bam
		samfile = pysam.AlignmentFile(bam_orig, "rc")
		non_sex_scaffolds = filter(
			lambda x: x not in sex_chroms, list(samfile.references))
		subprocess.call(
			"{} view -h -b {} {} > {}/no_sex.cram".format(
				samtools_path, bam_orig, " ".join(non_sex_scaffolds),
				output_directory),
			shell=True)
		subprocess.call(
			"{} index {}/no_sex.cram".format(
				samtools_path, output_directory), shell=True)

		# Merge bam files
		subprocess.call(
			"{} merge -h {}/header.sam {}/{}.cram {}/no_sex.cram {}".format(
				samtools_path, output_directory, output_directory,
				output_prefix, output_directory, bam_new), shell=True)
		subprocess.call("{} index {}/{}.cram".format(
			samtools_path, output_directory, output_prefix), shell=True)

		return "{}/{}.cram".format(output_directory, output_prefix)

if __name__ == "__main__":
	main()