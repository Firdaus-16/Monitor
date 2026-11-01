#!/usr/bin/env python3
"""Monitoring module for SD-WAN"""
import subprocess
import platform
import time
import logging
from datetime import datetime
from database import DatabaseManager
from telegram_bot import send_telegram_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db_manager = DatabaseManager()

LATENCY_WARNING_MS = 150
LATENCY_CRITICAL_MS = 200
CONSISTENCY_CHECKS = 5

def check_router(router, conn):
    ip = router['ip']
    site = router['site']
    provider = router['provider']
    name = router['name']
    
    state = conn.execute('SELECT * FROM runtime_states WHERE ip = ?', (ip,)).fetchone()
    is_up = ping_host(ip)
    new_status = 'up' if is_up else 'down'
    latency = check_latency(ip) if is_up else None
    
    if state is None:
        conn.execute('''
            INSERT INTO runtime_states 
            (ip, status, first_rto_time, down_time, up_since, fail_count, 
             high_latency_active, high_latency_fail_count, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ip, new_status,
              datetime.now() if not is_up else None,
              datetime.now() if not is_up else None,
              datetime.now() if is_up else None,
              0 if is_up else 1,
              False, 0, datetime.now()))
    else:
        old_status = state['status']
        fail_count = state['fail_count']
        high_latency_active = state['high_latency_active']
        high_latency_fail_count = state['high_latency_fail_count']
        first_down_time = state['down_time']
        
        if old_status == 'up' and new_status == 'down':
            fail_count = 1
            conn.execute('''
                UPDATE runtime_states 
                SET status = ?, first_rto_time = ?, down_time = ?, fail_count = ?, last_updated = ?
                WHERE ip = ?
            ''', (new_status, datetime.now(), datetime.now(), fail_count, datetime.now(), ip))
            if fail_count >= CONSISTENCY_CHECKS:
                send_telegram_message(f"WARNING: {provider.upper()} DOWN konsisten di {site} ({ip}) - 5 menit", provider=provider)
                check_both_down(site, conn)
        
        elif old_status == 'down' and new_status == 'up':
            down_duration = (datetime.now() - datetime.fromisoformat(first_down_time)).total_seconds()
            conn.execute('''
                UPDATE runtime_states 
                SET status = ?, up_since = ?, fail_count = 0, last_updated = ?
                WHERE ip = ?
            ''', (new_status, datetime.now(), datetime.now(), ip))
            conn.execute('''
                INSERT INTO downtime_history (name, ip, provider, down_time, up_time, duration_sec)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (name, ip, provider, first_down_time, datetime.now(), int(down_duration)))
            send_telegram_message(f"OK: {provider.upper()} UP kembali di {site} ({ip}) - Down selama {int(down_duration/60)} menit", provider=provider)
        
        elif old_status == 'down' and new_status == 'down':
            fail_count += 1
            conn.execute('UPDATE runtime_states SET fail_count = ?, last_updated = ? WHERE ip = ?', (fail_count, datetime.now(), ip))
            if fail_count == CONSISTENCY_CHECKS:
                send_telegram_message(f"WARNING: {provider.upper()} DOWN konsisten di {site} ({ip}) - 5 menit", provider=provider)
                check_both_down(site, conn)
            elif fail_count % 60 == 0:
                hours = fail_count // 60
                send_telegram_message(f"REMINDER: {provider.upper()} masih DOWN di {site} ({ip}) - {hours} jam", provider=provider)
        
        if is_up and latency is not None:
            if latency > LATENCY_WARNING_MS:
                high_latency_fail_count += 1
                conn.execute('UPDATE runtime_states SET high_latency_fail_count = ?, last_updated = ? WHERE ip = ?', (high_latency_fail_count, datetime.now(), ip))
                if high_latency_fail_count == CONSISTENCY_CHECKS and not high_latency_active:
                    high_latency_active = True
                    conn.execute('UPDATE runtime_states SET high_latency_active = ?, last_updated = ? WHERE ip = ?', (high_latency_active, datetime.now(), ip))
                    if latency > LATENCY_CRITICAL_MS:
                        send_telegram_message(f"CRITICAL: Latency SANGAT TINGGI konsisten di {site} ({ip}): {latency}ms selama 5 menit", provider=provider)
                    else:
                        send_telegram_message(f"WARNING: Latency tinggi konsisten di {site} ({ip}): {latency}ms selama 5 menit", provider=provider)
            else:
                if high_latency_active:
                    high_latency_active = False
                    conn.execute('UPDATE runtime_states SET high_latency_active = ?, high_latency_fail_count = 0, last_updated = ? WHERE ip = ?', (high_latency_active, 0, datetime.now(), ip))
                    send_telegram_message(f"OK: Latency normal kembali di {site} ({ip}): {latency}ms", provider=provider)
                else:
                    conn.execute('UPDATE runtime_states SET high_latency_fail_count = 0, last_updated = ? WHERE ip = ?', (datetime.now(), ip))
            conn.execute('INSERT INTO latency_history (name, ip, provider, latency) VALUES (?, ?, ?, ?)', (name, ip, provider, latency))

