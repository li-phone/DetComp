import os
import time
import json
import cv2
import torch
import numpy as np
from mmcv.ops.nms import batched_nms
from pycocotools.coco import COCO
from mmdet.datasets.pipelines import Compose
from mmdet.third_party.parallel import Parallel
from mmdet.apis import init_detector, inference_detector, show_result_pyplot


class Config(object):
    # process module
    # 1000 x 1000
    # train_pipeline0 = [
    #     dict(type='LoadImageFromFile'),
    #     dict(type='SliceImage', base_win=(1000, 1000), step=(0.2, 0.2), resize=(1, 1), keep_none=True),
    # ]
    # 2000 x 2000
    train_pipeline1 = [
        dict(type='LoadImageFromFile'),
        dict(type='SliceImage', base_win=(2000, 2000), step=(0.2, 0.2), resize=(1, 1), keep_none=True),
    ]
    # 4000 x 4000
    train_pipeline2 = [
        dict(type='LoadImageFromFile'),
        dict(type='SliceImage', base_win=(2000, 2000), step=(0.2, 0.2), resize=(1 / 2, 1 / 2), keep_none=True),
    ]
    # 8000 x 8000
    train_pipeline3 = [
        dict(type='LoadImageFromFile'),
        dict(type='SliceImage', base_win=(2000, 2000), step=(0.2, 0.2), resize=(1 / 4, 1 / 4), keep_none=True),
    ]
    composes = [Compose(train_pipeline3), Compose(train_pipeline2), Compose(train_pipeline1)]
    max_slice_num = np.array([300, 150, 75])[::-1]

    # data module
    img_dir = "data/track/panda_round1_test_202104_A/"
    test_file = "data/track/annotations/submit_testA.json"
    save_file = "work_dirs/track/best-r50-mst_slice-mst_slice-scale_3-2.json"
    original_coco = COCO(test_file)
    # label2name = {x['id']: x['name'] for x in original_coco.dataset['categories']}
    label2name = {1: 4, 2: 2, 3: 3, 4: 1}
    from fname2id import fname2id
    fname2id = fname2id

    # inference module
    device = 'cuda:0'
    config_file = '../configs/track/best-r50-mst_slice.py'
    checkpoint_file = 'work_dirs/best-r50-mst_slice/latest.pth'
    model = init_detector(config_file, checkpoint_file, device=device)


def mkdirs(path, is_file=True):
    if is_file:
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))
    else:
        if not os.path.exists(path):
            os.makedirs(path)


def plt_bbox(img, boxes, labels, idx=None):
    # show test image
    import matplotlib.pyplot as plt
    from mmcv.visualization.image import imshow_det_bboxes
    img = np.array(img)
    img = imshow_det_bboxes(img, boxes, labels, show=False)
    # plt.imshow(img)
    file_name = "__show_img__/" + '{:04d}'.format(idx) + '.jpg'
    mkdirs(file_name)
    img = np.array(img)
    cv2.imwrite(file_name, img)
    pass


