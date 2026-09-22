# the-mind edge wrapper

`the-mind.xyz` remains hosted by GitHub Pages. This Cloudflare Worker is a
thin edge wrapper for the existing Pages origin: it handles the no-JavaScript
analytics preference forms, proxies the public response, and counts eligible
successful HTML document responses after the origin responds. It does not
move the origin or ship a browser tracker.

The deployment owner must set these server-only variables before attaching a
route for `the-mind.xyz/*`:

- `ORIGIN_BASE_URL`: the verified GitHub Pages origin URL, including any
  repository path (for example `https://p0s.github.io/the-mind/`); never set it
  to `the-mind.xyz`.
- `ANALYTICS_INGEST_URL`: the gateway's `/ingest/v1` URL.
- `ANALYTICS_INGEST_TOKEN`: the per-site secret for `the-mind.xyz`.

The route, Cloudflare account, zone, and secrets are intentionally absent from
this repository. Verify the existing GitHub Pages response and origin before
setting `ORIGIN_BASE_URL`; no DNS or hosting migration is implied.
