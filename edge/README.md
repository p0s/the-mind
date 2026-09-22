# the-mind edge worker

The existing site build remains the source of the public files. This Cloudflare
Worker serves that build through the `ASSETS` binding, handles the no-JavaScript
analytics preference forms, and counts eligible successful HTML document
responses after the asset responds. It does not proxy GitHub Pages and does not
ship a browser tracker.

Build the public tree from the repository root with:

```sh
python3 scripts/build_site.py --out dist
```

The output directory is `dist`; the Wrangler config resolves its assets
directory as `../dist` from `edge/wrangler.toml`. The existing GitHub Pages
workflow may continue to publish the same build as a source/fallback path, but
the Worker has no `ORIGIN_BASE_URL` dependency and must not be configured to
proxy the `p0s.github.io` redirecting origin.

The deployment owner must set these server-only variables before attaching the
Worker to `the-mind.xyz/*`:

- `ANALYTICS_INGEST_URL`: the gateway's `/ingest/v1` URL.
- `ANALYTICS_INGEST_TOKEN`: the per-site secret for `the-mind.xyz`.

The configuration pins the approved tightness Cloudflare account and disables
workers.dev and preview URLs. The route, zone, custom-domain binding, DNS records
and secrets remain deployment configuration. Attach the canonical hostname
without changing the registrar or adding a second public host.
