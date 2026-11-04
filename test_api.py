#!/usr/bin/env python3
import time
from app import app

c = app.test_client()
c.post('/login', data={'username': 'admin', 'password': 'admin123'})

time.sleep(1)
r = c.get('/api/routers')
print('Status:', r.status_code)
data = r.get_json()
print('Routers count:', len(data) if data else 0)
if data:
    print('First router keys:', list(data[0].keys()) if isinstance(data, list) else 'not list')
print('Done')