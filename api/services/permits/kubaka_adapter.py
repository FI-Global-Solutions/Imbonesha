"""KubakaPermitAdapter — production stub for the real KUBAKA API.

This class will be implemented when RHA / MININFRA grants API access.
Until then it raises NotImplementedError so any accidental use in dev
fails loudly rather than silently falling back to mock data.

When implemented, this adapter will:
  - Authenticate via OAuth 2.0 client credentials (token endpoint TBD).
  - Map KUBAKA's actual JSON shapes to our ParcelData / PermitData types.
  - Use the same retry + cache strategy as MockPermitAdapter.
  - Log every call with UPI, timestamp, and response checksum for the
    audit trail required by docs/integration-contract.md.
"""

from typing import Optional

from .base import LookupResult, ParcelData, PermitVerificationService


class KubakaPermitAdapter(PermitVerificationService):
    """Real KUBAKA API adapter. Not yet implemented — awaiting API access."""

    def verify_upi(self, upi: str) -> Optional[ParcelData]:
        raise NotImplementedError(
            "KubakaPermitAdapter is not yet implemented. "
            "Set PERMIT_ADAPTER=mock to use the local mock service."
        )

    def lookup_by_coords(
        self,
        lat: float,
        lng: float,
        max_distance_m: float = 100.0,
    ) -> LookupResult:
        raise NotImplementedError(
            "KubakaPermitAdapter is not yet implemented. "
            "Set PERMIT_ADAPTER=mock to use the local mock service."
        )
