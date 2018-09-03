from __future__ import print_function
import os
import numpy as np
from DietNetworks.experiments.common.dataset_utils import load_1000_genomes
import sys

def generate_1000_genomes_hist(path, label_splits=None, feature_splits=None, fold=0, perclass=True):

    train, valid, test, _ = load_1000_genomes(path,
                                                label_splits=label_splits,
                                                feature_splits=feature_splits,
                                                fold=fold, norm=False)

    for data in [train, valid, test]:
        X, y = data
        print(X.shape, y.shape)
            
    # Generate no_label: fuse train and valid sets
    nolabel_orig = (np.vstack([train[0], valid[0]])).transpose()
    nolabel_y = np.vstack([train[1], valid[1]])

    nolabel_y = nolabel_y.argmax(axis=1)

    filename = 'histo3x26' if perclass else 'histo3'
    filename += '_fold%d.npy' % fold

    if perclass:
        # the first dimension of the following is length 'number of snps'
        nolabel_x = np.zeros((nolabel_orig.shape[0], 3*26))
        for i in range(nolabel_x.shape[0]):
            if i % 5000 == 0:
                print("processing snp no: ", i)
            for j in range(26):
                nolabel_x[i, j*3:j*3+3] += \
                    np.bincount(nolabel_orig[i, nolabel_y == j ].astype('int32'), minlength=3)
                nolabel_x[i, j*3:j*3+3] /= \
                    nolabel_x[i, j*3:j*3+3].sum()
    else:
        nolabel_x = np.zeros((nolabel_orig.shape[0], 3))
        for i in range(nolabel_x.shape[0]):
            nolabel_x[i, :] += np.bincount(nolabel_orig[i, :].astype('int32'),
                                           minlength=3)
            nolabel_x[i, :] /= nolabel_x[i, :].sum()

    nolabel_x = nolabel_x.astype('float32')

    np.save(os.path.join(path, filename), nolabel_x)

def generate_1000_genomes_bag_of_genes(path, label_splits=None, feature_splits=[0.8], fold=0):

    train, valid, test, _ = load_1000_genomes(label_splits, feature_splits, fold, norm=False)

    nolabel_orig = (np.vstack([train[0], valid[0]]))

    if not os.path.isdir(path):
        os.makedirs(path)

    filename = 'unsupervised_bag_of_genes'
    filename += '_fold' + str(fold) + '.npy'

    nolabel_x = np.zeros((nolabel_orig.shape[0], nolabel_orig.shape[1]*2))

    mod1 = np.zeros(nolabel_orig.shape)
    mod2 = np.zeros(nolabel_orig.shape)

    for i in range(nolabel_x.shape[0]):
        mod1[i, :] = np.where(nolabel_orig[i, :] > 0)[0]*2 + 1
        mod2[i, :] = np.where(nolabel_orig == 2)[0]*2

    nolabel_x[mod1] += 1
    nolabel_x[mod2] += 1

def generate_1000_genomes_snp2bin(path, label_splits=None, feature_splits=None, fold=0):

    train, valid, test, _ = load_1000_genomes(label_splits, feature_splits, fold, norm=False)

    # Generate no_label: fuse train and valid sets
    nolabel_orig = (np.vstack([train[0], valid[0]]))
    nolabel_x = np.zeros((nolabel_orig.shape[0], nolabel_orig.shape[1]*2),
                         dtype='uint8')

    filename = 'unsupervised_snp_bin_fold' + str(fold) + '.npy'

    # SNP to bin
    nolabel_x[:, ::2] += (nolabel_orig == 2)
    nolabel_x[:, 1::2] += (nolabel_orig >= 1)

    np.save(os.path.join(path, filename), nolabel_x)

if __name__ == '__main__':
    nfold = 5
    path = sys.argv[1]

    for fold in range(nfold):
        print(fold)
        generate_1000_genomes_hist(path=path, label_splits=[.75], feature_splits=[1.], fold=fold)
