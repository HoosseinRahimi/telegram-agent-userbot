"""
Telegram AI Agent Userbot - Main Application Entrypoint.

Bootstraps configuration, initializes modular LLM engine, sets up security filters,
wires Telethon event listeners, starts the periodic digest worker, and manages graceful shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Optional

from client.telethon_client import UserbotClient
from config.settings import get_settings
from filters.pipeline import build_default_pipeline
from handlers.dm_handler import register_dm_handler
from handlers.saved_messages_handler import register_saved_messages_handler
from llm.factory import create_llm_provider
from scheduler.digest_scheduler import DigestScheduler
from services.alert_service import AlertService
from services.auto_reply_service import AutoReplyService
from services.digest_service import DigestService
from services.humanizer import HumanizerService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("UserbotMain")


async def async_main() -> None:
    """
    Asynchronous application bootstrap and lifecycle loop.
    """
    logger.info("=" * 60)
    logger.info("Initializing Telegram AI Agent Userbot...")
    logger.info("=" * 60)

    # 1. Load application configuration
    try:
        settings = get_settings()
        logger.info(f"Loaded configuration for LLM provider: '{settings.llm_provider}'")
    except Exception as exc:
        logger.critical(f"Failed to load or validate settings: {exc}")
        sys.exit(1)

    # 2. Instantiate core client & modular dependencies
    userbot_client = UserbotClient(settings=settings)
    llm_provider = create_llm_provider(settings=settings)
    filter_pipeline = build_default_pipeline(settings=settings)

    # 3. Instantiate domain services
    alert_service = AlertService(userbot_client=userbot_client)
    humanizer_service = HumanizerService(userbot_client=userbot_client)
    auto_reply_service = AutoReplyService(
        userbot_client=userbot_client,
        llm_provider=llm_provider,
        filter_pipeline=filter_pipeline,
        alert_service=alert_service,
        humanizer_service=humanizer_service,
        persona_prompt_path=settings.persona_prompt_path,
    )
    digest_service = DigestService(
        userbot_client=userbot_client,
        llm_provider=llm_provider,
    )

    # 4. Wire Telethon event handlers
    raw_telethon = userbot_client.client
    register_dm_handler(raw_telethon, auto_reply_service)
    register_saved_messages_handler(raw_telethon, digest_service, settings)

    # 5. Initialize background scheduler
    scheduler = DigestScheduler(digest_service=digest_service, settings=settings)

    # 6. Lifecycle startup
    await userbot_client.start()
    scheduler.start()
    logger.info("🟢 Userbot successfully started and listening for incoming messages.")
    logger.info("Press Ctrl+C to terminate.")

    # 7. Run until disconnected or interrupted
    try:
        await userbot_client.run_until_disconnected()
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Received termination signal. Shutting down...")
    finally:
        await scheduler.stop()
        await userbot_client.disconnect()
        logger.info("🔴 Userbot stopped gracefully.")


def main() -> None:
    """Synchronous process entrypoint."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user.")


if __name__ == "__main__":
    main()
