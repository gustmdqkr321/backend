import os
import re
import requests
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

import queue
import threading
from io import BytesIO

from mimetypes import guess_extension
import numpy as np
from PIL import Image
import cv2
from pillow_heif import register_heif_opener

from sqlalchemy.orm import scoped_session
from database.database import SessionLocal, engine
from database.models import Base, DesignImages, ItemImages


Base.metadata.create_all(bind=engine)


def create_retry_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session
                  

class BaseCrawler:
    def __init__(self, path, prefix, num_workers, resize, verbose):
        register_heif_opener()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        self.finished = False
        self.num_progressed = 0
        self.queue = queue.Queue()
        self.lock = threading.Lock()

        self.prefix = prefix
        self.num_workers = num_workers
        self.verbose = verbose
        self.path = path
        self.resize = resize
        os.makedirs(self.path, exist_ok=True)
        
        self.get_session = scoped_session(SessionLocal)

    def crawling(self):
        self.num_progressed = 0
        
        producer_thread = threading.Thread(target=self.producer)
        consumer_threads = []
        for _ in range(self.num_workers):
            consumer_threads.append(threading.Thread(target=self.consumer))
        
        producer_thread.start()
        for consumer_thread in consumer_threads:
            consumer_thread.start()
        
        producer_thread.join()
        for consumer_thread in consumer_threads:
            consumer_thread.join()
        
        if self.verbose:
            print(f"total {self.num_progressed} images downloaded")
    
    def producer(self):
        ...
    
    def consumer(self):
        while True:
            self.lock.acquire()
            if not self.queue.empty():
                image = self.queue.get()
                self.lock.release()
                ret = self.download_image(image)

                if self.verbose and ret:
                    with self.lock:
                        self.num_progressed += 1
                        print(f"Progressed {self.num_progressed} images", end="\r")
            else:
                self.lock.release()
                
                if self.finished:
                    break

    def download_image(self, image):
        url = image["src_url"]
        filename = self.sanitize_filename(image["filename"])

        session = create_retry_session()
        response = session.get(url)
        if response.status_code != 200:
            return False

        file_extension = guess_extension(response.headers.get("content-type"))
        image_data = response.content

        if file_extension is None:
            return False

        image_data = self.validate_image_data(image_data)
        if not image_data:
            return False

        file_extension = ".jpg"
        image["filename"] = self.prefix + "_" + filename + file_extension
        image_data.save(os.path.join(self.path, image["filename"]))

        ret = self.to_db(image)
        return ret
    

    def sanitize_filename(self, filename):
        sanitized_filename = re.sub(r"[\/\\\:\*\?\"\<\>\|\s]", "_", filename)
        sanitized_filename = "".join(c for c in sanitized_filename if c.isprintable())
        return sanitized_filename
    
    def validate_image_data(self, image_data):
        try:
            image = Image.open(BytesIO(image_data))
            pixels = image.load()
            image = image.convert("RGB")
            if self.resize:
                image = image.resize(self.resize)
            
            return image
        except:
            return None
    
    def to_db(self, image):
        try:
            design_image = DesignImages(**image)
            session = self.get_session()
            session.add(design_image)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            return False
        

class OhouseCrawler(BaseCrawler):
    def __init__(self, path, query, style=None, num_workers=8, resize=None, verbose=False):
        super().__init__(path, "ohouse", num_workers, resize, verbose)
        self.query = query
        self.style = style
        self.api_url = "https://ohou.se/cards/feed.json"

    def producer(self):
        page = 1
        while not self.finished:
            desks = self.fetch_desks(page)
            with self.lock:
                for desk in desks:
                    self.queue.put(desk)
            page += 1

    def fetch_desks(self, page):
        params = {
            "v": 5,
            "query": self.query,
            "search_affect_type": "Typing",
            "page": page,
            "per": 48,
        }
        if self.style:
            params["style"] = self.style

        session = create_retry_session()
        response = session.get(self.api_url, params=params, headers=self.headers)
        if response.status_code != 200:
            raise Exception("Failed to fetch data")

        desks = []
        response_data = response.json()
        fetched_desks = response_data["cards"]
        for fetched_desk in fetched_desks:
            url = fetched_desk["image"]["url"]
            if "amazon" in url:
                url = re.sub(r"\.s.*?\.com", "", url)
                url = url.replace("https://", "https://image.ohou.se/i/")
            url += "?gif=1&webp=1"
            
            desk = {
                "filename": re.search(r'/([^/]*)\.([^.]*)$', url).group(1),
                "src_url": url,
                "landing": fetched_desk["link"]["landingUrl"]
            }
            desks.append(desk)

        if not response_data["next"]:
            self.finished = True

        return desks
    

