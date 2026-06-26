from __future__ import annotations

import asyncio
import time
import threading
import uuid
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.core.tenant import (
    CrossTenantAccessError, TenantContext, TenantLimits, TenantPlan,
    TenantRegistry, TenantScope, _tenant_ctx,
    assert_tenant_access, get_current_tenant, get_registry, require_tenant,
)
from backend.core.tenant_scoped import (
    TenantAuditStore, TenantBotStore, TenantLicenseStore,
    TenantLogStore, TenantSignalStore, TenantScopedStore,
    get_license_store, get_signal_store, get_bot_store,
    get_log_store, get_audit_store,
)
from backend.middleware.tenant_middleware import (
    TenantMiddleware, _extract_tenant_id_from_jwt_sub, _is_public,
)


@pytest.fixture(autouse=True)
def reset_singletons():
    get_registry().reset()
    get_license_store().reset()
    get_signal_store().reset()
    get_bot_store().reset()
    get_log_store().reset()
    get_audit_store().reset()
    yield
    get_registry().reset()
    get_license_store().reset()
    get_signal_store().reset()
    get_bot_store().reset()
    get_log_store().reset()
    get_audit_store().reset()


@pytest.fixture
def reg():
    r = get_registry()
    r.register('t_alpha', TenantPlan.PRO,   is_active=True)
    r.register('t_beta',  TenantPlan.BASIC,  is_active=True)
    r.register('t_gamma', TenantPlan.TRIAL,  is_active=True)
    r.register('t_susp',  TenantPlan.BASIC,  is_active=False)
    return r


class TestTenantContext:
    def test_T001_context_fields(self):
        ctx = TenantContext(tenant_id='t_abc', plan=TenantPlan.PRO)
        assert ctx.tenant_id == 't_abc'
        assert ctx.plan == TenantPlan.PRO
        assert ctx.is_active is True

    def test_T002_suspended(self):
        ctx = TenantContext(tenant_id='t_abc', plan=TenantPlan.TRIAL, is_active=False)
        assert ctx.is_suspended() is True

    def test_T003_not_suspended_when_active(self):
        ctx = TenantContext(tenant_id='t_abc', plan=TenantPlan.PRO, is_active=True)
        assert ctx.is_suspended() is False

    def test_T004_limits_trial(self):
        lim = TenantLimits.for_plan(TenantPlan.TRIAL)
        assert lim.max_devices == 1
        assert lim.max_signals_day == 50
        assert lim.max_bots == 1

    def test_T005_limits_pro(self):
        lim = TenantLimits.for_plan(TenantPlan.PRO)
        assert lim.max_devices == 5
        assert lim.max_signals_day == 500
        assert lim.max_bots == 3

    def test_T006_limits_vip(self):
        lim = TenantLimits.for_plan(TenantPlan.VIP)
        assert lim.max_devices == 10
        assert lim.api_rate_per_min == 300

    def test_T007_limits_basic(self):
        lim = TenantLimits.for_plan(TenantPlan.BASIC)
        assert lim.max_devices == 2
        assert lim.max_users == 3

    def test_T008_limits_annual_equals_vip(self):
        vip = TenantLimits.for_plan(TenantPlan.VIP)
        ann = TenantLimits.for_plan(TenantPlan.ANNUAL)
        assert vip.max_devices == ann.max_devices

    def test_T009_context_limits_property(self):
        ctx = TenantContext(tenant_id='t_abc', plan=TenantPlan.VIP)
        assert ctx.limits.max_bots == 5

    def test_T010_unique_created_at(self):
        c1 = TenantContext(tenant_id='t1', plan=TenantPlan.TRIAL)
        time.sleep(0.01)
        c2 = TenantContext(tenant_id='t2', plan=TenantPlan.TRIAL)
        assert c2.created_at >= c1.created_at

    def test_T011_plan_enum_values(self):
        assert TenantPlan.TRIAL  == 'trial'
        assert TenantPlan.PRO    == 'pro'
        assert TenantPlan.VIP    == 'vip'

    def test_T012_limits_unknown_plan_defaults(self):
        lim = TenantLimits.for_plan('unknown_plan')
        assert lim.max_devices == 1

    def test_T013_context_tenant_id_correct(self):
        ctx = TenantContext(tenant_id='t_abc', plan=TenantPlan.PRO)
        assert ctx.tenant_id == 't_abc'

    def test_T014_suspended_tenant_not_active(self):
        ctx = TenantContext(tenant_id='t_x', plan=TenantPlan.PRO, is_active=False)
        assert ctx.is_suspended()
        assert not ctx.is_active

    def test_T015_trial_rate_limit_low(self):
        lim = TenantLimits.for_plan(TenantPlan.TRIAL)
        assert lim.api_rate_per_min < 60

    def test_T016_pro_higher_than_basic(self):
        basic = TenantLimits.for_plan(TenantPlan.BASIC)
        pro   = TenantLimits.for_plan(TenantPlan.PRO)
        assert pro.max_devices > basic.max_devices


