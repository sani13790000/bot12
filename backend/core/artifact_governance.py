"""
artifact_governance.py -- Phase 25: Release Artifact Governance
Artifact lifecycle: draft -> signed -> published -> deprecated -> revoked
Checksum, compatibility, access control, audit chain.
"""
from __future__ import annotations

import hmac
import hashlib
import json
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
