#!/usr/bin/env python3
"""
Local-only, lightweight speaker attribution helper for multi-speaker sources.

Goal: mark approximate time ranges where Joscha Bach is speaking, so we can
verify anchors and avoid mis-attribution in interviews/podcasts.

Constraints:
- No heavy ML deps (no torch). We reuse:
  - faster_whisper.audio.decode_audio (PyAV) to decode media files
  - faster_whisper.vad (Silero ONNX) to detect speech regions
- Output goes under transcripts/ (gitignored).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from faster_whisper import audio as fw_audio
from faster_whisper import vad as fw_vad


ROOT = Path(__file__).resolve().parents[1]
SOURCES_CSV = ROOT / "sources" / "sources.csv"
INDEX_CSV = ROOT / "transcripts" / "_index.csv"
MEDIA_DIR = ROOT / "transcripts" / "_media"
OUT_DIR = ROOT / "transcripts" / "_speakers"

SR = 16000
N_FFT = 512
WIN_LENGTH = 400  # 25ms
HOP_LENGTH = 160  # 10ms
N_MELS = 40

# Reference audio snippets where Bach is speaking (start/end seconds).
# These are local-only and can be edited if needed.
BACH_REF_SLICES = [
    ("ccc_38c3_self_models_of_loving_grace", 130.0, 730.0),
    ("ccc_DS2017_8820_machine_dreams", 120.0, 720.0),
]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_sources() -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    with SOURCES_CSV.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            sid = (r.get("source_id") or "").strip()
            if sid:
                out[sid] = dict(r)
    return out


def load_index() -> Dict[str, Dict[str, str]]:
    if not INDEX_CSV.exists():
        return {}
    out: Dict[str, Dict[str, str]] = {}
    with INDEX_CSV.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            sid = (r.get("source_id") or "").strip()
            if sid:
                out[sid] = dict(r)
    return out


def find_media_path(source_id: str, index: Dict[str, Dict[str, str]]) -> Optional[Path]:
    row = index.get(source_id, {})
    rel = (row.get("media_path") or "").strip()
    if rel:
        p = ROOT / rel
        if p.exists():
            return p
    # Fallback to glob in _media.
    cands = sorted(MEDIA_DIR.glob(f"{source_id}.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    cands = [p for p in cands if p.is_file()]
    return cands[0] if cands else None


def hz_to_mel(hz: float) -> float:
    return 2595.0 * math.log10(1.0 + hz / 700.0)


def mel_to_hz(mel: float) -> float:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def build_mel_filterbank(sr: int = SR, n_fft: int = N_FFT, n_mels: int = N_MELS) -> np.ndarray:
    # Mel filters from ~0 Hz to Nyquist.
    f_min = 0.0
    f_max = sr / 2.0
    mel_min = hz_to_mel(f_min)
    mel_max = hz_to_mel(f_max)
    mels = np.linspace(mel_min, mel_max, n_mels + 2)
    hz = np.array([mel_to_hz(m) for m in mels], dtype=np.float32)
    bins = np.floor((n_fft + 1) * hz / sr).astype(int)
    bins = np.clip(bins, 0, n_fft // 2)

    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for i in range(n_mels):
        left, center, right = bins[i], bins[i + 1], bins[i + 2]
        if center <= left or right <= center:
            continue
        # Rising edge
        fb[i, left:center] = (np.arange(left, center) - left) / float(center - left)
        # Falling edge
        fb[i, center:right] = (right - np.arange(center, right)) / float(right - center)
    return fb


MEL_FB = build_mel_filterbank()
WINDOW = np.hanning(WIN_LENGTH).astype(np.float32)


def frame_audio(x: np.ndarray, win_length: int = WIN_LENGTH, hop_length: int = HOP_LENGTH) -> np.ndarray:
    if x.ndim != 1:
        raise ValueError("audio must be 1D")
    if len(x) < win_length:
        return np.zeros((0, win_length), dtype=np.float32)
    n_frames = 1 + (len(x) - win_length) // hop_length
    stride = x.strides[0]
    frames = np.lib.stride_tricks.as_strided(
        x,
        shape=(n_frames, win_length),
        strides=(hop_length * stride, stride),
        writeable=False,
    )
    return frames.astype(np.float32, copy=False)


def logmel_mean(x: np.ndarray) -> Optional[np.ndarray]:
    frames = frame_audio(x)
    if frames.shape[0] == 0:
        return None
    frames = frames * WINDOW[None, :]
    spec = np.fft.rfft(frames, n=N_FFT, axis=1)
    power = (spec.real * spec.real + spec.imag * spec.imag).astype(np.float32)
    mel = power @ MEL_FB.T
    log_mel = np.log(mel + 1e-10, dtype=np.float32)
    return log_mel.mean(axis=0)


def kmeans(x: np.ndarray, k: int, seed: int = 0, iters: int = 30) -> Tuple[np.ndarray, np.ndarray, float]:
    # Minimal k-means; good enough for local-only diarization heuristics.
    rng = np.random.default_rng(seed)
    n = x.shape[0]
    if n == 0:
        raise ValueError("empty dataset")
    k = max(1, min(k, n))
    idx = rng.choice(n, size=k, replace=False)
    centroids = x[idx].copy()

    labels = np.zeros((n,), dtype=np.int32)
    for _ in range(iters):
        # Assign
        d2 = ((x[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        new_labels = d2.argmin(axis=1).astype(np.int32)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels

        # Update
        for j in range(k):
            mask = labels == j
            if not np.any(mask):
                # Re-seed an empty cluster.
                centroids[j] = x[rng.integers(0, n)]
            else:
                centroids[j] = x[mask].mean(axis=0)

    inertia = float(((x - centroids[labels]) ** 2).sum())
    return labels, centroids, inertia


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a) + 1e-12)
    nb = float(np.linalg.norm(b) + 1e-12)
    return float(np.dot(a, b) / (na * nb))


def merge_segments(segments: List[Tuple[float, float, str]], gap_s: float = 0.5) -> List[Tuple[float, float, str]]:
    if not segments:
        return []
    segments = sorted(segments, key=lambda t: (t[0], t[1]))
    out: List[Tuple[float, float, str]] = []
    cur_s, cur_e, cur_l = segments[0]
    for s, e, l in segments[1:]:
        if l == cur_l and s <= cur_e + gap_s:
            cur_e = max(cur_e, e)
        else:
            out.append((cur_s, cur_e, cur_l))
            cur_s, cur_e, cur_l = s, e, l
    out.append((cur_s, cur_e, cur_l))
    return out


def merge_intervals(intervals: List[Tuple[float, float]], gap_s: float = 0.5) -> List[Tuple[float, float]]:
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda t: (t[0], t[1]))
    out: List[Tuple[float, float]] = []
    cur_s, cur_e = intervals[0]
    for s, e in intervals[1:]:
        if s <= cur_e + gap_s:
            cur_e = max(cur_e, e)
        else:
            out.append((cur_s, cur_e))
            cur_s, cur_e = s, e
    out.append((cur_s, cur_e))
    return out


def compute_bach_reference(index: Dict[str, Dict[str, str]]) -> np.ndarray:
    feats: List[np.ndarray] = []
    for sid, start_s, end_s in BACH_REF_SLICES:
        media = find_media_path(sid, index)
        if media is None:
            continue
        y = fw_audio.decode_audio(str(media), sampling_rate=SR)
        lo = int(max(0.0, start_s) * SR)
        hi = int(min(float(len(y)) / SR, end_s) * SR)
        if hi <= lo:
            continue
        chunk_len = int(8.0 * SR)
        t = lo
        while t + int(2.0 * SR) <= hi:
            t2 = min(t + chunk_len, hi)
            f = logmel_mean(y[t:t2])
            if f is not None:
                feats.append(f)
            t = t2
    if not feats:
        raise RuntimeError("failed to build Bach reference; missing reference audio in transcripts/_media")
    ref = np.stack(feats, axis=0).mean(axis=0)
    return ref.astype(np.float32)


def load_or_build_bach_reference(index: Dict[str, Dict[str, str]]) -> np.ndarray:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "_bach_ref.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        vec = np.array(data.get("logmel_mean", []), dtype=np.float32)
        if vec.shape == (N_MELS,):
            return vec
    ref = compute_bach_reference(index)
    path.write_text(
        json.dumps(
            {
                "generated_at": now_iso(),
                "feature": "logmel_mean",
                "n_mels": N_MELS,
                "ref_slices": [{"source_id": sid, "start_s": s, "end_s": e} for sid, s, e in BACH_REF_SLICES],
                "logmel_mean": ref.tolist(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return ref


def guess_num_speakers(meta: Dict[str, str]) -> int:
    title = (meta.get("title") or "").lower()
    channel = (meta.get("creator_or_channel") or "").lower()
    if "curt jaimungal" in channel:
        if "λ" in title or "&" in title:
            return 3
        return 2
    if "λ" in title:
        return 3
    return 2


def is_likely_multi_speaker(meta: Dict[str, str]) -> bool:
    title = (meta.get("title") or "").lower()
    channel = (meta.get("creator_or_channel") or "").lower()

    # Channels that are typically interviews/panels.
    if any(
        needle in channel
        for needle in [
            "lex fridman",
            "curt jaimungal",
            "machine learning street talk",
            "science, technology & the future",
        ]
    ):
        return True

    # Title markers for multi-speaker content.
    if " podcast" in title or "interview" in title or " with " in title:
        return True
    if "λ" in title or " & " in title:
        return True

    return False


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-id", action="append", required=True)
    ap.add_argument("--num-speakers", type=int, default=0, help="Override speaker count (0 = auto)")
    ap.add_argument("--chunk-seconds", type=float, default=8.0, help="Chunk length for clustering")
    ap.add_argument("--min-chunk-seconds", type=float, default=2.0, help="Skip chunks shorter than this")
    ap.add_argument("--force", action="store_true", help="Overwrite existing speaker files")
    args = ap.parse_args(list(argv) if argv is not None else None)

    sources = load_sources()
    index = load_index()
    bach_ref = load_or_build_bach_reference(index)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for sid in args.source_id:
        out_path = OUT_DIR / f"{sid}.speakers.json"
        if out_path.exists() and not args.force:
            print(f"skip (exists): {out_path}")
            continue

        meta = sources.get(sid, {})
        media = find_media_path(sid, index)
        if media is None:
            print(f"missing media for {sid} (download audio to transcripts/_media first)")
            continue

        print(f"decode: {sid} ({media.name})")
        y = fw_audio.decode_audio(str(media), sampling_rate=SR)
        media_duration_s = float(len(y)) / float(SR)

        print(f"vad: {sid}")
        speech = fw_vad.get_speech_timestamps(y, sampling_rate=SR)
        if not speech:
            print(f"no speech detected: {sid}")
            continue

        # Build analysis chunks within speech regions.
        chunk_s = float(args.chunk_seconds)
        min_chunk_s = float(args.min_chunk_seconds)
        chunks: List[Tuple[float, float]] = []
        feats: List[np.ndarray] = []

        for seg in speech:
            s0 = float(seg["start"]) / SR
            s1 = float(seg["end"]) / SR
            t = s0
            while t < s1:
                t2 = min(t + chunk_s, s1)
                if t2 - t >= min_chunk_s:
                    a0 = int(t * SR)
                    a1 = int(t2 * SR)
                    f = logmel_mean(y[a0:a1])
                    if f is not None:
                        chunks.append((t, t2))
                        feats.append(f)
                t = t2

        if not feats:
            print(f"no usable chunks: {sid}")
            continue

        x = np.stack(feats, axis=0).astype(np.float32)
        # Standardize for k-means.
        mu = x.mean(axis=0)
        sd = x.std(axis=0) + 1e-6
        xz = (x - mu) / sd

        k = args.num_speakers if args.num_speakers > 0 else guess_num_speakers(meta)
        labels, centroids, inertia = kmeans(xz, k=k, seed=0)

        # Find which cluster is most similar to the Bach reference.
        ref_z = (bach_ref - mu) / sd
        sims: List[Tuple[str, float, int]] = []
        for j in range(centroids.shape[0]):
            sim = cosine_sim(centroids[j], ref_z)
            sims.append((f"spk{j}", sim, int((labels == j).sum())))
        sims.sort(key=lambda t: t[1], reverse=True)
        multi = is_likely_multi_speaker(meta)
        if not multi:
            # For solo talks/lectures, the dominant speaker is overwhelmingly likely to be Bach.
            bach_label = max(sims, key=lambda t: t[2])[0]
        else:
            bach_label = sims[0][0]

        # Merge chunk labels into contiguous time segments.
        segs: List[Tuple[float, float, str]] = []
        for (t0, t1), lab in zip(chunks, labels, strict=True):
            segs.append((t0, t1, f"spk{int(lab)}"))
        segs = merge_segments(segs, gap_s=0.25)

        bach_intervals = merge_intervals([(s, e) for s, e, l in segs if l == bach_label], gap_s=0.25)

        out = {
            "source_id": sid,
            "generated_at": now_iso(),
            "audio_path": str(media.relative_to(ROOT)),
            "media_duration_s": media_duration_s,
            "feature": "logmel_mean",
            "sample_rate_hz": SR,
            "chunk_seconds": chunk_s,
            "min_chunk_seconds": min_chunk_s,
            "num_speakers": int(centroids.shape[0]),
            "kmeans_inertia": inertia,
            "multi_speaker_heuristic": bool(multi),
            "bach_label": bach_label,
            "clusters": [{"label": l, "similarity_to_bach": float(sim), "chunk_count": n} for l, sim, n in sims],
            "segments": [{"start_s": float(s), "end_s": float(e), "label": l} for s, e, l in segs],
            "bach_segments": [{"start_s": float(s), "end_s": float(e)} for s, e in bach_intervals],
        }
        out_path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"ok: {sid} -> {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
