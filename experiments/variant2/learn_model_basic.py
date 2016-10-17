#!/usr/bin/env python2

from __future__ import print_function
import argparse
import time
import os
import random
from distutils.dir_util import copy_tree

import lasagne
from lasagne.layers import DenseLayer, InputLayer, DropoutLayer, BatchNormLayer
from lasagne.nonlinearities import (sigmoid, softmax, tanh, linear, rectify,
                                    leaky_rectify, very_leaky_rectify)
import numpy as np
import theano
import theano.tensor as T

from feature_selection.experiments.common import dataset_utils, imdb


# Mini-batch iterator function
def iterate_minibatches(inputs, targets, batchsize,
                        shuffle=False):
    assert inputs.shape[0] == targets.shape[0]
    indices = np.arange(inputs.shape[0])
    if shuffle:
        indices = np.random.permutation(inputs.shape[0])
    for i in range(0, inputs.shape[0]-batchsize+1, batchsize):
        yield inputs[indices[i:i+batchsize], :],\
            targets[indices[i:i+batchsize]]


def iterate_testbatches(inputs, batchsize, shuffle=False):
    indices = np.arange(inputs.shape[0])
    if shuffle:
        indices = np.random.permutation(inputs.shape[0])
    for i in range(0, inputs.shape[0]-batchsize+1, batchsize):
        yield inputs[indices[i:i+batchsize], :]


def get_precision_recall_cutoff(predictions, targets):

    prev_threshold = 0.00
    threshold_inc = 0.10

    while True:
        if prev_threshold > 1.000:
            cutoff = 0.0
            break

        threshold = prev_threshold + threshold_inc
        tp = ((predictions >= threshold) * (targets == 1)).sum()
        fp = ((predictions >= threshold) * (targets == 0)).sum()
        fn = ((predictions < threshold) * (targets == 1)).sum()

        precision = float(tp) / (tp + fp + 1e-20)
        recall = float(tp) / (tp + fn + 1e-20)

        if precision > recall:
            if threshold_inc < 0.001:
                cutoff = recall
                break
            else:
                threshold_inc /= 10
        else:
            prev_threshold += threshold_inc

    return cutoff


# Monitoring function
def monitoring(minibatches, which_set, error_fn, monitoring_labels,
               prec_recall_cutoff=True):
    print('-'*20 + which_set + ' monit.' + '-'*20)
    monitoring_values = np.zeros(len(monitoring_labels), dtype="float32")
    global_batches = 0

    targets = []
    predictions = []

    for batch in minibatches:
        # Update monitored values
        out = error_fn(*batch)

        monitoring_values += out[1:]
        predictions.append(out[0])
        targets.append(batch[1])
        global_batches += 1

    # Print monitored values
    monitoring_values /= global_batches
    for (label, val) in zip(monitoring_labels, monitoring_values):
        print ("  {} {}:\t\t{:.6f}".format(which_set, label, val))

    # If needed, compute and print the precision-recall breakoff point
    if prec_recall_cutoff:
        predictions = np.vstack(predictions)
        targets = np.vstack(targets)
        cutoff = get_precision_recall_cutoff(predictions, targets)
        print ("  {} precis/recall cutoff:\t{:.6f}".format(which_set, cutoff))

    return monitoring_values


