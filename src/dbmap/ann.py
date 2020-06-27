#####################################
# NMSLIB approximate-nearest neighbors sklearn wrapper
# NMSLIB: https://github.com/nmslib/nmslib
# Wrapper author: Davi Sidarta-Oliveira
# School of Medical Sciences,University of Campinas,Brazil
# contact: davisidarta@gmail.com
######################################

import time
import sys
import numpy as np
from sklearn.base import TransformerMixin, BaseEstimator
from scipy.sparse import csr_matrix, find, issparse
from sklearn.neighbors import NearestNeighbors
from sklearn.model_selection import train_test_split
try:
    import nmslib
except ImportError:
    print("The package 'nmslib' is required to run accelerated dbMAP. Please install it 'with pip3 install nmslib'.")
    sys.exit()


class NMSlibTransformer(TransformerMixin, BaseEstimator):
    """
    Wrapper for using nmslib as sklearn's KNeighborsTransformer. This implements
    an escalable approximate k-nearest-neighbors graph on spaces defined by nmslib.
    Read more about nmslib and its various available metrics at
    https://github.com/nmslib/nmslib.




    """

    def __init__(self,
                 n_neighbors=30,
                 metric='angular_sparse',
                 method='hnsw',
                 n_jobs=-1,
                 M=30,
                 efC=100,
                 efS=100,
                 p=None):
        """
        Initialize neighbour search parameters.
        :param n_neighbors: number of nearest-neighbors to look for. In practice,
        this should be considered the average neighborhood size and can vary depending
        on your number of samples and data intrinsic dimensionality. Reasonable values
        range from 5 to 100. Smaller values tend to lead to increased graph structure
        resolution, but users should beware that a too low value may render granulated and vaguely
        defined neighborhoods that arise as an artifact of downsampling. Larger values
        will al

         Defaults to 30.

        """

        self.n_neighbors = n_neighbors
        self.method = method
        self.metric = metric
        self.n_jobs = n_jobs
        self.M = M
        self.efC = efC
        self.efS = efS
        self.p = p
        self.space = str = {
            'sqeuclidean': 'l2',
            'euclidean': 'l2',
            'euclidean_sparse': 'l2_sparse',
            'cosine': 'cosinesimil',
            'cosine_sparse': 'cosinesimil_sparse_fast',
            'l1': 'l1',
            'l1_sparse': 'l1_sparse',
            'linf': 'linf',
            'linf_sparse': 'linf_sparse',
            'angular': 'angulardist',
            'angular_sparse': 'angulardist_sparse_fast',
            'negdotprod': 'negdotprod',
            'negdotprod_sparse': 'negdotprod_sparse_fast',
            'levenshtein': 'leven',
            'hamming': 'bit_hamming',
            'jaccard': 'bit_jaccard',
            'jaccard_sparse': 'jaccard_sparse',
            'jansen-shan': 'jsmetrfastapprox'
        }[self.metric]

    def fit(self, data):
        # see more metrics in the manual
        # https://github.com/nmslib/nmslib/tree/master/manual

        if issparse(data) == True:
            print('Sparse input. Proceding without converting...')
        if issparse(data) == False:
            print('Converting input to sparse...')
            try:
                data = data.tocsr()
            except SyntaxError:
                print("Conversion to csr failed. Please provide a numpy array or a pandas dataframe."
                      "Trying internal construction...")
                sys.exit()
            try:
                data = csr_matrix(data)
            except SyntaxError:
                print("Conversion to csr failed. Please provide a numpy array or a pandas dataframe.")

        self.n_samples_fit_ = data.shape[0]

        index_time_params = {'M': self.M, 'indexThreadQty': self.n_jobs, 'efConstruction': self.efC, 'post': 0}

        self.nmslib_ = nmslib.init(method='hnsw',
                                   space='cosinesimil_sparse_fast',
                                   data_type=nmslib.DataType.SPARSE_VECTOR)

        self.nmslib_.addDataPointBatch(data)
        start = time.time()
        self.nmslib_.createIndex(index_time_params)
        end = time.time()
        print('Index-time parameters', 'M:', self.M, 'n_threads:', self.n_jobs, 'efConstruction:', self.efC, 'post:0')
        print('Indexing time = %f (sec)' % (end - start))
        return self

    def transform(self, data):
        start = time.time()
        n_samples_transform = data.shape[0]
        query_time_params = {'efSearch': self.efS}
        print('Setting query-time parameters:', query_time_params)
        self.nmslib_.setQueryTimeParams(query_time_params)

        # For compatibility reasons, as each sample is considered as its own
        # neighbor, one extra neighbor will be computed.
        self.n_neighbors = self.n_neighbors + 1

        results = self.nmslib_.knnQueryBatch(data, k=self.n_neighbors,
                                             num_threads=self.n_jobs)

        indices, distances = zip(*results)
        indices, distances = np.vstack(indices), np.vstack(distances)

        query_qty = data.shape[0]

        if self.metric == 'sqeuclidean':
            distances **= 2

        indptr = np.arange(0, n_samples_transform * self.n_neighbors + 1,
                           self.n_neighbors)
        kneighbors_graph = csr_matrix((distances.ravel(), indices.ravel(),
                                       indptr), shape=(n_samples_transform,
                                                       self.n_samples_fit_))
        end = time.time()
        print('kNN time total=%f (sec), per query=%f (sec), per query adjusted for thread number=%f (sec)' %
              (end - start, float(end - start) / query_qty, self.n_jobs * float(end - start) / query_qty))

        return kneighbors_graph

    def test_efficiency(self, data, data_use=0.1):
        """Test that NMSlibTransformer and KNeighborsTransformer give same results
        """
        self.data_use = data_use

        query_qty = data.shape[0]

        (dismiss, test) = train_test_split(data, test_size=self.data_use)
        query_time_params = {'efSearch': self.efS}
        print('Setting query-time parameters', query_time_params)
        self.nmslib_.setQueryTimeParams(query_time_params)

        # For compatibility reasons, as each sample is considered as its own
        # neighbor, one extra neighbor will be computed.
        self.n_neighbors = self.n_neighbors + 1
        start = time.time()
        ann_results = self.nmslib_.knnQueryBatch(data, k=self.n_neighbors,
                                                 num_threads=self.n_jobs)
        end = time.time()
        print('kNN time total=%f (sec), per query=%f (sec), per query adjusted for thread number=%f (sec)' %
              (end - start, float(end - start) / query_qty, self.n_jobs * float(end - start) / query_qty))

        # Use sklearn for exact neighbor search
        start = time.time()
        nbrs = NearestNeighbors(n_neighbors=self.n_neighbors,
                                metric='cosine',
                                algorithm='brute').fit(data)
        knn = nbrs.kneighbors(data)
        end = time.time()
        print('brute-force gold-standart kNN time total=%f (sec), per query=%f (sec)' %
              (end - start, float(end - start) / query_qty))

        recall = 0.0
        for i in range(0, query_qty):
            correct_set = set(knn[1][i])
            ret_set = set(ann_results[i][0])
            recall = recall + float(len(correct_set.intersection(ret_set))) / len(correct_set)
        recall = recall / query_qty
        print('kNN recall: %f' % recall)


