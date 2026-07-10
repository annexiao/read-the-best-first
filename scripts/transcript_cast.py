#!/usr/bin/env python3
"""transcript_cast: multi-voice (cast mode) audiobook from a speaker-labeled transcript.

Input: a .txt transcript whose turns look like (podcast/interview export format):

    Speaker Name (HH:MM:SS):
    what they said...

Each speaker gets their own TTS voice. Output: .m4b with chapter markers roughly
every 10 minutes (timestamped from the transcript itself).

Propose-then-dispose: run WITHOUT --voices first; the script lists detected speakers
and exits so a human assigns voices. Then run with:

  .venv/bin/python transcript_cast.py interview.txt \
      --voices "Ada Chen Rekhi=af_heart,Lenny=am_liam" [--device mps] [--speed 1.0]

Resumable: each turn is synthesized to <stem>_cast_work/turns/NNNN.m4a; finished
turns are skipped on re-run. Changing the voice map with existing audio aborts
unless --force (same guard philosophy as epub2m4b.py).
"""
import argparse
import json
import re
import subprocess
import time
from pathlib import Path

import numpy as np

from epub2m4b import FFMPEG, encode_m4a, log, probe_duration, finalize_audiobook

TURN_RE = re.compile(r"^(.+?) \((\d\d):(\d\d):(\d\d)\):\s*$", re.M)


def parse_turns(text):
    """Return [(speaker, start_seconds, body)] in order."""
    parts = TURN_RE.split(text)
    # parts = [preamble, name, hh, mm, ss, body, name, hh, mm, ss, body, ...]
    turns = []
    for i in range(1, len(parts) - 4, 5):
        name = parts[i].strip()
        secs = int(parts[i + 1]) * 3600 + int(parts[i + 2]) * 60 + int(parts[i + 3])
        body = re.sub(r"\[inaudible[^\]]*\]", "", parts[i + 4]).strip()
        if body:
            turns.append((name, secs, body))
    return turns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--voices", help='comma list: "Speaker Name=voice,Other=voice"')
    ap.add_argument("--out")
    ap.add_argument("--title")
    ap.add_argument("--author", default="")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--device", default="cpu", choices=["cpu", "mps"])
    ap.add_argument("--chapter-minutes", type=float, default=10.0)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    src = Path(args.transcript).expanduser()
    turns = parse_turns(src.read_text())
    speakers = {}
    for s, _, b in turns:
        speakers[s] = speakers.get(s, 0) + len(b)
    if not turns:
        raise SystemExit("no 'Speaker (HH:MM:SS):' turns found in the transcript")

    if not args.voices:  # propose step: list the cast, let the human assign
        print(f"{len(turns)} turns, {len(speakers)} speakers:")
        for s, chars in sorted(speakers.items(), key=lambda kv: -kv[1]):
            print(f"  {s}  ({chars:,} chars)")
        print('\nAssign voices and rerun, e.g. --voices "' +
              ",".join(f"{s}=af_heart" for s in speakers) + '"')
        return

    vmap = dict(pair.split("=", 1) for pair in args.voices.split(","))
    vmap = {k.strip(): v.strip() for k, v in vmap.items()}
    missing = [s for s in speakers if s not in vmap]
    if missing:
        raise SystemExit(f"--voices is missing speakers: {missing}")

    title = args.title or src.stem
    out_path = Path(args.out).expanduser() if args.out else src.with_suffix(".m4b")
    work = src.parent / (src.stem + "_cast_work")
    (work / "turns").mkdir(parents=True, exist_ok=True)

    cfg = {"voices": vmap, "speed": args.speed, "n_turns": len(turns)}
    cfg_path = work / "synth_config.json"
    if cfg_path.exists() and any((work / "turns").glob("*.m4a")):
        if json.loads(cfg_path.read_text()) != cfg and not args.force:
            raise SystemExit("work dir was synthesized with a different voice map/speed; "
                             "delete its turns/ dir or pass --force")
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False))

    total_chars = sum(len(b) for _, _, b in turns)
    log(f"{len(turns)} turns, {total_chars:,} chars (~{total_chars/900/60:.1f} h of audio)")

    from kokoro import KPipeline
    pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M", device=args.device)
    sr = 24000
    gap = np.zeros(int(sr * 0.55), dtype=np.float32)
    t0, done_chars = time.time(), 0
    for i, (speaker, _, body) in enumerate(turns):
        out = work / "turns" / f"{i:04d}.m4a"
        if out.exists():
            continue
        parts = []
        for _, _, audio in pipeline(body, voice=vmap[speaker], speed=args.speed,
                                    split_pattern=r"\n+"):
            parts.append(audio.detach().cpu().numpy().astype(np.float32))
        parts.append(gap)
        encode_m4a(np.concatenate(parts), sr, out)
        done_chars += len(body)
        if i % 20 == 0:
            log(f"[{i+1}/{len(turns)}] {speaker}: {len(body)} chars "
                f"(avg {done_chars/max(time.time()-t0,1):.0f} chars/s)")
    log("synthesis pass complete")

    # assemble: concat all turns; chapter mark whenever transcript time crosses the interval
    files = [(i, work / "turns" / f"{i:04d}.m4a") for i in range(len(turns))]
    missing_files = [i for i, p in files if not p.exists()]
    if missing_files:
        raise SystemExit(f"missing synthesized turns: {missing_files[:5]}")
    concat = work / "concat.txt"
    concat.write_text("\n".join(f"file '{p.resolve()}'" for _, p in files) + "\n")

    meta = [";FFMETADATA1", f"title={title}", f"artist={args.author}", "genre=Audiobook"]
    interval = args.chapter_minutes * 60
    next_mark, t_audio, chapters = 0.0, 0.0, []
    for i, p in files:
        if turns[i][1] >= next_mark:
            label = f"{turns[i][1]//60:02.0f}:{turns[i][1]%60:02.0f} {turns[i][0]}: {turns[i][2][:40]}"
            chapters.append((t_audio, label))
            next_mark = turns[i][1] + interval
        t_audio += probe_duration(p)
    for k, (start, label) in enumerate(chapters):
        end = chapters[k + 1][0] if k + 1 < len(chapters) else t_audio
        meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(start*1000)}",
                 f"END={int(end*1000)}", f"title={label}"]
    (work / "ffmeta.txt").write_text("\n".join(meta) + "\n")

    r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "concat", "-safe", "0", "-i", str(concat),
                        "-i", str(work / "ffmeta.txt"), "-map_metadata", "1",
                        "-c", "copy", "-movflags", "+faststart", str(out_path)],
                       capture_output=True)
    if r.returncode != 0:
        raise SystemExit("ffmpeg concat failed: " + r.stderr.decode()[:400])
    log(f"assembled {out_path} ({t_audio/3600:.1f} h, {len(chapters)} chapter marks)")
    finalize_audiobook(out_path, chapters)


if __name__ == "__main__":
    main()