class TestTenantScope:
    def test_T017_scope_sets_context(self):
        assert get_current_tenant() is None
        with TenantScope('t_abc', TenantPlan.PRO):
            ctx = get_current_tenant()
            assert ctx is not None
            assert ctx.tenant_id == 't_abc'

    def test_T018_scope_resets_after_exit(self):
        with TenantScope('t_abc'):
            pass
        assert get_current_tenant() is None

    def test_T019_scope_resets_on_exception(self):
        try:
            with TenantScope('t_abc'):
                raise ValueError('boom')
        except ValueError:
            pass
        assert get_current_tenant() is None

    def test_T020_nested_scopes(self):
        with TenantScope('t_outer'):
            assert get_current_tenant().tenant_id == 't_outer'
            with TenantScope('t_inner'):
                assert get_current_tenant().tenant_id == 't_inner'
            assert get_current_tenant().tenant_id == 't_outer'

    def test_T021_require_tenant_raises_without_scope(self):
        with pytest.raises(RuntimeError, match='No tenant context'):
            require_tenant()

    def test_T022_require_tenant_returns_ctx_inside_scope(self):
        with TenantScope('t_abc', TenantPlan.VIP):
            ctx = require_tenant()
            assert ctx.tenant_id == 't_abc'

    def test_T023_async_scope(self):
        async def _inner():
            async with TenantScope('t_async'):
                return get_current_tenant().tenant_id
        result = asyncio.get_event_loop().run_until_complete(_inner())
        assert result == 't_async'

    def test_T024_async_scope_reset_after(self):
        async def _inner():
            async with TenantScope('t_async'):
                pass
            return get_current_tenant()
        result = asyncio.get_event_loop().run_until_complete(_inner())
        assert result is None

    def test_T025_thread_isolation(self):
        results = {}
        def thread_fn(name, tenant_id):
            with TenantScope(tenant_id):
                time.sleep(0.05)
                results[name] = get_current_tenant().tenant_id
        t1 = threading.Thread(target=thread_fn, args=('th1', 't_thread_1'))
        t2 = threading.Thread(target=thread_fn, args=('th2', 't_thread_2'))
        t1.start(); t2.start()
        t1.join();  t2.join()
        assert results['th1'] == 't_thread_1'
        assert results['th2'] == 't_thread_2'

    def test_T026_no_leak_between_requests(self):
        leaked = []
        def req_a():
            with TenantScope('t_req_a'):
                time.sleep(0.02)
        def req_b():
            time.sleep(0.01)
            leaked.append(get_current_tenant())
        t1 = threading.Thread(target=req_a)
        t2 = threading.Thread(target=req_b)
        t1.start(); t2.start()
        t1.join();  t2.join()
        assert leaked[0] is None

    def test_T027_scope_plan_propagated(self):
        with TenantScope('t_x', TenantPlan.VIP):
            ctx = get_current_tenant()
            assert ctx.limits.max_bots == 5

    def test_T028_scope_suspended_flag(self):
        with TenantScope('t_x', is_active=False):
            ctx = get_current_tenant()
            assert ctx.is_suspended()

    def test_T029_multiple_sequential_scopes(self):
        for tenant in ['t1', 't2', 't3']:
            with TenantScope(tenant):
                assert get_current_tenant().tenant_id == tenant
        assert get_current_tenant() is None

    def test_T030_scope_in_list_comprehension(self):
        results = []
        for t in ['ta', 'tb']:
            with TenantScope(t):
                results.append(get_current_tenant().tenant_id)
        assert results == ['ta', 'tb']

    def test_T031_get_current_tenant_none_outside_scope(self):
        assert get_current_tenant() is None

    def test_T032_scope_created_at_set(self):
        before = time.time()
        with TenantScope('t_ts'):
            ctx = get_current_tenant()
            assert ctx.created_at >= before


