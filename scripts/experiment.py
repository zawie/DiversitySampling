import os
import subprocess
import argparse
import random
import time 
import statistics
import numpy as np
from numpy.polynomial.polynomial import polyfit

import matplotlib.pyplot as plt
from collections import defaultdict
from Bio import SeqIO

UNCLASSIFIED_SPECIES = 0

def stdev(data):
    if len(data) < 2:
        return 0
    return statistics.stdev(data)

# def run_kraken(fastq_file, seed):
#     # subprocess.call(["kraken2","--db", "/scratch1/zx22/bio/refseq214", "--threads", "12","--output",\
#     #     src_path+"out_race_"+str(size)+"_repeat_"+str(r), src_path+"race_"+str(size)+"_repeat_"+str(r)+".fastq"]) 
#     pass 

def run_diversity_sampling(fastq_file, sample_size, seed):
    output_file = f"./outputs/diverse-sample_seed={seed}_{os.path.basename(fastq_file)}"
    if os.path.isfile(output_file):
        print("Run diversity sampling already ran! Reusing...")
        return (output_file, output_file+".weights")
    subprocess.call(["./bin/diversesample", str(sample_size), "SE", fastq_file, output_file, "--seed", str(seed)]) 
    return (output_file, output_file+".weights")

def run_uniform_sampling(fastq_file, sample_size, seed):
    output_file = f"./outputs/uniform-sample_seed={seed}_{os.path.basename(fastq_file)}"
    if os.path.isfile(output_file):
        print("Run uniform sampling already ran! Reusing...")
        return (output_file)
    subprocess.call(["./bin/uniformsample", str(sample_size), "SE", fastq_file, output_file, "--seed", str(seed)]) 
    return (output_file)

#Parse commandlines
parser = argparse.ArgumentParser(
                    prog = 'RunExperiment',
                    description = 'What the program does',
                    epilog = '')

parser.add_argument('-f', '--fastq', help="fastq file pre sampling")

parser.add_argument('-a', '--sample_amount', help="post sampling fastq file", default=10000, type=int)  
parser.add_argument('-s', '--seed', help="seed to use", default=random.randint(0, 1 << 31), type=int)
parser.add_argument('-r', '--repetitions', help="number of times to repeat experiment", default=1, type=int)

parser.add_argument('-k', '--kraken', help="(Optional) kraken of original fastq file")
parser.add_argument('-v', '--verbose', action='store_true')  # on/off flag

args = parser.parse_args()

# Define verbose print function
def vprint(*x):
    if args.verbose:
        print(*x)

# Generate a seed for every repetition
vprint("Using sourceseed", args.seed)
random.seed(args.seed)
seeds = [random.randint(0, 1 << 31) for _ in range(args.repetitions)]

# Extract files
fastq_path = args.fastq
kraken_path = None

if (args.kraken == None):
    vprint("Running kraken...")
    # TODO: Execute kraken when needed.
    raise Exception("kraken execution not implemented")
    # kraken_file = run_kraken(fastq_file)
else:
    kraken_path = args.kraken
    vprint("Kraken file can be located at " + kraken_path)

# Identify each species form each sequence using kraken
id_to_species = defaultdict(lambda: UNCLASSIFIED_SPECIES)
true_proportion = defaultdict(lambda: 0)
all_diverse_estimates = defaultdict(lambda: list())
all_uniform_estimates = defaultdict(lambda: list())

# Extract species "true" proportion
numSequences = 0
with open(kraken_path) as infile:
    for line in infile:
        # Extract information from kraken line
        chunks = line.split('\t')
        classified = (chunks[0].strip() == 'C')  
        id = chunks[1]
        if classified and chunks[2] != None:
            species = int(chunks[2])
        else:
            species = UNCLASSIFIED_SPECIES
        # Map id to species
        id_to_species[id] = species
        true_proportion[species] += 1
        numSequences += 1
for species in true_proportion.keys():
    true_proportion[species] /= numSequences

for rep in range(args.repetitions):
    vprint(f"Running repitition #{rep+1}")
    seed = seeds[rep]
    vprint(f"seed={seed}")

    #Run the different sampling approaches
    vprint("Running uniform sampling...")
    (uniform_sample_path) = run_uniform_sampling(fastq_path, args.sample_amount, seed)
    # vprint(f" - Uniform sampling took {uniform_time_elapsed} ns")
    vprint(" - Uniform sample file can be located at " + uniform_sample_path)

    vprint("Running diversity sampling...")
    (diverse_sample_path, diverse_weights_path) = run_diversity_sampling(fastq_path, args.sample_amount, seed) 
    # vprint(f" - Diversity sampling took {diverse_time_elapsed} ns")
    vprint(" - Diversity sample file can be located at " + diverse_sample_path)
    vprint(" - Diversity sample Weights file can be located at " + diverse_weights_path)

    # Extract ids from samples 
    uniform_ids_list = list()
    with open(uniform_sample_path) as handle:
        for record in SeqIO.parse(handle, "fastq"):
            uniform_ids_list.append(record.id)
    diverse_ids_list = list()
    with open(diverse_sample_path) as handle:
        for record in SeqIO.parse(handle, "fastq"):
            diverse_ids_list.append(record.id)
    diverse_weights_list = list() 
    with open(diverse_weights_path) as infile:
        for line in infile:
            weight = float(line)
            diverse_weights_list.append(weight)

    assert(len(diverse_weights_list) == len(diverse_ids_list)) #Sanity check

    # Compute uniform estimate
    uniform_estimate = defaultdict(lambda: 0)
    total_count = 0
    for id in uniform_ids_list:
        uniform_estimate[id_to_species[id]] += 1
        total_count += 1
    for species in uniform_estimate.keys():
        uniform_estimate[species] /= total_count

    # Compute diverse estimate
    diverse_estimate = defaultdict(lambda: 0)
    total_weight = 0
    for (id, weight) in zip(diverse_ids_list, diverse_weights_list):
        diverse_estimate[id_to_species[id]] += weight
        total_weight += weight
    for species in diverse_estimate.keys():
        diverse_estimate[species] /= total_weight

    for species in true_proportion.keys():
        all_diverse_estimates[species].append(diverse_estimate[species])
        all_uniform_estimates[species].append(uniform_estimate[species])
    
    uniform_species_detected = 0
    diverse_species_detected = 0
    for species in true_proportion.keys():
        if uniform_estimate[species] > 0:
            uniform_species_detected += 1
        if diverse_estimate[species] > 0:
            diverse_species_detected += 1 
    print(f"Uniform species detected: {uniform_species_detected}")    
    print(f"Diverse species detected: {diverse_species_detected}")    

