"""Register all Telegram routers onto the Dispatcher."""
from __future__ import annotations

from aiogram import Dispatcher

from .start import router as start_router
from .help import router as help_router
from .signal import router as signal_router
from .analysis import router as analysis_router
from .admin import router as admin_router
from .callbacks import router as callback_router


def register_all_routers(dp: Dispatcher) -> None:
    """Include all routers. Order matters: more specific first."""
    dp.include_router(admin_router)     # admin commands first
    dp.include_router(start_router)
    dp.include_router(help_router)
    dp.include_router(signal_router)
    dp.include_router(analysis_router)
    dp.include_router(callback_router)  # inline keyboard callbacks last
