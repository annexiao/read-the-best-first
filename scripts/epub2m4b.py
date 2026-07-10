#!/usr/bin/env python3
"""epub2m4b: convert an EPUB to an .m4b audiobook with chapter markers, using Kokoro-82M locally.

Resumable: each chapter is synthesized to work_dir/chapters/NNN.m4a; existing files are skipped,
so an interrupted run continues where it left off. Re-run with --assemble-only to just build the
m4b from whatever chapters exist so far.

Usage:
  .venv/bin/python epub2m4b.py BOOK.epub [--out BOOK.m4b] [--voice af_heart] [--speed 1.0]
                    [--device mps|cpu] [--limit N] [--assemble-only]
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np


def _tool(name):
    """Resolve ffmpeg/ffprobe by absolute path: nohup/ssh/launchd shells often lack /opt/homebrew/bin on PATH."""
    p = shutil.which(name)
    if p:
        return p
    for c in (f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"):
        if Path(c).exists():
            return c
    raise SystemExit(f"{name} not found; brew install {name}")


FFMPEG = _tool("ffmpeg")
FFPROBE = _tool("ffprobe")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def extract_chapters(epub_path):
    """Return [(title, text)] in spine order."""
    from bs4 import BeautifulSoup
    from ebooklib import epub, ITEM_DOCUMENT
    book = epub.read_epub(str(epub_path))
    id2item = {it.id: it for it in book.get_items_of_type(ITEM_DOCUMENT)}
    chapters = []
    for idref, _linear in book.spine:
        item = id2item.get(idref)
        if item is None:
            continue
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for tag in soup(["style", "script", "nav"]):
            tag.decompose()
        body = soup.body or soup
        h1 = body.find(["h1", "h2"])
        title = (h1.get_text(" ", strip=True) if h1 else None) \
            or (soup.title.get_text(strip=True) if soup.title else item.get_name())
        paras = [p.get_text(" ", strip=True) for p in body.find_all(["p", "h1", "h2", "h3", "li", "blockquote"])]
        paras = [re.sub(r"\s+", " ", p) for p in paras if p and p.strip()]
        text = "\n".join(paras)
        if len(text) < 20:  # cover pages etc.
            continue
        chapters.append((title, text))
    return chapters


def synth_chapter(pipeline, text, voice, speed, sr=24000, para_gap=0.35):
    gap = np.zeros(int(sr * para_gap), dtype=np.float32)
    parts = []
    for _, _, audio in pipeline(text, voice=voice, speed=speed, split_pattern=r"\n+"):
        a = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
        parts.append(a.astype(np.float32))
        parts.append(gap)
    if not parts:
        return np.zeros(sr // 2, dtype=np.float32)
    return np.concatenate(parts)


def encode_m4a(wav_array, sr, out_path):
    """Pipe float32 PCM into ffmpeg -> AAC 64k mono."""
    p = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0",
         "-c:a", "aac", "-b:a", "64k", str(out_path)],
        input=wav_array.tobytes(), capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode()[:500])


def probe_duration(path):
    p = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    return float(p.stdout.strip())


def assemble(work, out_path, book_title, author):
    chapters = json.loads((work / "manifest.json").read_text())
    done = [(c, work / "chapters" / c["file"]) for c in chapters if (work / "chapters" / c["file"]).exists()]
    if not done:
        raise SystemExit("no synthesized chapters found; run synthesis first")
    # concat list + chapter metadata
    concat = work / "concat.txt"
    concat.write_text("\n".join(f"file '{p.resolve()}'" for _, p in done) + "\n")
    meta_lines = [";FFMETADATA1", f"title={book_title}", f"artist={author}", "genre=Audiobook"]
    starts = []  # (start_seconds, title) for the .chapters.txt used by finalize
    t = 0.0
    for c, p in done:
        d = probe_duration(p)
        starts.append((t, c["title"]))
        meta_lines += ["[CHAPTER]", "TIMEBASE=1/1000",
                       f"START={int(t*1000)}", f"END={int((t+d)*1000)}",
                       f"title={c['title']}"]
        t += d
    meta = work / "ffmeta.txt"
    meta.write_text("\n".join(meta_lines) + "\n")
    p = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", str(concat),
         "-i", str(meta), "-map_metadata", "1",
         "-c", "copy", "-movflags", "+faststart", str(out_path)],
        capture_output=True)
    if p.returncode != 0:
        raise SystemExit("ffmpeg concat failed: " + p.stderr.decode()[:500])
    log(f"assembled {out_path} ({t/3600:.1f} h, {len(done)}/{len(chapters)} chapters)")
    finalize_audiobook(out_path, starts)


def finalize_audiobook(out_path, starts):
    """Make iOS treat the file as an AUDIOBOOK, not a giant song.

    Two things ffmpeg never writes: (1) the iTunes media-kind atom `stik`
    (value 2 = Audiobook) — without it iOS Books shows no chapter list, no
    per-chapter skip, no resume; (2) Nero-format chapters alongside QuickTime,
    which Apple Books reads most reliably. Best-effort: if AtomicParsley /
    mp4chaps aren't installed, we log and leave the (still valid) file alone.
    Chapter timings come from the caller, NOT from re-exporting the file, so
    there is no stale-export drift.
    """
    ap = shutil.which("AtomicParsley")
    chaps = shutil.which("mp4chaps")
    if not (ap and chaps):
        log("finalize skipped (need `brew install atomicparsley mp4v2` for iOS "
            "audiobook chapters); file is valid but iOS may treat it as one track")
        return
    txt = Path(str(out_path) + ".chapters.txt")  # mp4chaps convention: <file>.chapters.txt
    txt.write_text("\n".join(
        f"{int(s//3600):02d}:{int(s % 3600//60):02d}:{s % 60:06.3f} {title}"
        for s, title in starts) + "\n")
    subprocess.run([ap, str(out_path), "--stik", "Audiobook", "--overWrite"],
                   capture_output=True)
    subprocess.run([chaps, "-r", "-A", str(out_path)], capture_output=True)   # clear existing
    subprocess.run([chaps, "-i", "-A", "-z", str(out_path)], capture_output=True)  # QT + Nero
    log("finalized as audiobook (stik=Audiobook, QuickTime+Nero chapters)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("epub")
    ap.add_argument("--out")
    ap.add_argument("--voice", default="af_heart")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--device", default="cpu", choices=["cpu", "mps"])
    ap.add_argument("--limit", type=int, help="synthesize only the first N chapters (for tests)")
    ap.add_argument("--assemble-only", action="store_true")
    ap.add_argument("--author", default="Unknown")
    ap.add_argument("--force", action="store_true",
                    help="reuse a work dir even if voice/speed/chapter order changed")
    args = ap.parse_args()

    epub_path = Path(args.epub).expanduser()
    book_title = epub_path.stem.replace("-", " ").title()
    out_path = Path(args.out).expanduser() if args.out else epub_path.with_suffix(".m4b")
    work = epub_path.parent / (epub_path.stem + "_audiobook_work")
    (work / "chapters").mkdir(parents=True, exist_ok=True)

    log(f"extracting chapters from {epub_path.name}")
    chaps = extract_chapters(epub_path)
    manifest = [{"idx": i, "title": t, "file": f"{i:03d}.m4a", "chars": len(x)}
                for i, (t, x) in enumerate(chaps)]
    (work / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    total_chars = sum(m["chars"] for m in manifest)
    log(f"{len(chaps)} chapters, {total_chars:,} chars (~{total_chars/900/60:.1f} h of audio)")

    # Guard: chapter files are index-named, so reusing a work dir after changing the
    # voice, the speed, or the chapter ORDER would silently mix stale audio into the
    # book (wrong voice, or metadata paired with the wrong chapter). Refuse unless --force.
    cfg = {"voice": args.voice, "speed": args.speed, "titles": [m["title"] for m in manifest]}
    cfg_path = work / "synth_config.json"
    has_audio = any((work / "chapters").glob("*.m4a"))
    if cfg_path.exists() and has_audio:
        old_cfg = json.loads(cfg_path.read_text())
        if old_cfg != cfg and not args.force:
            raise SystemExit(
                "work dir was synthesized with a different voice/speed/chapter order.\n"
                "Either delete its chapters/ dir, use a fresh work dir (rename the epub), "
                "or pass --force if you know the existing audio is what you want.")
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False))

    if not args.assemble_only:
        from kokoro import KPipeline
        pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M", device=args.device)
        todo = chaps[: args.limit] if args.limit else chaps
        t0, chars_done = time.time(), 0
        for i, (title, text) in enumerate(todo):
            out = work / "chapters" / f"{i:03d}.m4a"
            if out.exists():
                continue
            t1 = time.time()
            audio = synth_chapter(pipeline, text, args.voice, args.speed)
            encode_m4a(audio, 24000, out)
            chars_done += len(text)
            rate = chars_done / max(time.time() - t0, 1)
            log(f"[{i+1}/{len(todo)}] {title[:50]!r} {len(audio)/24000/60:.1f} min "
                f"(synth {time.time()-t1:.0f}s, avg {rate:.0f} chars/s)")
        log("synthesis pass complete")

    assemble(work, out_path, book_title, args.author)


if __name__ == "__main__":
    main()
