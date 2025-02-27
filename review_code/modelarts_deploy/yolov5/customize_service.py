# -*- coding: utf-8 -*-
import os
import time
import torch
import numpy as np
from PIL import Image

# modelarts import
try:
    import log
    from metric.metrics_manager import MetricsManager
    from model_service.pytorch_model_service import PTServingBaseService

    logger = log.getLogger(__name__)
except:
    print('model_service error!')

from inference import init_detector, inference_detector
import config


class ObjectDetectionService(PTServingBaseService):
    def __init__(self, model_name=None, model_path=None):
        if torch.cuda.is_available() is True:
            device = 'cuda:0'
            print('use torch GPU version,', torch.__version__)
        else:
            device = 'cpu'
            print('use torch CPU version,', torch.__version__)
        print('model_name:', model_name, ', model_path', model_path)

        self.cfg = config.cfg
        self.model_path = config.model_path
        self.cat2label = config.cat2label
        self.model_name = os.path.basename(self.cfg[:-3])
        print('starting init detector model...')
        print('cfg: ', self.cfg, 'model_path:', self.model_path)
        self.model, modelc = init_detector(self.model_path, device='cpu')
        print('load weights file success')

    def _preprocess(self, data):
        preprocessed_data = {}
        for k, v in data.items():
            for file_name, file_content in v.items():
                # image = Image.open(file_content)
                # image = np.array(image)
                preprocessed_data[k] = file_content
        return preprocessed_data

    def _inference(self, data):
        """
        model inference function
        Here are a inference example of resnet, if you use another model, please modify this function
        """
        images = data

        results = dict(detection_classes=[], detection_scores=[], detection_boxes=[])
        # import cv2 as cv
        for img_id, file_content in images.items():
            image = Image.open(file_content)
            image = np.array(image)
            result = inference_detector(self.model, image, conf_thres=0.001, device='cpu')  # list for image results
            for i, v1 in enumerate(result):
                if v1[0] is None:
                    continue
                v2 = v1[0].numpy()
                for j, v3 in enumerate(v2):
                    box, score, cat = list(map(float, v3[:4])), float(v3[4]), int(v3[5]) + 1
                    label = self.cat2label[cat]['supercategory'] + '/' + self.cat2label[cat]['name']
                    results['detection_classes'].append(label)
                    results['detection_scores'].append(round(score, 4))
                    bbox = [round(_, 1) for _ in box]
                    results['detection_boxes'].append(bbox)

            #         image = image[:, :, ::-1]  # BGR to RGB, to 3x416x416
            #         image = np.array(image)
            #         pt1 = (int(bbox[0]), int(bbox[1]))
            #         pt2 = (int(bbox[2]), int(bbox[3]))
            #         cv.rectangle(image, pt1, pt2, color=(0, 0, 255))
            #         _x = int((pt1[0] + pt2[0]) / 2)
            #         _y = int((pt1[1] + pt2[1]) / 2)
            #         cv.putText(image, str(cat), (_x, _y), cv.FONT_HERSHEY_COMPLEX, 1, (0, 0, 255), 2)
            # cv.imshow('', image)
            # cv.waitKey()
        return results

    def _postprocess(self, data):
        return data

    def inference(self, data):
        '''
        Wrapper function to run preprocess, inference and postprocess functions.

        Parameters
        ----------
        data : map of object

            Raw input from request.

        Returns
        -------
        list of outputs to be sent back to client.
            data to be sent back
        '''
        pre_start_time = time.time()
        data = self._preprocess(data)
        infer_start_time = time.time()
        # Update preprocess latency metric
        pre_time_in_ms = (infer_start_time - pre_start_time) * 1000
        logger.info('preprocess time: ' + str(pre_time_in_ms) + 'ms')

        if self.model_name + '_LatencyPreprocess' in MetricsManager.metrics:
            MetricsManager.metrics[self.model_name + '_LatencyPreprocess'].update(pre_time_in_ms)

        data = self._inference(data)
        infer_end_time = time.time()
        infer_in_ms = (infer_end_time - infer_start_time) * 1000

        logger.info('infer time: ' + str(infer_in_ms) + 'ms')
        data = self._postprocess(data)

        # Update inference latency metric
        post_time_in_ms = (time.time() - infer_end_time) * 1000
        logger.info('postprocess time: ' + str(post_time_in_ms) + 'ms')
        if self.model_name + '_LatencyInference' in MetricsManager.metrics:
            MetricsManager.metrics[self.model_name + '_LatencyInference'].update(post_time_in_ms)

        # Update overall latency metric
        if self.model_name + '_LatencyOverall' in MetricsManager.metrics:
            MetricsManager.metrics[self.model_name + '_LatencyOverall'].update(pre_time_in_ms + post_time_in_ms)

        logger.info('latency: ' + str(pre_time_in_ms + infer_in_ms + post_time_in_ms) + 'ms')
        data['latency_time'] = str(round(pre_time_in_ms + infer_in_ms + post_time_in_ms, 1)) + ' ms'
        return data

    def local_run(self):
        from glob import glob
        from tqdm import tqdm
        paths = glob('/home/liphone/undone-work/data/detection/garbage_huawei/images/*')
        avg_times = []
        for i, p in tqdm(enumerate(paths[:20])):
            data = {str(i): {'file_name': p}}
            start_time = time.time()
            data = self._preprocess(data)
            data = self._inference(data)
            data = self._postprocess(data)
            end_time = time.time()
            time_in_ms = (end_time - start_time) * 1000
            avg_times.append(time_in_ms)
            data['latency_time'] = str(round(time_in_ms, 1)) + ' ms'
            for k, v in data.items():
                print(k, ':', v)
        print('avg time: {:.2f} ms'.format(np.mean(avg_times)))


if __name__ == '__main__':
    ObjectDetectionService().local_run()
