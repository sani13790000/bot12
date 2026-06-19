"""Help handler."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="help")

_HELP_TEXT = """\
*Galaxy Vast Bot Commands*

\U0001f4ca *Signals*
/signal \u2014 Get latest trading signal
/signal XAUUSD \u2014 Signal for specific symbol

\U0001f50d *Analysis*
/analyze XAUUSD \u2014 Full SMC + PA analysis

\U0001f4c8 *Account*
/status \u2014 Account status
/risk \u2014 Risk management status

*Admin only:*
/admin \u2014 Admin panel
/broadcast \u003cmsg\u003e \u2014 Broadcast to all users
/stats \u2014 Bot statistics
"""


@router.message(Command("help"))
async def cmd_help(message: Message, **kwargs) -> None:
    await message.answer(_HELP_TEXT)
