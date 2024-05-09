import os
import numpy as np
from PIL import Image
from tqdm import tqdm

import torch
import torchvision.transforms as transforms

from ultralytics import YOLO
from config_loader import config


class Img2Vec:
    def get_vector(self, image_path):
        return self.get_vectors([image_path])[0]

    def get_vectors(self, image_paths): ...


class Feat2Vec(Img2Vec):
    def __init__(self, model, transform=None, batch_size=32, resize=(256, 256), verbose=False):
        self.batch_size = batch_size
        self.verbose = verbose
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.model = model
        self.model.to(self.device)
        self.model.eval()

        if transform:
            self.preprocess = transform
        else:
            self.preprocess = transforms.Compose([
                transforms.Resize(resize),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])

    def get_vectors(self, image_paths):
        iterator = range(0, len(image_paths), self.batch_size)
        if self.verbose:
            iterator = tqdm(iterator)

        vectors = []
        for i in iterator:
            batch_image_paths = image_paths[i : i + self.batch_size]
            batch_images = torch.stack([
                    self.preprocess(Image.open(path).convert("RGB")).to(self.device)
                    for path in batch_image_paths
            ])

            with torch.no_grad():
                batch_vectors = self.model(batch_images)
                batch_vectors = batch_vectors.flatten(start_dim=1)
            vectors.extend(batch_vectors.cpu())

        vectors = np.array(vectors)
        vectors /= np.linalg.norm(vectors, axis=1)[:, np.newaxis]
        return vectors


class Obj2Vec(Img2Vec):
    def __init__(self, conf_threshold=0.25, verbose=False):
        self.conf_threshold = conf_threshold
        self.verbose = verbose
        self.model = YOLO("yolov8x.pt")
        self.classes = [41, 56, 58, 59, 60, 62, 63, 64, 66, 73, 74, 75]
        self.cls_to_idx = {x: i for i, x in enumerate(self.classes)}

    def get_vectors(self, image_paths):
        iterator = image_paths
        if self.verbose:
            iterator = tqdm(iterator)

        vectors = []
        for image_path in iterator:
            result = self.model(
                image_path,
                conf=self.conf_threshold,
                classes=self.classes,
                verbose=False,
            )
            counter = [0] * len(self.classes)

            for box in result[0].boxes:
                counter[self.cls_to_idx[box.cls.item()]] += 1
            vectors.append(counter)

        vectors = np.array(vectors.cpu(), dtype=np.float32)
        return vectors


class Color2Vec(Img2Vec):
    def __init__(self, verbose=False):
        super().__init__()
        self.verbose = verbose

    def get_vectors(self, image_paths):
        iterator = image_paths
        if self.verbose:
            iterator = tqdm(iterator)

        vectors = []
        for image_path in iterator:
            image = Image.open(image_path)
            image = image.resize((256, 256))
            image_arr = np.array(image)
            pixels = image_arr.reshape(-1, 3)

            hist_r, _ = np.histogram(pixels[:, 0], bins=256, range=(0, 255))
            hist_g, _ = np.histogram(pixels[:, 1], bins=256, range=(0, 255))
            hist_b, _ = np.histogram(pixels[:, 2], bins=256, range=(0, 255))

            num_pixels = int(image.width * image.height)
            hist_r = hist_r / num_pixels
            hist_g = hist_g / num_pixels
            hist_b = hist_b / num_pixels
            vectors.append(np.concatenate((hist_r, hist_g, hist_b)))

        return vectors


if __name__ == "__main__":
    import faiss

    # def save_vectors(vectors, file_path):
    #     d = vectors.shape[1]
    #     index = faiss.IndexFlatL2(d)
    #     index.add(vectors)
    #     faiss.write_index(index, file_path)

    # # how to use Feature to Vector
    # feature_extractor = Feat2Vec(verbose=True)

    # image_dir = config["PATH"]["train"]
    # image_paths = [
    #     os.path.join(image_dir, file_name) for file_name in os.listdir(image_dir)
    # ]
    # vectors = feature_extractor.get_vectors(image_paths)
    # save_vectors(vectors, "vectors/vgg_features.index")

    # # how to use Object to Vector
    # object_counter = Obj2Vec(verbose=True)

    # image_dir = config["PATH"]["train"]
    # image_paths = [
    #     os.path.join(image_dir, file_name) for file_name in os.listdir(image_dir)
    # ]
    # vectors = object_counter.get_vectors(image_paths)
    # save_vectors(vectors, "vectors/object_counts.index")

    dir_path = "images/train/28070000"
    image_paths = [
        os.path.join(dir_path, image_name) for image_name in os.listdir(dir_path)
    ]

    color2vec = Color2Vec()
    vectors = color2vec.get_vectors(image_paths)
