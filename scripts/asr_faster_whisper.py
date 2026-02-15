#!/usr/bin/env python3
"""
ASR fallback for sources with no downloadable captions/subtitles.

This script is intentionally local-only:
- Writes transcripts under transcripts/ (gitignored).
- Updates transcripts/_index.csv (also gitignored).
- Downloads audio (via yt-dlp). By default, keeps the audio file until QA confirms
  transcript quality and (if applicable) speaker attribution; then it can be deleted.

Requires:
- A Python env with faster-whisper installed (e.g. `.venv313`).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
SOURCES_CSV = ROOT / "sources" / "sources.csv"
TRANSCRIPTS_DIR = ROOT / "transcripts"
INDEX_CSV = TRANSCRIPTS_DIR / "_index.csv"

YT_DLP = os.environ.get("YT_DLP", "/home/node/.local/bin/yt-dlp")
NODE = os.environ.get("NODE", "/usr/local/bin/node")
YT_DLP_REMOTE_COMPONENTS = os.environ.get("YT_DLP_REMOTE_COMPONENTS", "ejs:github")
YTDLP_COOKIES = os.environ.get("YTDLP_COOKIES", "")

INDEX_FIELDS_REQUIRED = [
    "source_id",
    "kind",
    "url",
    "published_date",
    "preferred_lang",
    "selected_lang",
    "selected_kind",
    "transcript_path",
    "media_kind",
    "media_path",
    "media_status",
    "media_error",
    "qa_status",
    "status",
    "error",
    "updated_at",
]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def run(cmd: List[str], timeout_s: int = 3600) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) or exc.stdout is None else exc.stdout.decode("utf-8", errors="replace")
        stderr = exc.stderr if isinstance(exc.stderr, str) or exc.stderr is None else exc.stderr.decode("utf-8", errors="replace")
        msg = f"timeout after {timeout_s}s"
        if stderr:
            msg = msg + "\n" + str(stderr)
        return subprocess.CompletedProcess(cmd, returncode=124, stdout=stdout or "", stderr=msg)


def run_ytdlp_with_backoff(cmd: List[str], timeout_s: int, max_attempts: int) -> subprocess.CompletedProcess[str]:
    last: Optional[subprocess.CompletedProcess[str]] = None
    for attempt in range(1, max_attempts + 1):
        cp = run(cmd, timeout_s=timeout_s)
        last = cp
        if cp.returncode == 0:
            return cp

        combined = (cp.stderr or "") + "\n" + (cp.stdout or "")
        if "HTTP Error 429" in combined or "Too Many Requests" in combined:
            sleep_s = min(5 * attempt, 30)
            eprint(f"yt-dlp hit HTTP 429; backing off for {sleep_s}s (attempt {attempt}/{max_attempts})")
            time.sleep(sleep_s)
            continue

        return cp

    return last or run(cmd, timeout_s=timeout_s)


def read_sources(path: Path) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            sid = row.get("source_id", "").strip()
            if sid:
                out[sid] = dict(row)
    return out


def load_index(path: Path) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
    if not path.exists():
        return [], {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows: Dict[str, Dict[str, str]] = {}
        for row in reader:
            sid = row.get("source_id", "").strip()
            if sid:
                rows[sid] = dict(row)
        return fieldnames, rows


def ensure_index_fields(fieldnames: List[str]) -> List[str]:
    # Preserve unknown local-only columns, but ensure the required schema exists.
    out = list(fieldnames) if fieldnames else []
    for k in INDEX_FIELDS_REQUIRED:
        if k not in out:
            out.append(k)
    return out


def write_index(path: Path, fieldnames: List[str], rows: Dict[str, Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for sid in sorted(rows.keys()):
            row = rows[sid]
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    tmp.replace(path)


def format_vtt_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"


def write_vtt(path: Path, segments) -> None:
    lines = ["WEBVTT", ""]
    for seg in segments:
        start = format_vtt_time(seg.start)
        end = format_vtt_time(seg.end)
        text = (seg.text or "").strip()
        if not text:
            continue
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def download_audio(
    url: str,
    source_id: str,
    out_dir: Path,
    timeout_s: int,
    max_attempts: int,
) -> Tuple[Optional[Path], Optional[str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    tmpl = str(out_dir / f"{source_id}.%(ext)s")
    cmd = [
        YT_DLP,
        "--no-playlist",
        "--js-runtimes",
        f"node:{NODE}",
        "--remote-components",
        YT_DLP_REMOTE_COMPONENTS,
        "-f",
        "ba",
        "-o",
        tmpl,
        url,
    ]
    if YTDLP_COOKIES:
        cmd.extend(["--cookies", YTDLP_COOKIES])
    cp = run_ytdlp_with_backoff(cmd, timeout_s=timeout_s, max_attempts=max_attempts)
    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "").strip()
        err = " ".join(err.split())[:500]
        return None, err or f"yt-dlp exited with {cp.returncode}"

    # Find the downloaded file (best effort).
    cands = sorted(out_dir.glob(f"{source_id}.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    cands = [p for p in cands if p.suffix.lower() not in {".part", ".ytdl", ".aria2"}]
    if not cands:
        return None, "audio download completed but no file found"
    return cands[0], None


def find_existing_media(media_dir: Path, source_id: str) -> Optional[Path]:
    if not media_dir.exists():
        return None
    cands = sorted(media_dir.glob(f"{source_id}.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    cands = [p for p in cands if p.suffix.lower() not in {".part", ".ytdl", ".aria2"}]
    return cands[0] if cands else None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-id", action="append", required=True, help="Repeatable source id (e.g. yt_XXXX)")
    ap.add_argument("--download-only", action="store_true", help="Only download+retain audio; do not run ASR")
    ap.add_argument("--model", default="small", help="Whisper model size (tiny/base/small/medium/large-v3...)")
    ap.add_argument("--language", default="en", help="Language code (default: en). Use 'auto' to detect.")
    ap.add_argument("--device", default="cpu", help="cpu or cuda (if available)")
    ap.add_argument("--compute-type", default="int8", help="ctranslate2 compute type (e.g. int8, float16)")
    ap.add_argument("--download-timeout", type=int, default=1800, help="yt-dlp audio download timeout (seconds)")
    ap.add_argument("--download-attempts", type=int, default=2, help="yt-dlp retry attempts for audio download")
    ap.add_argument("--media-dir", default=str(TRANSCRIPTS_DIR / "_media"), help="Where to keep audio for QA")
    ap.add_argument("--delete-audio", action="store_true", help="Delete audio after ASR (overrides default retention)")
    ap.add_argument("--force", action="store_true", help="Overwrite existing ASR transcript output if present")
    args = ap.parse_args(argv)

    sources = read_sources(SOURCES_CSV)
    fieldnames, index = load_index(INDEX_CSV)
    fieldnames = ensure_index_fields(fieldnames)
    if not INDEX_CSV.exists():
        # Allow ASR-only workflows to bootstrap the local index.
        write_index(INDEX_CSV, fieldnames, index)

    media_dir = Path(args.media_dir)
    media_dir.mkdir(parents=True, exist_ok=True)

    model = None
    if not args.download_only:
        # Import lazily so download-only mode doesn't require faster-whisper installed.
        from faster_whisper import WhisperModel  # type: ignore

        model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)

    tmp_dir = TRANSCRIPTS_DIR / "_tmp_audio"
    for sid in args.source_id:
        row = sources.get(sid)
        if not row:
            eprint(f"unknown source_id: {sid}")
            continue
        kind = row.get("kind")
        if kind not in {"youtube", "ccc"}:
            eprint(f"unsupported kind for ASR (currently youtube+ccc only): {sid} kind={kind}")
            continue

        url = row.get("url", "")
        if not url:
            eprint(f"missing url for {sid}")
            continue

        prev = index.get(sid, {})
        prev.update(
            {
                "source_id": sid,
                "kind": kind or "youtube",
                "url": url,
                "published_date": row.get("published_date", ""),
                "updated_at": now_iso(),
            }
        )

        # In download-only mode we want to keep the audio even if a transcript already exists.
        # In ASR mode we skip early if we already have a transcript and we're not forcing.
        out_vtt = TRANSCRIPTS_DIR / f"{sid}.{args.language}.asr.vtt"
        if not args.download_only and out_vtt.exists() and not args.force:
            eprint(f"skip (exists): {out_vtt}")
            index[sid] = prev
            write_index(INDEX_CSV, fieldnames, index)
            continue

        existing = find_existing_media(media_dir, sid)
        downloaded_tmp: Optional[Path] = None
        audio_path: Optional[Path] = None
        if existing is not None:
            audio_path = existing
            prev.update(
                {
                    "media_kind": "audio",
                    "media_path": str(existing.relative_to(ROOT)),
                    "media_status": "ok",
                    "media_error": "",
                    "qa_status": prev.get("qa_status") or "pending",
                }
            )
            index[sid] = prev
            write_index(INDEX_CSV, fieldnames, index)
        else:
            eprint(f"download audio: {sid}")
            downloaded_tmp, err = download_audio(
                url,
                sid,
                tmp_dir,
                timeout_s=args.download_timeout,
                max_attempts=args.download_attempts,
            )
            if downloaded_tmp is None:
                eprint(f"audio download failed: {sid}: {err}")
                prev.update(
                    {
                        "media_kind": "audio",
                        "media_path": prev.get("media_path", ""),
                        "media_status": "error",
                        "media_error": err or "audio download failed",
                        "qa_status": prev.get("qa_status") or "pending",
                    }
                )
                index[sid] = prev
                write_index(INDEX_CSV, fieldnames, index)
                continue
            audio_path = downloaded_tmp

        if args.download_only:
            if downloaded_tmp is None:
                eprint(f"skip (already have audio): {sid}")
                continue
            dest = media_dir / f"{sid}{downloaded_tmp.suffix}"
            try:
                downloaded_tmp.replace(dest)
                prev.update(
                    {
                        "media_kind": "audio",
                        "media_path": str(dest.relative_to(ROOT)),
                        "media_status": "ok",
                        "media_error": "",
                        "qa_status": prev.get("qa_status") or "pending",
                    }
                )
                index[sid] = prev
                write_index(INDEX_CSV, fieldnames, index)
                eprint(f"ok: {sid} -> {dest}")
            except Exception as exc:
                eprint(f"failed to store audio for QA: {sid}: {exc}")
                prev.update(
                    {
                        "media_kind": "audio",
                        "media_path": "",
                        "media_status": "error",
                        "media_error": f"failed to store audio: {exc}",
                        "qa_status": prev.get("qa_status") or "pending",
                    }
                )
                index[sid] = prev
                write_index(INDEX_CSV, fieldnames, index)
            continue

        try:
            lang_arg = None if args.language.lower() == "auto" else args.language
            assert audio_path is not None
            assert model is not None
            eprint(f"transcribe: {sid} ({audio_path.name})")
            segments, info = model.transcribe(
                str(audio_path),
                language=lang_arg,
                vad_filter=True,
            )
            write_vtt(out_vtt, segments)
        except Exception as exc:  # noqa: BLE001 - tool script
            eprint(f"transcription failed: {sid}: {exc}")
            prev.update(
                {
                    "status": "error",
                    "error": f"asr failed: {exc}",
                    "updated_at": now_iso(),
                }
            )
            if downloaded_tmp is not None and not args.delete_audio:
                dest = media_dir / f"{sid}{downloaded_tmp.suffix}"
                try:
                    downloaded_tmp.replace(dest)
                    prev.update(
                        {
                            "media_kind": "audio",
                            "media_path": str(dest.relative_to(ROOT)),
                            "media_status": "ok",
                            "media_error": "",
                        }
                    )
                except Exception as exc2:
                    prev.update(
                        {
                            "media_status": "error",
                            "media_error": f"failed to store audio: {exc2}",
                        }
                    )
            index[sid] = prev
            write_index(INDEX_CSV, fieldnames, index)
            continue
        finally:
            if args.delete_audio and downloaded_tmp is not None:
                try:
                    downloaded_tmp.unlink()
                except Exception:
                    pass

        # Update local transcript index.
        detected_lang = info.language if hasattr(info, "language") else ""
        selected_lang = detected_lang or ("" if lang_arg is None else args.language)
        preferred = "en" if selected_lang.startswith("en") else ("de" if selected_lang.startswith("de") else "other")
        prev.update(
            {
                "preferred_lang": preferred,
                "selected_lang": selected_lang,
                "selected_kind": "asr",
                "transcript_path": str(out_vtt.relative_to(ROOT)),
                "media_kind": "audio",
                "media_status": "missing" if args.delete_audio else (prev.get("media_status") or "ok"),
                "media_error": "" if not args.delete_audio else (prev.get("media_error") or ""),
                "qa_status": prev.get("qa_status") or "pending",
                "status": "ok",
                "error": "",
                "updated_at": now_iso(),
            }
        )
        if downloaded_tmp is not None and not args.delete_audio:
            dest = media_dir / f"{sid}{downloaded_tmp.suffix}"
            try:
                downloaded_tmp.replace(dest)
                prev["media_path"] = str(dest.relative_to(ROOT))
                prev["media_status"] = "ok"
                prev["media_error"] = ""
            except Exception as exc:
                prev["media_status"] = "error"
                prev["media_error"] = f"failed to store audio: {exc}"

        index[sid] = prev
        write_index(INDEX_CSV, fieldnames, index)
        eprint(f"ok: {sid} -> {out_vtt}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
