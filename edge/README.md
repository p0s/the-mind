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
workers.dev and preview URLs. It persists two intended Custom Domain targets:
`the-mind.xyz` and `www.the-mind.xyz`. The Worker serves the apex and redirects
the www hostname to the apex, preserving the existing canonical behavior.
DNS records, certificate issuance, and secrets remain deployment configuration.

After DNS and secret preflight, the deployment owner can activate the persisted
configuration with:

```sh
python3 scripts/build_site.py --out dist
/opt/homebrew/bin/wrangler deploy --profile Tightness_mannish146 --config edge/wrangler.toml --keep-vars
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
CI. A failed check stops the build before deployment. `--keep-vars` preserves
the existing server-side variables; the checked-in configuration retains the
Worker name, account, and custom domains. Use the existing Cloudflare GitHub
integration; no Cloudflare credential needs to be copied into this repository.

The existing Cloudflare GitHub App includes `p0s/the-mind` in its selected
repositories. The connection and settings above are saved in Cloudflare;
repository files alone do not establish or restore this connection. Check the
Worker's build history for the merged commit and verify the changed public
pages after a deployment. The local Wrangler command above remains available
for an authorized manual deployment using the saved account profile.
