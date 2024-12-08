import openai
import re
import logging

API_KEY = 'chat-gpt-token'

openai.api_key = API_KEY

default_prompt = (f"Translate the following text into Azerbaijani, "
          f"without prefaces, and remove various links or mentions of "
          f"channels or watermarks, if text is too small do not add nothing new to it. "
          f"This is text for news channels. The text needs to be made "
          f"interesting and up to 1024 characters")


def preprocess_text(original_text):
    """
    Удаляет повторяющиеся шаблоны и сокращает текст до 1024 символов.
    """
    text = re.sub(r"(.)\1{5,}", r"\1\1\1", original_text)

    text = text[:1024]

    return text.strip()


async def transform_text_gpt(original_text, custom_prompt=None):
    """
    Переводит текст на азербайджанский с использованием ChatGPT.
    Если custom_prompt передан, используется он. Иначе используется стандартный.
    """
    try:
        cleaned_text = preprocess_text(original_text)

        prompt = custom_prompt or f"{default_prompt} \n\n{cleaned_text}"

        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional CHAT-GPT"
                },
                {
                    "role": "user",
                    "content": f"{prompt}:\n\n{cleaned_text}"
                }
            ]
        )
        translated_text = response['choices'][0]['message']['content'].strip()
        return translated_text

    except openai.error.InvalidRequestError as e:
        logging.error(f"OpenAI Invalid Request: {e}")
        return preprocess_text(original_text)

    except Exception as e:
        logging.error(f"Ошибка при переводе: {e}")
        return original_text