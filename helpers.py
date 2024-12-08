import json
import os
import re
import glob
import logging


def is_url(path):
    return bool(re.match(r'^https?:\/\/', path))


def get_next_id(counter_file="id_counter.json"):
    """
    Возвращает следующий доступный ID в виде строки.
    Если файл не существует, создаёт его, начиная с 0.
    При каждом вызове счётчик увеличивается на 1.
    """
    if not os.path.exists(counter_file):
        with open(counter_file, 'w', encoding='utf-8') as file:
            json.dump({"current_id": 0}, file, ensure_ascii=False, indent=4)

    with open(counter_file, 'r+', encoding='utf-8') as file:
        data = json.load(file)
        next_id = data["current_id"]
        data["current_id"] = next_id + 1
        file.seek(0)
        json.dump(data, file, ensure_ascii=False, indent=4)
        file.truncate()

    return str(next_id)


def clear_images(folder_path):
    """
    Удаляет только файлы изображений из указанной папки.
    :param folder_path: Путь к папке, которую нужно очистить от изображений.
    """
    try:

        image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif']
        for ext in image_extensions:
            files = glob.glob(os.path.join(folder_path, ext))
            for file in files:
                os.remove(file)
        logging.info(f"Все изображения из папки {folder_path} удалены.")
    except Exception as e:
        logging.error(f"Ошибка при очистке изображений в папке {folder_path}: {e}")