# the-mind edge worker

The existing site build remains the source of the public files. This Cloudflare
Worker serves that build through the `ASSETS` binding, handles the no-JavaScript
analytics preference forms, and counts eligible successful HTML document
responses after the asset responds. One first-party module separately reports
ten-visible-second and trusted-input activity estimates. It follows a
response-specific privacy marker and creates no visitor ID or tracking cookie.
These estimates do not certify people. It does not proxy GitHub Pages.

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

The configuration preserves the existing production account and disables
workers.dev and preview URLs. It persists two intended Custom Domain targets:
`the-mind.xyz` and `www.the-mind.xyz`. The Worker serves the apex and redirects
the www hostname to the apex, preserving the existing canonical behavior.
DNS records, certificate issuance, and secrets remain deployment configuration.

After DNS and secret preflight, the deployment owner can activate the persisted
configuration with:

```sh
python3 scripts/build_site.py --out dist
wrangler deploy --config edge/wrangler.toml --keep-vars
```

## Deploy automatically after merges

Cloudflare Workers Builds connects the existing `the-mind-edge` Worker to
GitHub repository `p0s/the-mind`. Merges into `main` trigger validation and
production deployment. The GitHub Pages workflow publishes only the fallback
copy; it does not update `the-mind.xyz`.

In the Worker's **Settings > Builds**, use:

| Setting | Value |
| --- | --- |
| Production branch | `main` |
| Root directory | Repository root |
| Build variable | `NODE_VERSION=24` |
| Build command | `npm ci && python3 scripts/check.py && git diff --exit-code` |
| Deploy command | `npx --yes wrangler@4.138.0 deploy --config edge/wrangler.toml --keep-vars --strict` |
| Builds for non-production branches | Disabled |

The shared `scripts/check.py` command runs the same build, generated-link checks,
public-repository hygiene, content and provenance lint, and unit tests as GitHub
CI. The build verifies that the sitemap exactly matches rendered indexable
pages, uses the canonical host, and excludes drafts, noindex pages, and
redirects. A failed check stops the build before deployment. `--keep-vars`
preserves the existing server-side variables; the checked-in configuration
retains the Worker name, account, and custom domains. Use the existing
Cloudflare GitHub integration; no Cloudflare credential needs to be copied into
this repository.

The existing Cloudflare GitHub App includes `p0s/the-mind` in its selected
repositories. The connection and settings above are saved in Cloudflare;
repository files alone do not establish or restore this connection. Check the
Worker's build history for the merged commit and verify the changed public
pages after a deployment. The local Wrangler command above remains available
for an authorized manual deployment using the saved account profile.

## Agent-readable responses

The build writes an `index.md` beside every `index.html` page. It is rendered
from the same parsed source as the HTML, with absolute links, citation
locators, source details and the footer disclaimer. The build also writes an
`llms.txt` index of those Markdown pages. `robots.txt` declares the Content
Signals `search=yes, ai-input=yes`; it sets no `ai-train` signal, so it neither
grants nor restricts training.

HTML stays the default. A `GET` or `HEAD` page request whose `Accept` header
names `text/markdown` at least as highly as `text/html` receives the page's
`index.md` as `text/markdown; charset=utf-8`, with `Vary: Accept`,
`Content-Location` and a canonical `Link` header. HTML page responses advertise
the Markdown alternate in a `Link` header and `Vary: Accept`; the homepage also
links `llms.txt` with `rel="describedby"`. Markdown responses are not counted as
page views. The site publishes no MCP, A2A, OAuth, API catalog or payment
metadata, so those well-known paths keep returning 404.

## Measurement contract

Page observations, passive visible-page activity and foreground interaction
stay separate. The single versioned module sends only fixed signals and a
public path to `/analytics/signal`. Every relay checks same origin, privacy,
bots, prefetch and public-path eligibility again. Refusals produce no stage.
One bootstrap is a delivery-stage count, never a visitor count. The unchanged
producer v2 client uses random per-event delivery IDs and at most one bounded
retry; the collector refuses uncertain or unknown retries rather than writing
twice. Loss remains possible. Requests run in background tasks.

Use `?measurement_qa=1` for labelled technical verification. The original
document QA/path is captured before history changes; technical page, visible,
foreground and bootstrap counts remain separate from ordinary audience data.
No aggregate business action or Google tag is added. Privacy controls,
retention, existing site identities and the release/notification path stay intact.
Run `node --test edge/worker.test.mjs edge/measurement.test.mjs` for the local
adapter and browser controls; the shared site gate includes them too.
