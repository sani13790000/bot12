"""backend/core/exceptions.py — shared exceptions."""

class KillSwitchActivatedError(Exception):
    """Raised when kill switch is active and trading attempt is made."""
    pass

class LicenseError(Exception):
    pass

class PermissionDeniedError(Exception):
    pass
