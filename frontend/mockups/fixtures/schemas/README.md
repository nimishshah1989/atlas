# ATLAS fixture schemas

JSON Schema (Draft-07) contracts for the Stage-1 mockup fixtures in
`frontend/mockups/fixtures/`. These schemas are the **binding contract**
between the hand-curated mockup JSON files (which Stage-1 pages read
directly) and the Stage-2 backend endpoints (which must return the same
shape). A fixture and an API response for the same concept must both
validate against the same schema — that is how we guarantee the mockup
can swap to the live API with zero frontend changes.

## How mockups consume fixtures

Every Stage-1 page loads its fixture with a plain `fetch()` at page
init, then renders against the parsed object. Example:

```js
const events = await fetch("/mockups/fixtures/events.json").then(r => r.json());
// events now matches events.schema.json -> array of marker objects
```

Fixtures live alongside the mockups at `frontend/mockups/fixtures/*.json`.
Shared fixtures (like `events.json`) are read by multiple pages — that is
why the schema is a single source of truth, not duplicated per page.

## How Stage-2 endpoints must conform

Every Stage-2 route listed in `frontend-v1-spec.md §15 (API binding
matrix)` MUST return a response body that validates against the same
schema its fixture validates against. This is checked in CI against the
OpenAPI contract. If a route needs to add a field it must be added to
the schema FIRST (backward-compatible: new optional properties only),
mockups updated, THEN the route ships.

The route → schema mapping (see spec §15 for the full block-by-block
grid):

| Schema | Fixture | Stage-2 route |
|---|---|---|
| `events.schema.json` | `events.json` | `/api/v1/global/events` (new) |
| `breadth_daily_5y.schema.json` | `breadth_daily_5y.json` | `/api/v1/stocks/breadth?universe=X&range=5y` |
| `zone_events.schema.json` | `zone_events.json` | `/api/v1/stocks/breadth/zone-events` (new) |
| `search_index.schema.json` | `search_index.json` | `/api/v1/search?q=X` (new backlog) |
| `nav_series.schema.json` | `ppfas_flexi_nav_5y.json` etc. | `/api/v1/mf/{id}/nav-history?range=5y` |
| `price_series.schema.json` | `reliance_close_5y.json` etc. | `/api/v1/stocks/{symbol}/prices?range=5y` |
| `mf_rank_universe.schema.json` | `mf_rank.json` | `/api/v1/mf/rank` (new backlog) |
| `sector_rrg.schema.json` | `sector_rrg.json` | `/api/v1/sectors/rrg` |

## Running validation

Install `ajv-cli` once:

```bash
npm install -g ajv-cli ajv-formats
```

Then validate any fixture against its schema:

```bash
ajv validate -s schemas/events.schema.json -d events.json --spec=draft7 -c ajv-formats
ajv validate -s schemas/breadth_daily_5y.schema.json -d breadth_daily_5y.json --spec=draft7 -c ajv-formats
```

To validate every fixture in one shot (run from `frontend/mockups/fixtures/`):

```bash
for s in schemas/*.schema.json; do
  name=$(basename "$s" .schema.json)
  [ -f "$name.json" ] && ajv validate -s "$s" -d "$name.json" --spec=draft7 -c ajv-formats || true
done
```

CI runs the equivalent at the repo root. A fixture that fails validation
blocks merge.

## Conventions (applied across every schema)

- Dates are ISO `YYYY-MM-DD`, IST implicit (no offset suffix).
- Money and price numbers are Decimal-representable to 4 decimal places
  (`multipleOf: 0.0001`). Never float. Internal paise / rupees-at-boundary
  per project `CLAUDE.md`.
- Percent values are stored as decimal fractions (`0.1234` = 12.34%)
  UNLESS the field name ends in `_pct` or is a 0–100 score.
- Enum fields are closed sets — additions require a spec PR.
- `additionalProperties: false` everywhere — unknown fields fail.
- Sector / universe scoping uses the `sector:{slug}` prefix pattern.

## Related docs

- `docs/design/frontend-v1-spec.md` — §10 Breadth Terminal, §10.5 Signal
  Playback, §13 Global search, §15 API binding matrix.
- `docs/design/design-principles.md` — §12 Regime banner, §13 Signal
  strip, §16 Signal history table (field conventions).
- `docs/architecture/jip-data-atlas.md` — JIP `de_*` source tables these
  fixtures ultimately mirror.
