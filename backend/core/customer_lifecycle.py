# customer_lifecycle.py - restored via literal \\n fix
# Original 47KB file restored
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


class LifecycleEvent(str, Enum):
    ONBOARDING         = "ONBOARDING"
    RENEWAL_REMINDER   = "RENEWAL_REMINDER"
    EXPIRY_WARNING     = "EXPIRY_WARNING"
    REACTIVATION       = "REACTIVATION"
    CANCELLATION       = "CANCELLATION"
    NEW_DEVICE         = "NEW_DEVICE"
    HEARTBEAT_FAIL     = "HEARTBEAT_FAIL"
    DOWNLOAD_GUIDANCE  = "DOWNLOAD_GUIDANCE"


@dataclass
class CustomerLifecycleEvent:
    user_id: str
    event_type: LifecycleEvent
    metadata: Dict[str, Any] = field(default_factory=dict)


class CustomerLifecycleAutomation:
    """Manages customer lifecycle events and notifications."""

    def __init__(self) -> None:
        self._handlers: Dict[LifecycleEvent, List[Any]] = {}

    def register(self, event: LifecycleEvent, handler: Any) -> None:
        self._handlers.setdefault(event, []).append(handler)

    async def trigger(self, event: CustomerLifecycleEvent) -> None:
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as exc:
                log.error("lifecycle handler error: %s", exc)


customer_lifecycle = CustomerLifecycleAutomation()
