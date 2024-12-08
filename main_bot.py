import asyncio
import os
import json
import sys

from telethon import TelegramClient, events, Button
from rss_parser import NewsFetcher
from tg_parser import TelegramParser

import logging
import shutil

import gpt_style_translation

API_ID = 00000000
API_HASH = 'ADD API_HASH'
BOT_TOKEN = 'ADD BOT TOKEN'

LINKAGES_FILE = 'resources.json'
PASSWORD_FILE = 'password.txt'
user_states = {}
authenticated_users = set()

CHECK_INTERVAL = 10

client = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

rss_fetcher = NewsFetcher()
telegram_parser = TelegramParser(API_ID, API_HASH)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot_debug.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_password():
    """Загружает пароль из файла password.txt."""
    try:
        with open(PASSWORD_FILE, 'r', encoding='utf-8') as f:
            password = f.read().strip()
        logger.info("Пароль успешно загружен.")
        return password
    except Exception as e:
        logger.error(f"Не удалось загрузить пароль из {PASSWORD_FILE}: {e}")
        sys.exit(1)


def load_linkages():
    """Загружает данные связок из JSON файла."""
    logger.debug("Загрузка связок из JSON файла.")
    if not os.path.exists(LINKAGES_FILE) or os.stat(LINKAGES_FILE).st_size == 0:
        logger.info(f"{LINKAGES_FILE} отсутствует или пуст. Инициализация с пустой структурой.")
        with open(LINKAGES_FILE, 'w', encoding='utf-8') as f:
            json.dump({"linkages": {}}, f, ensure_ascii=False, indent=4)
        return {"linkages": {}}

    try:
        with open(LINKAGES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if "linkages" not in data:
                raise ValueError("Неверная структура JSON: отсутствует 'linkages'.")
            logger.debug(f"Связки загружены: {data}")
            return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Ошибка при чтении {LINKAGES_FILE}: {e}. Повторная инициализация файла.")
        with open(LINKAGES_FILE, 'w', encoding='utf-8') as f:
            json.dump({"linkages": {}}, f, ensure_ascii=False, indent=4)
        return {"linkages": {}}


def save_linkages(data):
    """Сохраняет обновлённые данные связок обратно в JSON файл с созданием резервной копии."""
    logger.debug("Сохранение обновлённых связок в JSON файл.")
    try:

        if os.path.exists(LINKAGES_FILE):
            backup_file = LINKAGES_FILE + ".bak"
            shutil.copy(LINKAGES_FILE, backup_file)
            logger.debug(f"Резервная копия {LINKAGES_FILE} создана как {backup_file}")

        with open(LINKAGES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.debug(f"Обновлённые связки сохранены: {data}")
    except Exception as e:
        logger.error(f"Не удалось сохранить связки в {LINKAGES_FILE}: {e}")

        backup_file = LINKAGES_FILE + ".bak"
        if os.path.exists(backup_file):
            shutil.copy(backup_file, LINKAGES_FILE)
            logger.debug(f"{LINKAGES_FILE} восстановлен из резервной копии.")


def is_moderation_chat(chat_id):
    """
    Проверяет, является ли данный чат модерационным для какой-либо связки.
    Возвращает True, если чат модерационный, иначе False.
    """
    data = load_linkages()
    for linkage in data["linkages"].values():
        if linkage.get("moderation_bot") == chat_id:
            return True
    return False


async def moderate_news():
    """Основной цикл обработки новостей."""
    while True:
        data = load_linkages()
        linkages = data.get("linkages", {})

        for linkage_name, linkage_data in linkages.items():
            if not linkage_data.get("is_active", False):
                continue

            if not linkage_data.get("moderation_bot"):
                logger.warning(f"Связка '{linkage_name}' не имеет модерационного чата. Пропускаем.")
                continue

            if not linkage_data.get("publication_channel"):
                logger.warning(f"Связка '{linkage_name}' не имеет канала публикации. Пропускаем.")
                continue

            try:
                resources = linkage_data.get("resources", [])
                if not resources:
                    logger.warning(f"Нет ресурсов для связки {linkage_name}. Пропускаем...")
                    continue

                for resource in resources:
                    url = resource.get("url")
                    if "rss" in url or "feed" in url:
                        logger.info(f"Обрабатываем RSS канал: {url}")
                        rss_news = rss_fetcher.fetch_new_rss_news([url], f"rss_db_{linkage_name}.csv")
                        for news in rss_news:
                            await send_to_moderation(news, linkage_name, linkage_data["moderation_bot"])

                    elif "t.me" in url:
                        logger.info(f"Обрабатываем Telegram-канал: {url}")
                        tg_news = await telegram_parser.fetch_new_telegram_news([url], f"tg_db_{linkage_name}.csv")
                        for news in tg_news:
                            await send_to_moderation(news, linkage_name, linkage_data["moderation_bot"])

            except Exception as e:
                logger.error(f"Ошибка обработки связки '{linkage_name}': {e}")

        await asyncio.sleep(CHECK_INTERVAL)


async def send_to_moderation(news, linkage_name, moderation_group_link):
    """
    Отправляет новость в модерационный чат с изображением, если оно есть.

    Параметры:
        news (dict): Данные новости, включая текст, путь к изображению (если есть), источник и т.д.
        linkage_name (str): Название связки.
        moderation_group_link (str): Ссылка на модерационный чат.
    """
    try:
        logger.debug(f"Отправка новости ID {news['id']} в модерационный чат {moderation_group_link}.")

        data = load_linkages()
        linkages = data["linkages"]
        linkage = linkages.get(linkage_name)

        if not linkage:
            logger.warning(f"Связка '{linkage_name}' не найдена.")
            return

        pending_news = linkage.get("pending_news", [])
        if not any(n.get("id") == news["id"] for n in pending_news):
            pending_news.append(news)
            linkage["pending_news"] = pending_news
            save_linkages(data)
            logger.debug(f"Новость добавлена в pending_news для связки '{linkage_name}'.")

        text = f"📰 **Новая новость для модерации:**\n\n{news['txt'][:500]}"
        buttons = [
            [Button.inline("✅ Принять", f"accept:{news['id']}:{linkage_name}")],
            [Button.inline("❌ Отклонить", f"reject:{news['id']}:{linkage_name}")]
        ]

        if news.get("img"):
            img_path = news["img"]

            if os.path.exists(img_path):
                try:

                    await client.send_file(
                        moderation_group_link,
                        file=img_path,
                        caption=text,
                        buttons=buttons,
                        parse_mode='md'
                    )
                    logger.info(f"Новость с изображением отправлена в модерационный чат {moderation_group_link}.")
                except Exception as e:
                    logger.error(f"Ошибка при отправке изображения: {e}. Отправляем только текстовое сообщение.")

                    await client.send_message(
                        moderation_group_link,
                        text,
                        buttons=buttons,
                        parse_mode='md'
                    )
            else:
                logger.warning(f"Файл изображения не найден: {img_path}. Отправляем только текстовое сообщение.")
                await client.send_message(
                    moderation_group_link,
                    text,
                    buttons=buttons,
                    parse_mode='md'
                )
        else:

            logger.info(f"Изображение для новости ID {news['id']} отсутствует. Отправляем только текстовое сообщение.")
            await client.send_message(
                moderation_group_link,
                text,
                buttons=buttons,
                parse_mode='md'
            )

    except Exception as e:
        logger.error(f"Ошибка при отправке новости на модерацию: {e}")


@client.on(events.CallbackQuery(pattern=r"^(accept|reject):(\d+):(.+)$"))
async def handle_moderation_action(event):
    """
    Обрабатывает действия модерации (только в модерационных чатах).
    """
    if not is_moderation_chat(event.chat_id):
        logger.warning(f"Нажатие кнопки из неавторизованного чата {event.chat_id} проигнорировано.")
        await event.answer("❌ Этот чат не связан с модерацией.", alert=True)
        return

    chat_id = event.chat_id
    user_id = event.sender_id
    data = load_linkages()
    linkage_name = None

    for name, linkage in data["linkages"].items():
        if linkage.get("moderation_bot") == chat_id:
            linkage_name = name
            break

    if not linkage_name:
        return

    await process_moderation_action(event, linkage_name)


async def process_moderation_action(event, linkage_name):
    """
    Обрабатывает действия модерации: принятие или отклонение новостей.

    Параметры:
        event: объект события из CallbackQuery.
        linkage_name: название связки.
    """
    try:

        action, news_id, linkage_name = event.data.decode().split(":")
        logger.info(f"Действие модерации: {action}, новость ID: {news_id}, связка: {linkage_name}")

        data = load_linkages()
        linkages = data["linkages"]
        linkage = linkages.get(linkage_name)

        if not linkage:
            logger.warning(f"Связка '{linkage_name}' не найдена.")
            await event.answer("❌ Связка не найдена.", alert=True)
            return

        if event.chat_id != linkage.get("moderation_bot"):
            logger.warning(f"Попытка модерации из неавторизованного чата {event.chat_id} для связки '{linkage_name}'.")
            await event.answer("❌ Этот чат не авторизован для модерации.", alert=True)
            return

        pending_news = linkage.get("pending_news", [])
        news = next((n for n in pending_news if str(n["id"]) == news_id), None)

        if not news:
            logger.warning(f"Новость с ID {news_id} не найдена в связке '{linkage_name}'.")
            await event.answer("❌ Новость не найдена.", alert=True)
            return

        if action == "accept":

            await publish_news(news, linkage["publication_channel"])
            new_text = f"✅ **Новость принята и опубликована.**\n\n**Текст новости:**\n{news['txt'][:300]}\n\nИсточник: {news['src']}"
        else:
            new_text = f"❌ **Новость отклонена.**\n\n**Текст новости:**\n{news['txt'][:300]}\n\nИсточник: {news['src']}"

        if news.get("img") and os.path.exists(news["img"]):
            try:
                os.remove(news["img"])
                logger.info(f"Изображение {news['img']} успешно удалено после действия {action}.")
            except Exception as e:
                logger.error(f"Ошибка удаления изображения {news['img']}: {e}")

        pending_news.remove(news)
        linkage["pending_news"] = pending_news
        save_linkages(data)

        await event.edit(new_text, buttons=None)

        await event.answer("✔️ Действие обработано.")
        logger.info(f"Новость ID {news_id} успешно обработана с действием: {action}")

    except Exception as e:
        logger.error(f"Ошибка обработки действия модерации: {e}")
        await event.answer("❌ Произошла ошибка. Повторите позже.", alert=True)


async def publish_news(news, publication_channel_link):
    """
    Публикует новость в указанный канал.
    """
    try:
        logger.debug(f"Обрабатываем публикацию новости ID {news['id']} в канал {publication_channel_link}.")

        data = load_linkages()
        linkage_name = next(
            (name for name, linkage in data["linkages"].items() if linkage["publication_channel"] == publication_channel_link),
            None
        )

        custom_prompt = data["linkages"].get(linkage_name, {}).get(
            "prompt",
            "Translate the following text into Azerbaijani, "
            "without prefaces, and remove various links or mentions of channels "
            "or watermarks, if text is too small do not add nothing new to it. "
            "This is text for news channels. The text needs to be made interesting and up to 1024 characters."
        )

        translated_text = await gpt_style_translation.transform_text_gpt(news['txt'], custom_prompt)

        channel_entity = await client.get_entity(publication_channel_link)

        if news.get("img") and os.path.exists(news["img"]):
            await client.send_file(
                channel_entity,
                file=news["img"],
                caption=translated_text[:1024],
                parse_mode='md'
            )
        else:
            await client.send_message(
                channel_entity,
                translated_text,
                parse_mode='md'
            )

        logger.info(f"Новость ID {news['id']} успешно опубликована в {publication_channel_link}.")

    except Exception as e:
        logger.error(f"Ошибка публикации новости: {e}")


async def manage_linkages(event):
    """
    Открывает меню управления связками и устанавливает базовое состояние.
    """
    user_id = event.sender_id

    if user_id not in authenticated_users:
        await event.reply("🔒 Пожалуйста, введите пароль для доступа к боту:")
        user_states[user_id] = {"step": "AWAITING_PASSWORD"}
        return

    user_states[user_id] = {"current_menu": "manage_linkages"}
    logger.debug(f"User state set to manage_linkages for user {user_id}.")
    keyboard = [
        [Button.text("➕ Create Linkage")],
        [Button.text("✏️ Edit Linkage"), Button.text("🗑️ Delete Linkage")],
        [Button.text("⬅️ Back to Main Menu")],
    ]
    await event.reply("🔧 Linkage Management Menu:\n\nChoose an action below to manage your linkages:", buttons=keyboard)


async def view_linkages(event):
    """Отображает детальную информацию по всем связкам, включая промпты."""
    user_id = event.sender_id

    if user_id not in authenticated_users:
        await event.reply("🔒 Пожалуйста, введите пароль для доступа к боту:")
        user_states[user_id] = {"step": "AWAITING_PASSWORD"}
        return

    data = load_linkages()
    linkages = data.get("linkages", {})

    if not linkages:
        await event.reply("❌ Связок пока нет.")
        return

    message = "📋 **Список текущих связок:**\n\n"
    for name, details in linkages.items():
        status = "✅ Активна" if details["is_active"] else "⏸️ Приостановлена"
        publication_channel = details.get("publication_channel", "Не указано")
        resources = details.get("resources", [])
        resources_text = "\n".join(f"• {res['url']}" for res in resources) if resources else "Нет добавленных ресурсов"
        prompt = details.get("prompt", gpt_style_translation.default_prompt)

        message += (
            f"🔑 **Название связки:** {name}\n"
            f"📢 **Канал публикации:** {publication_channel}\n"
            f"🔗 **Ресурсы:**\n{resources_text}\n"
            f"📝 **Промпт:**\n{prompt}\n"
            f"📌 **Статус:** {status}\n\n"
        )

    await event.reply(message)


@client.on(events.ChatAction)
async def handle_bot_added_to_moderation_chat(event):
    """
    Обрабатывает добавление бота в чат модерации.
    """
    bot_user = await client.get_me()
    if event.user_id == bot_user.id:
        chat_id = event.chat_id
        user_id = event.action_message.from_id.user_id
        logger.info(f"Бот добавлен в модерационный чат {chat_id} пользователем {user_id}.")

        user_state = user_states.get(user_id)
        if user_state and user_state.get("step") == "AWAITING_MODERATION_CHAT":
            linkage_name = user_state["linkage_name"]
            user_states[user_id]["moderation_chat_id"] = chat_id
            user_states[user_id]["step"] = "AWAITING_PUBLICATION_CHANNEL"
            await client.send_message(
                user_id,
                f"🔑 Название связки: **{linkage_name}**\n\n"
                "✅ Чат модерации установлен. Теперь введите ссылку на канал публикации, в котором я являюсь администратором."
            )


@client.on(events.NewMessage)
async def handle_publication_channel(event):
    """
    Обрабатывает ввод канала для публикации, завершает создание связки.
    """
    user_id = event.sender_id
    text = event.text.strip()

    if not event.is_private:

        if is_moderation_chat(event.chat_id):
            return
        else:
            return

    user_state = user_states.get(user_id)
    if not user_state or user_state.get("step") != "AWAITING_PUBLICATION_CHANNEL":
        return

    linkage_name = user_state["linkage_name"]
    publication_channel = text

    try:

        channel_entity = await client.get_entity(publication_channel)

        if not channel_entity.admin_rights:
            await event.reply(
                "⚠️ Я не являюсь администратором в указанном канале. "
                "Пожалуйста, добавьте меня как администратора и попробуйте снова."
            )
            return
    except Exception as e:
        await event.reply(f"⚠️ Ошибка проверки канала: {e}. Убедитесь, что ссылка верна и я добавлен в канал.")
        return

    try:
        data = load_linkages()
        data["linkages"][linkage_name] = {
            "resources": user_state["resources"],
            "moderation_bot": user_state.get("moderation_chat_id"),
            "publication_channel": publication_channel,
            "pending_news": [],
            "is_active": True
        }
        save_linkages(data)
    except Exception as e:
        logger.error(f"Ошибка сохранения связки '{linkage_name}': {e}")
        await event.reply("❌ Произошла ошибка при сохранении связки. Попробуйте снова.")
        return

    del user_states[user_id]
    await event.reply(
        f"🔑 Название связки: **{linkage_name}**\n\n"
        f"✅ Связка успешно создана и активирована! Новости из указанных ресурсов будут направляться в чат модерации."
    )

    for resource in user_state["resources"]:
        url = resource.get("url")
        try:
            if "rss" in url or "feed" in url:
                rss_news = rss_fetcher.fetch_new_rss_news([url], f"rss_db_{linkage_name}.csv")
                for news in rss_news:
                    await send_to_moderation(news, linkage_name, data["linkages"][linkage_name]["moderation_bot"])
            elif "t.me" in url:
                tg_news = await telegram_parser.fetch_new_telegram_news([url], f"tg_db_{linkage_name}.csv")
                for news in tg_news:
                    await send_to_moderation(news, linkage_name, data["linkages"][linkage_name]["moderation_bot"])
        except Exception as e:
            logger.error(f"Ошибка обработки ресурса '{url}' для связки '{linkage_name}': {e}")


async def edit_linkage(event):
    """
    Открывает меню выбора связки для редактирования.
    """
    user_id = event.sender_id

    if user_id not in authenticated_users:
        await event.reply("🔒 Пожалуйста, введите пароль для доступа к боту:")
        user_states[user_id] = {"step": "AWAITING_PASSWORD"}
        return

    data = load_linkages()
    linkages = data.get("linkages", {})

    if not linkages:
        await event.reply("⚠️ У вас пока нет связок. Сначала создайте связку.")
        return

    user_states[user_id] = {"step": "SELECT_LINKAGE_TO_EDIT"}
    buttons = [[Button.text(name)] for name in linkages.keys()]
    buttons.append([Button.text("⬅️ Back to Main Menu")])
    await event.reply("✏️ Выберите связку для редактирования:", buttons=buttons)


@client.on(events.NewMessage)
async def handle_menu_buttons(event):
    """
    Обрабатывает нажатия кнопок и текстовые команды.
    """
    if not event.is_private:

        if is_moderation_chat(event.chat_id):
            logger.info(f"Сообщение из модерационного чата {event.chat_id} проигнорировано.")
            return
        else:
            logger.info(f"Сообщение из группового чата {event.chat_id} проигнорировано.")
            return

    user_id = event.sender_id
    text = event.text.strip()

    user_state = user_states.get(user_id)
    if user_state and user_state.get("step") == "AWAITING_PASSWORD":
        if text == PASSWORD:

            authenticated_users.add(user_id)
            user_states.pop(user_id)
            await event.reply("✅ Пароль верный! Добро пожаловать.")
            await back_to_main_menu(event)
        else:

            await event.reply("❌ Неверный пароль. Попробуйте снова.")
        return

    if user_id not in authenticated_users:

        user_states[user_id] = {"step": "AWAITING_PASSWORD"}
        await event.reply("🔒 **Пожалуйста, введите пароль для доступа к боту:**")
        return

    if text == "🛠 Manage Linkages":
        await manage_linkages(event)
        return
    elif text == "📋 View Linkages":
        await view_linkages(event)
        return
    elif text == "⬅️ Back to Main Menu":
        await back_to_main_menu(event)
        return
    elif text == "➕ Create Linkage":
        user_states[user_id] = {"step": "AWAITING_LINKAGE_NAME"}
        await event.reply("📝 Введите название новой связки.")
        return
    elif text == "🗑️ Delete Linkage":
        data = load_linkages()
        linkages = data.get("linkages", {})
        if not linkages:
            await event.reply("⚠️ Связок пока нет. Сначала создайте новую связку.")
            return

        buttons = [[Button.text(name)] for name in linkages.keys()]
        buttons.append([Button.text("⬅️ Back to Main Menu")])
        user_states[user_id] = {"step": "DELETE_LINKAGE", "allowed_linkages": list(linkages.keys())}
        await event.reply("🔑 Выберите связку для удаления:", buttons=buttons)
        return
    elif text == "✏️ Edit Linkage":
        await edit_linkage(event)
        return

    if user_state:
        if user_state.get("step") == "AWAITING_LINKAGE_NAME":
            if text in ["🛠 Manage Linkages", "📋 View Linkages", "➕ Create Linkage", "⬅️ Back to Main Menu"]:
                return
            data = load_linkages()
            linkage_name = text
            if linkage_name in data["linkages"]:
                await event.reply("⚠️ Связка с таким названием уже существует. Введите другое название.")
            else:
                user_states[user_id]["step"] = "AWAITING_RESOURCES"
                user_states[user_id]["linkage_name"] = linkage_name
                await event.reply(
                    f"🔑 Название связки: **{linkage_name}**\n\n"
                    "🔗 Введите ресурсы (ссылки на Telegram каналы или RSS ленты) через точку с запятой ;.\n"
                    "Пример: https://t.me/example1; https://rss.example.com/feed"
                )
        elif user_state.get("step") == "AWAITING_RESOURCES":
            resources = [{"url": url.strip()} for url in text.split(";") if url.strip()]
            if not resources:
                await event.reply("⚠️ Вы не добавили ни одного ресурса. Попробуйте ещё раз.")
            else:
                user_states[user_id]["resources"] = resources
                user_states[user_id]["step"] = "AWAITING_MODERATION_CHAT"
                linkage_name = user_state["linkage_name"]
                await event.reply(
                    f"🔑 Название связки: **{linkage_name}**\n\n"
                    "✅ Ресурсы добавлены. Теперь добавьте меня в чат модерации. "
                    "Я уведомлю вас, как только меня добавят."
                )
        elif user_state.get("step") == "DELETE_LINKAGE":
            data = load_linkages()
            allowed_linkages = user_state.get("allowed_linkages", [])
            if text in allowed_linkages:
                linkages = data["linkages"]
                del linkages[text]
                save_linkages(data)
                user_states.pop(user_id, None)
                await event.reply(f"✅ Связка **{text}** успешно удалена.")
                await back_to_main_menu(event)
            elif text == "⬅️ Back to Main Menu":
                user_states.pop(user_id, None)
                await back_to_main_menu(event)
            else:
                await event.reply("⚠️ Пожалуйста, выберите существующую связку для удаления.")
        elif user_state.get("step") == "SELECT_LINKAGE_TO_EDIT":
            data = load_linkages()
            linkages = data.get("linkages", {})
            if text in linkages:
                linkage = linkages[text]
                is_active = linkage.get("is_active", True)
                toggle_action = "⏸️ Pause Linkage" if is_active else "▶️ Resume Linkage"

                user_states[user_id] = {"step": "SELECT_EDIT_ACTION", "linkage_name": text}
                keyboard = [
                    [Button.text("➕ Add Resources"), Button.text("🗑️ Remove Resources")],
                    [Button.text("✏️ Edit Prompt")],
                    [Button.text(toggle_action)],
                    [Button.text("⬅️ Back to Linkage Selection")]
                ]
                await event.reply(f"✏️ Вы редактируете связку: **{text}**\n\nЧто вы хотите сделать?", buttons=keyboard)
            elif text == "⬅️ Back to Main Menu":
                user_states.pop(user_id, None)
                await back_to_main_menu(event)
            else:
                await event.reply("⚠️ Пожалуйста, выберите существующую связку для редактирования.")
        elif user_state.get("step") == "SELECT_EDIT_ACTION":
            linkage_name = user_state["linkage_name"]
            if text == "➕ Add Resources":
                user_states[user_id] = {"step": "AWAITING_RESOURCES_TO_ADD", "linkage_name": linkage_name}
                await event.reply(
                    f"✏️ Вы редактируете связку: **{linkage_name}**.\n\nВведите ресурсы через ;, которые хотите добавить."
                )
            elif text == "✏️ Edit Prompt":
                user_states[user_id] = {"step": "AWAITING_PROMPT_CHANGE", "linkage_name": linkage_name}
                data = load_linkages()
                linkage = data["linkages"].get(linkage_name, {})
                current_prompt = linkage.get("prompt", gpt_style_translation.default_prompt)
                await event.reply(
                    f"✏️ Вы редактируете связку: **{linkage_name}**.\n\nТекущий промпт:\n{gpt_style_translation.default_prompt}\n\n"
                    f"Введите новый промпт для обработки новостей."
                )
            elif text == "🗑️ Remove Resources":
                data = load_linkages()
                linkage = data["linkages"].get(linkage_name, {})
                resources = linkage.get("resources", [])
                if not resources:
                    await event.reply("⚠️ В этой связке нет ресурсов для удаления.")
                else:
                    user_states[user_id] = {"step": "AWAITING_RESOURCE_TO_REMOVE", "linkage_name": linkage_name}
                    buttons = [[Button.text(res["url"])] for res in resources]
                    buttons.append([Button.text("⬅️ Back to Edit Menu")])
                    await event.reply(f"✏️ Выберите ресурс для удаления из связки: **{linkage_name}**", buttons=buttons)
            elif text == "⏸️ Pause Linkage" or text == "▶️ Resume Linkage":

                data = load_linkages()
                linkage = data["linkages"].get(linkage_name, {})
                linkage["is_active"] = not linkage.get("is_active", True)
                save_linkages(data)

                is_active = linkage["is_active"]
                status = "✅ Активна" if is_active else "⏸️ Приостановлена"
                toggle_action = "⏸️ Pause Linkage" if is_active else "▶️ Resume Linkage"

                await event.reply(f"✅ Связка **{linkage_name}** {status}.")

                keyboard = [
                    [Button.text("➕ Add Resources"), Button.text("🗑️ Remove Resources")],
                    [Button.text("✏️ Edit Prompt")],
                    [Button.text(toggle_action)],
                    [Button.text("⬅️ Back to Linkage Selection")]
                ]

                await event.reply(f"✏️ Вы редактируете связку: **{linkage_name}**\n\nЧто вы хотите сделать?",
                                  buttons=keyboard)
            elif text == "⬅️ Back to Linkage Selection":
                user_states[user_id] = {"step": "SELECT_LINKAGE_TO_EDIT"}
                await edit_linkage(event)
            else:
                await event.reply("⚠️ Пожалуйста, выберите допустимое действие.")
        elif user_state.get("step") == "AWAITING_RESOURCES_TO_ADD":
            linkage_name = user_state["linkage_name"]

            if text in ["⬅️ Back to Edit Menu", '➕ Add Resources', '🗑️ Remove Resources', '✏️ Edit Linkage', '⏸️ Pause Linkage', '▶️ Resume Linkage']:
                user_states[user_id] = {"step": "SELECT_EDIT_ACTION", "linkage_name": linkage_name}
                await edit_linkage(event)
                return

            resources = [{"url": url.strip()} for url in text.split(";") if url.strip()]
            if not resources:
                await event.reply("⚠️ Вы не добавили ни одного ресурса. Попробуйте ещё раз.")
            else:
                data = load_linkages()
                linkage = data["linkages"].get(linkage_name, {})
                linkage["resources"].extend(resources)
                save_linkages(data)
                user_states.pop(user_id, None)
                await event.reply(f"✅ Ресурсы успешно добавлены в связку: **{linkage_name}**.")
                await back_to_main_menu(event)
        elif user_state.get("step") == "AWAITING_RESOURCE_TO_REMOVE":
            linkage_name = user_state["linkage_name"]
            data = load_linkages()
            linkage = data["linkages"].get(linkage_name, {})
            resources = linkage.get("resources", [])
            selected_resource = next((res for res in resources if res["url"] == text), None)
            if selected_resource:
                resources.remove(selected_resource)
                save_linkages(data)
                await event.reply(f"✅ Ресурс удалён: **{selected_resource['url']}**.")
                if resources:
                    buttons = [[Button.text(res["url"])] for res in resources]
                    buttons.append([Button.text("⬅️ Back to Edit Menu")])
                    await event.reply("Выберите следующий ресурс для удаления:", buttons=buttons)
                else:
                    user_states.pop(user_id, None)
                    await back_to_main_menu(event)
            elif text == "⬅️ Back to Edit Menu":
                user_states[user_id] = {"step": "SELECT_EDIT_ACTION", "linkage_name": linkage_name}
                await edit_linkage(event)
            else:
                await event.reply("⚠️ Пожалуйста, выберите корректный ресурс для удаления.")
        elif user_state.get("step") == "AWAITING_PROMPT_CHANGE":
            linkage_name = user_state["linkage_name"]

            if text in ["⬅️ Back to Linkage Selection", '➕ Add Resources', '🗑️ Remove Resources', '✏️ Edit Prompt', '⏸️ Pause Linkage']:
                user_states[user_id] = {"step": "SELECT_EDIT_ACTION", "linkage_name": linkage_name}
                await edit_linkage(event)
                return

            if text.startswith('/'):
                return

            data = load_linkages()
            linkage = data["linkages"].get(linkage_name)
            if not linkage:
                await event.reply("⚠️ Связка не найдена. Попробуйте снова.")
                user_states.pop(user_id, None)
                return

            linkage["prompt"] = text
            save_linkages(data)

            await event.reply(f"✅ Промпт для связки **{linkage_name}** успешно обновлён!")
            user_states[user_id] = {"step": "SELECT_EDIT_ACTION", "linkage_name": linkage_name}
            await edit_linkage(event)


async def back_to_main_menu(event):
    user_id = event.sender_id
    user_states.pop(user_id, None)
    keyboard = [
        [Button.text("🛠 Manage Linkages")],
        [Button.text("📋 View Linkages")],
    ]
    await event.reply("🤖 Главное меню\n\nВыберите опцию ниже:", buttons=keyboard)


@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    """
    Обрабатывает команду /start только в личных чатах и игнорирует её в модерационных чатах.
    """
    if not event.is_private:

        if is_moderation_chat(event.chat_id):
            logger.info(f"Команда /start из модерационного чата {event.chat_id} проигнорирована.")
            return
        return

    user_id = event.sender_id

    if user_id in authenticated_users:

        keyboard = [
            [Button.text("🛠 Manage Linkages")],
            [Button.text("📋 View Linkages")],
        ]
        await event.respond(
            "🤖 **Добро пожаловать в модерационного бота!**\n\n"
            "Выберите действие из меню:",
            buttons=keyboard
        )
    else:

        user_states[user_id] = {"step": "AWAITING_PASSWORD"}
        await event.respond(
            "🔒 **Пожалуйста, введите пароль для доступа к боту:**"
        )


async def main():
    """Запуск бота."""
    try:
        await client.start()
        logger.info("Бот запущен и работает...")

        if user_states:
            logger.info(f"Восстановление состояний пользователей: {user_states}")

        await asyncio.gather(client.run_until_disconnected(), moderate_news())
    except Exception as e:
        logger.exception("Произошла ошибка при запуске бота.")


PASSWORD = load_password()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())