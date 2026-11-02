#!/usr/bin/env python3
"""
Enterprise SD-WAN Monitoring System - Main Application
Dual-provider infrastructure for Bank Kalsel (Lintasarta/Versa & ICON/Starlink)
"""
import os
import json
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, jsonify, request, render_template, session, redirect, url_for, send_file
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import urllib.parse
import atexit

from database import DatabaseManager
from telegram_bot import get_setting, set_setting, test_telegram_connection
from monitor import check_all_routers
from importer import BranchImporter

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Secret key from environment variable or constant default for production session persistence
app.secret_key = os.environ.get('SECRET_KEY', 'bank-kalsel-sdwan-secret-2026-production')

db_manager = DatabaseManager()
db_manager.init_db()

# --- Auth Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for('login'))
        if session.get('role') not in ['admin', 'super_admin']:
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for('login'))
        if session.get('role') != 'super_admin':
            return jsonify({"error": "Super admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function

def log_audit(action, table_name, record_id=None, old_value=None, new_value=None):
    try:
        conn = db_manager.get_connection()
        conn.execute('''
            INSERT INTO audit_log 
            (username, action, table_name, record_id, old_value, new_value, ip_address, user_agent) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session.get('username', 'system'),
            action,
            table_name,
            str(record_id) if record_id is not None else None,
            json.dumps(old_value) if old_value else None,
            json.dumps(new_value) if new_value else None,
            request.remote_addr if request else '127.0.0.1',
            request.headers.get('User-Agent', '') if request else 'system'
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Audit log error: {e}")

# --- Authentication Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        conn = db_manager.get_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            log_audit('LOGIN', 'users', user['id'])
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Username atau password salah.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    log_audit('LOGOUT', 'users', session.get('user_id'))
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/user/info', methods=['GET'])
@login_required
def user_info():
    return jsonify({
        "username": session.get('username'),
        "role": session.get('role')
    })

# --- Health & Main View ---
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "OK",
        "timestamp": datetime.now().isoformat(),
        "database": os.path.exists(db_manager.db_path)
    }), 200

@app.route('/')
@login_required
def index():
    return render_template('index.html', username=session.get('username'), role=session.get('role'))

# --- Router Management (CRUD) ---
@app.route('/api/routers', methods=['GET'])
@login_required
def get_routers():
    try:
        conn = db_manager.get_connection()
        cursor = conn.execute('''
            SELECT r.*, 
                   COALESCE(rs.status, 'unknown') as status,
                   rs.fail_count,
                   rs.up_since,
                   rs.down_time as last_down_time,
                   rs.high_latency_active,
                   rs.last_updated
            FROM routers r
            LEFT JOIN runtime_states rs ON r.ip = rs.ip
            ORDER BY r.site ASC, r.provider ASC
        ''')
        routers = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify(routers)
    except Exception as e:
        logger.error(f"Error getting routers: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/routers/<ip>', methods=['GET'])
@login_required
def get_router(ip):
    try:
        conn = db_manager.get_connection()
        cursor = conn.execute('''
            SELECT r.*, COALESCE(rs.status, 'unknown') as status 
            FROM routers r 
            LEFT JOIN runtime_states rs ON r.ip = rs.ip
            WHERE r.ip = ?
        ''', (ip,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "Router not found"}), 404
        return jsonify(dict(row))
    except Exception as e:
        logger.error(f"Error getting router {ip}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/routers', methods=['POST'])
@admin_required
def create_router():
    data = request.get_json() or {}
    required = ['site', 'name', 'ip', 'provider']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Kolom wajib belum diisi: {', '.join(missing)}"}), 400

    try:
        conn = db_manager.get_connection()
        cursor = conn.execute('''
            INSERT INTO routers (site, name, ip, provider, access_type, 
                                 nojar_cpe_versa, nojar_starlink, latitude, longitude, timezone,
                                 router_versa_name, router_model, router_versa_regist, psu_regist,
                                 pic_name, pic_phone, pic_provider_phone)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('site'), data.get('name'), data.get('ip'), data.get('provider').lower(),
            data.get('access_type', 'SD-WAN'), data.get('nojar_cpe_versa'), data.get('nojar_starlink'),
            data.get('latitude'), data.get('longitude'), data.get('timezone', 'Asia/Makassar'),
            data.get('router_versa_name'), data.get('router_model'), data.get('router_versa_regist'),
            data.get('psu_regist'), data.get('pic_name'), data.get('pic_phone'), data.get('pic_provider_phone')
        ))
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        log_audit('CREATE', 'routers', new_id, None, data)
        return jsonify({"message": "Router created successfully", "id": new_id}), 201
    except Exception as e:
        logger.error(f"Error creating router: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/routers/<ip>', methods=['PUT'])
@admin_required
def update_router(ip):
    data = request.get_json() or {}
    try:
        conn = db_manager.get_connection()
        old_router = conn.execute('SELECT * FROM routers WHERE ip = ?', (ip,)).fetchone()
        if not old_router:
            conn.close()
            return jsonify({"error": "Router not found"}), 404

        old_value = dict(old_router)
        cursor = conn.execute('''
            UPDATE routers SET 
                site = ?, name = ?, ip = ?, provider = ?, access_type = ?,
                nojar_cpe_versa = ?, nojar_starlink = ?, latitude = ?, longitude = ?, timezone = ?,
                router_versa_name = ?, router_model = ?, router_versa_regist = ?, psu_regist = ?,
                pic_name = ?, pic_phone = ?, pic_provider_phone = ?, updated_at = CURRENT_TIMESTAMP
            WHERE ip = ?
        ''', (
            data.get('site', old_value['site']),
            data.get('name', old_value['name']),
            data.get('ip', old_value['ip']),
            data.get('provider', old_value['provider']).lower(),
            data.get('access_type', old_value['access_type']),
            data.get('nojar_cpe_versa', old_value['nojar_cpe_versa']),
            data.get('nojar_starlink', old_value['nojar_starlink']),
            data.get('latitude', old_value['latitude']),
            data.get('longitude', old_value['longitude']),
            data.get('timezone', old_value['timezone']),
            data.get('router_versa_name', old_value['router_versa_name']),
            data.get('router_model', old_value['router_model']),
            data.get('router_versa_regist', old_value['router_versa_regist']),
            data.get('psu_regist', old_value['psu_regist']),
            data.get('pic_name', old_value['pic_name']),
            data.get('pic_phone', old_value['pic_phone']),
            data.get('pic_provider_phone', old_value['pic_provider_phone']),
            ip
        ))
        conn.commit()
        conn.close()
        log_audit('UPDATE', 'routers', ip, old_value, data)
        return jsonify({"message": "Router updated successfully"}), 200
    except Exception as e:
        logger.error(f"Error updating router {ip}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/routers/<ip>', methods=['DELETE'])
@admin_required
def delete_router(ip):
    try:
        conn = db_manager.get_connection()
        old_router = conn.execute('SELECT * FROM routers WHERE ip = ?', (ip,)).fetchone()
        if not old_router:
            conn.close()
            return jsonify({"error": "Router not found"}), 404

        old_value = dict(old_router)
        conn.execute('DELETE FROM routers WHERE ip = ?', (ip,))
        conn.execute('DELETE FROM runtime_states WHERE ip = ?', (ip,))
        conn.commit()
        conn.close()
        log_audit('DELETE', 'routers', ip, old_value, None)
        return jsonify({"message": "Router deleted successfully"}), 200
    except Exception as e:
        logger.error(f"Error deleting router {ip}: {e}")
        return jsonify({"error": str(e)}), 500

# --- Map & Sites ---
@app.route('/api/map/routers', methods=['GET'])
@login_required
def get_map_routers():
    try:
        conn = db_manager.get_connection()
        routers = conn.execute('''
            SELECT r.site, r.name, r.ip, r.provider, r.access_type, 
                   r.latitude, r.longitude, r.pic_name, r.pic_phone, r.timezone,
                   COALESCE(rs.status, 'unknown') as status
            FROM routers r
            LEFT JOIN runtime_states rs ON r.ip = rs.ip
            WHERE r.latitude IS NOT NULL AND r.longitude IS NOT NULL
        ''').fetchall()
        conn.close()
        return jsonify([dict(row) for row in routers])
    except Exception as e:
        logger.error(f"Error getting map routers: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/sites', methods=['GET'])
@login_required
def get_sites():
    try:
        conn = db_manager.get_connection()
        sites = conn.execute('SELECT DISTINCT site FROM routers ORDER BY site').fetchall()
        conn.close()
        return jsonify([row['site'] for row in sites])
    except Exception as e:
        logger.error(f"Error getting sites: {e}")
        return jsonify({"error": str(e)}), 500

# --- Statistics & Reports Endpoints ---
@app.route('/api/stats/downtime-by-site', methods=['GET'])
@login_required
def stats_downtime_by_site():
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    provider = request.args.get('provider')
    
    try:
        conn = db_manager.get_connection()
        query = '''
            SELECT COALESCE(site, name) as site, provider, COUNT(*) as count, 
                   COALESCE(SUM(duration_sec), 0) as total_duration
            FROM downtime_history 
            WHERE 1=1
        '''
        params = []
        if from_date:
            query += ' AND down_time >= ?'
            params.append(from_date)
        if to_date:
            query += ' AND down_time <= ?'
            params.append(to_date + ' 23:59:59')
        if provider:
            query += ' AND provider = ?'
            params.append(provider.lower())
        
        query += ' GROUP BY COALESCE(site, name), provider ORDER BY count DESC LIMIT 10'
        stats = conn.execute(query, params).fetchall()
        conn.close()
        return jsonify([dict(row) for row in stats])
    except Exception as e:
        logger.error(f"Error getting downtime stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats/downtime-by-provider', methods=['GET'])
@login_required
def stats_downtime_by_provider():
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    
    try:
        conn = db_manager.get_connection()
        query = '''
            SELECT provider, COUNT(*) as count, COALESCE(SUM(duration_sec), 0) as total_duration
            FROM downtime_history 
            WHERE 1=1
        '''
        params = []
        if from_date:
            query += ' AND down_time >= ?'
            params.append(from_date)
        if to_date:
            query += ' AND down_time <= ?'
            params.append(to_date + ' 23:59:59')
        
        query += ' GROUP BY provider'
        stats = conn.execute(query, params).fetchall()
        conn.close()
        return jsonify([dict(row) for row in stats])
    except Exception as e:
        logger.error(f"Error getting provider stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats/downtime-trend', methods=['GET'])
@login_required
def stats_downtime_trend():
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    provider = request.args.get('provider')
    
    try:
        conn = db_manager.get_connection()
        query = '''
            SELECT DATE(down_time) as date, COUNT(*) as count, 
                   COALESCE(SUM(duration_sec), 0) as total_duration
            FROM downtime_history 
            WHERE 1=1
        '''
        params = []
        if from_date:
            query += ' AND down_time >= ?'
            params.append(from_date)
        if to_date:
            query += ' AND down_time <= ?'
            params.append(to_date + ' 23:59:59')
        if provider:
            query += ' AND provider = ?'
            params.append(provider.lower())
        
        query += ' GROUP BY DATE(down_time) ORDER BY date ASC'
        stats = conn.execute(query, params).fetchall()
        conn.close()
        return jsonify([dict(row) for row in stats])
    except Exception as e:
        logger.error(f"Error getting trend stats: {e}")
        return jsonify({"error": str(e)}), 500

# --- User Management (Admin / Super Admin) ---
@app.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    try:
        conn = db_manager.get_connection()
        users = conn.execute('SELECT id, username, role, created_at FROM users').fetchall()
        conn.close()
        return jsonify([dict(row) for row in users])
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'viewer')
    
    if not username or not password:
        return jsonify({"error": "Username dan password harus diisi"}), 400
    if role not in ['super_admin', 'admin', 'viewer']:
        return jsonify({"error": "Role tidak valid"}), 400
    if role == 'super_admin' and session.get('role') != 'super_admin':
        return jsonify({"error": "Hanya super admin yang dapat membuat super admin baru"}), 403
    
    try:
        conn = db_manager.get_connection()
        existing = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if existing:
            conn.close()
            return jsonify({"error": "Username sudah terdaftar"}), 400
        
        password_hash = generate_password_hash(password)
        cursor = conn.execute(
            'INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
            (username, password_hash, role)
        )
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        log_audit('CREATE', 'users', new_id, None, {'username': username, 'role': role})
        return jsonify({"message": "User created", "id": new_id}), 201
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    data = request.get_json() or {}
    try:
        conn = db_manager.get_connection()
        old_user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if not old_user:
            conn.close()
            return jsonify({"error": "User tidak ditemukan"}), 404
        
        if old_user['role'] == 'super_admin' and session.get('role') != 'super_admin':
            conn.close()
            return jsonify({"error": "Tidak berwenang mengubah akun super admin"}), 403
        
        new_role = data.get('role', old_user['role'])
        if new_role not in ['super_admin', 'admin', 'viewer']:
            conn.close()
            return jsonify({"error": "Role tidak valid"}), 400
        if new_role == 'super_admin' and session.get('role') != 'super_admin':
            conn.close()
            return jsonify({"error": "Hanya super admin yang dapat memberikan role super admin"}), 403
        
        username = data.get('username', old_user['username'])
        if data.get('password'):
            password_hash = generate_password_hash(data.get('password'))
            conn.execute('''
                UPDATE users SET username = ?, password_hash = ?, role = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (username, password_hash, new_role, user_id))
        else:
            conn.execute('''
                UPDATE users SET username = ?, role = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (username, new_role, user_id))
        
        conn.commit()
        conn.close()
        log_audit('UPDATE', 'users', user_id, dict(old_user), {"username": username, "role": new_role})
        return jsonify({"message": "User updated"}), 200
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@super_admin_required
def delete_user(user_id):
    try:
        conn = db_manager.get_connection()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            conn.close()
            return jsonify({"error": "User tidak ditemukan"}), 404
        if user['role'] == 'super_admin':
            conn.close()
            return jsonify({"error": "Akun super admin tidak dapat dihapus"}), 403
        if user['id'] == session.get('user_id'):
            conn.close()
            return jsonify({"error": "Tidak dapat menghapus akun sendiri"}), 403
        
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        log_audit('DELETE', 'users', user_id, dict(user), None)
        return jsonify({"message": "User deleted"}), 200
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}")
        return jsonify({"error": str(e)}), 500

# --- Telegram Bot Config & Test ---
@app.route('/api/telegram/config', methods=['GET'])
@admin_required
def get_telegram_config():
    return jsonify({
        'bot_token': get_setting('telegram_bot_token') or '',
        'chat_id_lintasarta': get_setting('telegram_chat_id_lintasarta') or '',
        'chat_id_icon': get_setting('telegram_chat_id_icon') or '',
        'chat_id_all': get_setting('telegram_chat_id_all') or '',
    })

@app.route('/api/telegram/config', methods=['POST'])
@admin_required
def save_telegram_config():
    data = request.get_json() or {}
    set_setting('telegram_bot_token', data.get('bot_token', '').strip())
    set_setting('telegram_chat_id_lintasarta', data.get('chat_id_lintasarta', '').strip())
    set_setting('telegram_chat_id_icon', data.get('chat_id_icon', '').strip())
    set_setting('telegram_chat_id_all', data.get('chat_id_all', '').strip())
    log_audit('CONFIG', 'settings', None, None, {"action": "telegram_config_updated"})
    return jsonify({"message": "Pengaturan Telegram berhasil disimpan."}), 200

@app.route('/api/telegram/test', methods=['POST'])
@admin_required
def test_telegram():
    data = request.get_json() or {}
    provider = data.get('provider')
    result = test_telegram_connection(provider)
    return jsonify(result)

# --- WhatsApp Message Templates & Generator ---
@app.route('/api/whatsapp/templates', methods=['GET'])
@login_required
def get_whatsapp_templates():
    template_type = request.args.get('type')
    try:
        conn = db_manager.get_connection()
        if template_type:
            templates = conn.execute('SELECT * FROM message_templates WHERE type = ?', (template_type,)).fetchall()
        else:
            templates = conn.execute('SELECT * FROM message_templates').fetchall()
        conn.close()
        return jsonify([dict(row) for row in templates])
    except Exception as e:
        logger.error(f"Error getting templates: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/whatsapp/templates/<int:template_id>', methods=['PUT'])
@admin_required
def update_whatsapp_template(template_id):
    data = request.get_json() or {}
    try:
        conn = db_manager.get_connection()
        cursor = conn.execute(
            'UPDATE message_templates SET name = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (data.get('name'), data.get('content'), template_id)
        )
        conn.commit()
        conn.close()
        if cursor.rowcount == 0:
            return jsonify({"error": "Template tidak ditemukan"}), 404
        log_audit('UPDATE', 'message_templates', template_id, None, data)
        return jsonify({"message": "Template WhatsApp berhasil diperbarui"}), 200
    except Exception as e:
        logger.error(f"Error updating template: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/whatsapp/generate', methods=['POST'])
@login_required
def generate_whatsapp_url():
    data = request.get_json() or {}
    ip = data.get('ip')
    template_type = data.get('template_type', 'pic')
    template_id = data.get('template_id')
    
    try:
        conn = db_manager.get_connection()
        router = conn.execute('SELECT * FROM routers WHERE ip = ?', (ip,)).fetchone()
        
        if template_id:
            template = conn.execute('SELECT * FROM message_templates WHERE id = ?', (template_id,)).fetchone()
        else:
            template = conn.execute('SELECT * FROM message_templates WHERE type = ? LIMIT 1', (template_type,)).fetchone()
        conn.close()
        
        if not router:
            return jsonify({"error": "Router tidak ditemukan"}), 404
        
        if template:
            message = template['content']
        else:
            if template_type == 'pic':
                message = "Halo Bapak/Ibu {pic_name} di Cabang {site}, kami mendeteksi link jaringan (IP: {ip}, Versa: {nojar_versa}, Starlink: {nojar_starlink}) sedang DOWN. Mohon konfirmasi kondisi listrik/perangkat di lokasi."
            else:
                message = "Yth. Helpdesk Provider, mohon open tiket gangguan link di Bank Kalsel Cabang {site} (IP: {ip}, Versa: {nojar_versa}, Starlink: {nojar_starlink}). Mohon segera dilakukan pengecekan."
        message = message.replace('{site}', router['site'] or '')
        message = message.replace('{ip}', router['ip'] or '')
        message = message.replace('{pic_name}', router['pic_name'] or 'PIC')
        message = message.replace('{nojar_versa}', router['nojar_cpe_versa'] or '-')
        message = message.replace('{nojar_starlink}', router['nojar_starlink'] or '-')
        
        phone = router['pic_phone'] if template_type == 'pic' else router['pic_provider_phone']
        clean_phone = ''.join(filter(str.isdigit, str(phone or '')))
        if clean_phone.startswith('0'):
            clean_phone = '62' + clean_phone[1:]
        
        encoded_message = urllib.parse.quote(message)
        whatsapp_url = f"https://wa.me/{clean_phone}?text={encoded_message}" if clean_phone else None
        
        return jsonify({
            "url": whatsapp_url,
            "message": message,
            "phone": clean_phone or phone
        })
    except Exception as e:
        logger.error(f"Error generating WhatsApp URL: {e}")
        return jsonify({"error": str(e)}), 500

# --- Bulk Excel Importer Upload Endpoint ---
@app.route('/api/upload/branches', methods=['POST'])
@admin_required
def upload_branches():
    if 'file' not in request.files:
        return jsonify({"error": "File Excel tidak disertakan"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nama file kosong"}), 400
    
    uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
    os.makedirs(uploads_dir, exist_ok=True)
    filename = secure_filename(file.filename)
    save_path = os.path.join(uploads_dir, filename)
    file.save(save_path)
    
    importer = BranchImporter(db_manager)
    result = importer.import_branches_from_excel(save_path)
    if result.get('success'):
        log_audit('IMPORT', 'routers', None, None, {"filename": filename, "result": result})
        return jsonify(result), 200
    else:
        return jsonify(result), 400

# --- Excel Export Endpoints ---
@app.route('/api/export/downtime', methods=['GET'])
@login_required
def export_downtime():
    import pandas as pd
    from io import BytesIO
    
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    provider = request.args.get('provider')
    site = request.args.get('site')
    
    try:
        conn = db_manager.get_connection()
        query = 'SELECT * FROM downtime_history WHERE 1=1'
        params = []
        if from_date:
            query += ' AND down_time >= ?'
            params.append(from_date)
        if to_date:
            query += ' AND down_time <= ?'
            params.append(to_date + ' 23:59:59')
        if provider:
            query += ' AND provider = ?'
            params.append(provider.lower())
        if site:
            query += ' AND (site LIKE ? OR name LIKE ?)'
            params.extend([f'%{site}%', f'%{site}%'])
        
        query += ' ORDER BY down_time DESC'
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            total_events = len(df)
            total_duration_min = round(df['duration_sec'].sum() / 60, 2) if not df.empty else 0
            avg_duration_min = round(df['duration_sec'].mean() / 60, 2) if not df.empty else 0
            lintas_count = len(df[df['provider'].str.lower() == 'lintasarta']) if not df.empty else 0
            icon_count = len(df[df['provider'].str.lower() == 'icon']) if not df.empty else 0
            
            summary_data = {
                'Metric': ['Total Insiden', 'Total Durasi (Menit)', 'Rata-rata Durasi (Menit)', 'Gangguan Lintasarta', 'Gangguan ICON'],
                'Value': [total_events, total_duration_min, avg_duration_min, lintas_count, icon_count]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
            df.to_excel(writer, sheet_name='Downtime Detail', index=False)
            
            if not df.empty:
                group_col = 'site' if 'site' in df.columns and df['site'].notna().any() else 'name'
                site_summary = df.groupby(group_col).agg(
                    Total_Events=('id', 'count'),
                    Total_Duration_Sec=('duration_sec', 'sum'),
                    Avg_Duration_Sec=('duration_sec', 'mean')
                ).reset_index()
                site_summary.to_excel(writer, sheet_name='Site Summary', index=False)
                
                provider_summary = df.groupby('provider').agg(
                    Total_Events=('id', 'count'),
                    Total_Duration_Sec=('duration_sec', 'sum'),
                    Avg_Duration_Sec=('duration_sec', 'mean')
                ).reset_index()
                provider_summary.to_excel(writer, sheet_name='Provider Summary', index=False)
        
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f"downtime_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
    except Exception as e:
        logger.error(f"Error exporting downtime: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/export/latency', methods=['GET'])
@login_required
def export_latency():
    import pandas as pd
    from io import BytesIO
    
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    provider = request.args.get('provider')
    site = request.args.get('site')
    
    try:
        conn = db_manager.get_connection()
        query = 'SELECT * FROM latency_history WHERE 1=1'
        params = []
        if from_date:
            query += ' AND timestamp >= ?'
            params.append(from_date)
        if to_date:
            query += ' AND timestamp <= ?'
            params.append(to_date + ' 23:59:59')
        if provider:
            query += ' AND provider = ?'
            params.append(provider.lower())
        if site:
            query += ' AND (site LIKE ? OR name LIKE ?)'
            params.extend([f'%{site}%', f'%{site}%'])
        
        query += ' ORDER BY timestamp DESC'
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            summary_data = {
                'Metric': ['Total Records', 'Avg Latency (ms)', 'Min Latency (ms)', 'Max Latency (ms)'],
                'Value': [
                    len(df),
                    round(df['latency'].mean(), 2) if not df.empty else 0,
                    round(df['latency'].min(), 2) if not df.empty else 0,
                    round(df['latency'].max(), 2) if not df.empty else 0
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
            df.to_excel(writer, sheet_name='Latency Detail', index=False)
            
            if not df.empty:
                group_col = 'site' if 'site' in df.columns and df['site'].notna().any() else 'name'
                site_summary = df.groupby(group_col).agg(
                    Avg_Latency_ms=('latency', 'mean'),
                    Min_Latency_ms=('latency', 'min'),
                    Max_Latency_ms=('latency', 'max'),
                    Count=('latency', 'count')
                ).reset_index()
                site_summary.to_excel(writer, sheet_name='Site Summary', index=False)
        
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f"latency_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
    except Exception as e:
        logger.error(f"Error exporting latency: {e}")
        return jsonify({"error": str(e)}), 500

# --- Safe Data Retention & Deletion API (Parameterized) ---
def build_safe_delete_filter(filter_type, filter_value, date_column='down_time'):
    if filter_type == 'all':
        return '1=1', []
    elif filter_type == 'date':
        parts = filter_value.split(' to ')
        if len(parts) == 2:
            return f"{date_column} >= ? AND {date_column} <= ?", [parts[0].strip(), parts[1].strip() + ' 23:59:59']
        elif len(parts) == 1:
            return f"{date_column} >= ?", [parts[0].strip()]
    elif filter_type == 'site':
        return "site = ? OR name LIKE ?", [filter_value, f"%{filter_value}%"]
    elif filter_type == 'provider':
        return "provider = ?", [filter_value.lower()]
    elif filter_type == 'template':
        today = datetime.now()
        if filter_value == 'daily':
            from_date = today.strftime('%Y-%m-%d')
        elif filter_value == 'weekly':
            from_date = (today - timedelta(days=7)).strftime('%Y-%m-%d')
        elif filter_value == 'monthly':
            from_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        elif filter_value == '3months':
            from_date = (today - timedelta(days=90)).strftime('%Y-%m-%d')
        else:
            return None, []
        return f"{date_column} >= ?", [from_date]
    return None, []

@app.route('/api/delete/preview', methods=['POST'])
@admin_required
def delete_preview():
    data = request.get_json() or {}
    table = data.get('table')
    filter_type = data.get('filter_type')
    filter_value = data.get('filter_value')
    
    table_map = {'downtime': 'downtime_history', 'latency': 'latency_history', 'runtime': 'runtime_states'}
    db_table = table_map.get(table)
    if not db_table:
        return jsonify({"error": "Tabel tidak valid"}), 400
    
    date_column = 'down_time' if table == 'downtime' else 'timestamp' if table == 'latency' else 'last_updated'
    where_clause, params = build_safe_delete_filter(filter_type, filter_value, date_column)
    if where_clause is None:
        return jsonify({"error": "Filter tidak valid"}), 400
    
    try:
        conn = db_manager.get_connection()
        count = conn.execute(f'SELECT COUNT(*) FROM {db_table} WHERE {where_clause}', params).fetchone()[0]
        conn.close()
        return jsonify({"count": count})
    except Exception as e:
        logger.error(f"Error previewing delete: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete/downtime', methods=['DELETE'])
@admin_required
def delete_downtime():
    data = request.get_json() or {}
    where_clause, params = build_safe_delete_filter(data.get('filter_type'), data.get('filter_value'), 'down_time')
    if where_clause is None:
        return jsonify({"error": "Filter tidak valid"}), 400
    
    try:
        conn = db_manager.get_connection()
        cursor = conn.execute(f'DELETE FROM downtime_history WHERE {where_clause}', params)
        deleted_count = cursor.rowcount
        conn.execute(
            'INSERT INTO delete_log (table_name, filter_type, filter_value, rows_deleted, deleted_by) VALUES (?, ?, ?, ?, ?)',
            ('downtime_history', data.get('filter_type'), data.get('filter_value'), deleted_count, session.get('username'))
        )
        conn.commit()
        conn.close()
        log_audit('DELETE', 'downtime_history', None, data, {"deleted": deleted_count})
        return jsonify({"deleted": deleted_count, "message": f"Berhasil menghapus {deleted_count} data downtime."}), 200
    except Exception as e:
        logger.error(f"Error deleting downtime: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete/latency', methods=['DELETE'])
@admin_required
def delete_latency():
    data = request.get_json() or {}
    where_clause, params = build_safe_delete_filter(data.get('filter_type'), data.get('filter_value'), 'timestamp')
    if where_clause is None:
        return jsonify({"error": "Filter tidak valid"}), 400
    
    try:
        conn = db_manager.get_connection()
        cursor = conn.execute(f'DELETE FROM latency_history WHERE {where_clause}', params)
        deleted_count = cursor.rowcount
        conn.execute(
            'INSERT INTO delete_log (table_name, filter_type, filter_value, rows_deleted, deleted_by) VALUES (?, ?, ?, ?, ?)',
            ('latency_history', data.get('filter_type'), data.get('filter_value'), deleted_count, session.get('username'))
        )
        conn.commit()
        conn.close()
        log_audit('DELETE', 'latency_history', None, data, {"deleted": deleted_count})
        return jsonify({"deleted": deleted_count, "message": f"Berhasil menghapus {deleted_count} data latensi."}), 200
    except Exception as e:
        logger.error(f"Error deleting latency: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete/runtime', methods=['DELETE'])
@admin_required
def delete_runtime():
    data = request.get_json() or {}
    filter_type = data.get('filter_type', 'all')
    filter_value = data.get('filter_value')
    
    try:
        conn = db_manager.get_connection()
        if filter_type == 'all':
            cursor = conn.execute('DELETE FROM runtime_states')
        elif filter_type == 'site' and filter_value:
            routers = conn.execute('SELECT ip FROM routers WHERE site = ?', (filter_value,)).fetchall()
            ips = [r['ip'] for r in routers]
            if ips:
                placeholders = ','.join('?' * len(ips))
                cursor = conn.execute(f'DELETE FROM runtime_states WHERE ip IN ({placeholders})', ips)
            else:
                cursor = conn.execute('DELETE FROM runtime_states WHERE 1=0')
        else:
            cursor = conn.execute('DELETE FROM runtime_states WHERE 1=0')
        
        deleted_count = cursor.rowcount
        conn.execute(
            'INSERT INTO delete_log (table_name, filter_type, filter_value, rows_deleted, deleted_by) VALUES (?, ?, ?, ?, ?)',
            ('runtime_states', filter_type, filter_value, deleted_count, session.get('username'))
        )
        conn.commit()
        conn.close()
        log_audit('DELETE', 'runtime_states', None, data, {"deleted": deleted_count})
        return jsonify({"deleted": deleted_count, "message": f"Berhasil mereset {deleted_count} status runtime."}), 200
    except Exception as e:
        logger.error(f"Error deleting runtime: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete/log', methods=['GET'])
@admin_required
def get_delete_log():
    try:
        conn = db_manager.get_connection()
        logs = conn.execute('SELECT * FROM delete_log ORDER BY deleted_at DESC LIMIT 50').fetchall()
        conn.close()
        return jsonify([dict(row) for row in logs])
    except Exception as e:
        logger.error(f"Error getting delete log: {e}")
        return jsonify({"error": str(e)}), 500

# --- Audit Trail Endpoints ---
@app.route('/api/audit/log', methods=['GET'])
@admin_required
def get_audit_log():
    try:
        conn = db_manager.get_connection()
        logs = conn.execute('SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 100').fetchall()
        conn.close()
        return jsonify([dict(row) for row in logs])
    except Exception as e:
        logger.error(f"Error getting audit log: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/audit/log', methods=['DELETE'])
@super_admin_required
def delete_audit_log():
    data = request.get_json() or {}
    filter_type = data.get('filter_type', 'all')
    filter_value = data.get('filter_value')
    try:
        conn = db_manager.get_connection()
        if filter_type == 'all':
            cursor = conn.execute('DELETE FROM audit_log')
        elif filter_type == 'date' and filter_value:
            cursor = conn.execute('DELETE FROM audit_log WHERE created_at < ?', (filter_value,))
        elif filter_type == 'user' and filter_value:
            cursor = conn.execute('DELETE FROM audit_log WHERE username = ?', (filter_value,))
        else:
            cursor = conn.execute('DELETE FROM audit_log WHERE 1=0')
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        log_audit('DELETE', 'audit_log', None, data, {"deleted": deleted_count})
        return jsonify({"deleted": deleted_count, "message": f"Berhasil menghapus {deleted_count} log audit."}), 200
    except Exception as e:
        logger.error(f"Error deleting audit log: {e}")
        return jsonify({"error": str(e)}), 500

# --- Background Scheduler Setup (Runs Only Once) ---
def init_scheduler():
    # Avoid duplicate scheduler execution in Werkzeug reloader or multi-worker setups
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'false':
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(check_all_routers, 'interval', seconds=60, id='sdwan_monitor_job', replace_existing=True)
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown(wait=False))
        logger.info("SD-WAN Monitoring Scheduler successfully started (interval: 60s)")
    except Exception as e:
        logger.warning(f"Could not initialize APScheduler: {e}")

init_scheduler()

if __name__ == '__main__':
    # Listen on all interfaces on port 5000
    app.run(host='0.0.0.0', port=5000, debug=False)
