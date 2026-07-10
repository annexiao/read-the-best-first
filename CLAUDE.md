# Read the Best First

**Stack:** Python 3.12 | **Runtime:** local (no API keys required for the pipeline itself; ranking uses your coding agent's own model)

## What

Turns a book EPUB or a blog/essay archive into a cleaned, inspiration-ranked EPUB, and
optionally a chaptered `.m4b` audiobook narrated by a local TTS model (Kokoro-82M). Best
pieces first, so the reader can stop at their own break-even point. See `README.md` for the
full rationale (do not modify it — it's the owner's voice).

## Start here

This repo is meant to be driven by a coding agent reading its skills, not by hand-run scripts
in isolation. Open these in order:

| Goal | Read |
|---|---|
| Full pipeline: acquire → strip → rank → build EPUB → audiobook | `skills/curated-epub-audiobook/SKILL.md` |
| Deploy/run the local TTS model (Kokoro-82M) | `skills/kokoro-local-tts/SKILL.md` |
| **Change the ranking rubric (do this first, every time)** | `skills/curated-epub-audiobook/SKILL.md`, section "The rubric" |
| Build an EPUB from an ordered manifest | `scripts/build_epub.py` (see its docstring + `examples/paul-graham/manifest.example.json`) |
| Convert an EPUB to a chaptered `.m4b` | `scripts/epub2m4b.py` |
| See a real ranked-output sample | `examples/paul-graham/` |

## Quick start

```bash
./setup.sh                                   # one-time: brew deps + .venv
.venv/bin/python scripts/build_epub.py manifest.json --out book.epub
.venv/bin/python scripts/epub2m4b.py book.epub --limit 3 --device mps   # voice check first
.venv/bin/python scripts/epub2m4b.py book.epub --device mps             # full run
```

## The rubric is not a config detail — it's the product

`skills/curated-epub-audiobook/SKILL.md` ships a default rubric (scores unique insight,
contrarian depth, philosophical reach). **It is meant to be edited per user, every time this
skill is used for a new person or a new goal.** If you're an agent running this pipeline for
someone, the first step is asking what they want to rank for (practical usefulness? emotional
resonance? historical importance?) and rewriting the rubric anchors in that section before
ranking anything.

## Architecture

```
skills/
  curated-epub-audiobook/SKILL.md   # the pipeline: acquire, strip, rank, build, audiobook
  kokoro-local-tts/SKILL.md         # deploying + running Kokoro-82M locally
scripts/
  build_epub.py                    # ordered manifest (JSON) -> EPUB3
  epub2m4b.py                      # EPUB -> chaptered .m4b via Kokoro-82M (resumable per chapter)
examples/paul-graham/              # a real ranked run: manifest + top-20 ranking writeup
```

Data flow: raw texts (EPUB spine or downloaded HTML) -> stripped of non-author content
(`trafilatura` for web, a stop-list for book front/back matter) -> LLM-judge ranking (batched,
parallel, JSON output) -> human approves the order -> `build_epub.py` assembles the EPUB ->
`epub2m4b.py` synthesizes audio per chapter with Kokoro-82M and muxes chapter markers into an
`.m4b`.

## Dependencies

- **Python 3.12** specifically (torch/kokoro wheels lag newest Python; see
  `skills/kokoro-local-tts/SKILL.md` for why).
- **Homebrew**: `espeak-ng` (grapheme-to-phoneme fallback for out-of-vocabulary words),
  `ffmpeg` (audio encoding/muxing), `python@3.12`.
- **Python packages** (installed into `.venv` by `setup.sh`): `kokoro>=0.9.4`, `soundfile`,
  `ebooklib`, `beautifulsoup4`, `trafilatura`, `numpy`.
- No API keys needed for TTS or EPUB building. The ranking step uses whatever LLM your coding
  agent is running as (no separate key to configure).

## Verify before claiming a run is done

Per `skills/curated-epub-audiobook/SKILL.md`: every XML file in the built EPUB parses, the first
content chapter after the title page is the top-ranked piece, the ranked order was shown to and approved by the human before any
synthesis ran, and (for audiobooks) `ffprobe` duration matches the estimate and one chapter has
been spot-checked by listening.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
