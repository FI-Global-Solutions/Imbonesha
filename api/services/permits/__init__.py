"""Permit verification service — adapter pattern.

Import the factory function to get the configured adapter:

    from services.permits import get_permit_adapter
    adapter = get_permit_adapter()
    result = adapter.verify_upi("1/01/03/05/0042")
"""

from .factory import get_permit_adapter
from .base import PermitVerificationService, ParcelData, PermitData, LookupResult

__all__ = [
    "get_permit_adapter",
    "PermitVerificationService",
    "ParcelData",
    "PermitData",
    "LookupResult",
]
