# Sweep seeds

This file defines the public, reviewable discovery scope for **manual** source sweeps.

Rules:
- Public only (no credentials, cookies, private URLs, or acquisition details).
- Prefer stable targets (channels/playlists/sitemaps) over ad-hoc search results.
- After importing/discovery, the canonical place for sources is `sources/sources.csv`.

Template:
| kind | target | importer | notes |
| --- | --- | --- | --- |
| web_sitemap | `<url>` | `python3 scripts/import_bach_ai_sitemap.py` |  |
| youtube_search | `query="..."` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` |  |
| youtube_channel | `<channel url>` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` |  |
| youtube_playlist | `<playlist url>` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` |  |
| ccc | `<event/search target>` | `python3 scripts/import_ccc_sources.py` |  |
| web_urls | `<url>` | `python3 scripts/import_web_urls.py` |  |

