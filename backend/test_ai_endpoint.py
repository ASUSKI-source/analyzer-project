import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from jose import jwt
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import urllib.request as r
import urllib.error as e

load_dotenv()
SECRET_KEY = os.getenv('SECRET_KEY', 'supersecretkey_change_in_production')
DATABASE_URL = os.getenv('DATABASE_URL')
# For asyncpg:
if DATABASE_URL and DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://')

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def main():
    try:
        from app.models.user import User
        async with async_session() as db:
            result = await db.execute(select(User))
            user = result.scalars().first()
            if not user:
                print('No users in DB!')
                return
            print(f'Using user: {user.email}')
            
            expire = datetime.utcnow() + timedelta(minutes=60)
            token = jwt.encode({'sub': user.email, 'exp': expire}, SECRET_KEY, algorithm='HS256')
            print('Token generated. Sending request...')
            
            req = r.Request(
                'http://localhost:8000/api/v1/ai/watchlist-analysis?symbols=NVDA,BTC', 
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
            except Exception as e2:
                print('URL OPEN CRASH:', type(e2), e2)
    except Exception as ex:
        print('CRASH:', type(ex), ex)

asyncio.run(main())
