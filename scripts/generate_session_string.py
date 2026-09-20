"""
Utility Script: Generate Telethon StringSession.

Run this script locally to authenticate with your Telegram account and generate
a portable `TELEGRAM_SESSION_STRING` for cloud deployments (Railway, Render, Fly.io, etc.).
"""

import asyncio
import os
import sys

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
except ImportError:
    print("❌ Error: Telethon is not installed. Please run: pip install telethon")
    sys.exit(1)


async def main() -> None:
    print("=" * 65)
    print("🔑 Telethon StringSession Generator for Cloud Deployments")
    print("=" * 65)

    api_id_str = os.getenv("TELEGRAM_API_ID") or input("Enter TELEGRAM_API_ID: ").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH") or input("Enter TELEGRAM_API_HASH: ").strip()

    if not api_id_str or not api_hash:
        print("❌ Error: TELEGRAM_API_ID and TELEGRAM_API_HASH are required.")
        return

    try:
        api_id = int(api_id_str)
    except ValueError:
        print("❌ Error: TELEGRAM_API_ID must be a valid integer.")
        return

    print("\nConnecting to Telegram MTProto servers...")
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start()

    session_string = client.session.save()
    me = await client.get_me()

    print("\n" + "=" * 65)
    print("🎉 Authentication successful!")
    print(f"User: {getattr(me, 'first_name', '')} (@{getattr(me, 'username', '')}) [ID: {getattr(me, 'id', '')}]")
    print("=" * 65)
    print("\nCopy and paste this string into your .env file:\n")
    print(f"TELEGRAM_SESSION_STRING={session_string}\n")
    print("=" * 65)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
