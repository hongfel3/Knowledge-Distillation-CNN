from .deeplabv3 import DeepWV3Plus
from .hrnet_ocr import HighResolutionNet, get_seg_model
from . import cifar_models
from .gscnn import GSCNN
from functools import reduce
from torch import nn
import torch
import logging
import importlib


def get_net(config, criterion):
    """
    Get Network Architecture based on arguments provided
    """
    net = get_model(network=config['TA']['tc_arch'], num_classes=config['segmentation']['num_classes'],
                    criterion=criterion)
    num_params = sum([param.nelement() for param in net.parameters()])
    logging.info('Model params = {:2.1f}M'.format(num_params / 1000000))

    net = net.cuda()
    return net


def get_model(network, num_classes, criterion):
    """
    Fetch Network Function Pointer
    """
    module = network[:network.rfind('.')]
    model = network[network.rfind('.') + 1:]
    mod = importlib.import_module(module)
    net_func = getattr(mod, model)
    net = net_func(num_classes=num_classes, criterion=criterion)
    return net


def load_weights(snapshot_file, net, optimizer=None, restore_optimizer_bool=False):
    """
    Load weights from snapshot file
    """
    net, optimizer = restore_snapshot(net, optimizer, snapshot_file, restore_optimizer_bool)
    return net, optimizer


def restore_snapshot(net, optimizer, snapshot, restore_optimizer_bool):
    """
    Restore weights and optimizer (if needed ) for resuming job.
    """
    checkpoint = torch.load(snapshot, map_location=torch.device('cpu'))
    if optimizer is not None and 'optimizer' in checkpoint and restore_optimizer_bool:
        optimizer.load_state_dict(checkpoint['optimizer'])

    if 'state_dict' in checkpoint:
        net = forgiving_state_restore(net, checkpoint['state_dict'])
    else:
        net = forgiving_state_restore(net, checkpoint)

    return net, optimizer


def forgiving_state_restore(net, loaded_dict):
    """
    Handle partial loading when some tensors don't match up in size.
    Because we want to use models that were trained off a different
    number of classes.
    """
    # check if state dict checkpoint saved nn.DataParallel module or not
    # if ALL modules state dict in checkpoints start with module. then this is a state dict of nn.DataParallel instance
    is_parallel = reduce(lambda acc, elem: acc and elem.startswith('module.'), list(loaded_dict.keys()))
    print('Checkpoint state_dict is in nn.DataParallel mode')
    if is_parallel:
        net = nn.DataParallel(net)

    net_state_dict = net.state_dict()
    new_loaded_dict = {}

    for k in net_state_dict:
        if k in loaded_dict and net_state_dict[k].size() == loaded_dict[k].size():
            new_loaded_dict[k] = loaded_dict[k]
        else:
            logging.info("Skipped loading parameter %s", k)
    net_state_dict.update(new_loaded_dict)
    net.load_state_dict(net_state_dict)

    if is_parallel:
        net = net.module

    return net
