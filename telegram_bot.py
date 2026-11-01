#!/usr/bin/env python3
"""Telegram Bot Module"""
import requests
import logging
from database import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
db_manager = DatabaseManager()

def get_setting(key):
    try:
        conn = db_manager.get_connection()
        setting = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
        conn.close()
        return setting['value'] if setting else None
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        return None

def set_setting(key, value):
    try:
        conn = db_manager.get_connection()
        conn.execute('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP', (key, value, value))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error setting {key}: {e}")
        return False

def get_chat_ids(provider=None):
    chat_ids = []
    if provider == 'lintasarta':
        cid = get_setting('telegram_chat_id_lintasarta')
        if cid: chat_ids.append(cid)
    elif provider == 'icon':
        cid = get_setting('telegram_chat_id_icon')
        if cid: chat_ids.append(cid)
    all_cid = get_setting('telegram_chat_id_all')
    if all_cid: chat_ids.append(all_cid)
    return list(set(chat_ids))

def send_telegram_message(message, provider=None):
    token = get_setting('telegram_bot_token')
    chat_ids = get_chat_ids(provider)
    if not token or not chat_ids:
        logger.warning("Telegram not configured")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    success = False
    for chat_id in chat_ids:
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                success = True
                logger.info(f"Telegram message sent to {chat_id}")
            else:
                logger.error(f"Telegram send failed to {chat_id}: {response.text}")
        except Exception as e:
            logger.error(f"Telegram send error to {chat_id}: {e}")
    return success

def test_telegram_connection(provider=None):
    token = get_setting('telegram_bot_token')
    chat_ids = get_chat_ids(provider) if provider else [get_setting('telegram_chat_id_all')]
    if not token:
        return {"success": False, "error": "Bot token not configured"}
    if not chat_ids or not chat_ids[0]:
        return {"success": False, "error": "Chat ID not configured"}
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            bot_info = response.json()
            test_msg = f"Test connection successful! SD-WAN Monitoring Bot is active.\nProvider: {provider or 'all'}"
            send_result = send_telegram_message(test_msg, provider)
            return {"success": send_result, "bot_name": bot_info['result'].get('first_name', 'Unknown'), "bot_username": bot_info['result'].get('username', 'Unknown')}
        else:
            return {"success": False, "error": "Invalid bot token"}
    except Exception as e:
        return {"success": False, "error": str(e)}
