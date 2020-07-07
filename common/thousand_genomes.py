import numpy as np
import os

def load_data(path='', force_npz_recreation=False):
    dataset_file = 'affy_6_biallelic_snps_maf005_thinned_aut_dataset.npz'
    genome_file = 'affy_6_biallelic_snps_maf005_thinned_aut_A.raw'
    label_file = '../data/affy_samples.20141118.panel'
    
    if os.path.exists(os.path.join(path, dataset_file)) and not force_npz_recreation:
        genomic_data, label_data = np.load(os.path.join(path, dataset_file)).values()
        return genomic_data, label_data
        
    print('No binary .npz file has been found for this dataset. The data will '
          'be parsed to produce one. This will take a few minutes.')
    
    # Load the genomic data file
    with open(os.path.join(path, genome_file), 'r') as f:
        lines = f.readlines()[1:]
    headers = [l.split()[:6] for l in lines]
    
    nb_features = len(lines[-1].split()[6:])
    genomic_data = np.empty((len(lines), nb_features), dtype='int8')
    for idx, line in enumerate(lines):
        if idx % 100 == 0:
            print('Parsing subject %i out of %i' % (idx, len(lines)))
        genomic_data[idx] = [int(e) for e in line.replace('NA', '0').split()[6:]]
    
    # Load the label file
    label_dict = {}
    with open(os.path.join(path, label_file), 'r') as f:
        for line in f.readlines()[1:]:
            patient_id, ethnicity, _ = line.split()
            label_dict[patient_id] = ethnicity
            
    # Transform the label into a one-hot format
    all_labels = list(set(label_dict.values()))
    all_labels.sort()
    
    label_data = np.zeros((genomic_data.shape[0], len(all_labels)), dtype='float32')

    for subject_idx in range(len(headers)):
        subject_id = headers[subject_idx][0]
        subject_label = label_dict[subject_id]
        label_idx = all_labels.index(subject_label)
        label_data[subject_idx, label_idx] = 1.0

    # Save the parsed data to the filesystem
    print('Saving parsed data to a binary format for faster loading in the future.')
    np.savez(path + dataset_file, genomic=genomic_data, label=label_data)

    return genomic_data, label_data

if __name__ == '__main__':
    x = load_data(force_npz_recreation=True)
    print('Load1 done')
    x = load_data()
    print('Load2 done')
