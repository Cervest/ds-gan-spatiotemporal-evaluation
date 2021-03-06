import random
import numpy as np
import pandas as pd
from functools import reduce
import matplotlib.pyplot as plt
from torch.utils.data import Dataset
from sktime.utils.load_data import load_from_tsfile_to_dataframe
from src.utils import setseed
from .utils import labels_as_int, pad_to_max_length


class TSDataset(Dataset):
    """Time Series dataset

    Args:
        root (str): path to .ts file to load

    Attributes:
        data (pd.DataFrame): (n_sample, n_dim) dataframe where columns
            corresponds to a time serie dimension and rows to a time serie.
            Time series along one dimension are stored in each cell as pd.Serie
        labels (np.ndarray): (n_sample, ) array with each serie label
    """
    def __init__(self, root, ndim, nclass, rescale=True):
        self.root = root
        df, labels = load_from_tsfile_to_dataframe(root)
        self.data = df
        self.labels = labels_as_int(labels)
        self._preprocess_dataset(ndim, nclass, rescale)

    def _preprocess_dataset(self, ndim, nclass, rescale):
        """Handles optional dataset preprocessing by :

            (1) Truncating time series dimensionality
            (2) Grouping classes to match desired number of class
            (3) Rescale time series values range

        Args:
            ndim (int): desired time series dimensionality
            nclass (int): desired number of class
            rescale (bool): if True, applies minmax rescale to value range
        """
        self._truncate_dimensions(ndim=ndim)
        self._group_labels(n_groups=nclass)
        if rescale:
            self._min_max_rescale()

    def __getitem__(self, idx, t=None):
        """Series access method

        Given an index, loads serie as a (n_steps, n_dim) array along with its
            label.
        If time step t is additionally specified, label is not returned and only
            (n_dim, ) array at specified time step is returned

        Args:
            idx (int): index on time serie to access in self.data
            t (int): time step

        Returns:
            type: (np.ndarray, np.ndarray) or np.ndarray
        """
        # Extract each dimension array for ts at specified location
        X = [x.values for x in self.data.iloc[idx]]

        # Stack them with padding if lengths do not match
        try:
            X = np.stack(X, axis=1)
        except ValueError:
            X = np.stack(pad_to_max_length(X), axis=1)

        # If time step precised, return time serie slice at t
        if t:
            return X[t]

        # Else, return full time serie as numpy array with label
        else:
            y = self.labels[idx]
            return X, y

    def __repr__(self):
        output = ["~~ Time Serie Dataset ~~"]
        output += [f"Dataset Path : {self.root}"]
        output += [f"Nb of samples : {len(self)}"]
        output += [f"Dimensionality : {self.ndim}"]
        output += [f"Nb of classes : {len(set(self.labels))}"]
        return '\n'.join(output)

    def __len__(self):
        return len(self.data)

    def _truncate_length(self, length):
        """Drops rows from dataframe to match specified length

        Args:
            length (int): if negative of greater than current length, dataset
                is left unchanged
        """
        if length < len(self) and length > 0:
            self.data = self.data.truncate(after=length - 1)
            self.labels = self.labels[:length]

    def _truncate_dimensions(self, ndim):
        """Drops columns from dataframe to match specfied number of dimensions

        Args:
            ndim (int): if negative or greater than max number of dims, dataset
                is left unchanged
        """
        if ndim >= 0:
            truncated_dims = self.data.columns[:ndim]
            self.data = self.data[truncated_dims]

    def _reorder(self, indices):
        """Reorders dataset and labels to match provided indices order

        Args:
            indices (list[int])
        """
        self.data = self.data.reindex(indices).reset_index(drop=True)
        self.labels = self.labels[indices]

    def _min_max_rescale(self, amin=0, amax=1):
        """Rescales dataset time series values in [amin, amax] independently along
        each dimension/column

        Args:
            amin (float): minimum affine rescaling value
            amax (float): maximum affine rescaling value
        """
        # Get maximum and minimum value by dimension
        min_by_dim = [np.min([x.values for x in self.data[col]]) for col in self.data.columns]
        max_by_dim = [np.max([x.values for x in self.data[col]]) for col in self.data.columns]

        # Rescale rows while keeping them encapsulated as pd.Series
        rescale = lambda x, min, max: (amax - amin) * (x - min) / (max - min) + amin
        rescale_by_dim = lambda row: pd.Series([rescale(x, min, max) for (x, min, max) in zip(row, min_by_dim, max_by_dim)])
        self.data = self.data.apply(rescale_by_dim, axis=1)

    def _group_labels(self, n_groups):
        """Processes dataset labels array of size (N, ) filled with C possible
        labels values. Splits the C label values into n_groups of - if possible -
        equally sized groups and replace with group labels the original (N, ) labels

        Args:
            n_groups (int)

        Returns:
            type: timeserie.TSDataset
        """
        # Group unique labels values
        unique_labels = np.unique(self.labels)
        grouped_labels = np.array_split(unique_labels, n_groups)

        # Map each label value to its corresponding group index
        groups_mapping = [{label: idx for label in group} for idx, group in enumerate(grouped_labels)]
        groups_mapping = reduce(lambda a, b: {**a, **b}, groups_mapping)

        # Replace actual label values with group labels
        new_labels = 1 + np.array([groups_mapping[label] for label in self.labels])
        self.labels = new_labels

    def plot(self, idx, figsize=(10, 6)):
        """Quick utility to visualize a time serie from dataframe

        Args:
            idx (int): index on time serie to access in self.data
            figsize (tuple[int]): figure size
        """
        ts, label = self[idx]
        length, n_dim = ts.shape

        fig, ax = plt.subplots(n_dim, 1, figsize=figsize)
        for i in range(n_dim):
            ax[i].plot(range(ts.shape[0]), ts[:, i], label=f"Label : {label}")
        plt.legend()
        plt.show()

    def _choice_given_label(self, label, replace=True):
        """Draws random sample among samples with specified label

        Args:
            label (int)
            replace (bool): if True, allows to pick same sample multiple times
        """
        if replace:
            possible_indices = np.argwhere(self.labels == label).squeeze()
            idx = np.random.choice(possible_indices)
        else:
            raise NotImplementedError("Random choice by label without replace not implemented yet")
        return self[idx]

    def _random_choice(self, replace=True):
        """Mimics random.choice by returning random sample from dataset

        Args:
            replace (bool): if True, allows to pick same sample multiple times
        """
        if replace:
            idx = random.randint(0, len(self) - 1)
        else:
            if not hasattr(self, '_left_to_draw'):
                self._left_to_draw = list(range(len(self)))
                random.shuffle(self._left_to_draw)
            if len(self._left_to_draw) > 0:
                idx = self._left_to_draw.pop()
            else:
                raise IndexError("All samples have already been drawn once")
        return self[idx]

    @setseed('random')
    def choice(self, label=None, replace=True, seed=None):
        """Return random sample from dataset

        Args:
            label (int): if specified, draws from samples with this label
            seed (int): random seed
            replace (bool): if True, allows to pick same sample multiple times
        """
        if label:
            output = self._choice_given_label(label=label, replace=replace)
        else:
            output = self._random_choice(replace=replace)
        return output

    @setseed('numpy')
    def _draw_label_list(self, size, distribution, seed=None):
        """Draws random vector of labels according to multinomial distribution
        of labels provided and sets as private attribute

        Args:
            size (int): length of random vector
            distribution (np.ndarray): multinomial distribution over label values
            seed (int): random seed
        """
        unique_labels = np.unique(self.labels)
        if len(distribution) != len(unique_labels):
            raise ValueError(f"{len(unique_labels)} labels with distribution has size {len(distribution)}")
        labels_order_list = np.random.choice(unique_labels, size=size, p=distribution)
        self._labels_order_list = labels_order_list

    def __add__(self, ts_dataset):
        self.data = pd.concat([self.data, ts_dataset.data])
        self.labels = np.concatenate([self.labels, ts_dataset.labels])
        return self

    @property
    def root(self):
        return self._root

    @property
    def data(self):
        return self._data

    @property
    def labels(self):
        return self._labels

    @property
    def ndim(self):
        return self.data.shape[1]

    @root.setter
    def root(self, root):
        self._root = root

    @data.setter
    def data(self, df):
        if not isinstance(df, pd.DataFrame):
            raise TypeError
        else:
            self._data = df

    @labels.setter
    def labels(self, labels):
        if not isinstance(labels, np.ndarray):
            raise TypeError
        else:
            self._labels = labels