def check_both_down(site, conn):
    routers = conn.execute('SELECT * FROM routers WHERE site = ?', (site,)).fetchall()
    providers_down = []
    for router in routers:
        state = conn.execute('SELECT status, fail_count FROM runtime_states WHERE ip = ?', (router['ip'],)).fetchone()
        if state and state['status'] == 'down' and state['fail_count'] >= CONSISTENCY_CHECKS:
            providers_down.append(router['provider'])
    if 'lintasarta' in providers_down and 'icon' in providers_down:
        send_telegram_message(f"CRITICAL: KEDUA LINK DOWN konsisten di {site}! - 5 menit. Kemungkinan listrik mati.", provider='lintasarta')
def ping_host(ip):
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '1', '-w', '2000', ip]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        return result.returncode == 0
    except:
        return False

def check_latency(ip):
    start = time.time()
    if ping_host(ip):
        return round((time.time() - start) * 1000, 2)
    return None

def check_all_routers():
    try:
        conn = db_manager.get_connection()
        routers = conn.execute('SELECT * FROM routers').fetchall()
        for router in routers:
            check_router(router, conn)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error checking routers: {e}")
def check_both_down(site, conn):
    routers = conn.execute('SELECT * FROM routers WHERE site = ?', (site,)).fetchall()
    providers_down = []
    for router in routers:
        state = conn.execute('SELECT status, fail_count FROM runtime_states WHERE ip = ?', (router['ip'],)).fetchone()
        if state and state['status'] == 'down' and state['fail_count'] >= CONSISTENCY_CHECKS:
            providers_down.append(router['provider'])
    if 'lintasarta' in providers_down and 'icon' in providers_down:
        send_telegram_message(f"CRITICAL: KEDUA LINK DOWN konsisten di {site}! - 5 menit. Kemungkinan listrik mati.", provider='lintasarta')
        send_telegram_message(f"CRITICAL: KEDUA LINK DOWN konsisten di {site}! - 5 menit. Kemungkinan listrik mati.", provider='icon')
def check_both_down(site, conn):
    routers = conn.execute('SELECT * FROM routers WHERE site = ?', (site,)).fetchall()
    providers_down = []
    for router in routers:
        state = conn.execute('SELECT status, fail_count FROM runtime_states WHERE ip = ?', (router['ip'],)).fetchone()
        if state and state['status'] == 'down' and state['fail_count'] >= CONSISTENCY_CHECKS:
            providers_down.append(router['provider'])
    if 'lintasarta' in providers_down and 'icon' in providers_down:
        send_telegram_message(f"CRITICAL: KEDUA LINK DOWN konsisten di {site}! - 5 menit. Kemungkinan listrik mati.", provider='lintasarta')
        send_telegram_message(f"CRITICAL: KEDUA LINK DOWN konsisten di {site}! - 5 menit. Kemungkinan listrik mati.", provider='icon')
        send_telegram_message(f"CRITICAL: KEDUA LINK DOWN konsisten di {site}! - 5 menit. Kemungkinan listrik mati.", provider='icon')
def ping_host(ip):
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '1', '-w', '2000', ip]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        return result.returncode == 0
    except:
        return False

def check_latency(ip):
    start = time.time()
    if ping_host(ip):
        return round((time.time() - start) * 1000, 2)
    return None

def check_all_routers():
    try:
        conn = db_manager.get_connection()
        routers = conn.execute('SELECT * FROM routers').fetchall()
        for router in routers:
            check_router(router, conn)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error checking routers: {e}")
def ping_host(ip):
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '1', '-w', '2000', ip]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        return result.returncode == 0
    except:
        return False

def check_latency(ip):
    start = time.time()
    if ping_host(ip):
        return round((time.time() - start) * 1000, 2)
    return None

def check_all_routers():
    try:
        conn = db_manager.get_connection()
        routers = conn.execute('SELECT * FROM routers').fetchall()
        for router in routers:
            check_router(router, conn)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error checking routers: {e}")
#!/usr/bin/env python3
"""Monitoring module placeholder"""
import logging
logger = logging.getLogger(__name__)
