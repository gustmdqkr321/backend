import os
import faiss
import numpy as np
import cv2
from fastapi import APIRouter, UploadFile, Depends

from sqlalchemy.orm import Session

from database import crud
from database.models import *
from database.schemas import *
from img2vec import Feat2Vec

from models.VGGAutoEncoder import LightVGGAutoEncoder
import torchvision.models as models

from dependencies import *


router = APIRouter(
    prefix="/recommend",
    tags=["recommend"]
)


@router.get("/sample", response_model=list[DesignImage])
async def get_images_to_rate(n: int = 5, db: Session = Depends(get_db)):
    return await crud.read_random_design_images(db, n)


@router.post("/preference_before", response_model=list[DesignImage])
async def recommend_by_preference(rated_images: list[RatedImage], user_id: str = Depends(get_current_user), db: Session = Depends(get_db)):
    feat_idx = faiss.read_index("vectors/features.index")

    weighted_vectors = []
    weight_mapping = [-0.2, 0.2, 1.0, 1.2, 2.0]

    weights = 0
    for rated_image in rated_images:
        vector = feat_idx.reconstruct(rated_image.index)
        weight = weight_mapping[rated_image.rating-1]
        weighted_vectors.append(weight * vector)
        weights += weight
    weighted_vector = np.mean(weighted_vectors, axis=0)

    user = await crud.read_user_by_id(db, user_id)
    user_vector = user.embedding
    user_vector = None

    user_vector = weighted_vector if user_vector is None else (user_vector + weighted_vector) * 0.5
    user.embedding = user_vector
    db.commit()

    design_images = []
    _, feat_result = feat_idx.search(np.expand_dims(user_vector, axis=0), 5)
    for i in feat_result[0]:
        design_image = await crud.read_design_images(db, int(i))
        design_images.append(design_image)

    return design_images


@router.post("/preference", response_model=list[DesignImage])
async def recommend_by_preference2(rated_images: list[RatedImage], user_id: str = Depends(get_current_user), db: Session = Depends(get_db)):
    feature_mat = np.load("vectors/features.npy")
    query_mat = feature_mat[np.array([rated_image.index for rated_image in rated_images])]
    preference_mat = np.array([[rated_image.rating for rated_image in rated_images]])

    similarity_mat = query_mat @ feature_mat.T
    result_mat = preference_mat @ similarity_mat

    design_images = []
    for i in result_mat[0].argsort()[-1:-6:-1]:
        design_image = await crud.read_design_images(db, int(i))
        design_images.append(design_image)
    
    return design_images


@router.post("/image", response_model=list[DesignImage])
async def recommend_by_source_image(file: UploadFile, user_id: str = Depends(get_current_user), db: Session = Depends(get_db)):
    file_path = os.path.join(config["PATH"]["upload"], file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # autoencoder = LightVGGAutoEncoder.load_from_checkpoint(config["PATH"]["model"])
    # encoder = autoencoder.model.encoder
    model = models.vgg16(weights=models.VGG16_Weights.DEFAULT)
    model.classifier = model.classifier[:-1]
    feat2vec = Feat2Vec(model, resize=(224, 224))
    query_vec = feat2vec.get_vector(file_path)

    feature_mat = np.load("vectors/features.npy")
    query_mat = query_vec.reshape(1, -1)
    similarity_mat = query_mat @ feature_mat.T

    design_images = []
    for i in similarity_mat[0].argsort()[-1:-6:-1]:
        design_image = await crud.read_design_images(db, int(i))
        design_images.append(design_image)
    
    return design_images

    # feat_idx = faiss.read_index("vectors/features.index")
    # design_images = []
    # _, feat_result = feat_idx.search(np.expand_dims(feat_vec, axis=0), 5)
    # for i in feat_result[0]:
    #     design_image = await crud.read_design_images(db, int(i))
    #     design_images.append(design_image)
    
    # return design_images


import requests
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter


@router.get("/item")
async def recoomend_items_by_color(index: int, user_id: str = Depends(get_current_user), db: Session = Depends(get_db)):
    image = await crud.read_design_images(db, index)
    url = image.src_url

    session = requests.Session()
    retries = Retry(total=5, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))

    response = session.get(url)
    if response.status_code != 200:
        raise Exception("Failed to fetch data")
    
    image_array = np.frombuffer(response.content, np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    image = cv2.resize(image, (200, 200), interpolation=cv2.INTER_AREA)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    pixels = image.reshape(-1, 3)
    pixels = np.float32(pixels)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
    _, labels, centers = cv2.kmeans(pixels, 5, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)

    colors = np.uint8(centers)
    result = []
    for color in colors:
        color = color.tolist()
        items = await crud.read_item_images(db, color)
        result.append({
            "color": '#{:02x}{:02x}{:02x}'.format(*color),
            "items": [ItemImage.model_validate(item) for item in items]
        })
    
    return result