"""telegram/handlers/trades.py -- Phase P Fix P-4a/b/c/d."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
from aiogram import Dispatcher, F, types

from ....core.config import settings
from ....core.logger import get_logger
from ..keyboards import get_confirm_keyboard, get_trades_keyboard
from ..rbac_service import rbac_service
from ..utils import format_trade_list

logger = get_logger("telegram.handlers.trades")

_API_PREFIX = getattr(settings, "API_PREFIX", "/api/v1") or "/api/v1"
API_BASE = os.environ.get("API_BASE_URL", f"http://localhost:{settings.API_PORT}") + _API_PREFIX
_HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


async def _api_get(path: str, token: str) -> Optional[Dict[str, Any]]:
    """FIX P-4a: timeout enforced. FIX P-4b: no internal error in user msg."""
    url = f"{API_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        logger.warning("[trades] GET %s timed out", url)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("[trades] GET %s HTTP %d", url, exc.response.status_code)
        return None
    except Exception as exc:
        logger.error("[trades] GET %s error: %s", url, exc)
        return None


async def _api_post(path: str, token: str, data: Dict) -> Optional[Dict[str, Any]]:
    """FIX P-4a: timeout enforced on POST."""
    url = f"{API_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(url, json=data, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        logger.warning("[trades] POST %s timed out", url)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("[trades] POST %s HTTP %d", url, exc.response.status_code)
        return None
    except Exception as exc:
        logger.error("[trades] POST %s error: %s", url, exc)
        return None


def register_trade_handlers(dp: Dispatcher) -> None:

    @dp.message(F.text == "\U0001f4ca \u0645\u0639\u0627\u0645\u0644\u0627\u062a \u0645\u0646")
    async def menu_trades(message: types.Message) -> None:
        user = await rbac_service.get_user_by_telegram_id(message.from_user.id)
        if not user:
            await message.answer(
                "\u26a0\ufe0f \u0628\u0631\u0627\u06cc \u062f\u0633\u062a\u0631\u0633\u06cc \u0628\u0647 \u0645\u0639\u0627\u0645\u0644\u0627\u062a \u0628\u0627\u06cc\u062f \u062b\u0628\u062a\u200c\u0646\u0627\u0645 \u06a9\u0646\u06cc\u062f.",
                parse_mode="HTML",
            )
            return
        role = await rbac_service.get_user_role(message.from_user.id)
        if role and role.value in ("trader", "admin", "super_admin"):
            await message.answer(
                "\U0001f4ca <b>\u0645\u062f\u06cc\u0631\u06cc\u062a \u0645\u0639\u0627\u0645\u0644\u0627\u062a</b>\n\n\u06af\u0632\u06cc\u0646\u0647 \u0645\u0648\u0631\u062f \u0646\u0638\u0631 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
                reply_markup=get_trades_keyboard(full=True),
                parse_mode="HTML",
            )
        else:
            await message.answer(
                "\U0001f4ca <b>\u0645\u0639\u0627\u0645\u0644\u0627\u062a</b>\n\n\u06af\u0632\u06cc\u0646\u0647 \u0645\u0648\u0631\u062f \u0646\u0638\u0631 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u06cc\u062f:",
                reply_markup=get_trades_keyboard(full=False),
                parse_mode="HTML",
            )

    @dp.message(
        F.text == "\U0001f4cb \u0645\u0639\u0627\u0645\u0644\u0627\u062a \u0628\u0627\u0632"
    )
    async def show_open_trades(message: types.Message) -> None:
        token = await rbac_service.get_user_token(message.from_user.id)
        if not token:
            await message.answer(
                "\u26d4\ufe0f \u0644\u0637\u0641\u0627\u064b \u0627\u0628\u062a\u062f\u0627 \u0648\u0627\u0631\u062f \u0634\u0648\u06cc\u062f."
            )
            return
        data = await _api_get("/trades/open", token)
        if data is None:
            await message.answer(
                "\u274c \u062e\u0637\u0627 \u062f\u0631 \u062f\u0631\u06cc\u0627\u0641\u062a \u0645\u0639\u0627\u0645\u0644\u0627\u062a. \u0644\u0637\u0641\u0627\u064b \u062f\u0648\u0628\u0627\u0631\u0647 \u062a\u0644\u0627\u0634 \u06a9\u0646\u06cc\u062f.",
                parse_mode="HTML",
            )
            return
        trades = data.get("trades", [])
        if not trades:
            await message.answer(
                "\U0001f4ed \u0647\u06cc\u0686 \u0645\u0639\u0627\u0645\u0644\u0647 \u0628\u0627\u0632\u06cc \u0648\u062c\u0648\u062f \u0646\u062f\u0627\u0631\u062f.",
                parse_mode="HTML",
            )
            return
        await message.answer(format_trade_list(trades), parse_mode="HTML")

    @dp.message(
        F.text
        == "\U0001f4dc \u062a\u0627\u0631\u06cc\u062e\u0686\u0647 \u0645\u0639\u0627\u0645\u0644\u0627\u062a"
    )
    async def show_trade_history(message: types.Message) -> None:
        token = await rbac_service.get_user_token(message.from_user.id)
        if not token:
            await message.answer(
                "\u26d4\ufe0f \u0644\u0637\u0641\u0627\u064b \u0627\u0628\u062a\u062f\u0627 \u0648\u0627\u0631\u062f \u0634\u0648\u06cc\u062f."
            )
            return
        data = await _api_get("/trades/history?limit=20", token)
        if data is None:
            await message.answer(
                "\u274c \u062e\u0637\u0627 \u062f\u0631 \u062f\u0631\u06cc\u0627\u0641\u062a \u062a\u0627\u0631\u06cc\u062e\u0686\u0647. \u0644\u0637\u0641\u0627\u064b \u062f\u0648\u0628\u0627\u0631\u0647 \u062a\u0644\u0627\u0634 \u06a9\u0646\u06cc\u062f."
            )
            return
        trades = data.get("trades", [])
        if not trades:
            await message.answer(
                "\U0001f4ed \u062a\u0627\u0631\u06cc\u062e\u0686\u0647\u200c\u0627\u06cc \u06cc\u0627\u0641\u062a \u0646\u0634\u062f."
            )
            return
        await message.answer(format_trade_list(trades), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("close_trade:"))
    async def request_close_trade(callback: types.CallbackQuery) -> None:
        """FIX P-4c: show confirm keyboard before closing."""
        trade_id = callback.data.split(":", 1)[-1]
        if not trade_id.replace("-", "").replace("_", "").isalnum():
            await callback.answer(
                "\u274c \u0634\u0646\u0627\u0633\u0647 \u0646\u0627\u0645\u0639\u062a\u0628\u0631.",
                show_alert=True,
            )
            return
        await callback.message.answer(
            f"\u26a0\ufe0f <b>\u0622\u06cc\u0627 \u0645\u0637\u0645\u0626\u0646 \u0647\u0633\u062a\u06cc\u062f?</b>\n\n"
            f"\u0645\u0639\u0627\u0645\u0644\u0647 <code>{trade_id}</code> \u0628\u0633\u062a\u0647 \u062e\u0648\u0627\u0647\u062f \u0634\u062f.",
            reply_markup=get_confirm_keyboard(
                confirm_data=f"confirm_close:{trade_id}",
                cancel_data="cancel_close",
            ),
            parse_mode="HTML",
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("confirm_close:"))
    async def confirm_close_trade(callback: types.CallbackQuery) -> None:
        trade_id = callback.data.split(":", 1)[-1]
        token = await rbac_service.get_user_token(callback.from_user.id)
        if not token:
            await callback.answer(
                "\u26d4\ufe0f \u0646\u06cc\u0627\u0632 \u0628\u0647 \u0627\u062d\u0631\u0627\u0632 \u0647\u0648\u06cc\u062a.",
                show_alert=True,
            )
            return
        result = await _api_post(f"/trades/{trade_id}/close", token, {})
        if result is None:
            await callback.message.answer(
                "\u274c \u0628\u0633\u062a\u0646 \u0645\u0639\u0627\u0645\u0644\u0647 \u0628\u0627 \u062e\u0637\u0627 \u0645\u0648\u0627\u062c\u0647 \u0634\u062f."
            )
        else:
            await callback.message.answer(
                f"\u2705 \u0645\u0639\u0627\u0645\u0644\u0647 <code>{trade_id}</code> \u0628\u0633\u062a\u0647 \u0634\u062f.",
                parse_mode="HTML",
            )
        await callback.answer()

    @dp.callback_query(F.data == "cancel_close")
    async def cancel_close_trade(callback: types.CallbackQuery) -> None:
        await callback.message.answer(
            "\u274e \u0628\u0633\u062a\u0646 \u0645\u0639\u0627\u0645\u0644\u0647 \u0644\u063a\u0648 \u0634\u062f."
        )
        await callback.answer()
