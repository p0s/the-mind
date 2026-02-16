# Local transcripts: time alignment

Anchors in committed writing refer to **public source time** (video/audio timecode), not transcript cue time.

Some downloaded transcripts can be offset relative to the source. To correct this locally, add a per-source offset in `transcripts/_index.csv`:

- Column: `time_offset_seconds`
- Meaning: `source_time = transcript_time + time_offset_seconds`

Example: if a transcript cue at `00:10:00` actually corresponds to source time `00:10:07`, set `time_offset_seconds=7`.

Scripts that honor this offset:
- `scripts/search_transcripts.py`
- `scripts/show_transcript_snippet.py`
- `scripts/build_source_notes.py`
