#!/usr/bin/env python3
"""Monitoring module for Enterprise SD-WAN Monitoring System (Dual-Link Support)"""
import subprocess
import platform
import time
import re
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from database import DatabaseManager
from telegram_bot import send_telegram_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db_manager = DatabaseManager()

LATENCY_WARNING_MS = 150
LATENCY_CRITICAL_MS = 200
CONSISTENCY_CHECKS = 5

def ping_host_and_latency(ip):
    """
    Ping a host once and return (is_up, latency_ms).
    Cross-platform support for Windows and Linux.
    """
    if not ip or not str(ip).strip():
        return False, None

    ip_str = str(ip).strip()
    is_windows = platform.system().lower() == 'windows'
    if is_windows:
        command = ['ping', '-n', '1', '-w', '2000', ip_str]
    else:
        command = ['ping', '-c', '1', '-W', '2', ip_str]

    start_time = time.time()
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4, text=True)
        elapsed_ms = round((time.time() - start_time) * 1000, 2)
        if result.returncode == 0:
            match = re.search(r'(?:time|waktu)[=<](\d+(?:\.\d+)?)\s*ms', result.stdout, re.IGNORECASE)
            if match:
                latency = round(float(match.group(1)), 2)
            else:
                latency = elapsed_ms
            return True, latency
        return False, None
    except Exception:
        return False, None

def ping_host(ip):
    is_up, _ = ping_host_and_latency(ip)
    return is_up

def check_latency(ip):
    _, latency = ping_host_and_latency(ip)
    return latency

