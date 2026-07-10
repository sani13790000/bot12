"""
backend/mt5_connector/error_handler.py
MT5 Connector Error Handling & Retry Logic
Production-ready error recovery mechanisms
"""

import logging
import asyncio
from typing import Optional, Callable, Any
from functools import wraps
import time

logger = logging.getLogger(__name__)


class MT5ConnectionError(Exception):
    """Base exception for MT5 connection errors"""
    pass


class MT5TemporaryError(MT5ConnectionError):
    """Temporary error that can be retried"""
    pass


class MT5PermanentError(MT5ConnectionError):
    """Permanent error that should not be retried"""
    pass


class MT5ErrorHandler:
    """Handles MT5 connection errors with exponential backoff retry"""
    
    def __init__(
        self,
        max_retries: int = 5,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0
    ):
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.retry_count = 0
        self.last_error = None
    
    async def retry_with_backoff(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with exponential backoff retry
        
        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
        
        Returns:
            Function result
        
        Raises:
            MT5PermanentError: If error is permanent
            MT5TemporaryError: If all retries exhausted
        """
        self.retry_count = 0
        backoff = self.initial_backoff
        
        while self.retry_count < self.max_retries:
            try:
                result = await func(*args, **kwargs)
                self.retry_count = 0  # Reset on success
                return result
            
            except MT5PermanentError as e:
                logger.error("[mt5] Permanent error, not retrying: %s", e)
                raise
            
            except MT5TemporaryError as e:
                self.retry_count += 1
                self.last_error = e
                
                if self.retry_count >= self.max_retries:
                    logger.error("[mt5] Max retries exceeded: %s", e)
                    raise
                
                logger.warning(
                    "[mt5] Temporary error (retry %d/%d), backoff %.1fs: %s",
                    self.retry_count,
                    self.max_retries,
                    backoff,
                    e
                )
                
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.max_backoff)  # Exponential backoff
            
            except Exception as e:
                # Unknown error - treat as temporary
                self.retry_count += 1
                self.last_error = e
                
                logger.error("[mt5] Unknown error (retry %d/%d): %s", self.retry_count, self.max_retries, e)
                
                if self.retry_count >= self.max_retries:
                    raise MT5PermanentError(f"Failed after {self.max_retries} retries: {e}")
                
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.max_backoff)
        
        raise MT5TemporaryError(f"Max retries exceeded: {self.last_error}")
    
    def classify_error(self, error: Exception) -> str:
        """Classify error as temporary or permanent"""
        error_str = str(error).lower()
        
        # Permanent errors
        permanent_keywords = [
            'invalid account',
            'authentication failed',
            'permission denied',
            'invalid credentials',
        ]
        
        for keyword in permanent_keywords:
            if keyword in error_str:
                return 'permanent'
        
        # Temporary errors
        temporary_keywords = [
            'connection',
            'timeout',
            'temporarily',
            'unavailable',
            'busy',
            'socket',
            'network',
        ]
        
        for keyword in temporary_keywords:
            if keyword in error_str:
                return 'temporary'
        
        return 'unknown'


def mt5_retry(max_retries: int = 3):
    """Decorator for MT5 operations with automatic retry"""
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            handler = MT5ErrorHandler(max_retries=max_retries)
            return await handler.retry_with_backoff(func, *args, **kwargs)
        
        return wrapper
    
    return decorator


class MT5CircuitBreaker:
    """Circuit breaker pattern for MT5 connection"""
    
    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.is_open = False
    
    def record_success(self):
        """Record successful operation"""
        self.failure_count = 0
        self.is_open = False
        logger.debug("[mt5-cb] Circuit breaker reset")
    
    def record_failure(self):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.is_open = True
            logger.error("[mt5-cb] Circuit breaker OPEN after %d failures", self.failure_count)
    
    def can_execute(self) -> bool:
        """Check if operation can be executed"""
        if not self.is_open:
            return True
        
        # Check if timeout has passed
        if self.last_failure_time and (time.time() - self.last_failure_time) > self.timeout:
            logger.info("[mt5-cb] Circuit breaker attempting recovery")
            self.is_open = False
            self.failure_count = 0
            return True
        
        return False
