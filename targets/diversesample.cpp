#include "io.h"
#include "SequenceMinHash.h"
#include "RACE.h"
#include "util.h"
#include "Reservoir.h"

#include <chrono>
#include <string>
#include <cstring>
#include <algorithm>

/*
Copyright 2019, Benjamin Coleman, All rights reserved. 
Free for research use. For commercial use, contact 
Rice University Invention & Patent or the author

*/


/*
Three types of reads: paired, interleaved and single

For single reads just do normally 
For interleaved reads just do normally but save "chunks"
For paired reads, assume they're in order (if they're not,you can use fastq-pair) 
and "rescue" saved reads


Desired interface:
samplerace tau SE input output <flags>
samplerace tau PE input1 input2 output1 output2 <flags>
samplerace tau I input output <flags>

*/

int main(int argc, char **argv){

    if (argc < 4){
        std::clog<<"Usage: "<<std::endl; 
        std::clog<<"diversesample <sample_size> <format> <input> <output>"; 
        std::clog<<" [--range race_range] [--reps race_reps] [--hashes n_minhashes] [-k kmer_size] [--seed random_seed]"<<std::endl; 
        std::clog<<"Positional arguments: "<<std::endl; 
        std::clog<<"sample_size: integer representing how many elements to sample"<<std::endl; 
        std::clog<<"format: Either PE, SE, or I for paired-end, single-end, and interleaved paired reads"<<std::endl; 
        std::clog<<"input: path to input data file (.fastq or .fasta extension). For PE format, specify two files."<<std::endl; 
        std::clog<<"output: path to output sample file (same extension as input). For PE format, specify two files."<<std::endl; 
        
        std::clog<<"Optional arguments: "<<std::endl; 
        std::clog<<"[--range race_range]: (Optional, default 10000) Hash range for each ACE (B)"<<std::endl;
        std::clog<<"[--reps race_reps]: (Optional, default 100) Number of ACE repetitions (R)"<<std::endl;
        std::clog<<"[--hashes n_minhashes]: (Optional, default 1) Number of MinHashes for each ACE (n)"<<std::endl;
        std::clog<<"[--k kmer_size]: (Optional, default 16) Size of each MinHash k-mer (k)"<<std::endl;
        std::clog<<"[--seed random_seed]: (Optional, default 0) The random seed to configure hash functions with"<<std::endl;

        std::clog<<std::endl<<"Example usage:"<<std::endl; 
        std::clog<<"diversesample 100 PE data/input-1.fastq data/input-2.fastq data/output-1.fastq data/output-2.fastq --range 100 --reps 50 --hashes 3 --k 5"<<std::endl; 
        std::clog<<"diversesample 200 SE data/input.fastq data/output.fastq --range 100 --reps 5 --hashes 1 --k 33"<<std::endl; 
        std::clog<<"diversitysample 300 SE data/input.fasta data/output.fasta --range 100000 --k 20"<<std::endl; 
        return -1; 
    }


    // POSITIONAL ARGUMENTS
    double sample_size = std::stoi(argv[1]);
    int format; // ENUM: 1 = unpaired, 2 = interleaved, 3 = paired
    if (std::strcmp("SE",argv[2]) == 0){
        format = 1;
    } else if (std::strcmp("I",argv[2]) == 0){
        format = 2; 
    } else if (std::strcmp("PE",argv[2]) == 0){
        format = 3; 
        if (argc < 7){
            std::cerr<<"For paired-end reads, please specify the input and output files as:"<<std::endl; 
            std::cerr<<"input1.fastq input2.fastq output1.fastq output2.fastq"<<std::endl; 
            return -1; 
        }
    } else {
        std::cerr<<"Invalid format, please specify either SE, PE, or I"<<std::endl; 
        return -1;
    }

    // open the correct file streams given the format
    std::ifstream datastream1;
    std::ofstream samplestream1;
    std::ofstream weightstream1;
    Reservoir reservoir1 = NULL;
    std::ifstream datastream2;
    std::ofstream samplestream2;
    std::ofstream weightstream2;
    Reservoir reservoir2 = NULL;

    if (format != 3){
        datastream1.open(argv[3]);
        samplestream1.open(argv[4]);
        weightstream1.open(strcat(argv[4], ".weights"));
        reservoir1 = Reservoir(sample_size);
    } else {
        datastream1.open(argv[3]);
        datastream2.open(argv[4]);
        samplestream1.open(argv[5]);
        samplestream2.open(argv[6]);
        weightstream1.open(strcat(argv[5], ".weights"));
        weightstream2.open(strcat(argv[6], ".weights"));
        reservoir1 = Reservoir(sample_size);
        reservoir2 = Reservoir(sample_size);
    }

    // determine file extension
    std::string filename(argv[3]); 
    std::string file_extension = "";
    size_t idx = filename.rfind('.',filename.length()); 
    if (file_extension == "fq"){
        file_extension = "fastq"; 
    }
    if (idx != std::string::npos){
        file_extension = filename.substr(idx+1, filename.length() - idx); 
    } else {
        std::cerr<<"Input file does not appear to have any file extension."<<std::endl; 
        return -1; 
    }
    if (file_extension != "fasta" && file_extension != "fastq"){
        std::cerr<<"Unknown file extension: "<<file_extension<<std::endl; 
        std::cerr<<"Please specify either a file with the .fasta or .fastq extension."<<std::endl; 
        return -1; 
    }

    // OPTIONAL ARGUMENTS
    int race_range = 10000;
    int race_repetitions = 10;
    int hash_power = 1;
    int kmer_k = 16;
    unsigned int seed = clock();

    for (int i = 0; i < argc; ++i){
        if (std::strcmp("--range",argv[i]) == 0){
            if ((i+1) < argc){
                race_range = std::stoi(argv[i+1]);
            } else {
                std::cerr<<"Invalid argument for optional parameter --range"<<std::endl; 
                return -1;
            }
        }
        if (std::strcmp("--reps",argv[i]) == 0){
            if ((i+1) < argc){
                race_repetitions = std::stoi(argv[i+1]);
            } else {
                std::cerr<<"Invalid argument for optional parameter --reps"<<std::endl; 
                return -1;
            }
        }
        if (std::strcmp("--hashes",argv[i]) == 0){
            if ((i+1) < argc){
                hash_power = std::stoi(argv[i+1]);
            } else {
                std::cerr<<"Invalid argument for optional parameter --hashes"<<std::endl; 
                return -1;
            }
        }
        if (std::strcmp("--k",argv[i]) == 0){
            if ((i+1) < argc){
                kmer_k = std::stoi(argv[i+1]);
            } else {
                std::cerr<<"Invalid argument for optional parameter --k"<<std::endl; 
                return -1;
            }
        }

         if (std::strcmp("--seed",argv[i]) == 0){
            if ((i+1) < argc){
                seed = std::stoi(argv[i+1]);
            } else {
                std::cerr<<"Invalid argument for optional parameter --seed"<<std::endl; 
                return -1;
            }
        }
    }

    srand(seed);

    // Check if arguments are valid
    if (sample_size <= 0){ std::cerr<<"Invalid value for parameter <sample_size>"<<std::endl; return -1; }
    if (race_range <= 0){ std::cerr<<"Invalid value for optional parameter --range"<<std::endl; return -1; }
    if (race_repetitions <= 0){ std::cerr<<"Invalid value for optional parameter --reps"<<std::endl; return -1; }
    if (hash_power <= 0){ std::cerr<<"Invalid value for optional parameter --hashes"<<std::endl; return -1; }
    if (kmer_k <= 0){ std::cerr<<"Invalid value for optional parameter --k"<<std::endl; return -1; }

    // done parsing information. Begin RACE algorithm: 

    // buffer for sequences and fasta/fastq chunks
    std::string sequence;
    std::string chunk1;
    std::string chunk2;

    // set up the hash function that will be used to hash input sequences
    SequenceMinHash hash = SequenceMinHash(race_repetitions*hash_power, seed);
    int* raw_hashes = new int[race_repetitions*hash_power]; 
    int* rehashes = new int[race_repetitions];

    RACE sketch = RACE(race_repetitions,race_range); 


    int t = 0;

    do{
        bool success = false; 
        int c = datastream1.peek(); 
        if (c == EOF) {
            if (datastream1.eof()){
                continue; 
            }
        }

        switch(format){
            case 1: // 1 = unpaired
            success = SequenceFeaturesSE(datastream1, sequence, chunk1, file_extension);
            break; 
            case 2: // 2 = interleaved
            success = SequenceFeaturesI(datastream1, sequence, chunk1, file_extension); 
            break; 
            case 3: // 3 = paired
            success = SequenceFeaturesPE(datastream1, datastream2, sequence, chunk1, chunk2, file_extension);
            break; 
        }
        if (!success) continue;

        hash.getHash(kmer_k, sequence, raw_hashes); 
        // now that we have the sequence and label
        // feed the sequence into the RACE structure
        // first rehash so that the arrays can fit into RACE
        rehash(raw_hashes, rehashes, race_repetitions, hash_power);
        // then simultaneously query and add 
        long double KDE = (long double) sketch.query_and_add(rehashes); 
        // note: KDE is on a scale from [0,N] not the normalized interval [0,1]

        long double weight = ((long double) ++t) / (KDE + 1);
        // long double weight = 1 / (KDE + EPSILON);

        switch(format){
            case 1: // 1 = unpaired
            case 2: // 2 = interleaved
            reservoir1.put(chunk1, weight, KDE);
            break; 
            case 3: // 3 = paired
            reservoir1.put(chunk1, weight, KDE);
            reservoir2.put(chunk2, weight, KDE);
            break; 
        }
        
    }
    while(datastream1);

    switch(format){
        case 1: // 1 = unpaired
        case 2: // 2 = interleaved
        reservoir1.drain(samplestream1, weightstream1);
        break; 
        case 3: // 3 = paired
        reservoir1.drain(samplestream1, weightstream1);
        reservoir2.drain(samplestream2, weightstream2);
        break; 
    }
}
