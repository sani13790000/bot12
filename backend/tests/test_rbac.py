"""
تست RBAC (Role-Based Access Control)

تست‌های مربوط به نظام نقش‌ها و دسترسی‌ها در تلگرام.

نویسنده: MT5 Trading Team
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from ..telegram.rbac import (
    UserRole, Permission,
    has_permission, get_role_permissions,
    get_role_level, get_min_role_for_permission,
    COMMAND_PERMISSIONS, get_permission_denied_message
)
from ..services.rbac_service import RBACService


# =====================================================
# تست‌های نقش‌ها و دسترسی‌ها
# =====================================================

class TestRolesAndPermissions:
    """تست‌های نقش‌ها و دسترسی‌ها"""

    def test_user_role_permissions(self):
        """تست دسترسی‌های کاربر عادی"""
        permissions = get_role_permissions(UserRole.USER)

        # کاربر عادی باید این دسترسی‌ها را داشته باشد
        assert Permission.VIEW_OWN_REPORTS in permissions
        assert Permission.VIEW_DAILY_REPORT in permissions
        assert Permission.VIEW_SIGNALS in permissions

        # و نباید این دسترسی‌ها را داشته باشد
        assert Permission.CLOSE_ALL_TRADES not in permissions
        assert Permission.START_BOT not in permissions
        assert Permission.MANAGE_USERS not in permissions

    def test_trader_role_permissions(self):
        """تست دسترسی‌های معامله‌گر"""
        permissions = get_role_permissions(UserRole.TRADER)

        # معامله‌گر باید همه دسترسی‌های user + معاملاتی را داشته باشد
        assert Permission.VIEW_OWN_REPORTS in permissions
        assert Permission.CLOSE_ALL_TRADES in permissions
        assert Permission.CLOSE_BUY_TRADES in permissions
        assert Permission.CLOSE_SELL_TRADES in permissions
        assert Permission.ENTRY_ALERT in permissions

        # و نباید دسترسی مدیریتی داشته باشد
        assert Permission.MANAGE_USERS not in permissions
        assert Permission.MANAGE_LICENSES not in permissions

    def test_admin_role_permissions(self):
        """تست دسترسی‌های مدیر"""
        permissions = get_role_permissions(UserRole.ADMIN)

        # مدیر باید همه دسترسی‌های trader + مدیریت را داشته باشد
        assert Permission.CLOSE_ALL_TRADES in permissions
        assert Permission.START_BOT in permissions
        assert Permission.STOP_BOT in permissions
        assert Permission.MANAGE_USERS in permissions

        # فقط super_admin باید license مدیریت کند
        assert Permission.MANAGE_LICENSES not in permissions

    def test_super_admin_role_permissions(self):
        """تست دسترسی‌های مدیر کل"""
        permissions = get_role_permissions(UserRole.SUPER_ADMIN)

        # مدیر کل باید همه دسترسی‌ها را داشته باشد
        assert Permission.CLOSE_ALL_TRADES in permissions
        assert Permission.START_BOT in permissions
        assert Permission.STOP_BOT in permissions
        assert Permission.MANAGE_USERS in permissions
        assert Permission.MANAGE_LICENSES in permissions

    def test_has_permission_true(self):
        """تست بررسی دسترسی - موافق"""
        assert has_permission(UserRole.TRADER, Permission.CLOSE_ALL_TRADES) is True
        assert has_permission(UserRole.ADMIN, Permission.START_BOT) is True
        assert has_permission(UserRole.SUPER_ADMIN, Permission.MANAGE_LICENSES) is True

    def test_has_permission_false(self):
        """تست بررسی دسترسی - مخالف"""
        assert has_permission(UserRole.USER, Permission.CLOSE_ALL_TRADES) is False
        assert has_permission(UserRole.TRADER, Permission.MANAGE_USERS) is False
        assert has_permission(UserRole.ADMIN, Permission.MANAGE_LICENSES) is False

    def test_role_level_comparison(self):
        """تست مقایسه سطوح نقش‌ها"""
        assert get_role_level(UserRole.USER) == 0
        assert get_role_level(UserRole.TRADER) == 1
        assert get_role_level(UserRole.ADMIN) == 2
        assert get_role_level(UserRole.SUPER_ADMIN) == 3

        assert get_role_level(UserRole.USER) < get_role_level(UserRole.TRADER)
        assert get_role_level(UserRole.TRADER) < get_role_level(UserRole.ADMIN)
        assert get_role_level(UserRole.ADMIN) < get_role_level(UserRole.SUPER_ADMIN)

    def test_min_role_for_permission(self):
        """تست حداقل نقش برای دسترسی"""
        # CLOSE_ALL_TRADES حداقل trader نیاز دارد
        assert get_min_role_for_permission(Permission.CLOSE_ALL_TRADES) == UserRole.TRADER

        # MANAGE_USERS حداقل admin نیاز دارد
        assert get_min_role_for_permission(Permission.MANAGE_USERS) == UserRole.ADMIN

        # MANAGE_LICENSES فقط super_admin دارد
        assert get_min_role_for_permission(Permission.MANAGE_LICENSES) == UserRole.SUPER_ADMIN


# =====================================================
# تست‌های Command Permissions
# =====================================================

class TestCommandPermissions:
    """تست دسترسی‌های command"""

    def test_command_permission_mapping(self):
        """تست نگاشت command به permission"""
        assert COMMAND_PERMISSIONS.get("/close_all") == Permission.CLOSE_ALL_TRADES
        assert COMMAND_PERMISSIONS.get("/close_buy") == Permission.CLOSE_BUY_TRADES
        assert COMMAND_PERMISSIONS.get("/close_sell") == Permission.CLOSE_SELL_TRADES
        assert COMMAND_PERMISSIONS.get("/start_bot") == Permission.START_BOT
        assert COMMAND_PERMISSIONS.get("/stop_bot") == Permission.STOP_BOT

    def test_user_allowed_commands(self):
        """تست commandهای مجاز برای user"""
        user_permissions = get_role_permissions(UserRole.USER)

        # user فقط commandهای محدود را می‌تواند اجرا کند
        assert COMMAND_PERMISSIONS.get("/daily") in user_permissions
        # assert COMMAND_PERMISSIONS.get("/signal") in user_permissions

        # نباید بتواند ببندد
        assert COMMAND_PERMISSIONS.get("/close_all") not in user_permissions

    def test_trader_allowed_commands(self):
        """تست commandهای مجاز برای trader"""
        trader_permissions = get_role_permissions(UserRole.TRADER)

        # trader می‌تواند همه معاملات را ببندد
        assert COMMAND_PERMISSIONS.get("/close_all") in trader_permissions
        assert COMMAND_PERMISSIONS.get("/close_buy") in trader_permissions
        assert COMMAND_PERMISSIONS.get("/close_sell") in trader_permissions

        # ولی نمی‌تواند ربات را کنترل کند
        assert COMMAND_PERMISSIONS.get("/start_bot") not in trader_permissions

    def test_admin_allowed_commands(self):
        """تست commandهای مجاز برای admin"""
        admin_permissions = get_role_permissions(UserRole.ADMIN)

        # admin همه commandها به جز license management
        assert COMMAND_PERMISSIONS.get("/start_bot") in admin_permissions
        assert COMMAND_PERMISSIONS.get("/stop_bot") in admin_permissions
        # assert COMMAND_PERMISSIONS.get("/users") in admin_permissions


# =====================================================
# تست‌های RBACService
# =====================================================

class TestRBACService:
    """تست سرویس RBAC"""

    @pytest.mark.asyncio
    async def test_get_user_role_existing(self):
        """تست دریافت نقش کاربر موجود"""
        service = RBACService()

        # Mock دیتابیس
        with patch.object(service, 'get_user_by_telegram_id', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "id": "user-123",
                "role": "trader",
                "status": "active"
            }

            role = await service.get_user_role(12345)
            assert role == UserRole.TRADER

    @pytest.mark.asyncio
    async def test_get_user_role_not_found(self):
        """تست دریافت نقش کاربر ناموجود"""
        service = RBACService()

        with patch.object(service, 'get_user_by_telegram_id', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            role = await service.get_user_role(99999)
            assert role is None

    @pytest.mark.asyncio
    async def test_check_permission_allowed(self):
        """تست بررسی دسترسی مجاز"""
        service = RBACService()

        with patch.object(service, 'get_user_by_telegram_id', new_callable=AsyncMock) as mock_get:
            with patch.object(service, '_check_license', new_callable=AsyncMock) as mock_license:
                mock_get.return_value = {
                    "id": "user-123",
                    "role": "trader",
                    "status": "active"
                }
                mock_license.return_value = {"valid": True, "allowed": True}

                result = await service.check_permission(
                    12345,
                    Permission.CLOSE_ALL_TRADES
                )

                assert result.get("allowed") is True

    @pytest.mark.asyncio
    async def test_check_permission_denied_not_registered(self):
        """تست بررسی دسترسی - عدم ثبت"""
        service = RBACService()

        with patch.object(service, 'get_user_by_telegram_id', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await service.check_permission(
                12345,
                Permission.CLOSE_ALL_TRADES
            )

            assert result.get("allowed") is False
            assert result.get("reason") == "not_registered"

    @pytest.mark.asyncio
    async def test_check_permission_denied_role(self):
        """تست بررسی دسترسی - نقش کافی نیست"""
        service = RBACService()

        with patch.object(service, 'get_user_by_telegram_id', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "id": "user-123",
                "role": "user",  # user نمی‌تواند close_all کند
                "status": "active"
            }

            result = await service.check_permission(
                12345,
                Permission.CLOSE_ALL_TRADES
            )

            assert result.get("allowed") is False
            assert result.get("reason") == "no_permission"

    @pytest.mark.asyncio
    async def test_set_user_role_by_admin(self):
        """تست تغییر نقش توسط admin"""
        service = RBACService()

        with patch.object(service, 'get_user_role', new_callable=AsyncMock) as mock_role:
            with patch.object(service, 'get_user_by_telegram_id', new_callable=AsyncMock) as mock_get:
                mock_role.return_value = UserRole.ADMIN
                mock_get.return_value = {
                    "id": "target-user",
                    "role": "user"
                }

                # با mock دیتابیس
                with patch('..database.db.update', new_callable=AsyncMock) as mock_db:
                    mock_db.return_value = [{"id": "target-user"}]

                    result = await service.set_user_role(
                        telegram_user_id=11111,
                        new_role=UserRole.TRADER,
                        admin_id=12345
                    )

    @pytest.mark.asyncio
    async def test_set_user_role_denied_for_non_admin(self):
        """تست جلوگیری از تغییر نقش توسط غیر admin"""
        service = RBACService()

        with patch.object(service, 'get_user_role', new_callable=AsyncMock) as mock_role:
            mock_role.return_value = UserRole.USER  # user نمی‌تواند نقش تغییر دهد

            result = await service.set_user_role(
                telegram_user_id=11111,
                new_role=UserRole.TRADER,
                admin_id=12345
            )

            assert result is False


# =====================================================
# تست‌های Rate Limiting
# =====================================================

class TestRateLimiting:
    """تست محدودیت نرخ"""

    def test_rate_limiter_allows_initial_requests(self):
        """تست اجازه درخواست‌های اولیه"""
        from ..telegram.auth import rate_limiter

        # پاک کردن state
        rate_limiter._requests.clear()

        user_id = 12345

        # 5 درخواست اول باید مجاز باشد
        for i in range(5):
            assert rate_limiter.check(user_id, "command") is True

    def test_rate_limiter_blocks_after_limit(self):
        """تست بلاک بعد از حد"""
        from ..telegram.auth import rate_limiter

        rate_limiter._requests.clear()
        user_id = 99999

        # پر کردن limit
        for i in range(10):
            rate_limiter.check(user_id, "command")

        # درخواست بعدی نباید مجاز باشد
        assert rate_limiter.check(user_id, "command") is False

    def test_rate_limiter_different_types(self):
        """تست limits مختلف برای انواع مختلف"""
        from ..telegram.auth import rate_limiter

        rate_limiter._requests.clear()
        user_id = 88888

        # sensitive limit کمتر است
        for i in range(5):
            rate_limiter.check(user_id, "sensitive")

        # باید بلاک شود
        assert rate_limiter.check(user_id, "sensitive") is False

        # ولی default باید هنوز کار کند
        assert rate_limiter.check(user_id, "default") is True


# =====================================================
# تست‌های Permission Messages
# =====================================================

class TestPermissionMessages:
    """تست پیام‌های خطای دسترسی"""

    def test_not_registered_message(self):
        """تست پیام عدم ثبت"""
        message = get_permission_denied_message("not_registered")

        assert "ثبت" in message
        assert "دسترسی محدود" in message
        # assert "پشتیبانی" in message

    def test_no_permission_message(self):
        """تست پیام عدم دسترسی"""
        message = get_permission_denied_message(
            "no_permission",
            role="user",
            required_role="trader"
        )

        assert "معامله‌گر" in message or "کاربر" in message

    def test_license_expired_message(self):
        """تست پیام لایسنس منقضی"""
        message = get_permission_denied_message("license_expired")

        assert "لایسنس" in message
        assert "منقضی" in message


# =====================================================
# تست‌های Integration
# =====================================================

class TestRBACIntegration:
    """تست‌های یکپارچه RBAC"""

    @pytest.mark.asyncio
    async def test_command_flow_user_cannot_close(self):
        """تست فلوی command - user نمی‌تواند ببندد"""
        service = RBACService()

        with patch.object(service, 'get_user_by_telegram_id', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "id": "user-123",
                "role": "user",
                "status": "active"
            }

            check = await service.check_command_permission(
                12345,
                "/close_all"
            )

            assert check.get("allowed") is False

    @pytest.mark.asyncio
    async def test_command_flow_trader_can_close(self):
        """تست فلوی command - trader می‌تواند ببندد"""
        service = RBACService()

        with patch.object(service, 'get_user_by_telegram_id', new_callable=AsyncMock) as mock_get:
            with patch.object(service, '_check_license', new_callable=AsyncMock) as mock_license:
                mock_get.return_value = {
                    "id": "user-123",
                    "role": "trader",
                    "status": "active"
                }
                mock_license.return_value = {"valid": True, "allowed": True}

                check = await service.check_command_permission(
                    12345,
                    "/close_all"
                )

                assert check.get("allowed") is True

    @pytest.mark.asyncio
    async def test_command_flow_admin_can_control_bot(self):
        """تست فلوی command - admin می‌تواند ربات کنترل کند"""
        service = RBACService()

        with patch.object(service, 'get_user_by_telegram_id', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "id": "admin-123",
                "role": "admin",
                "status": "active"
            }

            # start_bot
            check = await service.check_command_permission(
                12345,
                "/start_bot"
            )

            assert check.get("allowed") is True


# =====================================================
# اجرای تست
# =====================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