# Main program
def execute(dataset, n_hidden_t_enc, n_hidden_s,
            num_epochs=500, learning_rate=.001, learning_rate_annealing=1.0,
            gamma=1, disc_nonlinearity="sigmoid", keep_labels=1.0,
            prec_recall_cutoff=True, missing_labels_val=-1.0,
            save_path='/Tmp/romerosa/feature_selection/',
            save_copy='/Tmp/romerosa/feature_selection/',
            dataset_path='/Tmp/carriepl/datasets/'):

    # Load the dataset
    print("Loading data")
    splits = [0.6, 0.2]  # This will split the data into [60%, 20%, 20%]

    if dataset == 'protein_binding':
        data = dataset_utils.load_protein_binding(transpose=False,
                                                  splits=splits)
    elif dataset == 'dorothea':
        data = dataset_utils.load_dorothea(transpose=False, splits=None)
    elif dataset == 'opensnp':
        data = dataset_utils.load_opensnp(transpose=False, splits=splits)
    elif dataset == 'reuters':
        data = dataset_utils.load_reuters(transpose=False, splits=splits)
    elif dataset == 'iric_molecule':
        data = dataset_utils.load_iric_molecules(transpose=False,
                                                 splits=splits)
    elif dataset == 'imdb':
        dataset_path = os.path.join(dataset_path, "imdb")
        # use feat_type='tfidf' to load tfidf features
        data = imdb.read_from_hdf5(path=dataset_path, unsupervised=False,
                                   feat_type='tfidf')
    elif dataset == 'dragonn':
        from feature_selection.experiments.common import dragonn_data
        data = dragonn_data.load_data(500, 100, 100)
    elif dataset == '1000_genomes':
        data = dataset_utils.load_1000_genomes(transpose=False,
                                               label_splits=splits)
    else:
        print("Unknown dataset")
        return

    if dataset == 'imdb':
        x_train = data.root.train_features
        y_train = data.root.train_labels[:][:, None].astype("float32")
        x_valid = data.root.val_features
        y_valid = data.root.val_labels[:][:, None].astype("float32")
        x_test = data.root.test_features
        y_test = None
        x_nolabel = None
    else:
        (x_train, y_train), (x_valid, y_valid), (x_test, y_test),\
            x_nolabel = data

    # If needed, remove some of the training labels
    if keep_labels <= 1.0:
        training_labels = y_train.copy()
        random.seed(23)
        nb_train = len(training_labels)

        indices = range(nb_train)
        random.shuffle(indices)

        indices_discard = indices[:int(nb_train * (1 - keep_labels))]
        for idx in indices_discard:
            training_labels[idx] = missing_labels_val
    else:
        training_labels = y_train

    # Extract required information from data
    n_samples, n_feats = x_train.shape
    print("Number of features : ", n_feats)
    print("Glorot init : ", 2.0 / (n_feats + n_hidden_t_enc[-1]))
    n_targets = y_train.shape[1]

    # Set some variables
    batch_size = 128

    # Preparing folder to save stuff
    exp_name = 'basic_' + str(keep_labels) + '_sup' + \
        ('_unsup' if gamma > 0 else '')
    save_path = os.path.join(save_path, dataset, exp_name)
    save_copy = os.path.join(save_copy, dataset, exp_name)
    if not os.path.exists(save_path):
        os.makedirs(save_path)

    # Prepare Theano variables for inputs and targets
    input_var_sup = T.matrix('input_sup')
    target_var_sup = T.matrix('target_sup')
    lr = theano.shared(np.float32(learning_rate), 'learning_rate')

    # Build model
    print("Building model")

    # Supervised network
    discrim_net = InputLayer((batch_size, n_feats), input_var_sup)
    discrim_net = DenseLayer(discrim_net, num_units=n_hidden_t_enc[-1],
                             nonlinearity=rectify)

    # Reconstruct the input using dec_feat_emb
    if gamma > 0:
        reconst_net = DenseLayer(discrim_net, num_units=n_feats)

    # Predict labels
    for hid in n_hidden_s:
        discrim_net = DropoutLayer(discrim_net)
        discrim_net = DenseLayer(discrim_net, num_units=hid)

    assert disc_nonlinearity in ["sigmoid", "linear", "rectify", "softmax"]
    discrim_net = DropoutLayer(discrim_net)
    discrim_net = DenseLayer(discrim_net, num_units=n_targets,
                             nonlinearity=eval(disc_nonlinearity))

    print("Building and compiling training functions")
    # Some variables
    loss_sup = 0
    loss_sup_det = 0

    # Build and compile training functions
    prediction = lasagne.layers.get_output(discrim_net)
    prediction_det = lasagne.layers.get_output(discrim_net,
                                               deterministic=True)

    # Supervised loss
    if disc_nonlinearity == "sigmoid":
        loss_sup = lasagne.objectives.binary_crossentropy(
            prediction, target_var_sup)
        loss_sup_det = lasagne.objectives.binary_crossentropy(
            prediction_det, target_var_sup)
    elif disc_nonlinearity == "softmax":
        loss_sup = lasagne.objectives.categorical_crossentropy(prediction,
                                                               target_var_sup)
        loss_sup_det = lasagne.objectives.categorical_crossentropy(
            prediction_det, target_var_sup)
    elif disc_nonlinearity in ["linear", "rectify"]:
        loss_sup = lasagne.objectives.squared_error(
            prediction, target_var_sup)
        loss_sup_det = lasagne.objectives.squared_error(
            prediction_det, target_var_sup)
    else:
        raise ValueError("Unsupported non-linearity")

    # If some labels are missing, mask the appropriate losses before taking
    # the mean.
    if keep_labels < 1.0:
        mask = T.neq(target_var_sup, missing_labels_val)
        scale_factor = 1.0 / mask.mean()
        loss_sup = (loss_sup * mask) * scale_factor
        loss_sup_det = (loss_sup_det * mask) * scale_factor
    loss_sup = loss_sup.mean()
    loss_sup_det = loss_sup_det.mean()

    inputs = [input_var_sup, target_var_sup]

    # Unsupervised reconstruction loss
    if gamma > 0:
        reconstruction = lasagne.layers.get_output(reconst_net)
        reconstruction_det = lasagne.layers.get_output(reconst_net,
                                                       deterministic=True)
        reconst_loss = lasagne.objectives.squared_error(
            reconstruction,
            input_var_sup).mean()
        reconst_loss_det = lasagne.objectives.squared_error(
            reconstruction_det,
            input_var_sup).mean()
        nets = [discrim_net, reconst_net]

        loss = loss_sup + gamma*reconst_loss
        loss_det = loss_sup_det + gamma*reconst_loss_det
    else:
        nets = [discrim_net]
        loss = loss_sup
        loss_det = loss_sup_det

    params = lasagne.layers.get_all_params(nets, trainable=True)

    # Compute network updates
    updates = lasagne.updates.rmsprop(loss,
                                      params,
                                      learning_rate=lr)
    # updates = lasagne.updates.sgd(loss,
    #                               params,
    #                               learning_rate=lr)
    # updates = lasagne.updates.momentum(loss, params,
    #                                    learning_rate=lr, momentum=0.0)

    # Apply norm constraints on the weights
    for k in updates.keys():
        if updates[k].ndim == 2:
            updates[k] = lasagne.updates.norm_constraint(updates[k], 1.0)

    # Compile training function
    train_fn = theano.function(inputs, loss, updates=updates,
                               on_unused_input='ignore')

    # Expressions required for test
    monitor_labels = ["total_loss_det", "loss_sup_det"]
    monitor_labels += ["recon. loss"] if gamma > 0 else []
    val_outputs = [loss_det, loss_sup_det]
    val_outputs += [reconst_loss_det] if gamma > 0 else []

    if disc_nonlinearity in ["sigmoid", "softmax"]:
        if disc_nonlinearity == "sigmoid":
            test_pred = T.gt(prediction_det, 0.5)
            test_acc = T.mean(T.eq(test_pred, target_var_sup),
                              dtype=theano.config.floatX) * 100.

        elif disc_nonlinearity == "softmax":
            test_pred = prediction_det.argmax(1)
            test_acc = T.mean(T.eq(test_pred, target_var_sup.argmax(1)),
                              dtype=theano.config.floatX) * 100

        monitor_labels.append("accuracy")
        val_outputs.append(test_acc)

    # Compile prediction function
    predict = theano.function([input_var_sup], test_pred)

    # Compile validation function
    val_fn = theano.function(inputs,
                             [prediction_det] + val_outputs,
                             on_unused_input='ignore')

    # Finally, launch the training loop.
    print("Starting training...")

    # Some variables
    max_patience = 100
    patience = 0

    train_loss = []
    train_loss_sup = []
    train_reconst_loss = []
    train_acc = []
    valid_loss = []
    valid_loss_sup = []
    valid_reconst_loss = []
    valid_acc = []

    # Pre-training monitoring
    print("Epoch 0 of {}".format(num_epochs))

    train_minibatches = iterate_minibatches(x_train, y_train,
                                            batch_size, shuffle=False)
    train_err = monitoring(train_minibatches, "train", val_fn, monitor_labels,
                           prec_recall_cutoff)

    valid_minibatches = iterate_minibatches(x_valid, y_valid,
                                            batch_size, shuffle=False)
    valid_err = monitoring(valid_minibatches, "valid", val_fn, monitor_labels,
                           prec_recall_cutoff)

    # Training loop
    start_training = time.time()
    for epoch in range(num_epochs):
        start_time = time.time()
        print("Epoch {} of {}".format(epoch+1, num_epochs))
        nb_minibatches = 0
        loss_epoch = 0

        # Train pass
        for batch in iterate_minibatches(x_train, training_labels,
                                         batch_size,
                                         shuffle=True):
            loss_epoch += train_fn(*batch)
            nb_minibatches += 1

        # Monitoring on the training set
        train_minibatches = iterate_minibatches(x_train, y_train,
                                                batch_size, shuffle=False)
        train_err = monitoring(train_minibatches, "train", val_fn,
                               monitor_labels, prec_recall_cutoff)

        train_loss += [train_err[0]]
        train_loss_sup += [train_err[1]]
        train_acc += [train_err[3] if gamma > 0 else train_err[2]]
        if gamma > 0:
            train_reconst_loss += [train_err[2]]

        # Monitoring on the validation set
        valid_minibatches = iterate_minibatches(x_valid, y_valid,
                                                batch_size, shuffle=False)

        valid_err = monitoring(valid_minibatches, "valid", val_fn,
                               monitor_labels, prec_recall_cutoff)
        valid_loss += [valid_err[0]]
        valid_loss_sup += [valid_err[1]]
        valid_acc += [valid_err[3] if gamma > 0 else valid_err[2]]
        if gamma > 0:
            valid_reconst_loss += [valid_err[2]]

        # Early stopping
        if epoch == 0:
            best_valid = valid_loss[epoch]
        elif valid_loss[epoch] < best_valid:
            best_valid = valid_loss[epoch]
            patience = 0

            # Save stuff
            np.savez(save_path+'/model_feat_sel.npz',
                     *lasagne.layers.get_all_param_values(nets))
            np.savez(save_path + "/errors_supervised.npz",
                     train_loss, train_loss_sup, train_acc, train_reconst_loss,
                     valid_loss, valid_loss_sup, valid_acc, valid_reconst_loss)
        else:
            patience += 1

        # End training
        if patience == max_patience or epoch == num_epochs-1:
            print("Ending training")
            # Load best model
            if not os.path.exists(save_path + '/model_feat_sel.npz'):
                print("No saved model to be tested and/or generate"
                      " the embedding !")
            else:
                with np.load(save_path + '/model_feat_sel.npz',) as f:
                    param_values = [f['arr_%d' % i]
                                    for i in range(len(f.files))]
                    nlayers = len(lasagne.layers.get_all_params(nets))
                    lasagne.layers.set_all_param_values(nets,
                                                        param_values[:nlayers])
            # Test
            if y_test is not None:
                test_minibatches = iterate_minibatches(x_test, y_test,
                                                       batch_size,
                                                       shuffle=False)

                test_err = monitoring(test_minibatches, "test", val_fn,
                                      monitor_labels, prec_recall_cutoff)
            else:
                for minibatch in iterate_testbatches(x_test,
                                                     batch_size,
                                                     shuffle=False):
                    test_predictions = []
                    test_predictions += [predict(minibatch)]
                np.savez(save_path+'/test_predictions.npz', test_predictions)

            # Stop
            print("  epoch time:\t\t\t{:.3f}s \n".format(time.time() -
                                                         start_time))
            break

        print("  epoch time:\t\t\t{:.3f}s \n".format(time.time() - start_time))

        # Anneal the learning rate
        lr.set_value(float(lr.get_value() * learning_rate_annealing))

    # Print all final errors for train, validation and test
    print("Training time:\t\t\t{:.3f}s".format(time.time() - start_training))

    # Copy files to loadpath
    if save_path != save_copy:
        print('Copying model and other training files to {}'.format(save_copy))
        copy_tree(save_path, save_copy)


