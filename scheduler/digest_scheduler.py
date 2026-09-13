"""
Periodic Digest Scheduler Worker.

Runs an asynchronous native background task that periodically fetches channel
updates and delivers automated digests to Saved Messages.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from config.settings import Settings
from services.digest_service import DigestService

logger = logging.getLogger(__name__)


class DigestScheduler:
    """
    Lightweight, dependency-free background scheduler for periodic digest reports.
    """

    def __init__(
        self,
        digest_service: DigestService,
        settings: Settings,
        sleep_func: Optional[callable] = None,
    ) -> None:
        self.service = digest_service
        self.settings = settings
        self.sleep = sleep_func or asyncio.sleep
        self._task: Optional[asyncio.Task[None]] = None
        self._running: bool = False

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    async def _loop(self) -> None:
        interval_seconds = max(60, self.settings.digest_interval_minutes * 60)
        logger.info(
            f"[DigestScheduler] Started. Periodic interval: {self.settings.digest_interval_minutes}m "
            f"({interval_seconds}s)."
        )

        while self._running:
            try:
                await self.sleep(interval_seconds)
                if not self._running:
                    break

                if self.settings.digest_channels:
                    logger.info("[DigestScheduler] Triggering scheduled periodic channels digest...")
                    await self.service.generate_channels_digest(
                        channels=self.settings.digest_channels,
                        limit_per_channel=20,
                        deliver_to="me",
                    )
            except asyncio.CancelledError:
                logger.info("[DigestScheduler] Scheduled task cancelled.")
                break
            except Exception as exc:
                logger.error(f"[DigestScheduler] Error during scheduled digest run: {exc}")
                # Brief pause before continuing loop on error
                await self.sleep(10)

    def start(self) -> None:
        """Starts the background periodic digest worker."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stops and cancels the background worker."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("[DigestScheduler] Stopped successfully.")