class TestTenantRegistry:
    def test_T033_register_and_get(self, reg):
        ctx = reg.get('t_alpha')
        assert ctx is not None
        assert ctx.plan == TenantPlan.PRO

    def test_T034_get_unknown_returns_none(self, reg):
        assert reg.get('t_unknown') is None

    def test_T035_all_tenants(self, reg):
        tenants = reg.all_tenants()
        ids = {t.tenant_id for t in tenants}
        assert 't_alpha' in ids

    def test_T036_suspend(self, reg):
        result = reg.suspend('t_alpha', actor='admin_1')
        assert result is True
        assert reg.get('t_alpha').is_suspended()

    def test_T037_reactivate(self, reg):
        reg.suspend('t_beta', actor='admin_1')
        reg.reactivate('t_beta', actor='admin_1')
        assert not reg.get('t_beta').is_suspended()

    def test_T038_suspend_unknown_returns_false(self, reg):
        assert reg.suspend('t_ghost', actor='admin') is False

    def test_T039_audit_log_on_suspend(self, reg):
        reg.suspend('t_alpha', actor='admin_X')
        log = reg.audit_log()
        assert any(e['action'] == 'suspend' and e['tenant_id'] == 't_alpha' for e in log)

    def test_T040_audit_log_on_reactivate(self, reg):
        reg.suspend('t_alpha', actor='admin_X')
        reg.reactivate('t_alpha', actor='admin_X')
        log = reg.audit_log()
        assert any(e['action'] == 'reactivate' for e in log)

    def test_T041_reset_clears_all(self, reg):
        reg.reset()
        assert reg.all_tenants() == []

    def test_T042_suspended_tenant_context_correct(self, reg):
        ctx = reg.get('t_susp')
        assert ctx.is_suspended()

    def test_T043_plan_preserved_after_suspend(self, reg):
        reg.suspend('t_beta', actor='admin')
        assert reg.get('t_beta').plan == TenantPlan.BASIC

    def test_T044_multiple_registrations_overwrite(self, reg):
        reg.register('t_alpha', TenantPlan.VIP)
        assert reg.get('t_alpha').plan == TenantPlan.VIP

    def test_T045_registry_singleton(self):
        assert get_registry() is get_registry()

    def test_T046_concurrent_register(self, reg):
        errors = []
        def _register(i):
            try:
                reg.register(f't_conc_{i}', TenantPlan.TRIAL)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=_register, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []

    def test_T047_audit_actor_recorded(self, reg):
        reg.suspend('t_gamma', actor='admin_99')
        log = reg.audit_log()
        entry = next(e for e in log if e['tenant_id'] == 't_gamma')
        assert entry['actor'] == 'admin_99'

    def test_T048_reactivate_unknown_returns_false(self, reg):
        assert reg.reactivate('t_ghost', actor='admin') is False


