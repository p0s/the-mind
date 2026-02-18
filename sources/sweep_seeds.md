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

## Seeds (search-heavy)

| kind | target | importer | notes |
| --- | --- | --- | --- |
| youtube_search | `query="Joscha Bach"` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` | broad; expect duplicates |
| youtube_search | `query="Joscha Bach consciousness"` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` | hard problem / phenomenology |
| youtube_search | `query="Joscha Bach attention"` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` | attention/workspace themes |
| youtube_search | `query="Joscha Bach self model"` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` | selfhood/narrative |
| youtube_search | `query="Joscha Bach agency"` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` | agency/control |
| youtube_search | `query="Joscha Bach free will"` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` | free will post |
| youtube_search | `query="Joscha Bach Kegan"` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` | stages / development |
| youtube_search | `query="Joscha Bach lucidity"` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` | lucidity framing |
| youtube_search | `query="Joscha Bach valence"` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` | value/valence |
| youtube_search | `query="Joscha Bach computational meta psychology"` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` | older framing; still referenced |
| youtube_search | `query="Joscha Bach interview"` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` | catch interviews labeled generically |
| youtube_search | `query="Joscha Bach podcast"` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` | podcast appearances |
| youtube_search | `query="Joscha Bach deutsch"` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` | German-language material |
| youtube_search | `query="Joscha Bach Vortrag"` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` | German-language: talks/lectures |
| youtube_search | `query="Joscha Bach Interview deutsch"` | `yt-dlp` + `python3 scripts/import_youtube_sources.py` | German-language: interviews |
| web_sitemap | `https://bach.ai/sitemap.xml` | `python3 scripts/import_bach_ai_sitemap.py` | stable index; complements search |
