import requests
import re
import os


headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}


def get_desks(query, page=1):
    api_url = "https://ohou.se/productions/feed.json"
    params = {
        "v": 7,
        "query": query,
        "search_affect_type": "CuratedLink",
        "page": page,
        "per": 20
    }

    response = requests.get(api_url, params=params, headers=headers)
    if response.status_code != 200:
        raise Exception("Failed to fetch data")

    desks = []
    fetched_desks = response.json()["productions"]
    for fetched_desk in fetched_desks:
        desks.append(
            {
                "id": fetched_desk["id"],
                "name": fetched_desk["name"],
                "image_url": fetched_desk["original_image_url"]
            }
        )
    return desks


if __name__ == "__main__":
    def sanitize_filename(filename):
        sanitized_filename = re.sub(r'[\/\\\:\*\?\"\<\>\|]', '_', filename)
        sanitized_filename = ''.join(c for c in sanitized_filename if c.isprintable())
        return sanitized_filename.replace(" ", "_")
    

    def download_image(url, file_name, download_folder):
        response = requests.get(url)
        if response.status_code == 200:
            with open(f"./{download_folder}/{file_name}.png", 'wb') as f:
                f.write(response.content)


    base_download_folder = "image"
    query = "컴퓨터책상"
    download_folder = f"{base_download_folder}/{query}"

    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    for page in range(1, 2):
        desks = get_desks(query, page=page)
        for desk in desks:
            download_image(desk["image_url"], sanitize_filename(desk["name"]), download_folder)
    