def check_single_link(ip, provider, site, name, conn, ping_res=None, nojar_versa=None, nojar_starlink=None):
    """Update runtime state and incident history for a specific link IP."""
    if not ip:
        return None

    if ping_res is not None:
        is_up, latency = ping_res
    else:
        is_up, latency = ping_host_and_latency(ip)

    new_status = 'up' if is_up else 'down'
    now_dt = datetime.now()
    now_str = now_dt.strftime('%Y-%m-%d %H:%M:%S')

    state = conn.execute('SELECT * FROM runtime_states WHERE ip = ?', (ip,)).fetchone()

    if state is None:
        conn.execute('''
            INSERT INTO runtime_states 
            (ip, status, first_rto_time, down_time, up_since, fail_count, 
             high_latency_active, high_latency_fail_count, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            ip, new_status,
            now_str if not is_up else None,
            now_str if not is_up else None,
            now_str if is_up else None,
            0 if is_up else 1,
            False, 0, now_str
        ))
        if not is_up:
            provider_label = 'Lintasarta' if str(provider).lower().startswith('lintas') else 'ICON'
            link_label = 'Link 1 (Lintasarta)' if str(provider).lower().startswith('lintas') else 'Link 2 (ICON/Fiber)'
            send_telegram_message(
                f"🚨 <b>LINK DOWN — {provider_label}</b> ({link_label})\\n"
                f"━━━━━━━━━━━━━━━━\\n"
                f"Cabang     : <b>{site}</b>\\n"
                f"IP {link_label}   : <code>{ip}</code>\\n"
                f"Nojar Versa (Lintasarta)   : {nojar_versa or '-'}\\n"
                f"Nojar Starlink (Lintasarta): {nojar_starlink or '-'}\\n"
                f"Waktu Down : {now_str}",
                provider=provider
            )
    else:
        old_status = state['status']
        fail_count = state['fail_count'] or 0
        high_latency_active = bool(state['high_latency_active'])
        high_latency_fail_count = state['high_latency_fail_count'] or 0
        first_down_time = state['down_time']

        # UP -> DOWN
        if old_status == 'up' and new_status == 'down':
            fail_count = 1
            conn.execute('''
                UPDATE runtime_states 
                SET status = ?, first_rto_time = ?, down_time = ?, fail_count = ?, last_updated = ?
                WHERE ip = ?
            ''', (new_status, now_str, now_str, fail_count, now_str, ip))
            # Immediate down notification with nojar info
            provider_label = 'Lintasarta' if str(provider).lower().startswith('lintas') else 'ICON'
            link_label = 'Link 1 (Lintasarta)' if str(provider).lower().startswith('lintas') else 'Link 2 (ICON/Fiber)'
            send_telegram_message(
                f"🚨 <b>LINK DOWN — {provider_label}</b> ({link_label})\\n"
                f"━━━━━━━━━━━━━━━━\\n"
                f"Cabang     : <b>{site}</b>\\n"
                f"IP {link_label}   : <code>{ip}</code>\\n"
                f"Nojar Versa (Lintasarta)   : {nojar_versa or '-'}\\n"
                f"Nojar Starlink (Lintasarta): {nojar_starlink or '-'}\\n"
                f"Waktu Down : {now_str}",
                provider=provider
            )
            if fail_count >= CONSISTENCY_CHECKS:
                send_telegram_message(f"⚠️ <b>WARNING</b>: Link {provider.upper()} DOWN di {site} ({ip}) - {CONSISTENCY_CHECKS} menit\nVersa: {nojar_versa or '-'}\nStarlink: {nojar_starlink or '-'}", provider=provider)

        # DOWN -> UP
        elif old_status == 'down' and new_status == 'up':
            down_duration = 0
            if first_down_time:
                try:
                    dt_clean = str(first_down_time).replace('T', ' ').split('.')[0]
                    start_dt = datetime.strptime(dt_clean, '%Y-%m-%d %H:%M:%S')
                    down_duration = int((now_dt - start_dt).total_seconds())
                except Exception:
                    down_duration = 0

            conn.execute('''
                UPDATE runtime_states 
                SET status = ?, up_since = ?, fail_count = 0, last_updated = ?
                WHERE ip = ?
            ''', (new_status, now_str, now_str, ip))

            conn.execute('''
                INSERT INTO downtime_history (site, name, ip, provider, down_time, up_time, duration_sec)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (site, name, ip, provider, first_down_time or now_str, now_str, down_duration))

            duration_min = max(1, int(down_duration / 60)) if down_duration else 0
            duration_sec = down_duration % 60 if down_duration else 0
            duration_str = f"{duration_min} menit {duration_sec} detik" if down_duration else "-"
            provider_label = 'Lintasarta' if str(provider).lower().startswith('lintas') else 'ICON'
            link_label = 'Link 1 (Lintasarta)' if str(provider).lower().startswith('lintas') else 'Link 2 (ICON/Fiber)'
            send_telegram_message(
                f"✅ <b>LINK UP (RECOVERED)</b> — {provider_label} ({link_label})\\n"
                f"━━━━━━━━━━━━━━━━\\n"
                f"Cabang     : <b>{site}</b>\\n"
                f"IP {link_label}   : <code>{ip}</code>\\n"
                f"Nojar Versa (Lintasarta)   : {nojar_versa or '-'}\\n"
                f"Nojar Starlink (Lintasarta): {nojar_starlink or '-'}\\n"
                f"Waktu Down : {first_down_time or now_str}\\n"
                f"Waktu Up   : {now_str}\\n"
                f"Durasi Down: {duration_str}",
                provider=provider
            )

        # Still DOWN
        elif old_status == 'down' and new_status == 'down':
            fail_count += 1
            conn.execute('UPDATE runtime_states SET fail_count = ?, last_updated = ? WHERE ip = ?', (fail_count, now_str, ip))
            if fail_count == CONSISTENCY_CHECKS:
                provider_label = 'Lintasarta' if str(provider).lower().startswith('lintas') else 'ICON'
                link_label = 'Link 1 (Lintasarta)' if str(provider).lower().startswith('lintas') else 'Link 2 (ICON/Fiber)'
                send_telegram_message(f"⚠️ <b>WARNING</b>: {provider_label} DOWN konsisten di {site} ({ip}) - {CONSISTENCY_CHECKS} menit ({link_label})\nNojar Versa (Lintasarta): {nojar_versa or '-'}\nNojar Starlink (Lintasarta): {nojar_starlink or '-'}", provider=provider)
            elif fail_count > 0 and fail_count % 60 == 0:
                hours = fail_count // 60
                provider_label = 'Lintasarta' if str(provider).lower().startswith('lintas') else 'ICON'
                link_label = 'Link 1 (Lintasarta)' if str(provider).lower().startswith('lintas') else 'Link 2 (ICON/Fiber)'
                send_telegram_message(f"🔔 <b>REMINDER</b>: {provider_label} masih DOWN di {site} ({ip}) - Sudah {hours} jam ({link_label})\nNojar Versa (Lintasarta): {nojar_versa or '-'}\nNojar Starlink (Lintasarta): {nojar_starlink or '-'}", provider=provider)

        # Latency check for UP router
        if is_up and latency is not None:
            if latency > LATENCY_WARNING_MS:
                high_latency_fail_count += 1
                conn.execute('UPDATE runtime_states SET high_latency_fail_count = ?, last_updated = ? WHERE ip = ?', (high_latency_fail_count, now_str, ip))
                if high_latency_fail_count == CONSISTENCY_CHECKS and not high_latency_active:
                    high_latency_active = True
                    conn.execute('UPDATE runtime_states SET high_latency_active = 1, last_updated = ? WHERE ip = ?', (now_str, ip))
                    if latency > LATENCY_CRITICAL_MS:
                        provider_label = 'Lintasarta' if str(provider).lower().startswith('lintas') else 'ICON'
                        link_label = 'Link 1 (Lintasarta)' if str(provider).lower().startswith('lintas') else 'Link 2 (ICON/Fiber)'
                        send_telegram_message(f"🔴 <b>CRITICAL</b>: Latency {provider_label} SANGAT TINGGI di {site} ({ip}): {latency}ms selama {CONSISTENCY_CHECKS} menit ({link_label})\nNojar Versa (Lintasarta): {nojar_versa or '-'}\nNojar Starlink (Lintasarta): {nojar_starlink or '-'}", provider=provider)
                    else:
                        send_telegram_message(f"🟡 <b>WARNING</b>: Latency {provider_label} tinggi di {site} ({ip}): {latency}ms selama {CONSISTENCY_CHECKS} menit ({link_label})\nNojar Versa (Lintasarta): {nojar_versa or '-'}\nNojar Starlink (Lintasarta): {nojar_starlink or '-'}", provider=provider)
            else:
                if high_latency_active:
                    high_latency_active = False
                    conn.execute('UPDATE runtime_states SET high_latency_active = 0, high_latency_fail_count = 0, last_updated = ? WHERE ip = ?', (now_str, ip))
                    provider_label = 'Lintasarta' if str(provider).lower().startswith('lintas') else 'ICON'
                    link_label = 'Link 1 (Lintasarta)' if str(provider).lower().startswith('lintas') else 'Link 2 (ICON/Fiber)'
                    send_telegram_message(f"🟢 <b>OK</b>: Latency {provider_label} normal kembali di {site} ({ip}): {latency}ms ({link_label})\nNojar Versa (Lintasarta): {nojar_versa or '-'}\nNojar Starlink (Lintasarta): {nojar_starlink or '-'}", provider=provider)
                else:
                    conn.execute('UPDATE runtime_states SET high_latency_fail_count = 0, last_updated = ? WHERE ip = ?', (now_str, ip))

            conn.execute('''
                INSERT INTO latency_history (site, name, ip, provider, latency, timestamp) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (site, name, ip, provider, latency, now_str))

    return new_status

def check_all_routers():
    """
    Monitor all SD-WAN routers concurrently.
    Pings both ip_lintas and ip_icon for each branch.
    """
    try:
        conn = db_manager.get_connection()
        routers = conn.execute('SELECT * FROM routers').fetchall()
        if not routers:
            conn.close()
            return

        # Prepare targets: (ip, provider, site, router_name)
        targets = []
        for r in routers:
            site = r['site']
            name = r['name']
            ip_lintas = r['ip_lintas'] if 'ip_lintas' in r.keys() else None
            ip_icon = r['ip_icon'] if 'ip_icon' in r.keys() else None
            legacy_ip = r['ip']
            nojar_versa = r['nojar_cpe_versa'] if 'nojar_cpe_versa' in r.keys() else None
            nojar_starlink = r['nojar_starlink'] if 'nojar_starlink' in r.keys() else None

            if ip_lintas:
                targets.append({'ip': ip_lintas, 'provider': 'lintasarta', 'site': site, 'name': name, 'nojar_versa': nojar_versa, 'nojar_starlink': nojar_starlink})
            if ip_icon:
                targets.append({'ip': ip_icon, 'provider': 'icon', 'site': site, 'name': name, 'nojar_versa': nojar_versa, 'nojar_starlink': nojar_starlink})
            if not ip_lintas and not ip_icon and legacy_ip:
                targets.append({'ip': legacy_ip, 'provider': r['provider'] or 'sdwan', 'site': site, 'name': name, 'nojar_versa': nojar_versa, 'nojar_starlink': nojar_starlink})

        if not targets:
            conn.close()
            return

        # Ping targets concurrently
        def worker(target):
            res = ping_host_and_latency(target['ip'])
            return target, res

        with ThreadPoolExecutor(max_workers=min(25, max(1, len(targets)))) as executor:
            results = list(executor.map(worker, targets))

        # Batch update database in main thread
        for target, ping_res in results:
            check_single_link(target['ip'], target['provider'], target['site'], target['name'], conn, ping_res=ping_res, nojar_versa=target.get('nojar_versa'), nojar_starlink=target.get('nojar_starlink'))

        # Check for Dual Link Down (Both Down) per branch
        for r in routers:
            site = r['site']
            ip_lintas = r['ip_lintas'] if 'ip_lintas' in r.keys() else None
            ip_icon = r['ip_icon'] if 'ip_icon' in r.keys() else None
            nojar_versa = r['nojar_cpe_versa'] if 'nojar_cpe_versa' in r.keys() else None
            nojar_starlink = r['nojar_starlink'] if 'nojar_starlink' in r.keys() else None

            if ip_lintas and ip_icon:
                state_l = conn.execute('SELECT status, fail_count FROM runtime_states WHERE ip = ?', (ip_lintas,)).fetchone()
                state_i = conn.execute('SELECT status, fail_count FROM runtime_states WHERE ip = ?', (ip_icon,)).fetchone()
                if (state_l and state_l['status'] == 'down' and state_l['fail_count'] >= CONSISTENCY_CHECKS and
                    state_i and state_i['status'] == 'down' and state_i['fail_count'] >= CONSISTENCY_CHECKS):
                    # Trigger alert only when threshold reached exactly or hourly reminder
                    if state_l['fail_count'] == CONSISTENCY_CHECKS or state_i['fail_count'] == CONSISTENCY_CHECKS:
                        send_telegram_message(
                            f"🚨🚨 <b>CRITICAL: KEDUA LINK DOWN</b> di <b>{site}</b>!\n"
                            f"━━━━━━━━━━━━━━━━\n"
                            f"Link 1 (Lintasarta) : {ip_lintas} [DOWN]\n"
                            f"Link 2 (ICON/Fiber) : {ip_icon} [DOWN]\n"
                            f"Nojar Versa (Lintasarta)   : {nojar_versa or '-'}\n"
                            f"Nojar Starlink (Lintasarta): {nojar_starlink or '-'}\n"
                            f"Kemungkinan blackout listrik di lokasi cabang.",
                            provider='all'
                        )

        conn.commit()
        conn.close()
        logger.info(f"Checked {len(results)} link targets across {len(routers)} SD-WAN branches.")
    except Exception as e:
        logger.error(f"Error checking all routers: {e}")

if __name__ == "__main__":
    check_all_routers()
