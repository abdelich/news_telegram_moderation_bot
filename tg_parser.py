import csv
import os

from telethon import TelegramClient

from helpers import get_next_id


class TelegramParser:
    def __init__(self, api_id, api_hash):
        self.client = TelegramClient('parser_session', api_id, api_hash)
        self.start()

    async def start(self):
        if not self.client.is_connected():
            await self.client.connect()
        if not await self.client.is_user_authorized():
            await self.authorize()

    async def stop(self):
        if self.client.is_connected():
            await self.client.disconnect()

    async def check_connection(self):
        try:
            await self.client.connect()
            if not await self.client.is_user_authorized():
                print("Не авторизован! Нужно выполнить авторизацию.")
                return False
            print("Авторизация успешна!")
            return True
        except Exception as e:
            print(f"Ошибка подключения: {e}")
            return False

    async def authorize(self):
        if await self.client.is_user_authorized():
            print("Уже авторизован.")
            return
        phone_number = input("Введите номер телефона в формате +1234567890: ")
        try:
            print("Отправляем код для авторизации...")
            await self.client.send_code_request(phone_number)
            code = input("Введите код из Telegram: ")
            await self.client.sign_in(phone_number, code)
            print("Авторизация завершена.")
        except Exception as e:
            print(f"Ошибка авторизации: {e}")

    async def get_last_post(self, channel_link, timeout=10):
        try:
            if not self.client.is_connected():
                await self.client.connect()
            if not await self.client.is_user_authorized():
                await self.authorize()

            print(f"Запрашиваем последние сообщения из канала: {channel_link}")
            if not await self.client.is_user_authorized():
                await self.authorize()

            print("Подключаемся к Telegram...")
            if not self.client.is_connected():
                await self.client.connect()
            print("Подключение установлено.")

            if not channel_link.startswith("https://"):
                channel_link = "https://" + channel_link

            if channel_link.startswith("https://t.me/"):
                channel_username = channel_link.split("/")[-1]
            else:
                channel_username = channel_link

            print(f"Запрашиваем последние сообщения из канала: {channel_username}...")

            message = (await self.client.get_messages(channel_username, limit=1))[0]

            post_data = {
                "id": get_next_id(),
                "type": "tg",
                "txt": self.format_text(message.text),
                "img": None,
                "src": channel_link,
                "src_name": message.chat.title if message.chat else "Unknown"
            }

            if message.photo:
                try:

                    image_path = await self.client.download_media(message.photo,
                                                                  file="images/")
                    post_data["img"] = image_path
                    print(f"Фото сохранено в {image_path}")
                except Exception as e:
                    print(f"Ошибка загрузки фото: {e}")
                    post_data["img"] = None

            print("Последнее сообщение успешно получено.")
            return post_data

        except Exception as e:
            print(f"Ошибка: {e}")
            return None

    def format_text(self, text):
        """
        Форматирует текст новости, оставляя только первые 1024 символа.
        """
        if not text:
            return ""
        formatted_text = text.replace("\n", " ").strip()
        if len(formatted_text) > 1024:
            formatted_text = formatted_text[:1024]
        return formatted_text

    async def fetch_new_telegram_news(self, tg_urls, tg_db_file):
        new_posts = []

        if not os.path.exists(tg_db_file):
            self.create_tg_db(tg_db_file)

        for channel_link in tg_urls:
            print(f"Обрабатываем Telegram-канал: {channel_link}")

            last_post = await self.get_last_post(channel_link)
            if last_post and not self.is_post_already_added(tg_db_file, last_post["txt"]):
                new_posts.append(last_post)
                self.add_post_to_tg_db(tg_db_file, last_post)
            else:
                print(f"Новость из {channel_link} уже была добавлена ранее, пропускаем.")

        return new_posts

    def create_tg_db(self, tg_db_file):
        """
        Создает новый файл tg_db с заголовками для новых новостей.
        """
        with open(tg_db_file, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(["ID", "TYPE", "TXT", "IMG", "SRC", "SRC_NAME"])

        print(f"Файл {tg_db_file} был успешно создан.")

    def add_post_to_tg_db(self, tg_db_file, post_data):
        """
        Добавляет новую новость в файл tg_db.csv.
        :param tg_db_file: Путь к файлу tg_db.csv.
        :param post_data: Данные поста, который нужно добавить.
        """
        try:
            with open(tg_db_file, mode='a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(
                    [post_data["id"], post_data["type"], post_data["txt"], post_data["img"], post_data["src"],
                     post_data["src_name"]])
            print(f"Новость с текстом: \"{post_data['txt']}\" добавлена в {tg_db_file}.")
        except Exception as e:
            print(f"Ошибка при добавлении новости в файл: {e}")

    def is_post_already_added(self, tg_db_file, post_text):
        """
        Проверяет, была ли уже добавлена новость с данным текстом в tg_db.csv.
        :param tg_db_file: Путь к файлу tg_db.csv.
        :param post_text: Текст поста, который нужно проверить.
        :return: True, если новость уже добавлена, иначе False.
        """
        try:
            with open(tg_db_file, mode='r', encoding='utf-8') as file:
                reader = csv.reader(file)
                next(reader)
                for row in reader:
                    if len(row) > 0 and row[2] == post_text:
                        return True
            return False
        except Exception as e:
            print(f"Ошибка при проверке файла: {e}")
            return False