class TimeSerie:
    """Time serie iterating class

    Args:
        ts (np.ndarray): (n_steps, n_dim) array
        label (int, str): the time serie label
        horizon (int): finite horizon for the time serie <= time serie actual length (default: None)
        seed (int): random seed
    """

    def __init__(self, ts, label, horizon=None, seed=None):
        self._ts = ts
        self._label = int(float(label))
        self._horizon = horizon
        self._ndim = ts.shape[1]
        self._seed = seed

    @setseed('numpy')
    def _pick_starting_point(self, seed=None):
        """Picks a starting point for the serie
        If no horizon provided, default is 0
        Otherwise, random starting point is drawn

        Args:
            seed (int): random seed

        Returns:
            type: int
        """
        if self.horizon:
            t_start = np.random.randint(0, len(self.ts) - len(self) + 1)
        else:
            t_start = 0
        return t_start

    def __iter__(self):
        """Iterates over time serie values
        Each __next__ call yields a (n_dim, ) np.ndarray
        """
        t_start = self._pick_starting_point(seed=self.seed)
        truncated_ts = self.ts[t_start:t_start + len(self)]
        return iter(truncated_ts)

    def __len__(self):
        """Time serie length or Horizon if specified

        Returns:
            type: int
        """
        return self.horizon or len(self.ts)

    @property
    def ts(self):
        return self._ts

    @property
    def label(self):
        return self._label

    @property
    def horizon(self):
        return self._horizon

    @property
    def ndim(self):
        return self._ndim

    @property
    def seed(self):
        return self._seed
