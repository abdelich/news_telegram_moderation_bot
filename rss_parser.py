from helpers import get_next_id
import csv
import os
import feedparser
import requests
from bs4 import BeautifulSoup
import logging as logger
from PIL import Image
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPM


class RSS_Parser:
    """
    Парсит RSS каналы и возвращает новость в формате:
    {id, type:rss, txt, img, src:url, src_name}
    """

    def parse(self, rss_url):
        rss = feedparser.parse(rss_url)
        results = []

        for item in rss.entries[:1]:
            article_data = {
                "id": get_next_id(),
                "type": "rss",
                "txt": None,
                "img": None,
                "src": rss_url,
                "src_name": rss.feed.get("title", "Unknown")
            }

            try:

                response = requests.get(item.link)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')

                article_body = soup.find('article') or soup.find('div', {'class': 'story-body'})
                if article_body:
                    paragraphs = article_body.find_all('p')
                    full_text = "\n".join([p.get_text() for p in paragraphs])
                    clean_text = " ".join(full_text.split())
                    if len(clean_text) > 1024:
                        clean_text = clean_text[:1024]
                    article_data["txt"] = clean_text

                img_url = None

                if hasattr(item, 'media_content') and item.media_content:
                    img_url = item.media_content[0].get("url", None)

                if not img_url and "description" in item:
                    soup_desc = BeautifulSoup(item["description"], 'html.parser')
                    img_tag = soup_desc.find("img")
                    if img_tag and img_tag.get("src"):
                        img_url = img_tag["src"]

                if not img_url:
                    img_tag = soup.find("img")
                    if img_tag and img_tag.get("src"):
                        img_url = img_tag["src"]

                if img_url:
                    img_path = self.save_image(img_url, article_data["id"])
                    article_data["img"] = img_path if img_path and isinstance(img_path, str) else None

            except requests.RequestException as e:
                logger.error(f"Ошибка загрузки страницы: {e}")

            if article_data["txt"]:
                results.append(article_data)

        return results

    def convert_svg_to_png(self, svg_path, output_path):
        """
        Convert SVG to PNG using svglib and Pillow.
        """
        try:

            drawing = svg2rlg(svg_path)
            img = renderPM.drawToPIL(drawing)

            img.save(output_path, format="PNG")
            logger.info(f"SVG converted to PNG: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to convert SVG to PNG: {e}")
            return None

    def save_image(self, img_url, news_id):
        try:

            img_extension = os.path.splitext(img_url.split("?")[0])[-1].lower()
            img_filename = f"images/{news_id}{img_extension}"

            if not os.path.exists("images"):
                os.makedirs("images")

            img_response = requests.get(img_url, timeout=10)
            img_response.raise_for_status()

            with open(img_filename, 'wb') as f:
                f.write(img_response.content)

            if img_extension == ".webp":
                png_filename = f"images/{news_id}.png"
                with Image.open(img_filename) as img:
                    img = img.convert("RGBA")
                    img.save(png_filename, format="PNG")
                os.remove(img_filename)
                logger.info(f"WEBP image converted to PNG: {png_filename}")
                return png_filename

            if img_extension == ".svg":
                png_filename = f"images/{news_id}.png"
                return self.convert_svg_to_png(img_filename, png_filename)

            return img_filename

        except requests.RequestException as e:
            logger.error(f"Failed to save image from URL {img_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to process image {img_url}: {e}")
            return None


class DatabaseHandler:
    def __init__(self, db_file):
        self.db_file = db_file

        if not os.path.exists(db_file):
            self.create_db()

    def create_db(self):
        """
        Создает новый файл базы данных с заголовками.
        """
        with open(self.db_file, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(["ID", "URL", "TYPE"])
        print(f"Файл {self.db_file} был успешно создан.")

    def read_db(self):
        """
        Читает файл базы данных и возвращает все записи.
        :return: Список всех каналов из базы данных.
        """
        channels = []
        try:
            with open(self.db_file, mode='r', encoding='utf-8') as file:
                reader = csv.reader(file)
                next(reader)
                for row in reader:
                    if len(row) == 3:
                        channels.append(row)
        except Exception as e:
            print(f"Ошибка при чтении базы данных: {e}")
        return channels


class NewsFetcher:
    def __init__(self):
        self.rss_parser = RSS_Parser()

    def create_rss_output_file(self, rss_db_file):
        """
        Создает новый файл для добавления новостей из RSS.
        """
        with open(rss_db_file, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(["ID", "TYPE", "TXT", "IMG", "SRC", "SRC_NAME"])
        print(f"Файл {rss_db_file} был успешно создан.")

    def fetch_new_rss_news(self, rss_urls, rss_db_file):
        new_posts = []

        if not os.path.exists(rss_db_file):
            self.create_rss_output_file(rss_db_file)

        for rss_url in rss_urls:
            print(f"Обрабатываем RSS канал: {rss_url}")
            posts = self.rss_parser.parse(rss_url)
            for post in posts:
                if post["txt"] and post["txt"].strip():
                    if not self.is_post_already_added(post["txt"], rss_db_file):
                        new_posts.append(post)
                        self.add_to_rss_output_file(post, rss_db_file)
        return new_posts

    def add_to_rss_output_file(self, post_data, rss_db_file):
        """
        Добавляет новую новость в файл RSS.
        """
        try:
            with open(rss_db_file, mode='a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow([post_data["id"], post_data["type"], post_data["txt"], post_data["img"], post_data["src"], post_data["src_name"]])
            print(f"Новость с текстом: \"{post_data['txt']}\" добавлена в {rss_db_file}.")
        except Exception as e:
            print(f"Ошибка при добавлении новости в файл: {e}")

    def is_post_already_added(self, post_text, rss_db_file):
        try:
            with open(rss_db_file, mode='r', encoding='utf-8') as file:
                reader = csv.reader(file)
                next(reader)
                for row in reader:
                    if len(row) > 2 and row[2] == post_text:
                        print(f"Новость уже добавлена: {post_text}")
                        return True
            return False
        except Exception as e:
            print(f"Ошибка при проверке файла: {e}")
            return False
