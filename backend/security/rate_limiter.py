"""
backend/security/rate_limiter.py
Rate Limiting & DDoS Protection
Token bucket algorithm implementation
"""

import logging
import time
from typing import Dict, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limiting configuration"""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    burst_size: int = 10


class TokenBucket:
    """Token bucket rate limiter"""
    
    def __init__(
        self,
        capacity: float,
        refill_rate: float,
        refill_interval: float = 1.0
    ):
        """
        Initialize token bucket
        
        Args:
            capacity: Maximum tokens in bucket
            refill_rate: Tokens added per interval
            refill_interval: Time between refills (seconds)
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.refill_interval = refill_interval
        self.tokens = capacity
        self.last_refill = time.time()
    
    def allow_request(self) -> bool:
        """
        Check if request is allowed
        
        Returns:
            True if within rate limit
        """
        self._refill()
        
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        
        return False
    
    def _refill(self):
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_refill
        
        if elapsed > self.refill_interval:
            tokens_to_add = (elapsed / self.refill_interval) * self.refill_rate
            self.tokens = min(self.capacity, self.tokens + tokens_to_add)
            self.last_refill = now


class RateLimiter:
    """Global rate limiter for API endpoints"""
    
    def __init__(self, config: RateLimitConfig = RateLimitConfig()):
        self.config = config
        self.buckets: Dict[str, Dict[str, TokenBucket]] = defaultdict(dict)
        
        # Create buckets for different time windows
        self.buckets_per_minute = defaultdict(
            lambda: TokenBucket(
                capacity=config.requests_per_minute,
                refill_rate=config.requests_per_minute / 60,
                refill_interval=1
            )
        )
        
        self.buckets_per_hour = defaultdict(
            lambda: TokenBucket(
                capacity=config.requests_per_hour,
                refill_rate=config.requests_per_hour / 3600,
                refill_interval=60
            )
        )
    
    def is_allowed(
        self,
        client_id: str,
        endpoint: str = "global"
    ) -> Tuple[bool, Dict[str, int]]:
        """
        Check if request is allowed for client
        
        Args:
            client_id: Client identifier (IP, user ID, API key)
            endpoint: API endpoint name
        
        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        key = f"{client_id}:{endpoint}"
        
        # Check minute limit
        minute_bucket = self.buckets_per_minute[key]
        if not minute_bucket.allow_request():
            logger.warning(
                "[rate-limit] Minute limit exceeded for client: %s on %s",
                client_id,
                endpoint
            )
            return False, {
                "limit_per_minute": self.config.requests_per_minute,
                "remaining": 0
            }
        
        # Check hour limit
        hour_bucket = self.buckets_per_hour[key]
        if not hour_bucket.allow_request():
            logger.warning(
                "[rate-limit] Hour limit exceeded for client: %s on %s",
                client_id,
                endpoint
            )
            return False, {
                "limit_per_hour": self.config.requests_per_hour,
                "remaining": 0
            }
        
        return True, {
            "limit_per_minute": self.config.requests_per_minute,
            "remaining_minute": int(minute_bucket.tokens),
            "limit_per_hour": self.config.requests_per_hour,
            "remaining_hour": int(hour_bucket.tokens)
        }
    
    def get_client_stats(self, client_id: str) -> Dict[str, any]:
        """Get rate limit statistics for client"""
        stats = {}
        for endpoint, bucket in self.buckets_per_minute.items():
            if endpoint.startswith(client_id):
                stats[endpoint] = {
                    "minute_tokens": int(bucket.tokens),
                    "minute_limit": self.config.requests_per_minute
                }
        return stats


class IPBasedRateLimiter:
    """Rate limiter based on client IP address"""
    
    def __init__(self, config: RateLimitConfig = RateLimitConfig()):
        self.limiter = RateLimiter(config)
    
    def is_allowed(self, client_ip: str, endpoint: str = "global") -> Tuple[bool, Dict]:
        """Check if request from IP is allowed"""
        return self.limiter.is_allowed(client_ip, endpoint)
    
    def block_ip(self, client_ip: str, duration: int = 3600):
        """Block IP for specified duration (seconds)"""
        logger.warning("[rate-limit] IP blocked: %s for %d seconds", client_ip, duration)
        # TODO: Implement IP blacklist with TTL


class APIKeyRateLimiter:
    """Rate limiter based on API key"""
    
    def __init__(self, config: RateLimitConfig = RateLimitConfig()):
        # Different limits for different key tiers
        self.free_tier_config = RateLimitConfig(
            requests_per_minute=10,
            requests_per_hour=100,
            requests_per_day=1000
        )
        self.premium_tier_config = config
        
        self.free_limiter = RateLimiter(self.free_tier_config)
        self.premium_limiter = RateLimiter(self.premium_tier_config)
    
    def is_allowed(
        self,
        api_key: str,
        tier: str = "free",
        endpoint: str = "global"
    ) -> Tuple[bool, Dict]:
        """Check if API key request is allowed"""
        
        if tier == "premium":
            limiter = self.premium_limiter
            config = self.premium_tier_config
        else:
            limiter = self.free_limiter
            config = self.free_tier_config
        
        is_allowed, stats = limiter.is_allowed(api_key, endpoint)
        
        if not is_allowed:
            logger.warning(
                "[rate-limit] API key quota exceeded: %s (tier: %s)",
                api_key[:10] + "...",
                tier
            )
        
        return is_allowed, stats


# Global rate limiters
_ip_limiter: Optional[IPBasedRateLimiter] = None
_api_key_limiter: Optional[APIKeyRateLimiter] = None


def get_ip_rate_limiter() -> IPBasedRateLimiter:
    """Get or create IP-based rate limiter"""
    global _ip_limiter
    if _ip_limiter is None:
        _ip_limiter = IPBasedRateLimiter()
    return _ip_limiter


def get_api_key_rate_limiter() -> APIKeyRateLimiter:
    """Get or create API key-based rate limiter"""
    global _api_key_limiter
    if _api_key_limiter is None:
        _api_key_limiter = APIKeyRateLimiter()
    return _api_key_limiter