class TestAssertTenantAccess:
    def test_T049_same_tenant_allowed(self):
        assert assert_tenant_access('t_a', 't_a', 'customer', 'u1') is True

    def test_T050_cross_tenant_customer_denied(self):
        with pytest.raises(CrossTenantAccessError):
            assert_tenant_access('t_a', 't_b', 'customer', 'u1')

    def test_T051_cross_tenant_admin_allowed(self):
        assert assert_tenant_access('t_a', 't_b', 'admin', 'a1') is True

    def test_T052_cross_tenant_super_admin_allowed(self):
        assert assert_tenant_access('t_a', 't_b', 'super_admin', 'su1') is True

    def test_T053_cross_tenant_support_denied(self):
        with pytest.raises(CrossTenantAccessError):
            assert_tenant_access('t_a', 't_b', 'support', 's1')

    def test_T054_cross_tenant_readonly_denied(self):
        with pytest.raises(CrossTenantAccessError):
            assert_tenant_access('t_a', 't_b', 'readonly', 'r1')

    def test_T055_admin_cross_tenant_creates_audit(self):
        reg = get_registry()
        initial = len(reg.audit_log())
        assert_tenant_access('t_a', 't_b', 'admin', 'a1')
        assert len(reg.audit_log()) > initial

    def test_T056_audit_entry_fields(self):
        reg = get_registry()
        assert_tenant_access('t_a', 't_b', 'admin', 'admin_42', resource_label='license')
        entries = [e for e in reg.audit_log() if e.get('type') == 'cross_tenant_access']
        e = entries[-1]
        assert e['actor_id'] == 'admin_42'
        assert e['resource'] == 'license'

    def test_T057_callback_called(self):
        called = []
        assert_tenant_access('t_a', 't_b', 'admin', 'a1', audit_callbacks=[lambda e: called.append(e)])
        assert len(called) == 1

    def test_T058_callback_not_called_same_tenant(self):
        called = []
        assert_tenant_access('t_a', 't_a', 'customer', 'u1', audit_callbacks=[lambda e: called.append(e)])
        assert len(called) == 0

    def test_T059_error_message_contains_ids(self):
        with pytest.raises(CrossTenantAccessError) as exc:
            assert_tenant_access('t_owner', 't_thief', 'customer', 'u1')
        assert 't_thief' in str(exc.value)

    def test_T060_multiple_callbacks_all_called(self):
        results = []
        cbs = [lambda e, i=i: results.append(i) for i in range(3)]
        assert_tenant_access('t_a', 't_b', 'admin', 'a1', audit_callbacks=cbs)
        assert len(results) == 3

    def test_T061_faulty_callback_doesnt_break(self):
        def bad_cb(e): raise RuntimeError('err')
        result = assert_tenant_access('t_a', 't_b', 'admin', 'a1', audit_callbacks=[bad_cb])
        assert result is True

    def test_T062_resource_label_in_error(self):
        with pytest.raises(CrossTenantAccessError) as exc:
            assert_tenant_access('t_a', 't_b', 'customer', 'u1', resource_label='signal')
        assert 'signal' in str(exc.value)

    def test_T063_empty_role_denied(self):
        with pytest.raises(CrossTenantAccessError):
            assert_tenant_access('t_a', 't_b', '', 'u1')

    def test_T064_no_audit_same_tenant(self):
        reg = get_registry()
        initial = len(reg.audit_log())
        assert_tenant_access('t_a', 't_a', 'customer', 'u1')
        assert len(reg.audit_log()) == initial


