import numpy as np
import os
import warnings
from util import load_states
from util import load_controls
from util import log_init
from util import load_files
from classifiers import RecurrentClassifier
from classifiers import Classifier


def main():

    # Number of datasets
    n = 13
    n_impulse_2000 = 5
    # RNN on top of LBN
    recurrent = False

    # Only for NO recurrent
    feet_learning = True
    feet_min = 50
    feet_max = 100

    assert not (
        feet_learning and recurrent), "Feet learning and recurrent cannot be true at the same time"

    # Load data
    seq_len = 61

    y = load_controls(n)
    if n_impulse_2000 > 0:
        y_impulse = load_files(n_impulse_2000, 'controls_impulse_2000')
        y = np.vstack((y, y_impulse))
    muy = np.mean(y, axis=0)
    stdy = np.std(y, axis=0)
    stdy[stdy == 0] = 1.

    if feet_learning:
        feet_idx = np.arange(y.shape[0])
        feet_idx = feet_idx[np.any(np.logical_and(
            np.abs(y[:, 6:16]) >= feet_min, np.abs(y[:, 6:16]) < feet_max), axis=1)]
        y = y[feet_idx, :]

    train_size = 0.8

    y = (y - muy) * 1. / stdy
    if recurrent:
        y = y.reshape(seq_len, -1, y.shape[1])
        idx = np.random.permutation(y.shape[1])

        y = y[:, idx, :-4]
        train_bucket = int(np.ceil(y.shape[1] * train_size))
        y_train = y[:, :train_bucket]
        y_test = y[:, train_bucket:]

    else:
        idx = np.random.permutation(y.shape[0])
        y = y[idx, :-4]
        train_bucket = int(np.ceil(y.shape[0] * train_size))
        y_train = y[:train_bucket]
        y_test = y[train_bucket:]

    x = load_states(n)
    if n_impulse_2000 > 0:
        x_impulse = load_files(n_impulse_2000, 'states_impulse_2000')
        x = np.vstack((x, x_impulse))

    mux = np.mean(x, axis=0)
    stdx = np.std(x, axis=0)
    stdx[stdx == 0] = 1.

    if feet_learning:

        x = x[feet_idx, :]

    x = (x - mux) * 1. / stdx
    if recurrent:
        x = x.reshape(seq_len, -1, x.shape[1])

        cols = [1] + list(range(3, x.shape[2]))
        x = x[:, :, cols]
        x = x[:, idx, :]

        x_train = x[:, :train_bucket]
        x_test = x[:, train_bucket:]
        n_in = x.shape[2]
        n_out = y.shape[2]
    else:

        cols = [1] + list(range(3, x.shape[1]))
        x = x[:, cols]
        x = x[idx]
        x_train = x[:train_bucket]
        x_test = x[train_bucket:]
        n_in = x.shape[1]
        n_out = y.shape[1]

    # MLP definition
    mlp_activation_names = ['sigmoid']
    mlp_n_in = 13
    mlp_n_hidden = [10]

    # LBN definition
    lbn_n_hidden = [150]  # , 100, 50]
    det_activations = ['linear', 'linear']  # , 'linear', 'linear']
    stoch_activations = ['sigmoid', 'sigmoid']
    likelihood_precision = 0.1
    m = 10

    # RNN definiton + LBN n_out if RNN is the final layer
    rnn_type = "LSTM"
    rnn_hidden = [30]
    rnn_activations = [['sigmoid', 'tanh', 'sigmoid',
                        'sigmoid', 'tanh'], 'linear']  # ['sigmoid', 'linear']
    lbn_n_out = 50
    noise_type = 'multiplicative'

    # Fit options
    b_size = 100
    epoch0 = 1001
    n_epochs = 300
    lr = .1
    save_every = 10  # Log saving
    chunk_size = 2000  # Memory chunks
    batch_normalization = False  # TODO FOR RECURRENT CLASSIFIER!

    # Optimizer
    opt_type = 'SGD'
    method = {'type': opt_type, 'lr_decay_schedule': 'constant',
              'lr_decay_parameters': [lr],
              'momentum_type': 'nesterov', 'momentum': 0.01, 'b1': 0.9,
              'b2': 0.999, 'epsilon': 1e-8, 'rho': 0.99,
              'learning_rate': lr}

    # Load from file?
    load_from_file = True
    session_name = None
    load_different_file = True

    assert not (load_different_file and not load_from_file), "You have set load different_file to True but you are not loading any network!"

    # Saving options
    network_name = "{0}_n_{1}_n_impulse_2000_{2}_mlp_hidden_[{3}]_mlp_activation_[{4}]"\
                   "_lbn_n_hidden_[{5}]_det_activations_[{6}]_stoch"\
                   "_activations_[{7}]_m_{8}_noise_type_{9}_bsize_{10}"\
                   "_method_{11}_bn_{12}".\
                   format(
                       'recurrentclassifier_{0}'.format(rnn_type) if recurrent
                       else 'classifier',
                       n, n_impulse_2000,
                       ','.join(str(e) for e in mlp_n_hidden),
                       ','.join(str(e) for e in mlp_activation_names),
                       ','.join(str(e) for e in lbn_n_hidden),
                       ','.join(str(e) for e in det_activations),
                       ','.join(str(e) for e in stoch_activations),
                       m, noise_type, b_size, method['type'], batch_normalization)

    opath = "network_output/{0}".format(network_name)
    if not os.path.exists(opath):
        os.makedirs(opath)

    fname = '{0}/{1}_lbn_n_hidden_[{2}]'.format(opath,
                                                'recurrentclassifier_{0}'.format(rnn_type) if recurrent
                                                else 'classifier', ','.join(str(e) for e in lbn_n_hidden))

    loaded_network_fname = '{0}/networks/{1}_lbn_n_hidden_[{2}]'.format(opath,
                                                                        'recurrentclassifier_{0}'.format(rnn_type) if recurrent
                                                                        else 'classifier', ','.join(str(e) for e in lbn_n_hidden))
    if load_different_file:
        warnings.warn(
            "CAUTION: loading log and network from different path than the saving path")

        loaded_network_folder = "{0}_n_{1}_n_impulse_2000_0_mlp_hidden_[{3}]_mlp_activation_[{4}]"\
            "_lbn_n_hidden_[{5}]_det_activations_[{6}]_stoch"\
            "_activations_[{7}]_m_{8}_noise_type_{9}_bsize_{10}"\
            "_method_SGD_bn_False".\
            format(
                'recurrentclassifier_{0}'.format(rnn_type) if recurrent
                else 'classifier',
                n, n_impulse_2000,
                ','.join(str(e) for e in mlp_n_hidden),
                ','.join(str(e) for e in mlp_activation_names),
                ','.join(str(e) for e in lbn_n_hidden),
                ','.join(str(e) for e in det_activations),
                ','.join(str(e) for e in stoch_activations),
                m, noise_type, b_size, method['type'], batch_normalization)
        loaded_opath = "network_output/{0}".format(loaded_network_folder)
        assert os.path.exists(
            loaded_opath), "Trying to load a network for non existing path: {0}".format(loaded_opath)

        loaded_network_name = "classifier_lbn_n_hidden_[150]"

        loaded_network_fname = '{0}/networks/{1}'.format(
            loaded_opath, loaded_network_name)

    else:
        loaded_opath = opath

    # LOGGING
    log, session_name = log_init(
        opath, session_name=session_name if load_from_file else None)

    if feet_learning:
        log.info("Using feet learning.\nFeet min: {0}\nFeet max: {1}".format(
            feet_min, feet_max))

    # Building network
    if recurrent:
        if load_from_file:

            c = RecurrentClassifier.init_from_file(
                '{0}_epoch_{1}.json'.format(loaded_network_fname, epoch0 - 1),
                log=log)
        else:
            c = RecurrentClassifier(n_in, n_out, mlp_n_in, mlp_n_hidden,
                                    mlp_activation_names, lbn_n_hidden,
                                    lbn_n_out, det_activations,
                                    stoch_activations,
                                    likelihood_precision, rnn_hidden,
                                    rnn_activations, rnn_type,
                                    log=log, noise_type=noise_type)

    else:
        if load_from_file:

            c = Classifier.init_from_file(
                '{0}_epoch_{1}.json'.format(loaded_network_fname, epoch0 - 1),
                log=log)
        else:
            c = Classifier(n_in, n_out, mlp_n_in, mlp_n_hidden,
                           mlp_activation_names, lbn_n_hidden,
                           det_activations,
                           stoch_activations, log=log,
                           likelihood_precision=likelihood_precision,
                           batch_normalization=batch_normalization)

    if load_from_file:
        log.info("Network loaded from file: {0}".format(loaded_network_fname))

    # Training
    c.fit(x_train, y_train, m, n_epochs, b_size, method, fname=fname,
          x_test=x_test, y_test=y_test,
          epoch0=epoch0, chunk_size=chunk_size,
          save_every=save_every, sample_axis=1 if recurrent else 0)


if __name__ == '__main__':
    main()
