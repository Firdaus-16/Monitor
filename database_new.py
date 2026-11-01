#!/usr/bin/env python3
"""Database module"""
import os
import sqlite3
import logging
from werkzeug.security import generate_password_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), 'data', 'monitoring.db')
        self.db_path = db_path
        self._ensure_data_directory()

    def _ensure_data_directory(self):
        data_dir = os.path.dirname(self.db_path)
        os.makedirs(data_dir, exist_ok=True)

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        try:
            conn = self.get_connection()
            conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS routers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site TEXT NOT NULL,
                    name TEXT NOT NULL,
                    ip TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    access_type TEXT NOT NULL,
                    nojar_cpe_versa TEXT,
                    nojar_starlink TEXT,
                    latitude REAL,
                    longitude REAL,
                    timezone TEXT DEFAULT 'Asia/Makassar',
                    router_versa_name TEXT,
                    router_model TEXT,
                    router_versa_regist TEXT,
                    psu_regist TEXT,
                    pic_name TEXT,
                    pic_phone TEXT,
                    pic_provider_phone TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(name, ip, provider)
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS downtime_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    ip TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    down_time TIMESTAMP NOT NULL,
                    up_time TIMESTAMP,
                    duration_sec INTEGER,
                    incident_type TEXT DEFAULT 'outage',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS latency_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    ip TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    latency REAL NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS runtime_states (
                    ip TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    first_rto_time TIMESTAMP,
                    down_time TIMESTAMP,
                    up_since TIMESTAMP,
                    fail_count INTEGER DEFAULT 0,
                    high_latency_active BOOLEAN DEFAULT 0,
                    high_latency_fail_count INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ip)
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    description TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    action TEXT NOT NULL,
                    table_name TEXT NOT NULL,
                    record_id TEXT,
                    old_value TEXT,
                    new_value TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS message_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS delete_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT NOT NULL,
                    filter_type TEXT,
                    filter_value TEXT,
                    rows_deleted INTEGER,
                    deleted_by TEXT,
                    deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            users = [
                ('superadmin', 'superadmin123', 'super_admin'),
                ('admin', 'admin123', 'admin'),
                ('viewer', 'viewer123', 'viewer'),
            ]
            for username, password, role in users:
                cursor = conn.execute('SELECT id FROM users WHERE username = ?', (username,))
                if cursor.fetchone() is None:
                    password_hash = generate_password_hash(password)
                    conn.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)', (username, password_hash, role))
                    logger.info(f"Default user created: {username}/{password} ({role})")

            default_settings = [
                ('monitoring_enabled', 'true', 'Enable/disable monitoring system'),
                ('alert_threshold_ms', '150', 'Latency threshold in milliseconds for alerts'),
                ('downtime_threshold_min', '5', 'Downtime threshold in minutes for alerts'),
                ('check_interval_sec', '60', 'Database check interval in seconds'),
                ('telegram_bot_token', '', 'Telegram bot token for notifications'),
                ('telegram_chat_id_lintasarta', '', 'Telegram chat ID for Lintasarta alerts'),
                ('telegram_chat_id_icon', '', 'Telegram chat ID for ICON alerts'),
                ('telegram_chat_id_all', '', 'Telegram chat ID for all alerts (optional)'),
            ]
            for key, value, description in default_settings:
                cursor = conn.execute('SELECT key FROM settings WHERE key = ?', (key,))
                if cursor.fetchone() is None:
                    conn.execute('INSERT INTO settings (key, value, description) VALUES (?, ?, ?)', (key, value, description))

            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")
            return True
        except sqlite3.Error as e:
            logger.error(f"Database init failed: {e}")
            return False
        finally:
            conn.close()

if __name__ == "__main__":
    db = DatabaseManager()
    if db.init_db():
        print("Database initialization completed successfully!")
    else:
        print("Database initialization failed!")
        exit(1)
