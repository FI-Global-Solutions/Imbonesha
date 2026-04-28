# Integration contract — KUBAKA / RHA permit verification

This document describes the API surface that Imbonesha needs from the
Rwanda Housing Authority's permit registry (currently delivered through the
KUBAKA platform). It exists for two reasons:

1. **During MVP development**, our mock permit service implements this
   contract exactly. This means every component of Imbonesha is built
   against a stable interface from day one — no integration shock when
   real access is granted.

2. **When data-sharing access is negotiated** with RHA / MININFRA / RISA,
   this document is what we put on the table. Rather than asking "give us
   API access," we ask "please implement these four endpoints with these
   response shapes." The conversation becomes concrete and technical.

---

## Authentication

Imbonesha will authenticate to KUBAKA using OAuth 2.0 client credentials
flow, with our service as a registered consumer. We expect:

- A client ID and client secret issued to the Imbonesha service account.
- A token endpoint we POST to for short-lived access tokens (1 hour).
- All API calls authenticated via `Authorization: Bearer <token>`.

We do **not** expect KUBAKA to give us read access to any personally
identifiable information beyond the registered owner's name on the
parcel — that's the minimum needed for inspector follow-up.

---

## Endpoints required

### `GET /api/v1/parcels/{upi}`

Lookup a parcel by its Unique Parcel Identifier.

**Path parameter**: `upi` — the 5-part UPI separated by `/`, e.g.
`1/01/03/05/0142`.

**Response 200**:
```json
{
  "upi": "1/01/03/05/0142",
  "owner_name": "Mukamana Jeanne",
  "district": "Gasabo",
  "sector": "Kacyiru",
  "cell": "Kamatamu",
  "land_use": "residential",
  "zone_type": "high_density_residential",
  "max_floors_allowed_by_zone": 3,
  "centroid_lat": -1.9441,
  "centroid_lng": 30.0890,
  "boundary_geojson": {
    "type": "Polygon",
    "coordinates": [[[30.0890, -1.9441], ...]]
  },
  "permits": [
    {
      "permit_no": "BP-2024-001234",
      "category": "1",
      "status": "active",
      "issued_date": "2024-03-15",
      "expiry_date": "2026-03-15",
      "intended_use": "residential",
      "max_floors_allowed": 2,
      "max_footprint_sqm": 150.0,
      "applicant_name": "Mukamana Jeanne"
    }
  ],
  "has_active_permit": true
}
```

**Response 404**: parcel not in registry.

---

### `GET /api/v1/parcels-lookup?lat={lat}&lng={lng}&max_distance_m={m}`

Find the parcel containing or nearest to a coordinate. This is the most
critical endpoint for Imbonesha — when the AI detects a new building at a
geographic location, this is how we determine which parcel it falls on.

**Query parameters**:
- `lat`, `lng` — coordinates in WGS84
- `max_distance_m` — if no parcel contains the point, return the nearest
  one within this distance (default 100m, max 10km)

**Response 200**:
```json
{
  "found": true,
  "parcel": { ...same shape as GET /api/v1/parcels/{upi}... },
  "distance_m": 0.0
}
```

If no parcel within range:
```json
{ "found": false }
```

---

### `GET /api/v1/parcels/{upi}/permits`

List all permits ever issued for a parcel, including expired and revoked
ones — historical record matters for enforcement.

**Response 200**: Array of permit objects, ordered by `issued_date` desc.

---

### `GET /api/v1/permits/{permit_no}`

Lookup a single permit by its number. Used when an inspector or admin
clicks into a specific permit from the dashboard.

---

## Permit categories (Rwanda Building Code)

We use the official categories from Ministerial Order N° 02/CAB.M/019 of
15/04/2019:

| Category | Description |
|----------|-------------|
| 1 | Single-family residential, ground floor only |
| 2 | Residential, up to G+1 |
| 3 | Towers and antennas, or buildings G+2 and above, capacity > 100 |
| 4 | Industrial and hazardous, sports/cultural/health/education, capacity > 500 |
| 5 | Large commercial complexes |
| 6 | Critical infrastructure (utilities, telecoms) |
| 7 | Mixed-use developments |

When the AI classifier determines a building's likely category and it
doesn't match the issued permit, that's a "wrong category" flag.

---

## Permit status values

| Status   | Meaning |
|----------|---------|
| pending  | Application submitted, under review |
| approved | Approved but construction not yet started |
| active   | Construction in progress, valid permit |
| expired  | Permit lapsed (typically 2 years from issue) |
| revoked  | Permit cancelled by RHA before expiry |

For Imbonesha's flag logic, only `active` permits count as "construction
authorized." Anything else flags.

---

## Service-level expectations

We expect the production KUBAKA API to provide:

- **Availability**: 99.5% monthly. We build retry + cache layers
  assuming occasional 5xx errors.
- **Latency**: p95 < 1000ms for parcel lookups. Our mock injects 300-500ms
  to keep us honest about caching strategy.
- **Rate limits**: At minimum 60 req/min per service account. Imbonesha
  generates batched lookups during AI inference cycles, peaking at
  several hundred req/min during full-AOI scans.
- **Webhooks (optional)**: If KUBAKA can push notifications when a permit
  is issued, modified, or revoked, we will subscribe — this lets us
  invalidate our cache and re-evaluate flags in near-real-time.

---

## What we do NOT need from KUBAKA

To minimize friction in negotiation, we explicitly do not need:

- Write access (we never modify KUBAKA records)
- Document attachments (architectural drawings, etc.)
- Application stage details (only final permit state matters to us)
- Personal data beyond the registered owner name
- Financial or fee information

---

## Caching and data freshness

Imbonesha caches parcel responses for 1 hour and permit responses for
6 hours. If KUBAKA can provide ETag or `Last-Modified` headers, we will
use conditional requests. If KUBAKA can push webhook notifications on
permit changes, we will invalidate cache entries on receipt.

---

## Versioning and changes

All endpoints are versioned at `/api/v1/`. Breaking changes go to `/v2/`.
We commit to supporting `/v1/` for at least 12 months after `/v2/`
launches, and to running both in parallel during transition.

---

## Audit and chain of custody

For enforcement evidence, we log every API call with: timestamp, UPI
queried, response checksum, and the model version that made the
detection that triggered the lookup. This audit trail is what makes
Imbonesha's flag reports admissible.
