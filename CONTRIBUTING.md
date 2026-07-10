# Contributing

This is a small, opinionated tool. The interesting contributions are the ones that make it
work well for readers whose taste isn't the default rubric, or whose language isn't English —
not general refactors.

## Most valuable contributions

- **Alternative rubrics.** The bundled rubric in `skills/curated-epub-audiobook/SKILL.md`
  scores inspiration density (unique insight, contrarian depth, philosophical reach). If you've
  built and used a different rubric that works well for a different goal — practical
  usefulness, emotional resonance, historical importance, humor — share it as an example
  (a copy of the rubric section plus a short note on what it optimizes for and a sample
  ranking, similar to `examples/paul-graham/`).
- **Language support.** Kokoro-82M covers more than English (Mandarin, Japanese, and others —
  see `skills/kokoro-local-tts/SKILL.md`), but the stripping heuristics (`trafilatura`, the
  book front/back-matter stop-list) are tuned on English and Chinese sources. If you've made
  the pipeline work cleanly for another language — a different stop-list, a different
  extraction fallback, voice recommendations — that's high-value.
- **Real ranking examples.** A worked example (manifest + top-N ranking writeup) for a
  different author/blog, especially one that stress-tests the pipeline differently (very
  short pieces, heavy code blocks, a non-English archive).

## Development setup

```bash
git clone <your fork>
cd read-the-best-first
./setup.sh
```

## Making a change

1. Fork and branch off `main`.
2. If you're changing `scripts/build_epub.py` or `scripts/epub2m4b.py`, test against
   `examples/paul-graham/manifest.example.json` (or your own small manifest) and confirm the
   output EPUB opens and, for audiobook changes, that `--limit 3` still produces a valid
   `.m4b` with correct chapter markers.
3. If you're changing a skill (`skills/*/SKILL.md`), keep the frontmatter's `description`
   trigger phrases accurate — that's what causes a coding agent to pick up the skill.
4. Open a PR describing what you changed and why, and what you tested it against.

## Code style

- Scripts are dependency-light, single-file, and read top to bottom — keep additions in that
  spirit rather than introducing a framework.
- Every interpolated string that lands in EPUB XML must stay escaped (see
  `build_epub.py` — an unescaped `&` once produced an EPUB Apple Books refused to open).
- Long-running synthesis must stay resumable (per-chapter output files, skip existing ones on
  re-run). Don't regress this to a single monolithic pass.

## Reporting issues

Open a GitHub issue with: what you ran, the source (book EPUB vs. blog archive, roughly how
many pieces), and the full error/traceback if there was one. For audiobook issues, include
`--device` and whether the job ran on a machine that could sleep mid-run.

## Using Claude Code

This project includes a `CLAUDE.md` that gives Claude Code (or any skill-reading agent) full
context on the pipeline, scripts, and dependencies. Open the repo in Claude Code and it reads
`CLAUDE.md` automatically.
