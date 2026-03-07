# `sources/sources.csv` notes tokens

The `notes` column in `sources/sources.csv` is a space-separated list of `key=value` tokens.

## Current keys

- `curation_status=keep|candidate|reject`
- `tier=keystone|supporting|legacy|aux`
- `format=talk|interview|essay` (presentation type; not media type)
- `discovered_via=<freeform>` (where the link came from)
- `license=<freeform>` (e.g., `cc-by-4.0`)
- `doi=<freeform>` (when available)

## Optional future keys (recommended)

These make the inventory sortable into a “next extraction queue” without changing the CSV schema.

- `topic=self|consciousness|agency|value|alignment|...`
- `bach_presence=solo|mostly|mixed|unknown`
- `transcript=ok|needs_asr|missing`
- `priority=1|2|3` (1 = highest)
- `last_updated=YYYY-MM-DD` (for “living” sources that declare an update date, e.g., PDFs/position papers)
