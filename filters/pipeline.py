"""
Filter Pipeline Orchestrator.

Chains security, bot, blacklist, and sensitive content filters with short-circuit evaluation.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from config.settings import Settings
from .base import BaseFilter, FilterContext, FilterResult
from .blacklist_filter import BlacklistFilter
from .bot_filter import BotFilter
from .sensitive_filter import SensitiveFilter
from .system_filter import SystemFilter

logger = logging.getLogger(__name__)


class FilterPipeline:
    """
    Executes an ordered sequence of filters with short-circuit evaluation.
    """

    def __init__(self, filters: Optional[List[BaseFilter]] = None) -> None:
        self.filters: List[BaseFilter] = filters or []

    def add_filter(self, filter_instance: BaseFilter) -> None:
        """Appends a filter to the pipeline."""
        self.filters.append(filter_instance)

    async def evaluate(self, context: FilterContext) -> FilterResult:
        """
        Runs all registered filters in order. Short-circuits on the first failure.
        """
        for flt in self.filters:
            res = await flt.check(context)
            if not res.allowed:
                logger.info(
                    f"[FilterPipeline] Filter '{flt.filter_name}' blocked message "
                    f"from {context.sender_id} (@{context.sender_username}): {res.reason}"
                )
                return res

        return FilterResult.allow()


def build_default_pipeline(settings: Settings) -> FilterPipeline:
    """
    Constructs the standard production filter pipeline configured from Settings.
    """
    pipeline = FilterPipeline()
    pipeline.add_filter(SystemFilter())
    pipeline.add_filter(BotFilter())
    pipeline.add_filter(BlacklistFilter(blacklist=settings.blacklist_users))
    pipeline.add_filter(SensitiveFilter(sensitive_keywords=settings.sensitive_keywords))
    return pipeline
