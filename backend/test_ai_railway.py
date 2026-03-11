import os
from dotenv import load_dotenv
import psycopg2
from jose import jwt
from datetime import datetime, timedelta
import urllib.request as r
import urllib.error as e

load_dotenv()
SECRET_KEY = os.getenv('SECRET_KEY', 'supersecretkey_change_in_production')
DATABASE_URL = os.getenv('DATABASE_URL')
# ensure it uses postgresql:// for psycopg2
DATABASE_URL = DATABASE_URL.replace('postgresql+asyncpg://', 'postgresql://')

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT email FROM users LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("No user in DB")
        exit(1)
    
    email = row[0]
    print(f"User: {email}")
    
    expire = datetime.utcnow() + timedelta(minutes=60)
    token = jwt.encode({'sub': email, 'exp': expire}, SECRET_KEY, algorithm='HS256')
    
    req = r.Request(
        'https://ai-consulting-tools-production-d8b0.up.railway.app/api/v1/ai/watchlist-analysis?symbols=NVDA,BTC', 
        method='GET', 
        headers={'Origin': 'https://frontend-production-24613.up.railway.app', 'Authorization': f'Bearer {token}'}
    )
    
    try:
        res = r.urlopen(req, timeout=120)
        print('STATUS:', res.getcode())
        print('BODY:', res.read().decode()[:500])
    except e.HTTPError as err:
        print('HTTP ERROR:', err.code)
        print('BODY:', err.read().decode())
    except Exception as ex:
        print('URLOPEN CRASH:', type(ex), ex)

except Exception as ex:
    print("CRASH:", type(ex), ex)
