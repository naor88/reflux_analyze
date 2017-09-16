import json
import os

import gc

from random import randint

import time

from cv2.cv2 import CV_64F
import keras.backend as K
import numpy as np
from keras.callbacks import ModelCheckpoint, LambdaCallback
from keras.layers import Conv2D, Convolution2D
from keras.optimizers import SGD
from sklearn.model_selection import train_test_split
from sklearn.utils import shuffle
from sklearn.metrics import confusion_matrix
from PIL import Image
from keras.utils import np_utils
from keras.layers.convolutional import MaxPooling2D
from keras.layers.core import Dense, Dropout, Activation, Flatten
from keras.models import Sequential, save_model, load_model
# from skimage.filters import gabor_kernel
import cv2
from theano import shared

from manage import ROOT_DIR
from utils.prepare_dataset import reshape_images


def calculate_score(confusion_matrix):
    tn, fp, fn, tp = confusion_matrix
    _recall = float(tp) / (tp + fn)
    _precision = float(tp) / (tp+fp)
    return float(2) / ((float(1) / _recall) + (float(1) / _precision))


class CNN(object):
    def __init__(self, params, reload=False):
        self.model_name = params['model_name']
        self.model_path = os.path.join(ROOT_DIR, 'cnn_models', self.model_name)
        # the original data set
        self.input_dataset_path = os.path.join(ROOT_DIR, 'dataset')
        # the deep learning model
        self.model = None
        self.split_cases = True
        if reload:
            self._load()
        else:
            self.img_rows = int(params.get('img_rows', 200))
            self.img_cols = int(params.get('img_cols', 200))
            self.nb_channel = int(params.get('nb_channel', 3))
            self.batch_size = int(params.get('batch_size', 32))
            self.epoch = int(params.get('epoch', 5))
            # number of convolution filter to use
            self.nb_filters = int(params.get('nb_filters', 32))

            # size of pooling area for max pooling
            self.pool_size = params.get('pool_size', (2, 2))
            if isinstance(self.pool_size, unicode):
                self.pool_size = int(self.pool_size)
            if isinstance(self.pool_size, int):
                self.pool_size = (self.pool_size, self.pool_size)

            # convolution kernel size
            self.kernel_size = params.get('kernel_size', (3, 3))
            if isinstance(self.kernel_size, unicode):
                self.kernel_size = int(self.kernel_size)
            if isinstance(self.kernel_size, int):
                self.kernel_size = (self.kernel_size, self.kernel_size)

            self.dropout = params.get('dropout', 0.5)
            self.activation_function = params.get('activation_function', 'softmax')  # 'sigmoid'
            self.con_mat_val = []
            self.con_mat_train = []
            # History of the training
            self.hist = None
            self.category = []
            self.total_train_epoch = 0
            self.done_train_epoch = 0

            # the data set for train and validation
            self.X_train = None
            self.X_test = None
            self.y_train = None
            self.y_test = None

            self._build_model_2()

        self.total_train_epoch = 0
        self.done_train_epoch = 0

    def load_data_set_split_cases(self):
        # the data set after resize
        self.adaptation_dataset = os.path.join(ROOT_DIR, self.input_dataset_path + '_' + str(self.img_rows) + 'X' + str(
            self.img_cols) + '_adaptation')

        # create adaption dataset if not exist
        if not os.path.exists(self.adaptation_dataset):
            reshape_images(self.input_dataset_path, self.adaptation_dataset, self.img_rows, self.img_cols)
        # global nb_classes, X_train, X_test, y_train, y_test
        # get the categories according to the folder
        self.category = os.listdir(self.adaptation_dataset)
        # create matrix to store all images flatten
        train_img_matrix = []
        train_label = []
        test_img_matrix = []
        test_label = []
        for idx, category in enumerate(self.category):
            category_path = os.path.join(self.adaptation_dataset, category)
            case_folder = os.listdir(category_path)
            for sub_folder in case_folder[:int(len(case_folder)*0.5)]:
                case_folder_path = os.path.join(self.adaptation_dataset, category, sub_folder)
                images = os.listdir(case_folder_path)
                for im in images:
                    im_path = os.path.join(case_folder_path, im)
                    test_img_matrix.append(np.array(np.array(Image.open(im_path)).flatten()))
                    test_label.append(idx)
            for sub_folder in case_folder[int(len(case_folder)*0.5):]:
                case_folder_path = os.path.join(self.adaptation_dataset, category, sub_folder)
                images = os.listdir(case_folder_path)
                for im in images:
                    im_path = os.path.join(case_folder_path, im)
                    train_img_matrix.append(np.array(np.array(Image.open(im_path)).flatten()))
                    train_label.append(idx)

        train_img_matrix = np.array(train_img_matrix)
        train_label = np.array(train_label)
        test_img_matrix = np.array(test_img_matrix)
        test_label = np.array(test_label)

        del images
        gc.collect()
        # random_state for psudo random
        # the data set load, shuffled and split between train and validation sets
        train_img_matrix, train_label = shuffle(train_img_matrix, train_label, random_state=7)
        test_img_matrix, test_label = shuffle(test_img_matrix, test_label, random_state=7)

        self.X_train = train_img_matrix
        self.y_train = train_label
        self.X_test = test_img_matrix
        self.y_test = test_label

        # reshape the data
        self.X_train = self.X_train.reshape(self.X_train.shape[0], self.nb_channel, self.img_rows, self.img_cols)
        self.X_test = self.X_test.reshape(self.X_test.shape[0], self.nb_channel, self.img_rows, self.img_cols)

        self.X_train = self.X_train.astype('float32')
        self.X_test = self.X_test.astype('float32')

        # help for faster convert
        self.X_train /= 255
        self.X_test /= 255

        # convert class vectore to binary class matrices
        self.y_train = np_utils.to_categorical(self.y_train, len(self.category))
        self.y_test = np_utils.to_categorical(self.y_test, len(self.category))

    def load_data_set(self):
        '''
        this method initialize the (X_train,y_train)(X_val, y_val) where X is the data and y is the label
        :return:
        '''
        # the data set after resize
        self.adaptation_dataset = os.path.join(ROOT_DIR, self.input_dataset_path + '_' + str(self.img_rows) + 'X' + str(self.img_cols) + '_adaptation')

        # create adaption dataset if not exist
        if not os.path.exists(self.adaptation_dataset):
            reshape_images(self.input_dataset_path, self.adaptation_dataset, self.img_rows, self.img_cols)
        # global nb_classes, X_train, X_test, y_train, y_test
        # get the categories according to the folder
        self.category = os.listdir(self.adaptation_dataset)
        # create matrix to store all images flatten
        img_matrix = []
        label = []
        for idx, category in enumerate(self.category):
            category_path = os.path.join(self.adaptation_dataset, category)
            sub_folders = os.listdir(category_path)
            for sub_folder in sub_folders:
                case_folder_path = os.path.join(self.adaptation_dataset, category, sub_folder)
                images = os.listdir(case_folder_path)
                for im in images:
                    im_path = os.path.join(case_folder_path, im)
                    img_matrix.append(np.array(np.array(Image.open(im_path)).flatten()))
                    label.append(idx)

        img_matrix = np.array(img_matrix)
        label = np.array(label)

        del images

        gc.collect()
        # random_state for psudo random
        # the data set load, shuffled and split between train and validation sets
        data, label = shuffle(img_matrix, label, random_state=7) #random_state=2
        self.X_train, self.X_test, self.y_train, self.y_test = train_test_split(data, label, test_size=0.2, random_state=7)

        # reshape the data
        self.X_train = self.X_train.reshape(self.X_train.shape[0], self.nb_channel, self.img_rows, self.img_cols)
        self.X_test = self.X_test.reshape(self.X_test.shape[0], self.nb_channel, self.img_rows, self.img_cols)

        self.X_train = self.X_train.astype('float32')
        self.X_test = self.X_test.astype('float32')

        # help for faster convert
        self.X_train /= 255
        self.X_test /= 255

        # convert class vectore to binary class matrices
        self.y_train = np_utils.to_categorical(self.y_train, len(self.category))
        self.y_test = np_utils.to_categorical(self.y_test, len(self.category))

        # print('X_train shape: ', self.X_train.shape)
        # print(self.X_train.shape[0], 'train example')
        # print(self.X_test.shape[0], 'validation example')

    def _build_model(self):
        self.model = Sequential()

        # Layer 1
        self.model.add(Conv2D(filters=self.nb_filters,
                              kernel_size=self.kernel_size,
                              padding='same',
                              input_shape=(self.nb_channel, self.img_rows, self.img_cols)))

        self.model.add(Activation('relu'))
        self.model.add(MaxPooling2D(pool_size=self.pool_size))

        # Layer 2
        self.model.add(Conv2D(filters=self.nb_filters, kernel_size=self.kernel_size, padding='same'))
        self.model.add(Activation('relu'))
        self.model.add(MaxPooling2D(pool_size=self.pool_size))

        # Layer 3
        self.model.add(Conv2D(filters=self.nb_filters, kernel_size=self.kernel_size, padding='same'))
        self.model.add(Activation('relu'))
        self.model.add(MaxPooling2D(pool_size=self.pool_size))

        self.model.add(Dropout(self.dropout))
        self.model.add(Flatten())
        self.model.add(Dense(64))
        self.model.add(Activation('relu'))
        self.model.add(Dropout(0.5))

        self.model.add(Dense(len(self.category)))
        self.model.add(Activation(self.activation_function))

        # rsm = optimizers.RMSprop(lr=0.001, rho=0.9, epsilon=1e-08, decay=0.0)
        sgd = SGD(lr=0.1, decay=1e-6, momentum=0.9, nesterov=True)
        # binary_accuracy, categorical_accuracy
        self.model.compile(loss='binary_crossentropy', optimizer=sgd, metrics=['accuracy'])  # 'adam'

    def _build_model_2(self):
        def custom_gabor(shape, dtype=None):
            total_ker = []
            for i in xrange(shape[0]):
                kernels = []
                for j in xrange(shape[1]):
                    # gk = gabor_kernel(frequency=0.2, bandwidth=0.1)
                    tmp_filter = cv2.getGaborKernel(ksize=(shape[3], shape[2]), sigma=1, theta=1, lambd=0.5, gamma=0.3,
                                                    psi=(3.14) * 0.5,
                                                    ktype=CV_64F)
                    filter = []
                    for row in tmp_filter:
                        filter.append(np.delete(row, -1))
                    kernels.append(filter)
                    # gk.real
                total_ker.append(kernels)
            np_tot = shared(np.array(total_ker))
            return K.variable(np_tot, dtype=dtype)

        self.with_gabor = True


        # the data set load, shuffled and split between train and validation sets
        self.model = Sequential()

        # Layer 1
        self.model.add(Convolution2D(self.nb_filters, self.kernel_size,
                                     kernel_initializer=custom_gabor,
                                     input_shape=(self.nb_channel, self.img_rows, self.img_cols)))

        self.model.add(Activation('relu'))
        self.model.add(MaxPooling2D(pool_size=self.pool_size))

        # Layer 2
        self.model.add(Convolution2D(self.nb_filters, self.kernel_size))  # kernel_initializer=custom_gabor))
        self.model.add(Activation('relu'))
        self.model.add(MaxPooling2D(pool_size=self.pool_size))

        # Layer 3
        # self.model.add(Convolution2D(self.nb_filters, self.kernel_size))  # , kernel_initializer=custom_gabor,))
        # self.model.add(Activation('relu'))
        # self.model.add(MaxPooling2D(pool_size=self.pool_size))

        self.model.add(Dropout(0.5))
        self.model.add(Flatten())
        self.model.add(Dense(64))
        self.model.add(Activation('relu'))
        self.model.add(Dropout(0.5))

        self.model.add(Dense(2))  # len(self.category)
        self.model.add(Activation('softmax'))  # 'sigmoid'

        # rsm = optimizers.RMSprop(lr=0.001, rho=0.9, epsilon=1e-08, decay=0.0)

        # binary_accuracy, categorical_accuracy
        self.model.compile(loss='binary_crossentropy', optimizer='adam', metrics=['accuracy'])

    def save_only_best(self, epoch=None, logs=None):
        scores = [calculate_score(item) for item in self.con_mat_val]
        last_biggest = True
        for i in xrange(len(scores)):
            if scores[i] > scores[-1]:
                last_biggest = False
                break
        if last_biggest:
            print 'find best model and save it.'
            self.save()

    def _calculate_confusion_matrix(self, epoch=None, logs=None):
        # For test set
        y_pred = self.model.predict_classes(self.X_test)
        # y_pred = [0 if p[0] > p[1] else 1 for p in y_pred]
        tn, fp, fn, tp = confusion_matrix(np.argmax(self.y_test, axis=1), y_pred).ravel()
        self.con_mat_val.append([tn, fp, fn, tp])

        # For train set
        y_pred = self.model.predict_classes(self.X_train)
        # y_pred = [0 if p[0] > p[1] else 1 for p in y_pred]
        tn, fp, fn, tp = confusion_matrix(np.argmax(self.y_train, axis=1), y_pred).ravel()
        self.con_mat_train.append([tn, fp, fn, tp])

        # print confusion_matrix(np.argmax(self.y_test, axis=1), y_pred)
        self.done_train_epoch += 1
        # self.save(only_json=True)



    def train_model(self, n_epoch=None):
        '''
            saves the model weights after each epoch if the validation loss decreased
        '''
        if not hasattr(self, 'X_train') or self.X_train is None:
            if self.split_cases:
                self.load_data_set_split_cases()
            else:
                self.load_data_set()

        self.total_train_epoch = n_epoch
        # check_pointer_best = ModelCheckpoint(filepath=self.model_path + '.h5(best)', verbose=1, save_best_only=True)
        # check_pointer = ModelCheckpoint(filepath=self.model_path + '.h5', verbose=1)
        _confusion_matrix = LambdaCallback(on_epoch_end=lambda epoch, logs: self._calculate_confusion_matrix(epoch, logs))
        _save_only_best = LambdaCallback(on_epoch_end=lambda epoch, logs: self.save_only_best(epoch, logs))
        self.hist = self.model.fit(self.X_train,
                                   self.y_train,
                                   batch_size=self.batch_size,
                                   epochs=n_epoch,
                                   verbose=1,
                                   validation_data=(self.X_test, self.y_test),
                                   callbacks=[_confusion_matrix, _save_only_best])  # check_pointer, check_pointer_best

        # load to self.model the best model
        self._load()

    def save(self, only_json=False):
        if self.with_gabor:
            self.model.save_weights(self.model_path + '.h5(weights)')
        elif not only_json:
            self.model.save(self.model_path + '.h5')
        save_dict = self.get_info()
        with open(self.model_path+'.json', 'wb') as output:
            output.write(json.dumps(save_dict))

    def _load(self):
        with open(self.model_path+'.json', 'rb') as _input:
            # tmp = pickle.load(input)
            tmp = json.loads(_input.read())
        self.__dict__.update(tmp)
        if self.with_gabor:
            self._build_model_2()
            self.model.load_weights(self.model_path + '.h5(weights)')
        elif os.path.exists(self.model_path + '.h5(best)'):
            self.model = load_model(self.model_path + '.h5(best)')
        else:
            self.model = load_model(self.model_path + '.h5')

    def predict(self, frame):
        img = Image.open(frame)
        if img.size != (self.img_cols, self.img_rows):
            raise Exception('Image Size Don\'t Matching.')
        frame = np.array(np.array(img).flatten())
        frame = frame.reshape(1, self.nb_channel, self.img_rows, self.img_cols)
        pred = self.model.predict(frame, batch_size=1)
        return self.category[0] if pred[0][0] > pred[0][1] else self.category[1]

    def get_random_frame(self):
        categories = os.listdir(self.adaptation_dataset)
        category = randint(0, len(self.category))
        category_path = os.path.join(self.adaptation_dataset, categories[category])
        cases = os.listdir(category_path)
        case_index = randint(0, len(cases)-1)
        frames = os.listdir(os.path.join(category_path, cases[case_index]))
        frame_index = randint(0, len(frames)-1)
        random_frame = os.path.join(category_path, cases[case_index], frames[frame_index])
        return random_frame, category

    def get_info(self):
        return {
            "category": self.category,
            "nb_channel": self.nb_channel,
            "activation_function": self.activation_function,
            "dropout": self.dropout,
            "nb_filters": self.nb_filters,
            "pool_size": self.pool_size,
            "hist": self.hist,
            "img_rows": self.img_rows,
            "img_cols": self.img_cols,
            "batch_size": self.batch_size,
            "con_mat_train": self.con_mat_train,
            "con_mat_val": self.con_mat_val,
            "model_name": self.model_name,
            "kernel_size": self.kernel_size,
            "total_train_epoch": self.total_train_epoch,
            "done_train_epoch": self.done_train_epoch,
            "with_gabor": self.with_gabor
        }

    def create_model_svg(self):
        # from IPython.display import SVG
        from keras.utils.vis_utils import model_to_dot

        # SVG(model_to_dot(model).create(prog='dot', format='svg'))
        svg_res = model_to_dot(self.model).create(prog='dot', format='svg')
        with open(self.model_path+'.svg','w') as _f:
            _f.write(svg_res)