def parse_int_list_arg(arg):
    if isinstance(arg, str):
        arg = eval(arg)

    if isinstance(arg, list):
        return arg
    if isinstance(arg, int):
        return [arg]
    else:
        raise ValueError("Following arg value could not be cast as a list of"
                         "integer values : " % arg)


def main():
    parser = argparse.ArgumentParser(description="""Implementation of the
                                     feature selection v2""")
    parser.add_argument('--dataset',
                        default='1000_genomes',
                        help='Dataset.')
    parser.add_argument('--n_hidden_t_enc',
                        default=[100],
                        help='List of theta transformation hidden units.')
    parser.add_argument('--n_hidden_s',
                        default=[100],
                        help='List of supervised hidden units.')
    parser.add_argument('--num_epochs',
                        '-ne',
                        type=int,
                        default=500,
                        help='Int to indicate the max number of epochs.')
    parser.add_argument('--learning_rate',
                        '-lr',
                        type=float,
                        default=0.000001,
                        help='Float to indicate learning rate.')
    parser.add_argument('--learning_rate_annealing',
                        '-lra',
                        type=float,
                        default=.99,
                        help='Float to indicate learning rate annealing rate.')
    parser.add_argument('--gamma',
                        '-g',
                        type=float,
                        default=0.,
                        help='reconst_loss coeff.')
    parser.add_argument('--disc_nonlinearity',
                        '-nl',
                        default="softmax",
                        help='Nonlinearity to use in disc_net last layer')
    parser.add_argument('--keep_labels',
                        type=float,
                        default=1.0,
                        help='Fraction of training labels to keep')
    parser.add_argument('--prec_recall_cutoff',
                        type=int,
                        help='Whether to compute the precision-recall cutoff' +
                             'or not')
    parser.add_argument('--save_tmp',
                        default='/Tmp/'+ os.environ["USER"]+'/feature_selection/',
                        help='Path to save results.')
    parser.add_argument('--save_perm',
                        default='/data/lisatmp4/'+ os.environ["USER"]+'/feature_selection/',
                        help='Path to save results.')
    parser.add_argument('--dataset_path',
                        default='/data/lisatmp4/romerosa/datasets/',
                        help='Path to dataset')

    args = parser.parse_args()
    print ("Printing args")
    print (args)

    execute(args.dataset,
            parse_int_list_arg(args.n_hidden_t_enc),
            parse_int_list_arg(args.n_hidden_s),
            int(args.num_epochs),
            args.learning_rate,
            args.learning_rate_annealing,
            args.gamma,
            args.disc_nonlinearity,
            args.keep_labels,
            args.prec_recall_cutoff != 0, -1,
            args.save_tmp,
            args.save_perm,
            args.dataset_path)


if __name__ == '__main__':
    main()