class PinterestCrawler(BaseCrawler):
    def __init__(self, path, query, num_workers=8, resize=None, verbose=False):
        super().__init__(path, "pinterest", num_workers, resize, verbose)
        self.query = query

        self.api_url = "https://pinterest.com/resource/BaseSearchResource/get/?"
        self.source_url = f"/search/pins/?q={query}"
        self.bookmark = ""

    def producer(self):
        while not self.finished:
            desks = self.fetch_desks()
            with self.lock:
                for desk in desks:
                    self.queue.put(desk)
        
    def fetch_desks(self):
        if self.bookmark == "":
            data = f'{{"options":{{"isPrefetch":false,"query":"{self.query}","scope":"pins","no_fetch_context_on_resource":false}},"context":{{}}}}'
        else:
            data = f'{{"options":{{"page_size":25,"query":"{self.query}","scope":"pins","bookmarks":["{self.bookmark}"],"field_set_key":"unauth_react","no_fetch_context_on_resource":false}},"context":{{}}}}'.strip()

        session = create_retry_session()
        response = session.get(self.api_url, params={"source_url": self.source_url, "data": data})
        if response.status_code != 200:
            raise Exception("Failed to fetch data")
        
        resource_response = response.json()["resource_response"]
        try:
            self.bookmark = resource_response["bookmark"]
        except KeyError:
            self.finished = True

        desks = []
        for fetched_desk in resource_response["data"]["results"]:
            desk = {
                "url": fetched_desk["images"]["orig"]["url"],
                "name": str(fetched_desk["id"])
            }
            desks.append(desk)
        return desks


class OhouseItemCrawler(BaseCrawler):
    def __init__(self, path, category_id, num_workers=8, resize=None, verbose=False):
        super().__init__(path, "ohouse", num_workers, resize, verbose)
        self.category_id = category_id

        self.api_url = "https://ohou.se/store/category.json"
        self.landing_url = "https://ohou.se/productions/{}/selling?affect_id&affect_type=ProductCategoryIndex"
    
    def producer(self):
        page = 1
        while not self.finished:
            desks = self.fetch_desks(page)
            with self.lock:
                for desk in desks:
                    self.queue.put(desk)
            page += 1
    
    def fetch_desks(self, page):
        params = {
            "v": 2,
            "category_id": self.category_id,
            "page": page,
            "per": 24,
        }

        session = create_retry_session()
        response = session.get(self.api_url, params=params, headers=self.headers)
        if response.status_code != 200:
            raise Exception("Failed to fetch data")

        items = []
        response_data = response.json()
        fetched_items = response_data["productions"]
        for fetched_item in fetched_items:
            url = fetched_item["original_image_url"]
            item = {
                "name": fetched_item["name"],
                "src_url": url,
                "landing": self.landing_url.format(fetched_item["id"]),
                "category_id": self.category_id
            }
            items.append(item)

        if not fetched_items:
            self.finished = True

        return items

    def download_image(self, image):
        url = image["src_url"]
        session = create_retry_session()
        response = session.get(url)
        if response.status_code != 200:
            return False

        file_extension = guess_extension(response.headers.get("content-type"))
        image_data = response.content

        if file_extension is None:
            return False

        image_data = self.validate_image_data(image_data)
        if not image_data:
            return False
        
        color = self.extract_color(image_data)
        image["color"] = color

        ret = self.to_db(image)
        return ret

    def extract_color(self, image):
        image = np.array(image)
        image = cv2.resize(image, (100, 100))
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        edges = cv2.Canny(blurred, 50, 100)
        contours, _ = cv2.findContours(edges.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:max(1, len(contours)//2)]

        mask = np.zeros_like(gray)
        for contour in contours:
            cv2.drawContours(mask, [contour], -1, 255, -1)

        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        image_without_bg = cv2.bitwise_and(image, image, mask=mask)

        colors = image_without_bg[image_without_bg.sum(axis=2) != 0]
        main_color = np.median(colors, axis=0).astype(np.uint8)
        return main_color

    def to_db(self, image):
        try:
            item_image = ItemImages(**image)
            session = self.get_session()
            session.add(item_image)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            return False


if __name__ == "__main__":

    from config_loader import config

    path = config["PATH"]["train"]
    os.makedirs(path, exist_ok=True)

    # # styles = ["모던", "북유럽", "빈티지", "내추럴", "프로방스&로맨틱", "클래식&앤틱", "한국&아시아", "유니크"]
    # # for i, style in enumerate(styles):
    # #     desk_crawler = OhouseCrawler(path, "데스크테리어", style=i, verbose=True, resize=(224, 224))
    # #     desk_crawler.crawling()

    # # desk_crawler = PinterestCrawler(train_path, "desk interior", verbose=True)

    categories = ["28070000"]
    for category_id in categories:
        path = os.path.join(path, category_id)
        item_crawler = OhouseItemCrawler(path, category_id, verbose=True)
        item_crawler.crawling()

    # image_url = "https://bucketplace-v2-development.s3.amazonaws.com/uploads/productions/168076630197287303.jpg"
    # session = create_retry_session()
    # response = session.get(image_url)

    # image_data = response.content
    # image = Image.open(BytesIO(image_data))
    # pixels = image.load()
    # image = image.convert("RGB")
    # image_data = image_data

    # image = np.array(image)
    # image = cv2.resize(image, (100, 100))
    # gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    # blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # edges = cv2.Canny(blurred, 50, 100)
    # contours, _ = cv2.findContours(edges.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # print(len(contours))
    # contours = sorted(contours, key=cv2.contourArea, reverse=True)[:max(1, len(contours)//2)]

    # mask = np.zeros_like(gray)
    # for contour in contours:
    #     cv2.drawContours(mask, [contour], -1, 255, -1)

    # kernel = np.ones((5, 5), np.uint8)
    # mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    # image_without_bg = cv2.bitwise_and(image, image, mask=mask)

    # colors = image_without_bg[image_without_bg.sum(axis=2) != 0]
    # main_color = np.median(colors, axis=0).astype(np.uint8)
    # print(main_color)