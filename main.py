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
from services.state_repository import StateRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("UserbotMain")


async def async_main() -> None:
    """
    Asynchronous application bootstrap and lifecycle loop with graceful shutdown.
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

    # 2. Load persistent runtime state
    state_repo = StateRepository()
    persisted_provider = state_repo.get_llm_provider()
    if persisted_provider:
        settings.llm_provider = persisted_provider
        logger.info(f"[StateRepository] Restored active LLM provider: '{persisted_provider}'")

    persisted_bl = state_repo.get_blacklist()
    for entry in persisted_bl:
        if entry not in settings.blacklist_users:
            settings.blacklist_users.append(entry)

    userbot_client: UserbotClient | None = None
    debouncer = None
    scheduler: DigestScheduler | None = None

    try:
        # 3. Instantiate core client & modular dependencies
        userbot_client = UserbotClient(settings=settings)
        llm_provider = create_llm_provider(settings=settings)
        filter_pipeline = build_default_pipeline(settings=settings)

        # 4. Instantiate domain services
        alert_service = AlertService(userbot_client=userbot_client)
        humanizer_service = HumanizerService(userbot_client=userbot_client)
        auto_reply_service = AutoReplyService(
            userbot_client=userbot_client,
            llm_provider=llm_provider,
            filter_pipeline=filter_pipeline,
            alert_service=alert_service,
            humanizer_service=humanizer_service,
            persona_prompt_path=settings.persona_prompt_path,
            auto_reply_enabled=settings.auto_reply_enabled,
            allowlist_users=settings.allowlist_users,
            dry_run=settings.dry_run,
            send_history_to_provider=settings.send_history_to_provider,
            alert_on_blocked_sensitive=settings.alert_on_blocked_sensitive,
            redact_pii_before_llm=settings.redact_pii_before_llm,
        )

        if state_repo.is_paused():
            auto_reply_service.pause()
            logger.info("[StateRepository] Restored paused state for auto-reply.")

        digest_service = DigestService(
            userbot_client=userbot_client,
            llm_provider=llm_provider,
        )

        # 5. Wire Telethon event handlers
        raw_telethon = userbot_client.client
        debouncer = register_dm_handler(raw_telethon, auto_reply_service)
        register_saved_messages_handler(
            raw_telethon,
            digest_service,
            settings,
            auto_reply_service=auto_reply_service,
            filter_pipeline=filter_pipeline,
            state_repo=state_repo,
        )

        # 6. Initialize background scheduler
        scheduler = DigestScheduler(digest_service=digest_service, settings=settings)

        # 7. Lifecycle startup
        await userbot_client.start()
        scheduler.start()
        logger.info("🟢 Userbot successfully started and listening for incoming messages.")
        logger.info("Press Ctrl+C to terminate.")

        # 8. Setup graceful shutdown signals
        shutdown_event = asyncio.Event()

        def _signal_handler() -> None:
            logger.info("Received termination signal (SIGINT/SIGTERM). Requesting shutdown...")
            shutdown_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _signal_handler)
            except (NotImplementedError, RuntimeError, AttributeError):
                signal.signal(sig, lambda *_: shutdown_event.set())

        # Wait until disconnected or shutdown signal
        telethon_task = asyncio.create_task(userbot_client.run_until_disconnected())
        shutdown_task = asyncio.create_task(shutdown_event.wait())

        done, pending = await asyncio.wait(
            [telethon_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for p in pending:
            p.cancel()

    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Process interrupted by user or orchestrator.")
    except Exception as exc:
        logger.error(f"Unexpected fatal runtime error: {exc}", exc_info=True)
    finally:
        logger.info("Initiating graceful teardown...")
        if debouncer is not None:
            await debouncer.stop()
        if scheduler is not None:
            await scheduler.stop()
        if userbot_client is not None:
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
