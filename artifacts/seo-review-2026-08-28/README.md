# the-mind SEO review package

Status: **PREPARED_FOR_REVIEW** on 2026-08-28. Nothing in this package was pushed, deployed, published, or used to change DNS or hosting.

## Provenance and scope

- Canonical repository: `p0s/the-mind`
- Implementation checkout: isolated task-owned worktree at the verified base below
- Local task branch: `codex/public-seo-review-2026-08-28`
- Verified base: `origin/main` at `c0bbcfd0d51ab5516eb3a4ef79602f5fd91a350c`
- Frozen prerequisite: orchestrator artifact `public-site-seo-2026-08-28/frozen-review-prerequisite.md`
- Frozen prerequisite SHA-256: `3b0b174cb8cc6209135cc21eb52b887a1a3aa5dbd9858c9833ee86f81e1363df`
- Governing product contract: repository `spec.md`; no repository-local `AGENTS.md` exists.

The implementation changes generated presentation and discovery only. It does not change the source ledger, source notes, claims ledger, manuscript meaning, or citation anchors.

## Prepared implementation

- Explicit, unique title and description metadata for all 17 public routes.
- Validated absolute canonical base behavior and matching canonical, Open Graph, and Twitter metadata.
- Explicit index/follow treatment, canonical-only XML sitemap, and robots sitemap discovery.
- Conservative `WebSite`, `WebPage`/`Article`/`CollectionPage`, `BreadcrumbList`, and Questions `ItemList` JSON-LD.
- Structured-data citations derived only from source anchors already rendered on each page.
- Visible, crawlable breadcrumbs, including Home → Questions → article and Home → Archive → Reader.
- A complete ordered Questions hub with a clear route into the main guide and deeper evidence pages.
- One generated H1 per route; V1 chapter headings are demoted only in generated Reader HTML, preserving source files and anchor IDs.

## Reachability conclusion

The apex was publicly reachable during review. Authoritative and public DNS returned GitHub Pages addresses, direct GitHub edge checks returned `200` for the apex and `301` from `www` to the apex, and the live certificate covered both names. The only reproduced failure used this host's intercepted resolver/proxy path: it returned synthetic `198.18.0.x` addresses, where `www` failed TLS/timed out while the apex loaded.

Classification: **external client resolver/proxy symptom; no code-owned or authoritative-DNS defect demonstrated**. No infrastructure mutation was warranted. See [reachability.md](reachability.md) for exact evidence and the smallest follow-up.

## Validation

- Focused: 31 SEO, generated HTML, breadcrumb, schema, sitemap, robots, and link tests passed.
- Final repository gate: `npm ci`; public hygiene; `scripts/build_all.py`; generated link check; knowledge-base lint; provenance lint; `python -m unittest discover -s tests` — **65/65 tests passed**.
- Post-gate focused check after the generated Reader/schema refinement: all 7 SEO tests passed; the unchanged broad gate was not rerun.
- Rendered matrix: all 17 routes had one H1, correct canonical/robots/schema, zero broken images, no horizontal overflow, and at least 18 internal links.
- `npm ci` used the unchanged lockfile and reported three existing dev-dependency advisories (two moderate, one high); no dependency or audit mutation was made in this SEO task.

## Review artifacts

- [Route and SEO evidence matrix](route-seo-matrix.md)
- [Reachability diagnosis](reachability.md)
- [Home desktop](screenshots/home-desktop.png) — 1440×1000
- [Guide desktop](screenshots/guide-desktop.png) — 1440×1000
- [Questions hub desktop](screenshots/questions-hub-desktop.png) — 1440×1000
- [Reader desktop](screenshots/reader-desktop.png) — 1440×1000
- [Could AI be conscious? mobile](screenshots/could-ai-mobile.png) — 390×844
- [Glossary mobile](screenshots/glossary-mobile.png) — 390×844
- [Mobile menu open](screenshots/could-ai-mobile-menu.png) — 390×844; coordinate click verified `aria-expanded=true`
- [Screenshot checksums](screenshots/SHA256SUMS)

Smallest review action: inspect the three primary screenshots (Home, Questions, Could AI mobile), then review the local commit diff. Deployment remains a separate decision.