def process(image, **kwargs):
    save_results = dict(result=[])
    config = kwargs['config']
    image['filename'] = image['file_name']
    # 多尺度测试
    mst_bboxes = np.empty([0, 6], dtype=np.float32)
    idx = 0
    for compose, slice_num in zip(config.composes, config.max_slice_num):
        results = compose({'img_prefix': config.img_dir, 'img_info': image})
        if results is None or len(results) == 0: continue
        if isinstance(results, dict): results = [results]
        img_bboxes = np.empty([0, 6], dtype=np.float32)
        for i, result in enumerate(results):
            bbox_result = inference_detector(config.model, result['img'])
            win_bboxes = np.empty([0, 6], dtype=np.float32)
            for j in range(len(bbox_result)):
                if len(bbox_result[j]) <= 0:
                    continue
                w, h = compose.transforms[1].base_win
                keep_idx = []
                for _, b in enumerate(bbox_result[j]):
                    if 0 <= b[0] and b[2] <= w and 0 <= b[1] and b[3] <= h:
                        keep_idx.append(_)
                bbox_result[j] = bbox_result[j][keep_idx]
                if 'slice_roi__left_top' in result:
                    bbox_result[j][:, 0] += result['slice_roi__left_top'][0]
                    bbox_result[j][:, 1] += result['slice_roi__left_top'][1]
                    bbox_result[j][:, 2] += result['slice_roi__left_top'][0]
                    bbox_result[j][:, 3] += result['slice_roi__left_top'][1]
                if 'slice_image__window' in result:
                    bbox_result[j][:, 0] += result['slice_image__window'][0]
                    bbox_result[j][:, 1] += result['slice_image__window'][1]
                    bbox_result[j][:, 2] += result['slice_image__window'][0]
                    bbox_result[j][:, 3] += result['slice_image__window'][1]
                x = np.array([[j] * len(bbox_result[j])])
                bbox_result[j] = np.concatenate([bbox_result[j], x.T], axis=1)
                win_bboxes = np.append(win_bboxes, bbox_result[j], axis=0)
            keep = np.argsort(-win_bboxes[:, 4])[:slice_num]
            win_bboxes = win_bboxes[keep]
            # plt_bbox(result['img'], win_bboxes[:, :4], win_bboxes[:, 5], idx)
            idx += 1
            img_bboxes = np.append(img_bboxes, win_bboxes, axis=0)
        img_bboxes[:, 0] = img_bboxes[:, 0] / compose.transforms[1].resize[0]
        img_bboxes[:, 1] = img_bboxes[:, 1] / compose.transforms[1].resize[1]
        img_bboxes[:, 2] = img_bboxes[:, 2] / compose.transforms[1].resize[0]
        img_bboxes[:, 3] = img_bboxes[:, 3] / compose.transforms[1].resize[1]
        mst_bboxes = np.append(mst_bboxes, img_bboxes, axis=0)
    if len(mst_bboxes) < 1:
        return save_results

    mst_bboxes = torch.from_numpy(mst_bboxes).float().cuda()
    bboxes = mst_bboxes[:, :4].contiguous()
    scores = mst_bboxes[:, 4].contiguous()
    labels = (mst_bboxes[:, 5].long() + 1).contiguous()
    bboxes, keep = batched_nms(bboxes, scores, labels, nms_cfg=config.model.cfg.test_cfg.rcnn.nms)
    labels = labels[keep]
    bboxes = bboxes.cpu().numpy()
    for r, label in zip(bboxes, labels):
        bbox = list(map(float, r[:4]))
        if int(label) not in config.label2name:
            continue
        category_id, score = config.label2name[int(label)], r[4]
        save_results['result'].append({
            'image_id': config.fname2id[str(image['filename'])],
            'category_id': int(category_id),
            'bbox_left': bbox[0],
            'bbox_top': bbox[1],
            'bbox_width': bbox[2] - bbox[0],
            'bbox_height': bbox[3] - bbox[1],
            'score': float(score)
        })

    end = time.time()
    print('second/img: {:.2f}'.format(end - kwargs['time']['start']))
    kwargs['time']['start'] = end
    return save_results


def parallel_infer():
    config = Config()
    if not os.path.exists(os.path.dirname(config.save_file)):
        os.makedirs(os.path.dirname(config.save_file))
    process_params = dict(config=config, time=dict(start=time.time()))
    settings = dict(tasks=config.original_coco.dataset['images'],
                    process=process, collect=['result'], workers_num=1,
                    process_params=process_params, print_process=1)
    parallel = Parallel(**settings)
    start = time.time()
    results = parallel()
    end = time.time()
    print('times: {} s'.format(end - start))
    with open(config.save_file, "w") as fp:
        json.dump(results['result'], fp, indent=4, ensure_ascii=False)
    print("process ok!")


if __name__ == '__main__':
    parallel_infer()