class TestTenantScopedStore:
    def setup_method(self):
        self.store = TenantScopedStore()

    def test_T065_put_and_get_same_tenant(self):
        self.store.put('k1', 'value1', 't_a')
        assert self.store.get('k1', 't_a', 't_a', 'customer', 'u1') == 'value1'

    def test_T066_cross_tenant_get_denied(self):
        self.store.put('k1', 'secret', 't_a')
        with pytest.raises(CrossTenantAccessError):
            self.store.get('k1', 't_a', 't_b', 'customer', 'u2')

    def test_T067_admin_cross_tenant_get_allowed(self):
        self.store.put('k1', 'secret', 't_a')
        assert self.store.get('k1', 't_a', 't_b', 'admin', 'a1') == 'secret'

    def test_T068_list_all_own_tenant(self):
        self.store.put('k1', 'v1', 't_a')
        self.store.put('k2', 'v2', 't_a')
        assert len(self.store.list_all('t_a', 't_a', 'customer', 'u1')) == 2

    def test_T069_list_all_cross_tenant_denied(self):
        self.store.put('k1', 'v1', 't_a')
        with pytest.raises(CrossTenantAccessError):
            self.store.list_all('t_a', 't_b', 'customer', 'u2')

    def test_T070_delete_own_tenant(self):
        self.store.put('k1', 'v1', 't_a')
        assert self.store.delete('k1', 't_a', 't_a', 'customer', 'u1') is True
        assert self.store.get('k1', 't_a', 't_a', 'customer', 'u1') is None

    def test_T071_delete_cross_tenant_denied(self):
        self.store.put('k1', 'v1', 't_a')
        with pytest.raises(CrossTenantAccessError):
            self.store.delete('k1', 't_a', 't_b', 'customer', 'u2')

    def test_T072_tenant_count_isolated(self):
        self.store.put('k1', 'v1', 't_a')
        self.store.put('k2', 'v2', 't_a')
        self.store.put('k3', 'v3', 't_b')
        assert self.store.tenant_count('t_a') == 2
        assert self.store.tenant_count('t_b') == 1

    def test_T073_reset_clears_all(self):
        self.store.put('k1', 'v1', 't_a')
        self.store.reset()
        assert self.store.tenant_count('t_a') == 0

    def test_T074_all_tenant_ids(self):
        self.store.put('k1', 'v1', 't_x')
        self.store.put('k2', 'v2', 't_y')
        ids = self.store.all_tenant_ids()
        assert 't_x' in ids and 't_y' in ids

    def test_T075_concurrent_puts_same_tenant(self):
        errors = []
        def _put(i):
            try: self.store.put(f'k_{i}', f'v_{i}', 't_conc')
            except Exception as e: errors.append(e)
        threads = [threading.Thread(target=_put, args=(i,)) for i in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []
        assert self.store.tenant_count('t_conc') == 50

    def test_T076_get_missing_returns_none(self):
        assert self.store.get('missing', 't_a', 't_a', 'customer', 'u1') is None


class TestTenantLicenseStore:
    def setup_method(self):
        self.store = get_license_store()
        self.store.reset()

    def test_T077_issue_license(self):
        lic = self.store.issue('t_a', 'u1', 'hash_abc', max_devices=2)
        assert lic.tenant_id == 't_a'
        assert lic.status == 'active'
        assert lic.is_active

    def test_T078_get_license_same_tenant(self):
        lic = self.store.issue('t_a', 'u1', 'hash_abc')
        fetched = self.store.get_license(lic.license_id, 't_a', 't_a', 'customer', 'u1')
        assert fetched.license_id == lic.license_id

    def test_T079_cross_tenant_license_denied(self):
        lic = self.store.issue('t_a', 'u1', 'hash_abc')
        with pytest.raises(CrossTenantAccessError):
            self.store.get_license(lic.license_id, 't_a', 't_b', 'customer', 'u2')

    def test_T080_admin_cross_tenant_license(self):
        lic = self.store.issue('t_a', 'u1', 'hash_abc')
        fetched = self.store.get_license(lic.license_id, 't_a', 't_b', 'admin', 'adm')
        assert fetched is not None

    def test_T081_revoke_license(self):
        lic = self.store.issue('t_a', 'u1', 'hash_abc')
        assert self.store.revoke(lic.license_id, 't_a') is True
        assert lic.status == 'revoked'

    def test_T082_add_device_within_limit(self):
        lic = self.store.issue('t_a', 'u1', 'hash_abc', max_devices=2)
        assert self.store.add_device(lic.license_id, 't_a', 'dev_1') is True
        assert self.store.add_device(lic.license_id, 't_a', 'dev_2') is True

    def test_T083_add_device_exceeds_limit(self):
        lic = self.store.issue('t_a', 'u1', 'hash_abc', max_devices=1)
        self.store.add_device(lic.license_id, 't_a', 'dev_1')
        assert self.store.add_device(lic.license_id, 't_a', 'dev_2') is False

    def test_T084_add_device_idempotent(self):
        lic = self.store.issue('t_a', 'u1', 'hash_abc', max_devices=3)
        self.store.add_device(lic.license_id, 't_a', 'dev_1')
        self.store.add_device(lic.license_id, 't_a', 'dev_1')
        assert len(lic.device_ids) == 1

    def test_T085_expired_license(self):
        lic = self.store.issue('t_a', 'u1', 'hash_abc', ttl_seconds=0.01)
        time.sleep(0.05)
        assert lic.is_expired and not lic.is_active

    def test_T086_no_expiry(self):
        lic = self.store.issue('t_a', 'u1', 'hash_abc')
        assert not lic.is_expired and lic.is_active

    def test_T087_revoke_unknown(self):
        assert self.store.revoke('ghost', 't_a') is False

    def test_T088_tenant_isolation(self):
        l_a = self.store.issue('t_a', 'u1', 'hash_a')
        self.store.issue('t_b', 'u2', 'hash_b')
        all_a = self.store.list_all('t_a', 't_a', 'customer', 'u1')
        ids = [r.license_id for r in all_a]
        assert l_a.license_id in ids
        assert self.store.tenant_count('t_b') == 1

    def test_T089_add_device_to_revoked_fails(self):
        lic = self.store.issue('t_a', 'u1', 'hash_abc', max_devices=5)
        self.store.revoke(lic.license_id, 't_a')
        assert self.store.add_device(lic.license_id, 't_a', 'dev_1') is False

    def test_T090_two_tenants_same_hash_isolated(self):
        l1 = self.store.issue('t_a', 'u1', 'same_hash')
        l2 = self.store.issue('t_b', 'u2', 'same_hash')
        assert l1.license_id != l2.license_id

    def test_T091_singleton_shared(self):
        assert get_license_store() is get_license_store()

    def test_T092_list_returns_license_records(self):
        self.store.issue('t_a', 'u1', 'h1')
        records = self.store.list_all('t_a', 't_a', 'customer', 'u1')
        assert all(hasattr(r, 'license_id') for r in records)


class TestTenantSignalStore:
    def setup_method(self):
        self.store = get_signal_store()
        self.store.reset()

    def test_T093_emit_signal(self):
        sig = self.store.emit('t_a', 'u1', 'EURUSD', 'buy')
        assert sig is not None and sig.tenant_id == 't_a'

    def test_T094_duplicate_within_60s(self):
        self.store.emit('t_a', 'u1', 'EURUSD', 'buy')
        assert self.store.emit('t_a', 'u1', 'EURUSD', 'buy') is None

    def test_T095_different_direction_not_duplicate(self):
        assert self.store.emit('t_a', 'u1', 'EURUSD', 'buy') is not None
        assert self.store.emit('t_a', 'u1', 'EURUSD', 'sell') is not None

    def test_T096_different_symbol_not_duplicate(self):
        assert self.store.emit('t_a', 'u1', 'EURUSD', 'buy') is not None
        assert self.store.emit('t_a', 'u1', 'GBPUSD', 'buy') is not None

    def test_T097_cross_tenant_denied(self):
        self.store.emit('t_a', 'u1', 'EURUSD', 'buy')
        with pytest.raises(CrossTenantAccessError):
            self.store.list_signals('t_a', 't_b', 'customer', 'u2')

    def test_T098_admin_sees_cross_tenant(self):
        self.store.emit('t_a', 'u1', 'EURUSD', 'buy')
        assert len(self.store.list_signals('t_a', 't_b', 'admin', 'adm')) == 1

    def test_T099_ttl_expires(self):
        sig = self.store.emit('t_a', 'u1', 'EURUSD', 'buy', ttl_seconds=0.01)
        time.sleep(0.05)
        assert sig.is_expired

    def test_T100_tenant_isolation(self):
        self.store.emit('t_a', 'u1', 'EURUSD', 'buy')
        self.store.emit('t_b', 'u2', 'GBPUSD', 'sell')
        sigs = self.store.list_signals('t_a', 't_a', 'customer', 'u1')
        assert all(s.tenant_id == 't_a' for s in sigs)

    def test_T101_diff_users_same_tenant_not_dedup(self):
        assert self.store.emit('t_a', 'u1', 'EURUSD', 'buy') is not None
        assert self.store.emit('t_a', 'u2', 'EURUSD', 'buy') is not None

    def test_T102_signal_has_uuid(self):
        sig = self.store.emit('t_a', 'u1', 'XAUUSD', 'buy')
        assert len(sig.signal_id) == 36

    def test_T103_stored_in_correct_bucket(self):
        self.store.emit('t_a', 'u1', 'EURUSD', 'buy')
        assert self.store.tenant_count('t_a') == 1
        assert self.store.tenant_count('t_b') == 0

    def test_T104_signal_fields_correct(self):
        sig = self.store.emit('t_a', 'u1', 'XAUUSD', 'sell')
        assert sig.user_id == 'u1' and sig.direction == 'sell'


class TestTenantBotAndLogStore:
    def setup_method(self):
        self.bots = get_bot_store()
        self.logs = get_log_store()
        self.bots.reset()
        self.logs.reset()

    def test_T105_register_bot(self):
        bot = self.bots.register('t_a', 'u1', 'EURUSD', max_bots=2)
        assert bot is not None and bot.status == 'running'

    def test_T106_bot_limit_enforced(self):
        self.bots.register('t_a', 'u1', 'EURUSD', max_bots=1)
        assert self.bots.register('t_a', 'u1', 'GBPUSD', max_bots=1) is None

    def test_T107_bot_limit_per_user(self):
        assert self.bots.register('t_a', 'u1', 'EURUSD', max_bots=1) is not None
        assert self.bots.register('t_a', 'u2', 'GBPUSD', max_bots=1) is not None

    def test_T108_cross_tenant_bot_denied(self):
        self.bots.register('t_a', 'u1', 'EURUSD', max_bots=5)
        with pytest.raises(CrossTenantAccessError):
            self.bots.list_bots('t_a', 't_b', 'customer', 'u2')

    def test_T109_stop_bot(self):
        bot = self.bots.register('t_a', 'u1', 'EURUSD', max_bots=5)
        assert self.bots.stop(bot.bot_id, 't_a') is True
        assert bot.status == 'stopped'

    def test_T110_stopped_bot_not_counted(self):
        bot = self.bots.register('t_a', 'u1', 'EURUSD', max_bots=1)
        self.bots.stop(bot.bot_id, 't_a')
        assert self.bots.register('t_a', 'u1', 'GBPUSD', max_bots=1) is not None

    def test_T111_tenant_a_bots_not_in_b(self):
        self.bots.register('t_a', 'u1', 'EURUSD', max_bots=5)
        self.bots.register('t_b', 'u2', 'GBPUSD', max_bots=5)
        bots = self.bots.list_bots('t_a', 't_a', 'customer', 'u1')
        assert all(b.tenant_id == 't_a' for b in bots)

    def test_T112_log_append(self):
        entry = self.logs.append('t_a', 'INFO', 'trade executed', symbol='EURUSD')
        assert entry.tenant_id == 't_a' and entry.level == 'INFO'

    def test_T113_log_context(self):
        entry = self.logs.append('t_a', 'ERROR', 'limit hit', pct=5.2)
        assert entry.context['pct'] == 5.2

    def test_T114_cross_tenant_log_denied(self):
        self.logs.append('t_a', 'INFO', 'secret')
        with pytest.raises(CrossTenantAccessError):
            self.logs.get_logs('t_a', 't_b', 'customer', 'u2')

    def test_T115_admin_cross_tenant_log(self):
        self.logs.append('t_a', 'INFO', 'admin see')
        assert len(self.logs.get_logs('t_a', 't_b', 'admin', 'adm')) == 1

    def test_T116_log_max_per_tenant(self):
        for i in range(self.logs.MAX_PER_TENANT + 5):
            self.logs.append('t_a', 'DEBUG', f'msg_{i}')
        assert self.logs.tenant_count('t_a') == self.logs.MAX_PER_TENANT

    def test_T117_logs_sorted_newest_first(self):
        for i in range(3):
            self.logs.append('t_a', 'INFO', f'msg_{i}')
            time.sleep(0.01)
        entries = self.logs.get_logs('t_a', 't_a', 'customer', 'u1')
        ts = [e.created_at for e in entries]
        assert ts == sorted(ts, reverse=True)

    def test_T118_log_limit_param(self):
        for i in range(20):
            self.logs.append('t_a', 'INFO', f'msg_{i}')
        assert len(self.logs.get_logs('t_a', 't_a', 'customer', 'u1', limit=5)) == 5

    def test_T119_tenant_b_logs_not_in_a(self):
        self.logs.append('t_a', 'INFO', 'alpha')
        self.logs.append('t_b', 'INFO', 'beta')
        entries = self.logs.get_logs('t_a', 't_a', 'customer', 'u1')
        assert all(e.tenant_id == 't_a' for e in entries)

    def test_T120_log_has_uuid(self):
        entry = self.logs.append('t_a', 'INFO', 'test')
        assert len(entry.log_id) == 36


class TestTenantAuditStore:
    def setup_method(self):
        self.store = get_audit_store()
        self.store.reset()

    def test_T121_record_audit(self):
        entry = self.store.record('t_a', 'u1', 'customer', 'login', 'auth')
        assert entry.tenant_id == 't_a' and entry.action == 'login'

    def test_T122_get_for_tenant(self):
        self.store.record('t_a', 'u1', 'customer', 'login', 'auth')
        assert len(self.store.get_for_tenant('t_a', 't_a', 'customer', 'u1')) == 1

    def test_T123_cross_tenant_denied(self):
        self.store.record('t_a', 'u1', 'customer', 'login', 'auth')
        with pytest.raises(CrossTenantAccessError):
            self.store.get_for_tenant('t_a', 't_b', 'customer', 'u2')

    def test_T124_admin_global_view(self):
        self.store.record('t_a', 'u1', 'customer', 'login', 'auth')
        self.store.record('t_b', 'u2', 'customer', 'trade', 'order')
        assert len(self.store.admin_global_view('admin')) >= 2

    def test_T125_global_view_requires_admin(self):
        with pytest.raises(CrossTenantAccessError):
            self.store.admin_global_view('customer')

    def test_T126_global_view_no_support(self):
        with pytest.raises(CrossTenantAccessError):
            self.store.admin_global_view('support')

    def test_T127_sorted_newest_first(self):
        for i in range(3):
            self.store.record('t_a', 'u1', 'customer', f'act_{i}', 'res')
            time.sleep(0.01)
        entries = self.store.get_for_tenant('t_a', 't_a', 'customer', 'u1')
        ts = [e.created_at for e in entries]
        assert ts == sorted(ts, reverse=True)

    def test_T128_meta_stored(self):
        self.store.record('t_a', 'u1', 'customer', 'trade', 'order', symbol='EURUSD')
        entries = self.store.get_for_tenant('t_a', 't_a', 'customer', 'u1')
        assert entries[0].meta['symbol'] == 'EURUSD'

    def test_T129_tenant_isolation(self):
        self.store.record('t_a', 'u1', 'customer', 'login', 'auth')
        self.store.record('t_b', 'u2', 'customer', 'trade', 'order')
        entries = self.store.get_for_tenant('t_a', 't_a', 'customer', 'u1')
        assert all(e.tenant_id == 't_a' for e in entries)

    def test_T130_super_admin_global_view(self):
        self.store.record('t_a', 'u1', 'customer', 'login', 'auth')
        assert len(self.store.admin_global_view('super_admin')) >= 1

    def test_T131_audit_uuid(self):
        entry = self.store.record('t_a', 'u1', 'customer', 'act', 'res')
        assert len(entry.audit_id) == 36

    def test_T132_concurrent_records(self):
        errors = []
        def _record(i):
            try: self.store.record(f't_{i%3}', f'u{i}', 'customer', 'act', 'res')
            except Exception as e: errors.append(e)
        threads = [threading.Thread(target=_record, args=(i,)) for i in range(30)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []


class TestTenantMiddlewareAndMigration:
    def test_T133_extract_from_sub_prefix(self):
        assert _extract_tenant_id_from_jwt_sub('t_acme:uuid') == 't_acme'

    def test_T134_extract_no_prefix(self):
        assert _extract_tenant_id_from_jwt_sub('plain-uuid') is None

    def test_T135_extract_none(self):
        assert _extract_tenant_id_from_jwt_sub(None) is None

    def test_T136_extract_empty(self):
        assert _extract_tenant_id_from_jwt_sub('') is None

    def test_T137_public_health(self):
        assert _is_public('/health/live') is True

    def test_T138_public_docs(self):
        assert _is_public('/docs') is True

    def test_T139_public_metrics(self):
        assert _is_public('/metrics') is True

    def test_T140_not_public_api(self):
        assert _is_public('/api/v1/signals') is False

    def test_T141_not_public_admin(self):
        assert _is_public('/admin/users') is False

    def test_T142_middleware_init(self):
        reg = get_registry()
        mw = TenantMiddleware(app=None, registry=reg)
        assert mw.registry is reg

    def test_T143_sql_file_exists(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'supabase', 'migrations',
            '20260626_028_phase19_rls_tenant.sql',
        )
        assert os.path.exists(path)

    def test_T144_sql_set_app_tenant(self):
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'supabase',
            'migrations', '20260626_028_phase19_rls_tenant.sql')
        assert 'set_app_tenant' in open(path).read()

    def test_T145_sql_current_tenant_id(self):
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'supabase',
            'migrations', '20260626_028_phase19_rls_tenant.sql')
        assert 'current_tenant_id' in open(path).read()

    def test_T146_sql_rls_licenses(self):
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'supabase',
            'migrations', '20260626_028_phase19_rls_tenant.sql')
        assert 'licenses ENABLE ROW LEVEL SECURITY' in open(path).read()

    def test_T147_sql_rls_billing(self):
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'supabase',
            'migrations', '20260626_028_phase19_rls_tenant.sql')
        assert 'billing_subscriptions ENABLE ROW LEVEL SECURITY' in open(path).read()

    def test_T148_sql_admin_global_view(self):
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'supabase',
            'migrations', '20260626_028_phase19_rls_tenant.sql')
        assert 'vw_admin_all_licenses' in open(path).read()

    def test_T149_sql_tenant_data_view(self):
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'supabase',
            'migrations', '20260626_028_phase19_rls_tenant.sql')
        assert 'vw_my_tenant_data' in open(path).read()

    def test_T150_sql_is_app_admin(self):
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'supabase',
            'migrations', '20260626_028_phase19_rls_tenant.sql')
        assert 'is_app_admin' in open(path).read()

    def test_T151_sql_transaction(self):
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'supabase',
            'migrations', '20260626_028_phase19_rls_tenant.sql')
        sql = open(path).read()
        assert 'BEGIN' in sql and 'COMMIT' in sql

    def test_T152_sql_covers_all_tables(self):
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'supabase',
            'migrations', '20260626_028_phase19_rls_tenant.sql')
        sql = open(path).read()
        for table in ['licenses', 'billing_subscriptions', 'billing_invoices',
                      'execution_orders', 'audit_log', 'refresh_tokens']:
            assert table in sql
