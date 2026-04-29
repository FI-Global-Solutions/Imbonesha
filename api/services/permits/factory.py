"""Factory for the configured permit verification adapter.

Reads PERMIT_ADAPTER from Django settings (set via the PERMIT_ADAPTER env
var in docker-compose). Valid values: "mock" (default), "kubaka".

Usage:

    from services.permits import get_permit_adapter
    adapter = get_permit_adapter()
    parcel = adapter.verify_upi("1/01/03/05/0042")
"""

from .base import PermitVerificationService


def get_permit_adapter() -> PermitVerificationService:
    """Return the configured permit adapter instance.

    Raises:
        ValueError: If PERMIT_ADAPTER is set to an unknown value.
    """
    from django.conf import settings

    adapter_name = getattr(settings, "PERMIT_ADAPTER", "mock").lower()

    if adapter_name == "mock":
        from .mock_adapter import MockPermitAdapter
        return MockPermitAdapter()

    if adapter_name == "kubaka":
        from .kubaka_adapter import KubakaPermitAdapter
        return KubakaPermitAdapter()

    raise ValueError(
        f"Unknown PERMIT_ADAPTER value: {adapter_name!r}. "
        "Valid options are 'mock' and 'kubaka'."
    )
