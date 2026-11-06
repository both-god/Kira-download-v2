"""បង្កើត SESSION_STRING សម្រាប់ Userbot: python gen_session.py"""
import asyncio
from pyrogram import Client


async def main():
    api_id = int(input("API_ID: "))
    api_hash = input("API_HASH: ").strip()
    async with Client("gen", api_id=api_id, api_hash=api_hash, in_memory=True) as app:
        print("\nSESSION_STRING=" + await app.export_session_string())


asyncio.run(main())
