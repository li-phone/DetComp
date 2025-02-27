_base_ = './cascade_rcnn_r50_fpn_1x_coco.py'
model = dict(
    type='CascadeRCNN',
    pretrained='open-mmlab://resnext101_64x4d',
    backbone=dict(
        type='ResNeXt',
        depth=101,
        groups=64,
        base_width=4,
        num_stages=4,
        out_indices=(0, 1, 2, 3),
        frozen_stages=1,
        norm_cfg=dict(type='BN', requires_grad=True),
        style='pytorch'))

work_dir = '../work_dirs/breast/cascade_rcnn_x101_64x4d_fpn_1x_quantile+multiscale+softnms'
