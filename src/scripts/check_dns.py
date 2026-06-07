import asyncio
import socket
from src.config import settings
from urllib.parse import urlparse

async def check_dns():
    try:
        url = settings.DATABASE_URL
        parsed = urlparse(url)
        hostname = parsed.hostname
        print(f"Attempting to resolve hostname: {hostname}")
        addr = socket.gethostbyname(hostname)
        print(f"Resolved to: {addr}")
    except Exception as e:
        print(f"DNS Resolution failed: {e}")

if __name__ == "__main__":
    asyncio.run(check_dns())
