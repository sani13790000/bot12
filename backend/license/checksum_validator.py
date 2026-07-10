"""
backend/license/checksum_validator.py
License Checksum Verification & Validation
Production-ready license security
"""

import logging
import hashlib
import hmac
from typing import Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ChecksumValidator:
    """Validates license checksums and integrity"""
    
    # Secret key for HMAC (should be in env variable in production)
    SECRET_KEY = "galaxyvast_license_secret_key_2024"
    
    @staticmethod
    def calculate_checksum(license_data: str) -> str:
        """
        Calculate HMAC SHA256 checksum for license data
        
        Args:
            license_data: License string to validate
        
        Returns:
            Hexadecimal checksum
        """
        return hmac.new(
            ChecksumValidator.SECRET_KEY.encode(),
            license_data.encode(),
            hashlib.sha256
        ).hexdigest()
    
    @staticmethod
    def verify_checksum(license_data: str, provided_checksum: str) -> Tuple[bool, str]:
        """
        Verify license checksum
        
        Args:
            license_data: License string
            provided_checksum: Checksum to verify against
        
        Returns:
            Tuple of (is_valid, message)
        """
        expected_checksum = ChecksumValidator.calculate_checksum(license_data)
        
        # Use constant-time comparison to prevent timing attacks
        is_valid = hmac.compare_digest(expected_checksum, provided_checksum)
        
        if not is_valid:
            logger.warning(
                "[license] Checksum mismatch - Expected: %s, Got: %s",
                expected_checksum[:8] + "...",
                provided_checksum[:8] + "..."
            )
            return False, "License checksum verification failed"
        
        logger.debug("[license] Checksum verified successfully")
        return True, "Checksum valid"


class LicenseValidator:
    """Complete license validation system"""
    
    # License status constants
    STATUS_VALID = "valid"
    STATUS_EXPIRED = "expired"
    STATUS_REVOKED = "revoked"
    STATUS_INVALID = "invalid"
    
    def __init__(self):
        self.revoked_licenses = set()  # Should be loaded from database in production
    
    def validate_license(self, license_key: str) -> Tuple[bool, str, dict]:
        """
        Complete license validation
        
        Args:
            license_key: License key to validate
        
        Returns:
            Tuple of (is_valid, message, license_info)
        """
        logger.info("[license] Validating license: %s", license_key[:10] + "...")
        
        # Parse license
        is_parsed, license_info, parse_msg = self._parse_license(license_key)
        if not is_parsed:
            return False, parse_msg, {}
        
        # Verify checksum
        is_checksum_valid, checksum_msg = ChecksumValidator.verify_checksum(
            license_info.get('data', ''),
            license_info.get('checksum', '')
        )
        if not is_checksum_valid:
            logger.error("[license] Checksum verification failed: %s", checksum_msg)
            return False, checksum_msg, license_info
        
        # Check if revoked
        if self._is_revoked(license_key):
            msg = "License has been revoked"
            logger.error("[license] %s - Key: %s", msg, license_key[:10] + "...")
            return False, msg, license_info
        
        # Check expiry
        is_valid, expiry_msg = self._check_expiry(license_info)
        if not is_valid:
            logger.error("[license] %s", expiry_msg)
            return False, expiry_msg, license_info
        
        # All checks passed
        logger.info("[license] License validated successfully")
        return True, "License is valid", license_info
    
    def _parse_license(self, license_key: str) -> Tuple[bool, dict, str]:
        """
        Parse license key format
        Expected format: GALAXYVAST-XXXXXXXX-YYYYYYYY-ZZZZZZZZ
        """
        try:
            parts = license_key.split('-')
            
            if len(parts) != 4:
                return False, {}, "Invalid license format"
            
            if parts[0] != 'GALAXYVAST':
                return False, {}, "Invalid license prefix"
            
            license_info = {
                'prefix': parts[0],
                'data': f"{parts[0]}-{parts[1]}-{parts[2]}",
                'checksum': parts[3],
                'created_at': datetime.utcnow().isoformat(),
            }
            
            return True, license_info, "License parsed"
        
        except Exception as e:
            logger.exception("[license] Error parsing license: %s", e)
            return False, {}, f"License parse error: {e}"
    
    def _is_revoked(self, license_key: str) -> bool:
        """
        Check if license is revoked
        In production, this should check a database or revocation list
        """
        if license_key in self.revoked_licenses:
            return True
        
        # TODO: Load revocation list from database
        # revocation_list = db.query(RevokedLicense).all()
        # return license_key in [l.key for l in revocation_list]
        
        return False
    
    def _check_expiry(self, license_info: dict) -> Tuple[bool, str]:
        """
        Check license expiry date
        """
        # TODO: Add expiry date to license_info
        # For now, just check if format includes expiry
        
        # Example: if license has expiry_date field
        if 'expiry_date' in license_info:
            expiry = datetime.fromisoformat(license_info['expiry_date'])
            if datetime.utcnow() > expiry:
                days_expired = (datetime.utcnow() - expiry).days
                return False, f"License expired {days_expired} days ago"
        
        return True, "License not expired"
    
    def revoke_license(self, license_key: str) -> bool:
        """
        Revoke a license
        
        Args:
            license_key: License to revoke
        
        Returns:
            True if revoked successfully
        """
        self.revoked_licenses.add(license_key)
        logger.warning("[license] License revoked: %s", license_key[:10] + "...")
        # TODO: Save to database
        return True
    
    def get_license_status(self, license_key: str) -> str:
        """
        Get license status
        
        Returns:
            One of: valid, expired, revoked, invalid
        """
        is_valid, msg, info = self.validate_license(license_key)
        
        if not is_valid:
            if "revoked" in msg.lower():
                return self.STATUS_REVOKED
            elif "expired" in msg.lower():
                return self.STATUS_EXPIRED
            else:
                return self.STATUS_INVALID
        
        return self.STATUS_VALID


# Global validator instance
_license_validator: Optional[LicenseValidator] = None


def get_license_validator() -> LicenseValidator:
    """Get or create global license validator"""
    global _license_validator
    if _license_validator is None:
        _license_validator = LicenseValidator()
    return _license_validator
