import torch
import torch.nn as nn
import torch.nn.functional as F

from ..registry import LOSSES
from .utils import weight_reduce_loss


def label_smooth_loss(x, labels, label_smooth=0.1):
    classification = nn.functional.softmax(x, dim=1)
    targets = torch.zeros(classification.shape)
    targets = targets.cuda()
    for label, target in zip(labels, targets):
        target[label] = 1

    k = classification.shape[1]
    epsilon = torch.ones(targets.shape).cuda() * label_smooth
    label_smooth_weight = torch.where(torch.eq(targets, 1.), 1 - epsilon, epsilon / (k - 1))

    bce = -(targets * torch.log(classification + 1e-37) + (1.0 - targets) * torch.log(1.0 - classification + 1e-37))
    cls_loss = label_smooth_weight * bce
    cls_loss = torch.where(torch.ne(targets, -1.0), cls_loss, torch.zeros(cls_loss.shape).cuda())
    return cls_loss.sum(dim=1)


def cross_entropy(pred, label, weight=None, reduction='mean', avg_factor=None, label_smooth=None):
    # element-wise losses
    if label_smooth is None:
        loss = F.cross_entropy(pred, label, reduction='none')
    else:
        loss = label_smooth_loss(pred, label, label_smooth)

    # apply weights and do the reduction
    if weight is not None:
        weight = weight.float()
    loss = weight_reduce_loss(
        loss, weight=weight, reduction=reduction, avg_factor=avg_factor)

    return loss


def _expand_binary_labels(labels, label_weights, label_channels):
    bin_labels = labels.new_full((labels.size(0), label_channels), 0)
    inds = torch.nonzero(labels >= 1).squeeze()
    if inds.numel() > 0:
        bin_labels[inds, labels[inds] - 1] = 1
    if label_weights is None:
        bin_label_weights = None
    else:
        bin_label_weights = label_weights.view(-1, 1).expand(
            label_weights.size(0), label_channels)
    return bin_labels, bin_label_weights


def binary_cross_entropy(pred,
                         label,
                         weight=None,
                         reduction='mean',
                         avg_factor=None):
    if pred.dim() != label.dim():
        label, weight = _expand_binary_labels(label, weight, pred.size(-1))

    # weighted element-wise losses
    if weight is not None:
        weight = weight.float()
    loss = F.binary_cross_entropy_with_logits(
        pred, label.float(), weight, reduction='none')
    # do the reduction for the weighted loss
    loss = weight_reduce_loss(loss, reduction=reduction, avg_factor=avg_factor)

    return loss


def mask_cross_entropy(pred, target, label, reduction='mean', avg_factor=None):
    # TODO: handle these two reserved arguments
    assert reduction == 'mean' and avg_factor is None
    num_rois = pred.size()[0]
    inds = torch.arange(0, num_rois, dtype=torch.long, device=pred.device)
    pred_slice = pred[inds, label].squeeze(1)
    return F.binary_cross_entropy_with_logits(
        pred_slice, target, reduction='mean')[None]


@LOSSES.register_module
class CrossEntropyLoss(nn.Module):

    def __init__(self,
                 use_sigmoid=False,
                 use_mask=False,
                 reduction='mean',
                 loss_weight=1.0,
                 label_smooth=None):
        super(CrossEntropyLoss, self).__init__()
        assert (use_sigmoid is False) or (use_mask is False)
        self.use_sigmoid = use_sigmoid
        self.use_mask = use_mask
        self.reduction = reduction
        self.loss_weight = loss_weight
        self.label_smooth = label_smooth

        if self.use_sigmoid:
            self.cls_criterion = binary_cross_entropy
        elif self.use_mask:
            self.cls_criterion = mask_cross_entropy
        else:
            self.cls_criterion = cross_entropy

    def forward(self,
                cls_score,
                label,
                weight=None,
                avg_factor=None,
                reduction_override=None,
                **kwargs):
        assert reduction_override in (None, 'none', 'mean', 'sum')
        reduction = (
            reduction_override if reduction_override else self.reduction)
        if self.label_smooth is None:
            loss_cls = self.loss_weight * self.cls_criterion(
                cls_score,
                label,
                weight,
                reduction=reduction,
                avg_factor=avg_factor,
                **kwargs)
        else:
            loss_cls = self.loss_weight * self.cls_criterion(
                cls_score,
                label,
                weight,
                reduction=reduction,
                avg_factor=avg_factor,
                label_smooth=self.label_smooth,
                **kwargs)
        return loss_cls
