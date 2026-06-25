"""
موتور Smaqrt Money Concept

اٌن مظتور تحلیم جامع SMC 
(فاز مغجاقى) by Galaxy Vast AI Trading Platform
"""
from __future__ import annotations

import logging
import math
import numpy as np
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..core.enums import (
    MarketStructure, BlockType, BlockStatus, FVGType,
    LiquidityType, TradingSession, TrendDirection
)
from ..core.logger import get_logger
from ..core.config import settings

logger = get_logger("smc_engine")
