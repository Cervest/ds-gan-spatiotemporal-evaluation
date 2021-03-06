"""
Train and validate reference pixel time series classifier

Usage:
    make_reference_classifier.py --cfg=<config_file_path>  --o=<output_dir> [--njobs=<number_of_workers>]

Options:
  --cfg=<config_file_path>      Path to config file.
  --o=<output_directory>        Path to output directory.
  --njobs=<number_of_workers>   Number of workers for parallelization [default: 1].
"""
import os
from docopt import docopt
import logging
import matplotlib.pyplot as plt
import numpy as np
import torch
from torch.utils.data import DataLoader, Subset
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay
from sklearn.linear_model import LogisticRegression
from src.rsgan import build_experiment
from src.toygeneration import ProductDataset
from src.utils import load_yaml, save_pickle, setseed


def main(args, cfg):
    # Build experiment
    experiment = build_experiment(cfg)

    # Retrieve dataloaders of annotated target frames from testing set
    logging.info("Loading training and validation sets")
    train_loader, val_loader = make_annotated_clean_frames_dataloaders(experiment)

    # Convert into (n_pixel, n_channel), (n_pixel,) arrays for sklearn
    logging.info("Converting datasets as arrays for sklearn")
    X_train, y_train = dataset_as_arrays(train_loader, seed=cfg['experiment']['seed'])
    X_val, y_val = dataset_as_arrays(val_loader, seed=cfg['experiment']['seed'])

    # Fit classifier to testing set
    classifier_cfg = cfg['reference_classifier']
    rf = fit_classifier_by_chunks(X_train=X_train[:classifier_cfg['train_set_size']],
                                  y_train=y_train[:classifier_cfg['train_set_size']],
                                  l2_weight=classifier_cfg['l2_weight'],
                                  n_chunks=classifier_cfg['n_chunks'],
                                  tol=classifier_cfg['tol'],
                                  seed=classifier_cfg['seed'],
                                  n_jobs=int(args['--njobs']))

    # Dump classifier at specified location
    dump_path = args['--o']
    logging.info(f"Saving classifier at {dump_path}")
    save_pickle(dump_path, rf)

    # Compute and save accuracy
    logging.info("Computing accuracy on validation set")
    compute_and_save_accuracy(X_val, y_val, rf, dump_path)

    # Compute and save confusion matrix
    logging.info("Computing confusion matrix on validation set")
    compute_and_save_confusion_matrix(X_val, y_val, rf, dump_path)


def make_annotated_clean_frames_dataloaders(experiment):
    """Builds dataloader of clean groundtruth frames along
    with their pixel-label masks.

    Applies same normalization procedure to frames than the one used for
    training generative models
    """
    # Retrieve clean groundtruth frames dataset which are targets in generative models training
    target_annotated_frames_dataset = experiment.test_set.dataset.target_dataset
    horizon = experiment.test_set.dataset.horizon

    # Set normalization transform for frames
    set_transform_recursively(concat_dataset=target_annotated_frames_dataset,
                              transform=lambda x: (x - 0.5) / 0.5,
                              attribute_name='frame_transform')

    # Set pixel-label selection transform for annotation masks
    set_transform_recursively(concat_dataset=target_annotated_frames_dataset,
                              transform=lambda x: x[:, :, 1],
                              attribute_name='annotation_transform')

    # Build dataloaders restricted to corresponding indices sets
    train_indices = experiment.train_set.indices
    train_loader = make_dataloader_from_indices(dataset=target_annotated_frames_dataset,
                                                batch_size=horizon,
                                                indices=train_indices)

    val_indices = experiment.val_set.indices
    val_loader = make_dataloader_from_indices(dataset=target_annotated_frames_dataset,
                                              batch_size=horizon,
                                              indices=val_indices)
    return train_loader, val_loader


def set_transform_recursively(concat_dataset, transform, attribute_name):
    """Used datasets results of recursive concatenation of ProductDataset
    instances encapsulated under torch.data.utils.ConcatDataset instances as a
    binary tree :

                            +---+ConcatDataset+---+
                            |                     |
                            +                     +
                 +---+ConcatDataset+---+    ProductDataset
                 |                     |
                 +                     +
           ConcatDataset         ProductDataset
                 +
                 |
                ...

    However, we want to define transforms for the leaves ProductDataset instances,
    we hence need to operate recursively

    Args:
        concat_dataset (torch.utils.data.ConcatDataset)
        transform (callable): np.ndarray -> np.ndarray
        attribute_name (str): attribute name where to set transform
    """
    concat_dataset.datasets[1].__setattr__(attribute_name, transform)
    if isinstance(concat_dataset.datasets[0], ProductDataset):
        concat_dataset.datasets[0].__setattr__(attribute_name, transform)
    else:
        set_transform_recursively(concat_dataset.datasets[0], transform, attribute_name)


