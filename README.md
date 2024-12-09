# News Moderation and Publication Bot

This bot streamlines the process of collecting, moderating, and publishing news from RSS feeds and Telegram channels. 
It is designed to automate content workflows while allowing customizable configurations for managing sources, moderation, and publication.

## Features

- Collects news from RSS feeds and Telegram channels.
- Sends news to a designated moderation chat for approval.
- Publishes approved news to specified Telegram channels.
- Supports customizable prompts for content transformation (e.g., translation or rephrasing).
- Allows creation and management of "linkages" (combinations of sources, moderation chats, and publication channels).
- Secure access with password authentication.

## Requirements

- Python 3.8+
- Telegram Bot Token, api_id, api_hash
- RSS feed or Telegram channel links
- Libs in requirements.txt

## Installation

1. pip install -r requirements.txt
2. Add your Telegram Bot Token, api_id, api_hash to main_bot.py
3. Add your Chat-GPT Token in gpt_style_translation.py
4. Create password.txt and add password
5. Launch main_bot.py



Feel free to fork the repository and submit pull requests. Suggestions and issue reports are welcome!
