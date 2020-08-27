import torch
import numpy as np

"""
Default batch formatting when using pytorch dataloading modules is done as :
[(data_1, target_1), (data_2, target_2), ... , (data_n, target_n)]

where the latter tuples are usually torch.Tensor instances or np.ndarray

The following utilities are meant to process such input and manipulate data in
order to yield the batches in a more training-compliant fashion
"""


def stack_input_frames(batch):
    """Stacks inputs as a single array and leaves target unchanged

    Args:
        batch (list): batch as [((frame_1, frame_2), target)]
    """
    data, target = zip(*batch)
    data = list(map(torch.cat, data))
    data = torch.stack(data).float()
    target = torch.stack(target).float()
    return data, target


def stack_annotated_input_frames(batch):
    """Stacks inputs as a single array and leaves target and annotation mask
        array unchanged

    Args:
        batch (list): batch as [((frame_1, frame_2), target, annotation)]
    """
    data, target, annotation = zip(*batch)
    data = list(map(torch.cat, data))
    data = torch.stack(data).float()
    target = torch.stack(target).float()
    annotation = np.stack(annotation)
    return data, target, annotation


def target_as_input(batch):
    """Replaces input with target while leaving target unchanged

    Args:
        batch (list): batch as [(input, target)]
    """
    _, target = zip(*batch)
    target = torch.stack(target).float()
    return target, target


def annotated_target_as_input(batch):
    """Replaces input with target while leaving target and annotation mask
        array unchanged

    Args:
        batch (list): batch as [(input, target, annotation)]
    """
    _, target, annotation = zip(*batch)
    target = torch.stack(target).float()
    annotation = np.stack(annotation)
    return target, target, annotation