def make_dataloader_from_indices(dataset, batch_size, indices):
    """Builds dataloader from ordered time series dataset on specified indices

    Args:
        dataset (torch.utils.data.Dataset)
        batch_size (int)
        indices (list[int]): list of allowed dataset indices

    Returns:
        type: torch.utils.data.DataLoader
    """

    dataloader = DataLoader(dataset=Subset(dataset=dataset, indices=indices),
                            batch_size=batch_size)
    return dataloader


@setseed('numpy')
def dataset_as_arrays(dataloader, seed):
    """Drain out dataloader to load frames and labels into memory as numpy arrays,
    ready to be fed to classifier
    """
    # Unpack frames and annotations
    frames, annotations = list(zip(*iter(dataloader)))

    # Reshape such that each pixel time serie is a sample and channels features + convert to numpy
    X = torch.stack(frames)
    batch_size, horizon, height, width, channels = X.shape
    X = X.permute(0, 2, 3, 1, 4).contiguous().view(-1, horizon * channels).numpy()

    # Flatten time series annotation masks - we keep first time step only
    y = torch.stack(annotations)[:, 0, :].flatten()

    # Shuffle jointly pixel and labels
    shuffled_indices = np.random.permutation(len(X))
    X = X[shuffled_indices]
    y = y[shuffled_indices]

    # Remove background pixels which we are not interested in classifying
    foreground_pixels = y != 0
    X, y = X[foreground_pixels], y[foreground_pixels]
    return X, y


def fit_classifier_by_chunks(X_train, y_train, l2_weight, n_chunks, tol, seed, n_jobs):
    """Fits classifier by chunk as dataset is to big to be fitted at once.
    """
    # Instantiate logistic regression classifier
    lr_kwargs = {'penalty': 'l2',
                 'C': l2_weight,
                 'solver': 'sag',
                 'tol': tol,
                 'n_jobs': n_jobs,
                 'max_iter': 1000,
                 'warm_start': True,
                 'random_state': seed}
    lr = LogisticRegression(**lr_kwargs)
    logging.info(lr)

    # Fit to training dataset by chunks
    chunks_iterator = zip(np.array_split(X_train, n_chunks), np.array_split(y_train, n_chunks))
    for i, (chunk_X, chunk_y) in enumerate(chunks_iterator):
        logging.info(f"Fitting Logistic Regression classifier on {len(chunk_X)} pixel time series")
        lr.fit(chunk_X, chunk_y)
    return lr


def compute_and_save_accuracy(X_val, y_val, classifier, dump_path):
    val_accuracy = classifier.score(X_val, y_val)
    val_accuracy_dump_path = os.path.join(os.path.dirname(dump_path), "accuracy.metric")
    with open(val_accuracy_dump_path, 'w') as f:
        f.write(str(val_accuracy))
    logging.info(f"Validation accuracy : {val_accuracy} - dumped at {val_accuracy_dump_path}")


def compute_and_save_confusion_matrix(X_val, y_val, classifier, dump_path):
    y_pred = classifier.predict(X_val)
    cm = confusion_matrix(y_val, y_pred, labels=classifier.classes_, normalize='true')
    disp = ConfusionMatrixDisplay(confusion_matrix=cm,
                                  display_labels=classifier.classes_)
    confusion_matrix_dump_path = os.path.join(os.path.dirname(dump_path), "confusion_matrix.png")
    save_confusion_matrix_plot(disp, confusion_matrix_dump_path)
    logging.info(f"Confusion matrix : {cm}")
    logging.info(f"Confusion matrix saved at {confusion_matrix_dump_path}")


def save_confusion_matrix_plot(disp, path):
    fig, ax = plt.subplots(figsize=(10, 10))
    disp.plot(include_values=True,
              cmap='magma',
              ax=ax)
    plt.tight_layout()
    plt.savefig(path)


if __name__ == "__main__":
    # Read input args
    args = docopt(__doc__)

    # Setup logging
    logging.basicConfig(level=logging.INFO)
    logging.info(f'arguments: {args}')

    # Load configuration file
    cfg = load_yaml(args["--cfg"])

    # Make dumping directory
    os.makedirs(os.path.dirname(args["--o"]), exist_ok=True)

    # Run generation
    main(args, cfg)
