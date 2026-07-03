"""
backend/license/engine.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Galaxy Vast AI Trading Platform — License Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

مسئولیت:
    - صدور و اعتبارسنجی کلید لایسنس با HMAC-SHA256
    - ثبت heartbeat برای جلوگیری از استفاده همزمان روی چند دستگاه
    - پشتیبانی از پلن‌های FREE، BASIC، PRO، ENTERPRISE

نحوه کار:
    1. هر کلید لایسنس یک HMAC-SHA256 از "{user_id}:{plan}:{expiry_epoch}" است
       که با مقدار محرمانه LICENSE_SECRET امضا می‌شود.
    2. متد validate() امضا را تأیید می‌کند، انقضا را بررسی می‌کند،
       و نام پلن را برمی‌گرداند.
    3. متد heartbeat() آخرین زمان فعالیت را ذخیره می‌کند تا از
       replay attack جلوگیری شود.

متغیرهای محیطی:
    LICENSE_SECRET  — کلید امضای HMAC (اجباری در محیط production)
    LICENSE_REPLAY_WINDOW_SECONDS — پنجره زمانی heartbeat (پیش‌فرض: ۳۶۰۰)

استفاده:
    from backend.license.engine import license_engine

    plan = license_engine.validate(license_key, user_id="user_abc")
    if plan is None:
        raise PermissionError("لایسنس نامعتبر یا منقضی شده است")
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ── ثابت‌ها ───────────────────────────────────────────────────────── #

VALID_PLANS = ("FREE", "BASIC", "PRO", "ENTERPRISE")

# پنجره‌ای که در آن یک heartbeat مجاز است (ثانیه)
_DEFAULT_REPLAY_WINDOW = 3_600  # یک ساعت


# ── ساختار داده داخلی ────────────────────────────────────────────────────── #

@dataclass
class _HeartbeatRecord:
    """اطلاعات heartbeat یک کاربر."""
    last_seen: float          # unix timestamp
    machine_id: str           # شناسه دستگاهی که آخرین بار لایسنس را استفاده کرد
    request_count: int = 0    # تعداد کل درخواست‌ها


# ── موتور اصلی ───────────────────────────────────────────────────────────────── #

class LicenseEngine:
    """
    موتور صدور و اعتبارسنجی لایسنس Galaxy Vast AI.

    پارامترها
    ----------
    secret:
        کلید امضای HMAC. باید از متغیر محیطی LICENSE_SECRET خوانده شود.
        هرگز این مقدار را در کد hardcode نکنید.
    replay_window:
        حداکثر فاصله زمانی مجاز بین دو heartbeat متوالی (ثانیه).
    """

    def __init__(
        self,
        secret: Optional[str] = None,
        replay_window: int = _DEFAULT_REPLAY_WINDOW,
    ) -> None:
        raw_secret = secret or os.environ.get("LICENSE_SECRET", "")
        if not raw_secret:
            logger.warning(
                "LICENSE_SECRET تنظیم نشده است. "
                "یک کلید تصادفی موقت تولید می‌شود که پس از راه‌اندازی مجدد تغییر می‌کند."
            )
            raw_secret = secrets.token_hex(32)

        self._secret: bytes = raw_secret.encode("utf-8")
        self._replay_window = replay_window
        self._heartbeats: Dict[str, _HeartbeatRecord] = {}

    # ── API عمومی ──────────────────────────────────────────────────────────────── #

    def issue(
        self,
        user_id: str,
        plan: str,
        ttl_seconds: int = 365 * 24 * 3600,
    ) -> str:
        """
        یک کلید لایسنس جدید صادر می‌کند.

        پارامترها
        ----------
        user_id : شناسه یکتای کاربر (معمولاً UUID از Supabase)
        plan    : نام پلن — باید یکی از VALID_PLANS باشد
        ttl_seconds : مدت اعتبار به ثانیه (پیش‌فرض: یک سال)

        بازگشت
        -------
        str  —  کلید لایسنس به فرمت ``{payload}.{hmac}``
        """
        if plan not in VALID_PLANS:
            raise ValueError(f"پلن نامعتبر: {plan!r}. گزینه‌های مجاز: {VALID_PLANS}")
        if not user_id:
            raise ValueError("user_id نمی‌تواند خالی باشد")

        expiry = int(time.time()) + ttl_seconds
        payload = f"{user_id}:{plan}:{expiry}"
        key = f"{payload}.{self._sign(payload)}"
        logger.info("لایسنس صادر شد | user=%s plan=%s expiry=%d", user_id, plan, expiry)
        return key

    def validate(
        self,
        license_key: str,
        user_id: str,
    ) -> Optional[str]:
        """
        کلید لایسنس را تأیید می‌کند.

        بازگشت
        -------
        str | None  —  نام پلن در صورت معتبر بودن، None در غیر این صورت
        """
        try:
            payload, received_sig = license_key.rsplit(".", 1)
        except ValueError:
            logger.warning("فرمت کلید لایسنس نامعتبر است")
            return None

        if not hmac.compare_digest(self._sign(payload), received_sig):
            logger.warning("امضای لایسنس نامعتبر است | user=%s", user_id)
            return None

        try:
            uid, plan, expiry_str = payload.split(":")
            expiry = int(expiry_str)
        except ValueError:
            logger.warning("payload لایسنس قابل تجزیه نیست")
            return None

        if uid != user_id:
            logger.warning("شناسه کاربر با لایسنس مطابقت ندارد | expected=%s got=%s", uid, user_id)
            return None

        if time.time() > expiry:
            logger.info("لایسنس منقضی شده است | user=%s", user_id)
            return None

        if plan not in VALID_PLANS:
            logger.warning("پلن نامعتبر در لایسنس: %s", plan)
            return None

        return plan

    def heartbeat(self, user_id: str, machine_id: str) -> bool:
        """
        ثبت heartbeat برای یک کاربر/دستگاه.
        اگر همان کاربر از دستگاه دیگری heartbeat بفرستد، رد می‌شود.

        بازگشت
        -------
        bool  —  True در صورت موفقیت، False در صورت تشخیص تخلف
        """
        now = time.time()
        record = self._heartbeats.get(user_id)

        if record is not None:
            same_window = (now - record.last_seen) < self._replay_window
            diff_machine = record.machine_id != machine_id
            if same_window and diff_machine:
                logger.warning(
                    "تلاش برای استفاده همزمان از لایسنس | "
                    "user=%s machine_expected=%s machine_got=%s",
                    user_id, record.machine_id, machine_id,
                )
                return False

        self._heartbeats[user_id] = _HeartbeatRecord(
            last_seen=now,
            machine_id=machine_id,
            request_count=(record.request_count + 1) if record else 1,
        )
        return True

    def revoke(self, user_id: str) -> None:
        """لیسنس کاربر را لغو می‌کند."""
        self._heartbeats.pop(user_id, None)
        logger.info("لیسنس کاربر لغو شد | user=%s", user_id)

    def stats(self) -> dict:
        """آمار کلی لایسنس‌های فعال را برمی‌گرداند."""
        return {
            "active_users": len(self._heartbeats),
            "records": [
                {
                    "user_id": uid,
                    "machine_id": r.machine_id,
                    "last_seen": r.last_seen,
                    "request_count": r.request_count,
                }
                for uid, r in self._heartbeats.items()
            ],
        }

    # ── متدهای داخلی ─────────────────────────────────────────────────────────── #

    def _sign(self, payload: str) -> str:
        """حساب HMAC-SHA256 و بازگشت به صورت hex."""
        return hmac.new(
            self._secret,
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


# ── نمونه Singleton ───────────────────────────────────────────────────────────────── #

# این نمونه در سراسر برنامه به اشتراک گذاشته می‌شود.
# کلید امضا از متغیر محیطی LICENSE_SECRET خوانده می‌شود.
license_engine = LicenseEngine()