# Organize results
rows = []
for species in true_proportion.keys():
    if (species == UNCLASSIFIED_SPECIES):
        continue # Don't plot the unclassified species
    true_pro = true_proportion[species]
    rows.append((species, true_pro, all_diverse_estimates[species], all_uniform_estimates[species]))

#Filter
# filtered_rows = []
# for row in rows:
#     (species, true_pro, d_est, u_est) = row
#     if (d_est > 0 and u_est > 0):
#         filtered_rows.append(row)
# rows = filtered_rows

# Print results to terminal
rows.sort(key=lambda row: row[1], reverse=True)

rows = rows[100:]

# for row in [("Species", "Proportion", "Diverse Estimate (Mean)", "Uniform Estimate (Mean)")] + rows:
#     print("{: >10} {: >25} {: >25} {: >25}".format(*row))

err_uniform = defaultdict(lambda: list())
err_diverse = defaultdict(lambda: list())
est_uniform = defaultdict(lambda: list())
est_diverse = defaultdict(lambda: list())

# det_uniform = defaultdict(lambda: list())
# det_diverse = defaultdict(lambda: list())
# num_species = defaultdict(lambda: 0)
x = set()
for (species, true_pro, d, u) in rows:
    x.add(true_pro)
    err_diverse[true_pro] += [abs(d_est - true_pro) for d_est in d]
    err_uniform[true_pro] += [abs(u_est - true_pro) for u_est in u]
    est_uniform[true_pro] += u
    est_diverse[true_pro] += d

    # num_species[true_pro] += 1
    # d_delta = 0
    # if (sum(d) > 0):
    #     d_delta = 1
    # u_delta = 0
    # if (sum(u) > 0):
    #     u_delta = 1
    # species_detected[true_pro] = (count + 1, d_detected + d_delta, u_detected + u_delta)

x = list(x)
x.sort()

# Create plots
plt.title('Error vs. Species Proportions')
plt.xlabel("True Proportion")
plt.ylabel("Mean Estimate Error (abs)")

plt.errorbar(x, 
    [statistics.mean(err_uniform[t]) for t in x],
    yerr=[stdev(err_uniform[t]) for t in x],
    capsize= 3,
    color="tab:pink", 
    label="Uniform Sampling",
    linestyle="", 
    marker="."
)

plt.errorbar(x, 
    [statistics.mean(err_diverse[t]) for t in x],
    yerr=[stdev(err_diverse[t]) for t in x],
    capsize= 3,
    color="tab:cyan", 
    label="Diverse Sampling",
    linestyle="", 
    marker="."
)

plt.legend(loc="upper left")
plt.savefig("error-plot.png")
plt.clf()

# Plot
plt.title('Estimate vs. Species Proportions')
plt.xlabel("True Proportion")
plt.ylabel("Mean Estimate")

plt.errorbar(x, 
    [statistics.mean(est_uniform[t]) for t in x],
    yerr=[stdev(est_uniform[t]) for t in x],
    capsize= 3,
    color="red", 
    label="Uniform Sampling",
    linestyle="", 
    marker="."
)

b, m = polyfit(x, [statistics.mean(est_uniform[t]) for t in x], 1)
plt.plot(x, [b + m * t for t in x ], '-', color="red", label=f"Uniform fit: {m}x + {b}")

plt.errorbar(x, 
    [statistics.mean(est_diverse[t]) for t in x],
    yerr=[stdev(est_diverse[t]) for t in x],
    capsize= 3,
    color="blue", 
    label="Diverse Sampling",
    linestyle="", 
    marker="."
)

b, m = polyfit(x, [statistics.mean(est_diverse[t]) for t in x], 1)
plt.plot(x, [b + m * t for t in x ], '-', color="blue", label=f"Diverse fit: {m}x + {b}")

plt.legend(loc="upper left")
plt.plot(x, x, color="black", label="Ideal Estimate",linestyle="dashed",marker="")

plt.savefig("estimate-plot.png")
# plt.clf()

# plt.title('Species Detected')
# plt.xlabel("True Proportion")
# plt.ylabel("Number of Speceis Detected")

# plt.plot(x,
#     [species_detected[t][0] for t in x],
#     color="gray",
#     label="Species Count",
#     linestyle="", 
#     marker="o"
# )

# plt.plot(x,
#     [species_detected[t][2] for t in x],
#     color="red",
#     label="Uniform Sampling",
#     linestyle="", 
#     marker="x"
# )

# plt.plot(x,
#     [species_detected[t][1] for t in x],
#     color="blue",
#     label="Diverse Sampling",
#     linestyle="", 
#     marker="+"
# )

# plt.legend(loc="upper right")
# plt.yscale("log")
# plt.savefig("detection-plot.png")



