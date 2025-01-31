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
    print("The package 'nmslib' is required. Please install it 'with pip3 install nmslib'.")
    sys.exit()

print(__doc__)


class NMSlibTransformer(TransformerMixin, BaseEstimator):
    """
    Wrapper for using nmslib as sklearn's KNeighborsTransformer. This implements
    an escalable approximate k-nearest-neighbors graph on spaces defined by nmslib.
    Read more about nmslib and its various available metrics at
    https://github.com/nmslib/nmslib.
    Calling 'nn <- NMSlibTransformer()' initializes the class with
     neighbour search parameters.
    Parameters
    ----------
    n_neighbors: int (optional, default 30)
        number of nearest-neighbors to look for. In practice,
        this should be considered the average neighborhood size and thus vary depending
        on your number of features, samples and data intrinsic dimensionality. Reasonable values
        range from 5 to 100. Smaller values tend to lead to increased graph structure
        resolution, but users should beware that a too low value may render granulated and vaguely
        defined neighborhoods that arise as an artifact of downsampling. Defaults to 30. Larger
        values can slightly increase computational time.
    metric: str (optional, default 'cosine')
        accepted NMSLIB metrics. Defaults to 'cosine'. Accepted metrics include:
        -'sqeuclidean'
        -'euclidean'
        -'l1'
        -'lp' - requires setting the parameter `p`
        -'cosine'
        -'angular'
        -'negdotprod'
        -'levenshtein'
        -'hamming'
        -'jaccard'
        -'jansen-shan'
    method: str (optional, default 'hsnw')
        approximate-neighbor search method. Available methods include:
                -'hnsw' : a Hierarchical Navigable Small World Graph.
                -'sw-graph' : a Small World Graph.
                -'vp-tree' : a Vantage-Point tree with a pruning rule adaptable to non-metric distances.
                -'napp' : a Neighborhood APProximation index.
                -'simple_invindx' : a vanilla, uncompressed, inverted index, which has no parameters.
                -'brute_force' : a brute-force search, which has no parameters.
        'hnsw' is usually the fastest method, followed by 'sw-graph' and 'vp-tree'.
    n_jobs: int (optional, default 1)
        number of threads to be used in computation. Defaults to 1. The algorithm is highly
        scalable to multi-threading.
    M: int (optional, default 30)
        defines the maximum number of neighbors in the zero and above-zero layers during HSNW
        (Hierarchical Navigable Small World Graph). However, the actual default maximum number
        of neighbors for the zero layer is 2*M.  A reasonable range for this parameter
        is 5-100. For more information on HSNW, please check https://arxiv.org/abs/1603.09320.
        HSNW is implemented in python via NMSlib. Please check more about NMSlib at https://github.com/nmslib/nmslib.
    efC: int (optional, default 100)
        A 'hnsw' parameter. Increasing this value improves the quality of a constructed graph
        and leads to higher accuracy of search. However this also leads to longer indexing times.
        A reasonable range for this parameter is 50-2000.
    efS: int (optional, default 100)
        A 'hnsw' parameter. Similarly to efC, increasing this value improves recall at the
        expense of longer retrieval time. A reasonable range for this parameter is 100-2000.
    dense: bool (optional, default False)
        Whether to force the algorithm to use dense data, such as np.ndarrays and pandas DataFrames.
    Returns
    ---------
    Class for really fast approximate-nearest-neighbors search.
    Example
    -------------
    import numpy as np
    from sklearn.datasets import load_digits
    from scipy.sparse import csr_matrix
    from dbmap.ann import NMSlibTransformer
    #
    # Load the MNIST digits data, convert to sparse for speed
    digits = load_digits()
    data = csr_matrix(digits)
    #
    # Start class with parameters
    nn = NMSlibTransformer()
    nn = nn.fit(data)
    #
    # Obtain kNN graph
    knn = nn.transform(data)
    #
    # Obtain kNN indices, distances and distance gradient
    ind, dist, grad = nn.ind_dist_grad(data)
    #
    # Test for recall efficiency during approximate nearest neighbors search
    test = nn.test_efficiency(data)
    """

    def __init__(self,
                 n_neighbors=30,
                 metric='cosine',
                 method='hnsw',
                 n_jobs=10,
                 p=None,
                 M=30,
                 efC=100,
                 efS=100,
                 dense=False,
                 verbose=False
                 ):

        self.n_neighbors = n_neighbors
        self.method = method
        self.metric = metric
        self.n_jobs = n_jobs
        self.p = p
        self.M = M
        self.efC = efC
        self.efS = efS
        self.space = self.metric

        self.dense = dense
        self.verbose = verbose

    def fit(self, data):
        # see more metrics in the manual
        # https://github.com/nmslib/nmslib/tree/master/manual
        if self.metric == 'lp' and self.p < 1:
            print('Fractional L norms are slower to compute. Computations are faster for fractions'
                  ' of the form \'1/2ek\', where k is a small integer (i.g. 0.5, 0.25) ')
        if self.dense:
            self.nmslib_ = nmslib.init(method=self.method,
                                       space=self.space,
                                       data_type=nmslib.DataType.DENSE_VECTOR)

        else:
            if issparse(data) == True:
                if self.verbose:
                    print('Sparse input. Proceding without converting...')
                if isinstance(data, np.ndarray):
                    data = csr_matrix(data)
            if issparse(data) == False:
                if self.verbose:
                    print('Input data is ' + str(type(data)) + ' .Converting input to sparse...')
                import pandas as pd
                if isinstance(data, pd.DataFrame):
                    data = csr_matrix(data.values.T)

        index_time_params = {'M': self.M, 'indexThreadQty': self.n_jobs, 'efConstruction': self.efC, 'post': 2}

        if issparse(data) and (not self.dense) and (not isinstance(data, np.ndarray)):
            if self.metric not in ['levenshtein', 'hamming', 'jansen-shan', 'jaccard']:
                self.space = {
                    'sqeuclidean': 'l2_sparse',
                    'euclidean': 'l2_sparse',
                    'cosine': 'cosinesimil_sparse_fast',
                    'lp': 'lp_sparse',
                    'l1_sparse': 'l1_sparse',
                    'linf_sparse': 'linf_sparse',
                    'angular_sparse': 'angulardist_sparse_fast',
                    'negdotprod_sparse': 'negdotprod_sparse_fast',
                }[self.metric]
                if self.metric == 'lp':
                    self.nmslib_ = nmslib.init(method=self.method,
                                               space=self.space,
                                               space_params={'p': self.p},
                                               data_type=nmslib.DataType.SPARSE_VECTOR)
                else:
                    self.nmslib_ = nmslib.init(method=self.method,
                                               space=self.space,
                                               data_type=nmslib.DataType.SPARSE_VECTOR)
            else:
                print('Metric ' + self.metric + 'available for string data only. Trying to compute distances...')
                data = data.toarray()
                self.nmslib_ = nmslib.init(method=self.method,
                                           space=self.space,
                                           data_type=nmslib.DataType.OBJECT_AS_STRING)
        else:
            self.space = {
                'sqeuclidean': 'l2',
                'euclidean': 'l2',
                'cosine': 'cosinesimil',
                'lp': 'lp',
                'l1': 'l1',
                'linf': 'linf',
                'angular': 'angulardist',
                'negdotprod': 'negdotprod',
                'levenshtein': 'leven',
                'hamming': 'bit_hamming',
                'jaccard': 'bit_jaccard',
                'jansen-shan': 'jsmetrfastapprox'
            }[self.metric]
            if self.metric == 'lp':
                self.nmslib_ = nmslib.init(method=self.method,
                                           space=self.space,
                                           space_params={'p': self.p},
                                           data_type=nmslib.DataType.DENSE_VECTOR)
            else:
                self.nmslib_ = nmslib.init(method=self.method,
                                           space=self.space,
                                           data_type=nmslib.DataType.DENSE_VECTOR)

        self.nmslib_.addDataPointBatch(data)
        start = time.time()
        self.nmslib_.createIndex(index_time_params)
        end = time.time()
        if self.verbose:
            print('Index-time parameters', 'M:', self.M, 'n_threads:', self.n_jobs, 'efConstruction:', self.efC,
                  'post:0')
            print('Indexing time = %f (sec)' % (end - start))

        return self

    def transform(self, data):
        start = time.time()
        n_samples_transform = data.shape[0]
        query_time_params = {'efSearch': self.efS}
        if self.verbose:
            print('Query-time parameter efSearch:', self.efS)
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
                                                       n_samples_transform))
        end = time.time()
        if self.verbose:
            print('kNN time total=%f (sec), per query=%f (sec), per query adjusted for thread number=%f (sec)' %
                  (end - start, float(end - start) / query_qty, self.n_jobs * float(end - start) / query_qty))

        return kneighbors_graph

    def ind_dist_grad(self, data, return_grad=True, return_graph=True):

        start = time.time()
        n_samples_transform = data.shape[0]
        query_time_params = {'efSearch': self.efS}
        if self.verbose:
            print('Query-time parameter efSearch:', self.efS)
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
                                                       n_samples_transform))
        if return_grad:
            x, y, dists = find(kneighbors_graph)

            # Define gradients
            grad = []
            if self.metric not in ['sqeuclidean', 'euclidean', 'cosine', 'linf']:
                print('Gradient undefined for metric \'' + self.metric + '\'. Returning empty array.')

            if self.metric == 'cosine':
                norm_x = 0.0
                norm_y = 0.0
                for i in range(x.shape[0]):
                    norm_x += x[i] ** 2
                    norm_y += y[i] ** 2
                if norm_x == 0.0 and norm_y == 0.0:
                    grad = np.zeros(x.shape)
                elif norm_x == 0.0 or norm_y == 0.0:
                    grad = np.zeros(x.shape)
                else:
                    grad = -(x * dists - y * norm_x) / np.sqrt(norm_x ** 3 * norm_y)

            if self.metric == 'euclidean':
                grad = x - y / (1e-6 + np.sqrt(dists))

            if self.metric == 'sqeuclidean':
                grad = x - y / (1e-6 + dists)

            if self.metric == 'linf':
                result = 0.0
                max_i = 0
                for i in range(x.shape[0]):
                    v = np.abs(x[i] - y[i])
                    if v > result:
                        result = dists
                        max_i = i
                grad = np.zeros(x.shape)
                grad[max_i] = np.sign(x[max_i] - y[max_i])

        end = time.time()

        if self.verbose:
            print('kNN time total=%f (sec), per query=%f (sec), per query adjusted for thread number=%f (sec)' %
                  (end - start, float(end - start) / query_qty, self.n_jobs * float(end - start) / query_qty))

        if return_graph and return_grad:
            return indices, distances, grad, kneighbors_graph
        if return_graph and not return_grad:
            return indices, distances, kneighbors_graph
        if not return_graph and return_grad:
            return indices, distances, grad
        if not return_graph and not return_grad:
            return indices, distances

    def test_efficiency(self, data, data_use=0.1):
        """Test if NMSlibTransformer and KNeighborsTransformer give same results
        """
        self.data_use = data_use

        query_qty = data.shape[0]

        (dismiss, test) = train_test_split(data, test_size=self.data_use)
        query_time_params = {'efSearch': self.efS}
        if self.verbose:
            print('Setting query-time parameters', query_time_params)
        self.nmslib_.setQueryTimeParams(query_time_params)

        # For compatibility reasons, as each sample is considered as its own
        # neighbor, one extra neighbor will be computed.
        self.n_neighbors = self.n_neighbors + 1
        start = time.time()
        ann_results = self.nmslib_.knnQueryBatch(data, k=self.n_neighbors,
                                                 num_threads=self.n_jobs)
        end = time.time()
        if self.verbose:
            print('kNN time total=%f (sec), per query=%f (sec), per query adjusted for thread number=%f (sec)' %
                  (end - start, float(end - start) / query_qty, self.n_jobs * float(end - start) / query_qty))

        # Use sklearn for exact neighbor search
        start = time.time()
        nbrs = NearestNeighbors(n_neighbors=self.n_neighbors,
                                metric=self.metric,
                                algorithm='brute').fit(data)
        knn = nbrs.kneighbors(data)
        end = time.time()
        if self.verbose:
            print('brute-force gold-standart kNN time total=%f (sec), per query=%f (sec)' %
                  (end - start, float(end - start) / query_qty))

        recall = 0.0
        for i in range(0, query_qty):
            correct_set = set(knn[1][i])
            ret_set = set(ann_results[i][0])
            recall = recall + float(len(correct_set.intersection(ret_set))) / len(correct_set)
        recall = recall / query_qty
        print('kNN recall %f' % recall)

    def update_search(self, n_neighbors):
        """
        Updates number of neighbors for kNN distance computation.
        Parameters
        -----------
        n_neighbors: New number of neighbors to look for.

        """
        self.n_neighbors = n_neighbors

