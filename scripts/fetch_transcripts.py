#!/usr/bin/env python3
"""
Fetch local-only transcripts for sources in sources/sources.csv.

Design goals:
- Deterministic, restartable: writes progress to transcripts/_index.csv after each source.
- Prefers English captions when available; falls back to German; else one arbitrary language.
- Never downloads full video (captions only). If no captions exist, marks needs_asr.

Note: transcripts/ is gitignored by design.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.request import Request, urlopen
from http.client import IncompleteRead


ROOT = Path(__file__).resolve().parents[1]
SOURCES_CSV = ROOT / "sources" / "sources.csv"
TRANSCRIPTS_DIR = ROOT / "transcripts"
INDEX_CSV = TRANSCRIPTS_DIR / "_index.csv"

YT_DLP = os.environ.get("YT_DLP", "/home/node/.local/bin/yt-dlp")
NODE = os.environ.get("NODE", "/usr/local/bin/node")
YT_DLP_REMOTE_COMPONENTS = os.environ.get("YT_DLP_REMOTE_COMPONENTS", "ejs:github")
YTDLP_SLEEP_REQUESTS = os.environ.get("YTDLP_SLEEP_REQUESTS", "1")
YTDLP_COOKIES_FROM_BROWSER = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "")
YTDLP_COOKIES = os.environ.get("YTDLP_COOKIES", "")


INDEX_FIELDS = [
    "source_id",
    "kind",
    "url",
    "published_date",
    "preferred_lang",
    "selected_lang",
    "selected_kind",  # subs|auto|web|ccc|none
    "transcript_path",
    # Optional local-only adjustment: add this offset (in seconds) to transcript cue times
    # to get canonical source timecodes for anchors/notes.
    "time_offset_seconds",
    # Optional local-only media retained for QA (primarily for ASR sources).
    "media_kind",  # audio|video|none
    "media_path",
    "media_status",  # ok|missing|error
    "media_error",
    "qa_status",  # pending|ok
    "status",  # ok|needs_asr|unavailable|error
    "error",
    "updated_at",
]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def read_sources(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
    # Basic schema sanity: fail early if the file changed unexpectedly.
    required = {"source_id", "kind", "url", "published_date"}
    missing = required - set(rows[0].keys()) if rows else required
    if missing:
        raise RuntimeError(f"sources.csv missing columns: {sorted(missing)}")
    return rows


def load_index(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        out: Dict[str, Dict[str, str]] = {}
        for row in reader:
            sid = row.get("source_id", "").strip()
            if sid:
                out[sid] = row
        return out


def write_index(path: Path, index: Dict[str, Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        for sid in sorted(index.keys()):
            row = index[sid]
            # Ensure stable columns.
            out_row = {k: row.get(k, "") for k in INDEX_FIELDS}
            writer.writerow(out_row)
    tmp.replace(path)


def run(cmd: List[str], timeout_s: int = 180) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        # Keep the corpus run moving; treat timeouts as retriable errors.
        stdout = exc.stdout if isinstance(exc.stdout, str) or exc.stdout is None else exc.stdout.decode("utf-8", errors="replace")
        stderr = exc.stderr if isinstance(exc.stderr, str) or exc.stderr is None else exc.stderr.decode("utf-8", errors="replace")
        msg = f"timeout after {timeout_s}s"
        if stderr:
            msg = msg + "\n" + str(stderr)
        return subprocess.CompletedProcess(cmd, returncode=124, stdout=stdout or "", stderr=msg)


def run_ytdlp_with_backoff(cmd: List[str], timeout_s: int = 300, max_attempts: int = 2) -> subprocess.CompletedProcess[str]:
    """
    yt-dlp against YouTube will occasionally hit transient failures (notably HTTP 429).
    We retry with exponential backoff to make a full corpus pull possible in one session.
    """
    last: Optional[subprocess.CompletedProcess[str]] = None
    for attempt in range(1, max_attempts + 1):
        cp = run(cmd, timeout_s=timeout_s)
        last = cp
        if cp.returncode == 0:
            return cp

        combined = (cp.stderr or "") + "\n" + (cp.stdout or "")
        if "HTTP Error 429" in combined or "Too Many Requests" in combined:
            # Keep this short: we want the full run to make progress, then rerun later.
            sleep_s = min(5 * attempt, 30)
            eprint(f"yt-dlp hit HTTP 429; backing off for {sleep_s}s (attempt {attempt}/{max_attempts})")
            time.sleep(sleep_s)
            continue

        return cp

    return last or run(cmd, timeout_s=timeout_s)


def classify_ytdlp_failure(err_text: str) -> str:
    """
    Best-effort classification for yt-dlp failures.

    Returns: "unavailable" or "error".
    """
    t = err_text.lower()
    unavailable_markers = [
        "video unavailable",
        "this video is private",
        "private video",
        "members-only",
        "has been removed",
        "does not exist",
        "account terminated",
        "sign in to confirm your age",
        "age-restricted",
        "premieres in",
    ]
    if any(m in t for m in unavailable_markers):
        return "unavailable"
    return "error"


def _filter_lang_keys(keys: Iterable[str]) -> List[str]:
    out = []
    for k in keys:
        kl = k.lower()
        if kl in {"live_chat"}:
            continue
        out.append(k)
    return out


def _best_lang_for_prefix(keys: List[str], prefix: str) -> Optional[str]:
    """Pick the "best" language code for a prefix (en/de)."""
    prefix_l = prefix.lower()
    keys_l = {k.lower(): k for k in keys}  # preserve original casing

    # Exact match first.
    if prefix_l in keys_l:
        return keys_l[prefix_l]

    # Common variants, shortest first (e.g., en-US over en-US-x-...).
    variants = [k for k in keys if k.lower().startswith(prefix_l + "-")]
    if variants:
        return sorted(variants, key=lambda s: (len(s), s.lower()))[0]

    # Any remaining startswith, e.g. "en_or" unlikely but keep it.
    any_pref = [k for k in keys if k.lower().startswith(prefix_l)]
    if any_pref:
        return sorted(any_pref, key=lambda s: (len(s), s.lower()))[0]
    return None


def _extract_lang_from_caption_filename(source_id: str, path: Path) -> str:
    # Expected: <source_id>.<lang>.<ext>
    name = path.name
    prefix = source_id + "."
    if not name.startswith(prefix):
        return ""
    rest = name[len(prefix) :]
    if "." not in rest:
        return ""
    return rest.rsplit(".", 1)[0]


def yt_download_try(url: str, source_id: str, lang_expr: str) -> Tuple[Optional[Path], Optional[str]]:
    """
    Attempt to download captions for the requested language expression.
    Returns (best_path, error).
    """
    outtmpl = str(TRANSCRIPTS_DIR / source_id)
    before = set(TRANSCRIPTS_DIR.glob(f"{source_id}.*"))

    cmd = [
        YT_DLP,
        "--skip-download",
        "--no-playlist",
        "--js-runtimes",
        f"node:{NODE}",
        "--remote-components",
        YT_DLP_REMOTE_COMPONENTS,
        "--sleep-requests",
        YTDLP_SLEEP_REQUESTS,
        "--write-subs",
        "--write-auto-subs",
        "--sub-format",
        "vtt/srt/best",
        "--sub-langs",
        lang_expr,
        "-o",
        outtmpl,
        url,
    ]
    if YTDLP_COOKIES_FROM_BROWSER:
        cmd.extend(["--cookies-from-browser", YTDLP_COOKIES_FROM_BROWSER])
    elif YTDLP_COOKIES:
        cmd.extend(["--cookies", YTDLP_COOKIES])
    cp = run_ytdlp_with_backoff(cmd, timeout_s=300, max_attempts=2)
    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "").strip()
        err = re.sub(r"\s+", " ", err)[:500]
        return None, err or f"yt-dlp exited with {cp.returncode}"

    after = set(TRANSCRIPTS_DIR.glob(f"{source_id}.*"))
    new_files = [p for p in (after - before) if p.suffix.lower() in {".vtt", ".srt"}]
    if not new_files:
        return None, None

    def file_health(p: Path) -> Tuple[int, int]:
        """
        Heuristics for selecting a usable caption file.
        Some caption variants occasionally contain pathological single-line dumps.
        """
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return (1, 0)
        cue_count = sum(1 for line in text.splitlines() if "-->" in line)
        max_line = max((len(line) for line in text.splitlines()), default=0)
        bad = 1 if max_line > 2000 else 0
        return (bad, cue_count)

    def rank(p: Path) -> Tuple[int, int, str]:
        ext_rank = 0 if p.suffix.lower() == ".vtt" else 1
        lang = _extract_lang_from_caption_filename(source_id, p).lower()
        live_rank = 1 if lang == "live_chat" else 0
        bad, cue_count = file_health(p)
        # Prefer orig tracks and plain language tags over regional variants.
        lang_pref = 0 if "orig" in lang else (1 if lang in {"en", "de"} else 2)
        # Sorting key: prefer non-live_chat, VTT, non-bad, richer cueing, and finally language.
        return (live_rank, ext_rank, bad, lang_pref, -cue_count, p.name.lower())

    best = sorted(new_files, key=rank)[0]

    # Keep only the selected caption from this attempt to avoid bloat.
    for p in new_files:
        if p != best:
            try:
                p.unlink()
            except Exception:
                # Non-critical: leave stray caption rather than failing the run.
                pass

    return best, None


def http_get(url: str, timeout_s: int = 60, max_attempts: int = 3) -> Tuple[Optional[bytes], Optional[str]]:
    req = Request(url, headers={"User-Agent": "the-mind-transcript-fetcher/1.0"})
    last_err: Optional[str] = None
    for attempt in range(1, max_attempts + 1):
        try:
            with urlopen(req, timeout=timeout_s) as resp:
                return resp.read(), None
        except IncompleteRead as exc:
            # Retry rather than accepting truncated HTML/subtitles.
            last_err = f"IncompleteRead({len(exc.partial)} bytes read, {exc.expected} more expected)"
        except Exception as exc:  # noqa: BLE001 - pragmatic tool script
            last_err = str(exc)
        if attempt < max_attempts:
            time.sleep(min(2 * attempt, 10))
    return None, last_err or "unknown error"


def ccc_find_subtitle_tracks(html: str) -> List[Tuple[str, str]]:
    """
    Parse media.ccc.de talk HTML and return [(srclang, src_url), ...].
    """
    tracks: List[Tuple[str, str]] = []
    for m in re.finditer(r"<track\b[^>]*>", html, flags=re.IGNORECASE):
        tag = m.group(0)
        if 'kind="subtitles"' not in tag and "kind='subtitles'" not in tag:
            continue
        src_m = re.search(r'\bsrc="([^"]+)"', tag)
        lang_m = re.search(r'\bsrclang="([^"]*)"', tag)
        if not src_m or not lang_m:
            continue
        src = src_m.group(1)
        lang = lang_m.group(1) or ""
        tracks.append((lang, src))
    return tracks


def ccc_pick_track(tracks: List[Tuple[str, str]]) -> Tuple[Optional[str], Optional[str]]:
    # tracks: [(lang, url)]
    langs = [t[0] for t in tracks]
    langs = _filter_lang_keys(langs)

    def find_lang(prefix: str) -> Optional[str]:
        return _best_lang_for_prefix(langs, prefix)

    for group in ("en", "de"):
        l = find_lang(group)
        if l:
            for lang, src in tracks:
                if lang == l:
                    return group, src

    if tracks:
        # Prefer a non-empty srclang.
        tracks_sorted = sorted(tracks, key=lambda t: (t[0] == "", t[0].lower(), t[1]))
        return "other", tracks_sorted[0][1]
    return None, None


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def fetch_for_row(row: Dict[str, str]) -> Dict[str, str]:
    sid = row["source_id"].strip()
    kind = row["kind"].strip()
    url = row["url"].strip()
    published_date = row.get("published_date", "").strip()

    base: Dict[str, str] = {
        "source_id": sid,
        "kind": kind,
        "url": url,
        "published_date": published_date,
        "preferred_lang": "",
        "selected_lang": "",
        "selected_kind": "",
        "transcript_path": "",
        "status": "",
        "error": "",
        "updated_at": now_iso(),
    }

    if kind == "youtube":
        # Fast path: try English, then German, else "all" (and keep one).
        tries = [
            ("en", "en.*,en,eng"),
            ("de", "de.*,de,deu,ger"),
            ("other", "all,-live_chat"),
        ]
        last_err: Optional[str] = None
        for group, lang_expr in tries:
            fp, err = yt_download_try(url, sid, lang_expr)
            if err:
                last_err = err
                # A hard failure usually means the video is unavailable or we got blocked.
                status = classify_ytdlp_failure(err)
                base.update(status=status, error=err)
                return base
            if fp is not None:
                base["preferred_lang"] = group
                base["selected_lang"] = _extract_lang_from_caption_filename(sid, fp)
                base["selected_kind"] = "youtube"
                base["transcript_path"] = str(fp.relative_to(ROOT))
                base["status"] = "ok"
                return base

        # No captions at all.
        base.update(status="needs_asr", preferred_lang="en", selected_kind="none")
        if last_err:
            base["error"] = last_err
        return base

    if kind == "ccc":
        body, err = http_get(url, timeout_s=60)
        if body is None:
            base.update(status="error", error=err or "failed to fetch CCC page")
            return base
        html = body.decode("utf-8", errors="replace")
        tracks = ccc_find_subtitle_tracks(html)
        pref_group, track_url = ccc_pick_track(tracks)
        if track_url is None:
            base.update(status="needs_asr", preferred_lang="en", selected_kind="none")
            return base

        base["preferred_lang"] = pref_group or ""
        base["selected_kind"] = "ccc"
        # Infer extension from URL.
        ext = ".vtt" if track_url.lower().endswith(".vtt") else ".srt"
        out = TRANSCRIPTS_DIR / f"{sid}{ext}"
        data, derr = http_get(track_url, timeout_s=60)
        if data is None:
            # Treat missing subtitle files as "needs_asr" rather than a hard error.
            base.update(
                status="needs_asr",
                preferred_lang=(pref_group or "en"),
                selected_kind="none",
                error=derr or "failed to download CCC subtitles",
            )
            return base
        write_bytes(out, data)
        base["selected_lang"] = pref_group or ""
        base["transcript_path"] = str(out.relative_to(ROOT))
        base["status"] = "ok"
        return base

    if kind == "web":
        body, err = http_get(url, timeout_s=60)
        if body is None:
            base.update(status="error", error=err or "failed to fetch web page")
            return base
        out = TRANSCRIPTS_DIR / f"{sid}.html"
        write_bytes(out, body)
        base["selected_kind"] = "web"
        base["transcript_path"] = str(out.relative_to(ROOT))
        base["status"] = "ok"
        return base

    base.update(status="error", error=f"unknown kind: {kind}")
    return base


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=str(SOURCES_CSV), help="Path to sources.csv")
    ap.add_argument("--kinds", default="", help="Comma-separated kinds to process (youtube,ccc,web)")
    ap.add_argument("--limit", type=int, default=0, help="Max sources to process (0 = all)")
    ap.add_argument("--sleep", type=float, default=0.0, help="Sleep seconds between sources")
    ap.add_argument("--jobs", type=int, default=1, help="Number of parallel workers (default: 1)")
    ap.add_argument("--only-new", action="store_true", help="Only process sources not yet in transcripts/_index.csv")
    ap.add_argument("--retry-errors", action="store_true", help="Only process sources with status=error in transcripts/_index.csv")
    args = ap.parse_args(argv)

    sources_path = Path(args.sources)
    rows = read_sources(sources_path)

    wanted_kinds = {k.strip() for k in args.kinds.split(",") if k.strip()}
    if wanted_kinds:
        rows = [r for r in rows if r.get("kind", "").strip() in wanted_kinds]

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    index = load_index(INDEX_CSV)

    # Build worklist with stable numbering for logs.
    work: List[Tuple[int, Dict[str, str]]] = []
    total = len(rows)
    for i, row in enumerate(rows, start=1):
        sid = row["source_id"].strip()
        prev = index.get(sid)
        if prev:
            if args.only_new:
                continue
            if args.retry_errors:
                if prev.get("status") != "error":
                    continue
            elif prev.get("status") == "ok" and prev.get("transcript_path"):
                continue
        work.append((i, row))
        if args.limit and len(work) >= args.limit:
            break

    processed = 0
    if args.jobs <= 1:
        for i, row in work:
            sid = row["source_id"].strip()
            eprint(f"[{i}/{total}] {sid} ({row.get('kind','')})")
            result = fetch_for_row(row)
            index[sid] = result
            write_index(INDEX_CSV, index)
            processed += 1
            if args.sleep:
                time.sleep(args.sleep)
    else:
        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            futs = {ex.submit(fetch_for_row, row): (i, row) for i, row in work}
            for fut in as_completed(futs):
                i, row = futs[fut]
                sid = row["source_id"].strip()
                try:
                    result = fut.result()
                except Exception as exc:  # noqa: BLE001 - tool script
                    result = {
                        "source_id": sid,
                        "kind": row.get("kind", ""),
                        "url": row.get("url", ""),
                        "published_date": row.get("published_date", ""),
                        "preferred_lang": "",
                        "selected_lang": "",
                        "selected_kind": "",
                        "transcript_path": "",
                        "status": "error",
                        "error": f"exception: {exc}",
                        "updated_at": now_iso(),
                    }
                eprint(f"[{i}/{total}] {sid} ({row.get('kind','')}) -> {result.get('status')}")
                index[sid] = result
                write_index(INDEX_CSV, index)
                processed += 1

    eprint(f"done: updated {INDEX_CSV} (processed {processed} new sources)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
