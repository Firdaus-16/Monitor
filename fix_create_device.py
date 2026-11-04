#!/usr/bin/env python3
import io

with io.open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = """        cursor = conn.execute('''
            INSERT INTO routers (site, name, ip_lintas, ip_icon, provider, access_type,
                                 nojar_cpe_versa, nojar_starlink, latitude, longitude, timezone,
                                 router_versa_name, router_model, router_versa_regist, psu_regist,
                                 pic_name, pic_phone, pic_provider_phone,
                                 access_lintas, access_icon, kuota_langganan)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            site, data.get('site'), None, None, 'dual', data.get('access_type', 'SD-WAN'),"""

new = """        cursor = conn.execute('''
            INSERT INTO routers (site, name, ip, ip_lintas, ip_icon, provider, access_type,
                                 nojar_cpe_versa, nojar_starlink, latitude, longitude, timezone,
                                 router_versa_name, router_model, router_versa_regist, psu_regist,
                                 pic_name, pic_phone, pic_provider_phone,
                                 access_lintas, access_icon, kuota_langganan)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            site, data.get('site'), '', None, None, 'dual', data.get('access_type', 'SD-WAN'),"""

if old in content:
    content = content.replace(old, new, 1)
    print("Fixed create_device INSERT")
else:
    print("Pattern NOT found")

with io.open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)