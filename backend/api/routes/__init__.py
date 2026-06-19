"""Route modules — do NOT import anything here.

Calling code (main.py) does:
    from backend.api.routes import auth, signals, ...

Keeping this file empty avoids circular imports that occur when
route modules import from backend.core which in turn might import
from backend.api.
"""
# intentionally empty — routes are imported explicitly in main.py
