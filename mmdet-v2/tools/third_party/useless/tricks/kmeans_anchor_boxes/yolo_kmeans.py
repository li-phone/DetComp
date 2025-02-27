import glob
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import numpy as np
import os
import seaborn as sns

try:
    from .kmeans import kmeans, avg_iou
except:
    from kmeans import kmeans, avg_iou

ANNOTATIONS_PATH = "Annotations"
CLUSTERS = 5


def load_dataset(path):
    dataset = []
    for xml_file in glob.glob("{}/*xml".format(path)):
        tree = ET.parse(xml_file)

        height = int(tree.findtext("./size/height"))
        width = int(tree.findtext("./size/width"))

        for obj in tree.iter("object"):
            xmin = int(obj.findtext("bndbox/xmin")) / width
            ymin = int(obj.findtext("bndbox/ymin")) / height
            xmax = int(obj.findtext("bndbox/xmax")) / width
            ymax = int(obj.findtext("bndbox/ymax")) / height

            dataset.append([xmax - xmin, ymax - ymin])

    return np.array(dataset)


def pascalvoc_example():
    data = load_dataset(ANNOTATIONS_PATH)
    out = kmeans(data, k=CLUSTERS)
    print("Accuracy: {:.2f}%".format(avg_iou(data, out) * 100))
    print("Boxes:\n {}".format(out))

    ratios = np.around(out[:, 0] / out[:, 1], decimals=2).tolist()
    print("Ratios:\n {}".format(sorted(ratios)))


def coco_kmeans(coco, k=7):
    if isinstance(coco, str):
        from pycocotools.coco import COCO
        coco = COCO(coco)
    data = coco.dataset['annotations']
    data = [b['bbox'] for b in data]
    data = np.asarray(data)
    data = data[:, 2:]
    out = kmeans(data, k=k)
    acc = avg_iou(data, out) * 100
    print("Accuracy: {:.2f}%".format(acc))
    print("Boxes:\n {}".format(out))
    ratios = np.around(out[:, 1] / out[:, 0], decimals=2).tolist()
    print("Ratios:\n {}".format(sorted(ratios)))
    return ratios, acc, out

    # [32, 64, 128, 256, 512]

    # Accuracy: 71.93%
    # Boxes:
    #  [[152.51712 130.12326]
    #  [ 94.60224 184.40136]
    #  [280.89696 144.4608 ]
    #  [320.68992 273.08016]
    #  [ 44.7216   44.09316]
    #  [ 92.9712   85.90104]
    #  [197.2656  216.93204]
    #  [461.65824 455.80698]
    #  [220.8288  354.62232]]
    # Ratios:
    #  [0.51, 0.62, 0.91, 1.01, 1.01, 1.08, 1.17, 1.17, 1.94]


def save_plt(save_name, file_types=None):
    if file_types is None:
        file_types = ['.svg', '.jpg', '.eps']
    save_dir = save_name[:save_name.rfind('/')]
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    for t in file_types:
        plt.savefig(save_name[:-4] + t)


def main():
    import pandas as pd
    from tqdm import tqdm
    ks, accs = [], []
    for i in tqdm(range(1, 11)):
        print('-' * 64)
        ratios, acc, out = coco_kmeans(
            '../../../../data/track/annotations/overlap_70_all_category/instance_val.json', k=i)
        ks.append(i)
        accs.append(acc)
    acc_df = pd.DataFrame(data={'k': ks, 'avg_iou': accs})
    ax = acc_df.plot.line(
        x='k', y='avg_iou', marker='^',
        grid=True, xlim=(1, 10), ylim=(0., 100.))
    plt.ylabel('avg_iou')
    save_plt('./results/track/k-means_cluster/k-means_cluster.jpg')
    plt.show()


if __name__ == "__main__":
    main()
