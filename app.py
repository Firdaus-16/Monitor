#!/usr/bin/env python3
"""
Enterprise SD-WAN Monitoring System - Main Application
"""
import os
import json
from flask import Flask, jsonify, request, render_template, session, redirect, url_for, send_file
import sqlite3
import logging
from datetime import datetime
from werkzeug.security import check_password_hash
from database import DatabaseManager
from telegram_bot import get_setting, set_setting, test_telegram_connection
from monitor import check_all_routers
import atexit

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)
db_manager = DatabaseManager()

def initialize_database():
    if not os.path.exists(db_manager.db_path):
        logger.info("Initializing database...")
        if db_manager.init_db():
            logger.info("Database initialized successfully")
        else:
            logger.error("Failed to initialize database")

initialize_database()

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') not in ['admin', 'super_admin']:
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'super_admin':
            return jsonify({"error": "Super admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function

def log_audit(action, table_name, record_id=None, old_value=None, new_value=None):
    try:
        conn = db_manager.get_connection()
        conn.execute('INSERT INTO audit_log (username, action, table_name, record_id, old_value, new_value, ip_address, user_agent) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (
            session.get('username', 'anonymous'), action, table_name, record_id,
            json.dumps(old_value) if old_value else None,
            json.dumps(new_value) if new_value else None,
            request.remote_addr, request.headers.get('User-Agent', '')))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Audit log error: {e}")

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
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@app.route('/api/routers/<ip>', methods=['PUT'])
@admin_required
def update_router(ip):
    data = request.get_json()
    try:
        conn = db_manager.get_connection()
        old_router = conn.execute('SELECT * FROM routers WHERE ip = ?', (ip,)).fetchone()
        old_value = dict(old_router) if old_router else None
        cursor = conn.execute('''
            UPDATE routers SET site = ?, name = ?, ip = ?, provider = ?, 
                access_type = ?, nojar_cpe_versa = ?, nojar_starlink = ?,
                latitude = ?, longitude = ?, timezone = ?, 
                router_versa_name = ?, router_model = ?, router_versa_regist = ?, psu_regist = ?,
                pic_name = ?, pic_phone = ?, pic_provider_phone = ?, updated_at = CURRENT_TIMESTAMP
            WHERE ip = ?
        ''', (data.get('site'), data.get('name'), data.get('ip'), data.get('provider'),
              data.get('access_type'), data.get('nojar_cpe_versa'), data.get('nojar_starlink'),
              data.get('latitude'), data.get('longitude'), data.get('timezone', 'Asia/Makassar'),
              data.get('router_versa_name'), data.get('router_model'), data.get('router_versa_regist'),
              data.get('psu_regist'), data.get('pic_name'), data.get('pic_phone'), 
              data.get('pic_provider_phone'), ip))
        conn.commit()
        conn.close()
        if cursor.rowcount == 0:
            return jsonify({"error": "Router not found"}), 404
        log_audit('UPDATE', 'routers', ip, old_value, data)
        return jsonify({"message": "Router updated"}), 200
    except Exception as e:
        logger.error(f"Error updating router {ip}: {e}")
        return jsonify({"error": str(e)}), 500
@app.route('/api/routers/<ip>', methods=['DELETE'])
@admin_required
def delete_router(ip):
    try:
        conn = db_manager.get_connection()
        old_router = conn.execute('SELECT * FROM routers WHERE ip = ?', (ip,)).fetchone()
        old_value = dict(old_router) if old_router else None
        cursor = conn.execute('DELETE FROM routers WHERE ip = ?', (ip,))
        conn.commit()
        conn.close()
        if cursor.rowcount == 0:
            return jsonify({"error": "Router not found"}), 404
        log_audit('DELETE', 'routers', ip, old_value, None)
        return jsonify({"message": "Router deleted"}), 200
    except Exception as e:
        logger.error(f"Error deleting router {ip}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/health', methods=['GET'])
@login_required
# Map & Stats endpoints
@app.route('/api/map/routers', methods=['GET'])
@login_required
def get_map_routers():
    """Get routers with coordinates for map"""
    try:
        conn = db_manager.get_connection()
        routers = conn.execute('''
            SELECT site, name, ip, provider, access_type, latitude, longitude, 
                   pic_name, pic_phone, timezone,
                   (SELECT status FROM runtime_states WHERE ip = routers.ip) as status
            FROM routers
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        ''').fetchall()
        conn.close()
        return jsonify([dict(row) for row in routers])
    except Exception as e:
        logger.error(f"Error getting map routers: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/sites', methods=['GET'])
@login_required
def get_sites():
    """Get list of unique sites for filter"""
    try:
        conn = db_manager.get_connection()
        sites = conn.execute('SELECT DISTINCT site FROM routers ORDER BY site').fetchall()
        conn.close()
        return jsonify([row['site'] for row in sites])
    except Exception as e:
        logger.error(f"Error getting sites: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats/downtime-by-site', methods=['GET'])
@login_required
def stats_downtime_by_site():
    """Get downtime count by site for chart"""
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    provider = request.args.get('provider')
    
    try:
        conn = db_manager.get_connection()
        query = '''
            SELECT name, site, provider, COUNT(*) as count, 
                   SUM(duration_sec) as total_duration
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
            params.append(provider)
        
        query += ' GROUP BY name, site, provider ORDER BY count DESC LIMIT 10'
        
        stats = conn.execute(query, params).fetchall()
        conn.close()
        
        return jsonify([dict(row) for row in stats])
    except Exception as e:
        logger.error(f"Error getting downtime stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats/downtime-by-provider', methods=['GET'])
@login_required
def stats_downtime_by_provider():
    """Get downtime count by provider for pie chart"""
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    
    try:
        conn = db_manager.get_connection()
        query = '''
            SELECT provider, COUNT(*) as count, SUM(duration_sec) as total_duration
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
    """Get downtime trend by day for line chart"""
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    provider = request.args.get('provider')
    
    try:
        conn = db_manager.get_connection()
        query = '''
            SELECT DATE(down_time) as date, COUNT(*) as count, 
                   SUM(duration_sec) as total_duration
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
            params.append(provider)
        
        query += ' GROUP BY DATE(down_time) ORDER BY date'
        
        stats = conn.execute(query, params).fetchall()
        conn.close()
        
        return jsonify([dict(row) for row in stats])
    except Exception as e:
        logger.error(f"Error getting trend stats: {e}")
        return jsonify({"error": str(e)}), 500
# Google Maps helper
def get_map_url(lat, lon):
    if lat and lon:
        return f"https://www.google.com/maps?q={lat},{lon}"
    return None

# Scheduler setup
# User management endpoints
@app.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    """Get all users (admin+ only)"""
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
    """Create new user (admin+ only)"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'viewer')
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    
    if role not in ['super_admin', 'admin', 'viewer']:
        return jsonify({"error": "Invalid role"}), 400
    
    if role == 'super_admin' and session.get('role') != 'super_admin':
        return jsonify({"error": "Only super admin can create super admin"}), 403
    
    try:
        conn = db_manager.get_connection()
        
        existing = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if existing:
            conn.close()
            return jsonify({"error": "Username already exists"}), 400
        
        from werkzeug.security import generate_password_hash
        password_hash = generate_password_hash(password)
        cursor = conn.execute('''
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, ?)
        ''', (username, password_hash, role))
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
    """Update user (admin+ only)"""
    data = request.get_json()
    
    try:
        conn = db_manager.get_connection()
        
        old_user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if not old_user:
            conn.close()
            return jsonify({"error": "User not found"}), 404
        
        if old_user['role'] == 'super_admin' and session.get('role') != 'super_admin':
            conn.close()
            return jsonify({"error": "Cannot modify super admin"}), 403
        
        new_role = data.get('role', old_user['role'])
        if new_role not in ['super_admin', 'admin', 'viewer']:
            conn.close()
            return jsonify({"error": "Invalid role"}), 400
        
        if new_role == 'super_admin' and session.get('role') != 'super_admin':
            conn.close()
            return jsonify({"error": "Only super admin can promote to super admin"}), 403
        
        if data.get('password'):
            from werkzeug.security import generate_password_hash
            password_hash = generate_password_hash(data.get('password'))
            conn.execute('''
                UPDATE users SET username = ?, password_hash = ?, role = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (data.get('username', old_user['username']), password_hash, new_role, user_id))
        else:
            conn.execute('''
                UPDATE users SET username = ?, role = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (data.get('username', old_user['username']), new_role, user_id))
        
        conn.commit()
        conn.close()
        
        log_audit('UPDATE', 'users', user_id, dict(old_user), data)
        
        return jsonify({"message": "User updated"}), 200
    except Exception as e:
        logger.error(f"Error updating user {user_id}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@super_admin_required
def delete_user(user_id):
    """Delete user (super_admin only)"""
    try:
        conn = db_manager.get_connection()
        
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            conn.close()
            return jsonify({"error": "User not found"}), 404
        
        if user['role'] == 'super_admin':
            conn.close()
            return jsonify({"error": "Cannot delete super admin"}), 403
        
        if user['id'] == session.get('user_id'):
            conn.close()
            return jsonify({"error": "Cannot delete yourself"}), 403
        
        cursor = conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        
        log_audit('DELETE', 'users', user_id, dict(user), None)
        
        return jsonify({"message": "User deleted"}), 200
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}")
        return jsonify({"error": str(e)}), 500
def health_check():
    return jsonify({"status": "OK", "timestamp": datetime.now().isoformat()}), 200

@app.route('/api/user/info', methods=['GET'])
@login_required
def user_info():
    return jsonify({"username": session.get('username'), "role": session.get('role')})

# Telegram config endpoints
@app.route('/api/telegram/config', methods=['GET'])
@admin_required
def get_telegram_config():
    return jsonify({
        'bot_token': get_setting('telegram_bot_token'),
        'chat_id_lintasarta': get_setting('telegram_chat_id_lintasarta'),
        'chat_id_icon': get_setting('telegram_chat_id_icon'),
        'chat_id_all': get_setting('telegram_chat_id_all'),
    })

@app.route('/api/telegram/config', methods=['POST'])
@admin_required
def save_telegram_config():
    data = request.get_json()
    set_setting('telegram_bot_token', data.get('bot_token', ''))
    set_setting('telegram_chat_id_lintasarta', data.get('chat_id_lintasarta', ''))
    set_setting('telegram_chat_id_icon', data.get('chat_id_icon', ''))
    set_setting('telegram_chat_id_all', data.get('chat_id_all', ''))
    log_audit('CONFIG', 'settings', None, None, data)
    return jsonify({"message": "Telegram configuration saved"}), 200

@app.route('/api/telegram/test', methods=['POST'])
@admin_required
def test_telegram():
    data = request.get_json()
    provider = data.get('provider')
    result = test_telegram_connection(provider)
    return jsonify(result)

# Audit log endpoints
@app.route('/api/audit/log', methods=['GET'])
@login_required
def get_audit_log():
    return jsonify([])
# WhatsApp template endpoints
@app.route('/api/whatsapp/templates', methods=['GET'])
@login_required
def get_whatsapp_templates():
    template_type = request.args.get('type')
    conn = db_manager.get_connection()
    if template_type:
        templates = conn.execute('SELECT * FROM message_templates WHERE type = ?', (template_type,)).fetchall()
    else:
        templates = conn.execute('SELECT * FROM message_templates').fetchall()
# Delete endpoints
def build_delete_filter(filter_type, filter_value, date_column='down_time'):
    if filter_type == 'all':
        return '1=1'
    elif filter_type == 'date':
        parts = filter_value.split(' to ')
        if len(parts) == 2:
            from_date = parts[0].strip()
            to_date = parts[1].strip()
            return f"{date_column} >= '{from_date}' AND {date_column} <= '{to_date} 23:59:59'"
        elif len(parts) == 1:
            return f"{date_column} >= '{parts[0].strip()}'"
    elif filter_type == 'site':
        return f"site = '{filter_value}'"
    elif filter_type == 'provider':
        return f"provider = '{filter_value}'"
    elif filter_type == 'template':
        from datetime import timedelta
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
            return None
        return f"{date_column} >= '{from_date}'"
@app.route('/api/delete/downtime', methods=['DELETE'])
@admin_required
def delete_downtime():
    data = request.get_json()
    filter_type = data.get('filter_type')
    filter_value = data.get('filter_value')
    
    where_clause = build_delete_filter(filter_type, filter_value, 'down_time')
    if where_clause is None:
        return jsonify({"error": "Invalid filter"}), 400
    
    try:
        conn = db_manager.get_connection()
        count = conn.execute(f'SELECT COUNT(*) FROM downtime_history WHERE {where_clause}').fetchone()[0]
        cursor = conn.execute(f'DELETE FROM downtime_history WHERE {where_clause}')
        conn.commit()
        conn.execute('INSERT INTO delete_log (table_name, filter_type, filter_value, rows_deleted, deleted_by) VALUES (?, ?, ?, ?, ?)', ('downtime_history', filter_type, filter_value, cursor.rowcount, session.get('username')))
        conn.commit()
        conn.close()
        log_audit('DELETE', 'downtime_history', None, {'filter_type': filter_type, 'filter_value': filter_value, 'count': count}, None)
        return jsonify({"deleted": cursor.rowcount, "message": f"Deleted {cursor.rowcount} rows"}), 200
    except Exception as e:
        logger.error(f"Error deleting downtime: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete/latency', methods=['DELETE'])
@admin_required
def delete_latency():
    data = request.get_json()
    filter_type = data.get('filter_type')
    filter_value = data.get('filter_value')
    
    where_clause = build_delete_filter(filter_type, filter_value, 'timestamp')
    if where_clause is None:
        return jsonify({"error": "Invalid filter"}), 400
    
    try:
        conn = db_manager.get_connection()
        count = conn.execute(f'SELECT COUNT(*) FROM latency_history WHERE {where_clause}').fetchone()[0]
        cursor = conn.execute(f'DELETE FROM latency_history WHERE {where_clause}')
        conn.commit()
        conn.execute('INSERT INTO delete_log (table_name, filter_type, filter_value, rows_deleted, deleted_by) VALUES (?, ?, ?, ?, ?)', ('latency_history', filter_type, filter_value, cursor.rowcount, session.get('username')))
        conn.commit()
        conn.close()
        log_audit('DELETE', 'latency_history', None, {'filter_type': filter_type, 'filter_value': filter_value, 'count': count}, None)
        return jsonify({"deleted": cursor.rowcount, "message": f"Deleted {cursor.rowcount} rows"}), 200
    except Exception as e:
        logger.error(f"Error deleting latency: {e}")
        return jsonify({"error": str(e)}), 500

# Excel export endpoints
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
            params.append(provider)
        if site:
            query += ' AND name LIKE ?'
            params.append(f'%{site}%')
        
        query += ' ORDER BY down_time DESC'
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            summary_data = {
                'Metric': ['Total Events', 'Total Duration (min)', 'Avg Duration (min)', 
                          'Lintasarta Events', 'ICON Events'],
                'Value': [
                    len(df),
                    round(df['duration_sec'].sum() / 60, 2) if not df.empty else 0,
                    round(df['duration_sec'].mean() / 60, 2) if not df.empty else 0,
                    len(df[df['provider'] == 'lintasarta']),
                    len(df[df['provider'] == 'icon'])
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
            df.to_excel(writer, sheet_name='Downtime Detail', index=False)
            
            if not df.empty:
                site_summary = df.groupby('name').agg({'id': 'count', 'duration_sec': ['sum', 'mean']}).reset_index()
                site_summary.columns = ['Site', 'Total Events', 'Total Duration (s)', 'Avg Duration (s)']
                site_summary.to_excel(writer, sheet_name='Site Summary', index=False)
                
                provider_summary = df.groupby('provider').agg({'id': 'count', 'duration_sec': ['sum', 'mean']}).reset_index()
                provider_summary.columns = ['Provider', 'Total Events', 'Total Duration (s)', 'Avg Duration (s)']
                provider_summary.to_excel(writer, sheet_name='Provider Summary', index=False)
        
        output.seek(0)
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        as_attachment=True, download_name='downtime_report.xlsx')
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
            params.append(provider)
        if site:
            query += ' AND name LIKE ?'
            params.append(f'%{site}%')
        
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
                site_summary = df.groupby('name').agg({'latency': ['mean', 'min', 'max', 'count']}).reset_index()
                site_summary.columns = ['Site', 'Avg Latency', 'Min Latency', 'Max Latency', 'Count']
                site_summary.to_excel(writer, sheet_name='Site Summary', index=False)
        
        output.seek(0)
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        as_attachment=True, download_name='latency_report.xlsx')
    except Exception as e:
        logger.error(f"Error exporting latency: {e}")
        return jsonify({"error": str(e)}), 500

# Scheduler setup
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    
    @scheduler.scheduled_job('interval', seconds=60)
    def scheduled_monitor():
        try:
            check_all_routers()
        except Exception as e:
            logger.error(f"Monitoring error: {e}")
    
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
    logger.info("Scheduler started (60s interval)")
except Exception as e:
    logger.warning(f"Scheduler not available: {e}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
@app.route('/api/delete/runtime', methods=['DELETE'])
@admin_required
def delete_runtime():
    data = request.get_json()
    filter_type = data.get('filter_type')
    filter_value = data.get('filter_value')
    
    try:
        conn = db_manager.get_connection()
        if filter_type == 'all':
            cursor = conn.execute('DELETE FROM runtime_states')
        elif filter_type == 'site':
            routers = conn.execute('SELECT ip FROM routers WHERE site = ?', (filter_value,)).fetchall()
            ips = [r['ip'] for r in routers]
            if ips:
                placeholders = ','.join('?' * len(ips))
                cursor = conn.execute(f'DELETE FROM runtime_states WHERE ip IN ({placeholders})', ips)
            else:
                cursor = conn.execute('DELETE FROM runtime_states WHERE 1=0')
        else:
            cursor = conn.execute('DELETE FROM runtime_states WHERE 1=0')
        
        conn.commit()
        conn.execute('INSERT INTO delete_log (table_name, filter_type, filter_value, rows_deleted, deleted_by) VALUES (?, ?, ?, ?, ?)', ('runtime_states', filter_type, filter_value, cursor.rowcount, session.get('username')))
        conn.commit()
        conn.close()
        log_audit('DELETE', 'runtime_states', None, {'filter_type': filter_type, 'filter_value': filter_value, 'count': cursor.rowcount}, None)
        return jsonify({"deleted": cursor.rowcount, "message": f"Deleted {cursor.rowcount} rows"}), 200
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
    return None

@app.route('/api/delete/preview', methods=['POST'])
@admin_required
def delete_preview():
    data = request.get_json()
    table = data.get('table')
    filter_type = data.get('filter_type')
    filter_value = data.get('filter_value')
    
    table_map = {'downtime': 'downtime_history', 'latency': 'latency_history', 'runtime': 'runtime_states'}
    db_table = table_map.get(table)
    if not db_table:
        return jsonify({"error": "Invalid table"}), 400
    
    date_column = 'down_time' if table == 'downtime' else 'timestamp' if table == 'latency' else 'last_updated'
    where_clause = build_delete_filter(filter_type, filter_value, date_column)
    if where_clause is None:
        return jsonify({"error": "Invalid filter"}), 400
    
    try:
        conn = db_manager.get_connection()
        count = conn.execute(f'SELECT COUNT(*) FROM {db_table} WHERE {where_clause}').fetchone()[0]
        conn.close()
        return jsonify({"count": count})
    except Exception as e:
        logger.error(f"Error previewing delete: {e}")
        return jsonify({"error": str(e)}), 500
# WhatsApp template endpoints
@app.route('/api/whatsapp/templates', methods=['GET'])
@login_required
def get_whatsapp_templates():
    template_type = request.args.get('type')
    conn = db_manager.get_connection()
    if template_type:
        templates = conn.execute('SELECT * FROM message_templates WHERE type = ?', (template_type,)).fetchall()
    else:
        templates = conn.execute('SELECT * FROM message_templates').fetchall()
    conn.close()
    return jsonify([dict(row) for row in templates])

@app.route('/api/whatsapp/templates/<int:template_id>', methods=['PUT'])
@admin_required
def update_whatsapp_template(template_id):
    data = request.get_json()
    try:
        conn = db_manager.get_connection()
        cursor = conn.execute('UPDATE message_templates SET name = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (data.get('name'), data.get('content'), template_id))
        conn.commit()
        conn.close()
        if cursor.rowcount == 0:
            return jsonify({"error": "Template not found"}), 404
        log_audit('UPDATE', 'message_templates', template_id, None, data)
        return jsonify({"message": "Template updated"}), 200
    except Exception as e:
        logger.error(f"Error updating template: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/whatsapp/generate', methods=['POST'])
@login_required
def generate_whatsapp_url():
    data = request.get_json()
    ip = data.get('ip')
    template_type = data.get('template_type')
    template_id = data.get('template_id')
    
    conn = db_manager.get_connection()
    router = conn.execute('SELECT * FROM routers WHERE ip = ?', (ip,)).fetchone()
    template = conn.execute('SELECT * FROM message_templates WHERE id = ?', (template_id,)).fetchone()
    conn.close()
    
    if not router:
        return jsonify({"error": "Router not found"}), 404
    if not template:
        return jsonify({"error": "Template not found"}), 404
    
    message = template['content']
    message = message.replace('{site}', router['site'] or '')
    message = message.replace('{ip}', router['ip'] or '')
    message = message.replace('{pic_name}', router['pic_name'] or 'PIC')
    message = message.replace('{nojar_versa}', router['nojar_cpe_versa'] or '-')
    message = message.replace('{nojar_starlink}', router['nojar_starlink'] or '-')
    
    if template_type == 'pic':
        phone = router['pic_phone']
    else:
        phone = router['pic_provider_phone']
    
    import urllib.parse
    encoded_message = urllib.parse.quote(message)
    whatsapp_url = f"https://wa.me/{phone}?text={encoded_message}"
    
    return jsonify({"url": whatsapp_url, "message": message, "phone": phone})
    conn.close()
    return jsonify([dict(row) for row in templates])

@app.route('/api/whatsapp/templates/<int:template_id>', methods=['PUT'])
@admin_required
def update_whatsapp_template(template_id):
    data = request.get_json()
    try:
        conn = db_manager.get_connection()
        cursor = conn.execute('UPDATE message_templates SET name = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (data.get('name'), data.get('content'), template_id))
        conn.commit()
        conn.close()
        if cursor.rowcount == 0:
            return jsonify({"error": "Template not found"}), 404
        log_audit('UPDATE', 'message_templates', template_id, None, data)
        return jsonify({"message": "Template updated"}), 200
    except Exception as e:
        logger.error(f"Error updating template: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/whatsapp/generate', methods=['POST'])
@login_required
def generate_whatsapp_url():
    data = request.get_json()
    ip = data.get('ip')
    template_type = data.get('template_type')
    template_id = data.get('template_id')
    
    conn = db_manager.get_connection()
    router = conn.execute('SELECT * FROM routers WHERE ip = ?', (ip,)).fetchone()
    template = conn.execute('SELECT * FROM message_templates WHERE id = ?', (template_id,)).fetchone()
    conn.close()
    
    if not router:
        return jsonify({"error": "Router not found"}), 404
    if not template:
        return jsonify({"error": "Template not found"}), 404
    
    message = template['content']
    message = message.replace('{site}', router['site'] or '')
    message = message.replace('{ip}', router['ip'] or '')
    message = message.replace('{pic_name}', router['pic_name'] or 'PIC')
    message = message.replace('{nojar_versa}', router['nojar_cpe_versa'] or '-')
    message = message.replace('{nojar_starlink}', router['nojar_starlink'] or '-')
    
    if template_type == 'pic':
        phone = router['pic_phone']
    else:
        phone = router['pic_provider_phone']
    
    import urllib.parse
    encoded_message = urllib.parse.quote(message)
    whatsapp_url = f"https://wa.me/{phone}?text={encoded_message}"
    
    return jsonify({"url": whatsapp_url, "message": message, "phone": phone})
@app.route('/api/audit/log', methods=['GET'])
@login_required
def get_audit_log():
    if session.get('role') not in ['admin', 'super_admin']:
        return jsonify({"error": "Admin access required"}), 403
    try:
        conn = db_manager.get_connection()
        logs = conn.execute('SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 100').fetchall()
        conn.close()
        return jsonify([dict(row) for row in logs])
    except Exception as e:
        logger.error(f"Error getting audit log: {e}")
    except Exception as e:
        logger.error(f"Error getting audit log: {e}")
        return jsonify({"error": str(e)}), 500
        return jsonify({"error": str(e)}), 500
    if session.get('role') not in ['admin', 'super_admin']:
        return jsonify({"error": "Admin access required"}), 403
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
    data = request.get_json()
    filter_type = data.get('filter_type', 'all')
    filter_value = data.get('filter_value')
    try:
        conn = db_manager.get_connection()
        if filter_type == 'all':
            cursor = conn.execute('DELETE FROM audit_log')
        elif filter_type == 'date':
            cursor = conn.execute('DELETE FROM audit_log WHERE created_at < ?', (filter_value,))
        elif filter_type == 'user':
            cursor = conn.execute('DELETE FROM audit_log WHERE username = ?', (filter_value,))
        conn.commit()
        log_audit('DELETE', 'audit_log', None, {'filter_type': filter_type, 'filter_value': filter_value, 'count': cursor.rowcount}, None)
        conn.close()
        return jsonify({"deleted": cursor.rowcount, "message": f"Deleted {cursor.rowcount} audit logs"}), 200
    except Exception as e:
        logger.error(f"Error deleting audit log: {e}")
        return jsonify({"error": str(e)}), 500
@login_required
def index():
    return render_template('index.html', username=session.get('username'), role=session.get('role'))

@app.route('/api/routers', methods=['GET'])
@login_required
def get_routers():
    try:
        conn = db_manager.get_connection()
        cursor = conn.execute('SELECT * FROM routers')
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
        cursor = conn.execute('SELECT * FROM routers WHERE ip = ?', (ip,))
        router = dict(cursor.fetchone()) if cursor.fetchone() else None
        conn.close()
        return jsonify(router) if router else jsonify({"error": "Router not found"}), 404
    except Exception as e:
        logger.error(f"Error getting router {ip}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/routers', methods=['POST'])
@admin_required
def create_router():
    data = request.get_json()
    try:
        conn = db_manager.get_connection()
        cursor = conn.execute('''
            INSERT INTO routers (site, name, ip, provider, access_type, 
                               nojar_cpe_versa, nojar_starlink, latitude, longitude, timezone,
                               router_versa_name, router_model, router_versa_regist, psu_regist,
                               pic_name, pic_phone, pic_provider_phone)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (data.get('site'), data.get('name'), data.get('ip'), data.get('provider'),
              data.get('access_type'), data.get('nojar_cpe_versa'), data.get('nojar_starlink'),
              data.get('latitude'), data.get('longitude'), data.get('timezone', 'Asia/Makassar'),
              data.get('router_versa_name'), data.get('router_model'), data.get('router_versa_regist'),
              data.get('psu_regist'), data.get('pic_name'), data.get('pic_phone'), data.get('pic_provider_phone')))
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        log_audit('CREATE', 'routers', new_id, None, data)
        return jsonify({"message": "Router created", "id": new_id}), 201
    except Exception as e:
        logger.error(f"Error creating router: {e}")
        return jsonify({"error": str(e)}), 500

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    
    @scheduler.scheduled_job('interval', seconds=60)
    def scheduled_monitor():
        try:
            check_all_routers()
        except Exception as e:
            logger.error(f"Monitoring error: {e}")
    
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())
    logger.info("Scheduler started (60s interval)")
except Exception as e:
    logger.warning(f"Scheduler not available: {e}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
