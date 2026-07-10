---
name: curated-epub-audiobook
description: Use when turning a book EPUB or a collection of articles (blog archive, newsletter, essay site) into a cleaned, inspiration-ranked EPUB and optionally an .m4b audiobook. Triggers on "convert this blog to an epub/audiobook", "make an audiobook from these essays", "rank these articles and package them", "把这本书转成有声书", "把这个博客做成 epub", "按精彩程度排序". Skip for a single article (just read or TTS it directly) and for converting an already-clean, already-ordered book (skip straight to the audiobook stage).
---

# Curated EPUB + Audiobook

## Overview

Pipeline: acquire the texts → strip everything that is not the author's content → order them (this is the heart) → build an EPUB → optionally synthesize an .m4b audiobook with a local TTS model. The reader's contract: best pieces first, so they can stop at their own break-even point.

**The deliverables are three**: the ranked **EPUB**, the **.m4b audiobook** (when requested), and the **ranking record** (`.ranking.json` + `.ranking.md`). Stripping happens BEFORE the EPUB is built, so every downstream artifact inherits clean content.

Scripts live in this repo's `scripts/` directory. The audiobook stage has its own reference: **REQUIRED SUB-SKILL** `kokoro-local-tts` (deploying and running the local model).

## Stage 1: acquire

- **Book**: you already have the EPUB. Go to Stage 2.
- **Substack**: better than scraping — the archive API returns a structured post list: `https://<pub>.substack.com/api/v1/archive?sort=new&limit=50&offset=N` (paginate by offset), each entry carrying date, title, canonical_url, and `audience`. `"everyone"` = free, fetch the canonical_url directly; `"only_paid"` yields only a preview without your subscription's auth. Gotcha: a profile URL (`substack.com/@handle`) is not the publication domain; resolve it from the profile page and sanity-check post dates (stale sibling publications exist).
- **Blog / essay site**: find the archive/index page listing all posts, extract `(url, title)` pairs, download each page (parallel curl with a small concurrency, e.g. `xargs -P 4`). Cache to a local `html/` directory so re-runs are free.
- **Login-walled or heavily scripted sites**: out of scope for the bundled scripts; bring your own authenticated fetcher (a logged-in browser automation that saves rendered HTML works fine; the pipeline only needs HTML files on disk).
- **Multiple authors' blogs at once**: acquire each archive separately, tag every piece with its author, then merge into ONE collection for stage 2. Conventions: chapter titles as `"Title · Author"` (keeps the epub nav and audiobook chapter list legible with no builder change); book-level author `"Various"`; ranking is cross-author with the one rubric (the best pieces of all authors interleave — that is the point); the dependency pass still applies within each author's series; the ranking record carries each piece's author so "whose pieces dominated the top 20" stays answerable.

## Stage 2: strip

Everything that is not the author's writing goes:

- **Web sources**: site chrome, nav, comments, subscribe boxes, related-post blocks. `trafilatura` (used by `scripts/build_epub.py`) removes most of this. `favor_recall=True` keeps more body text at the cost of occasional stray lines; spot-check 2-3 extracted pieces before a long run.
- **Book sources**: publisher front/back matter. Stop-list: copyright page, editor's preface, acknowledgements, index, TOC pages (the EPUB gets a fresh nav), 版权页, 编者的话.
- Sources yielding under 20 chars are dropped automatically (covers, junk). For books with short interstitial pages, raise the floor to ~200 but eyeball what gets dropped.
- **The article gate (collections only, runs BEFORE ranking)**: when crawling an archive, first judge whether each piece IS an article — extracted body under **~500 chars** is a stub (a feed note, a link page, an announcement) and is excluded before the judges ever see it. Anything legitimately shorter than that is a tweet, not an article. Record exclusions in the ranking record's `excluded` list and show them alongside the ranked proposal (a false positive on a real short essay is the human's call). Does not apply to authored book chapters, where a real preface can be short. Ground truth: the Paul Graham example initially ranked a 10-word feed note and a 55-word link page at the very bottom; they should never have reached the judges.

## Stage 3: order (the heart)

Two cases:

1. **A book with an authored narrative order keeps its order.** The author sequenced it deliberately; only strip matter.
2. **A collection of independent pieces gets ranked.** Two passes:
   - **Pass 1, dependencies as hard constraints**: does piece A explicitly build on B (a series, a "part 2", prerequisites)? Those pairs keep their relative order.
   - **Pass 2, rank by inspiration density, descending.** The design principle, in the author's words: *"Assume my time is so limited that I can only read from the most important first. The further down I go, the more I can decide: this is my threshold, I should stop, it is losing its marginal value."* Front-load the best; the reader chooses their stopping point.

**The top 30% is the default deliverable, not an extra.** After ranking, ship the top `floor(N * 0.30)` pieces as the book the reader actually opens — the break-even point pre-applied. Keep the full ranked version too, but as an archive. Both are cheap: the top cut is a re-assembly from the same chapter audio (hardlink the top slice into a fresh work dir, no re-synthesis). Name them distinctly (`<book>.m4b` full; `<book>-top30.m4b` the one to load).

### The rubric (edit this first)

**The rubric lives in its own file: [`rubrics/inspiration.md`](../../rubrics/inspiration.md)** — taste isolated from mechanics, so editing your taste can't break the pipeline. The file's YAML frontmatter defines dimensions (each with weight and optional `veto_below` disqualifier), the scoring policy (holistic / weighted_mean / median / max / min), and tie-break; judges receive its questions and anchors verbatim. Because dimension scores are persisted in the ranking record, switching among the mechanical policies, or changing weights under them, re-ranks in seconds with `.venv/bin/python scripts/rerank.py`, no re-judging (weights do nothing under `holistic`; and a rubric with DIFFERENT dimensions always needs a fresh judging pass — the script refuses to fake it). A rubric is dimensions, not a single number. Judges score each piece on every dimension separately, then give a holistic **overall** (1-10). The overall is the judge's call informed by the dimensions, NOT a mechanical average: averaging flattens exactly the spiky pieces this ordering exists to surface. The dimensions make each placement accountable — when a rank looks wrong, the dimension scores show why.

Default dimensions (the author's — swap in your own):

| Dimension (0-10 each) | 0 looks like | 10 looks like |
|---|---|---|
| **Insight** | restates what everyone knows | tells you something true you had never articulated |
| **Contrarian depth** | agrees with the crowd | challenges a broadly held belief, with substance behind it |
| **Philosophical reach** | stays inside its topic | generalizes to how you think or live |

Overall anchors: 9-10 worldview-shifting; 7-8 strong original framework, high transfer value; 5-6 solid but topic-bounded; 3-4 competent but conventional or era-bound; 1-2 announcements and occasional pieces.

**Change the dimensions to match what you want first** (practical usefulness? emotional resonance? historical importance?). The mechanics stay identical; only the dimension set and anchors change.

### Ranking mechanics

- Extract the first ~450 words of each piece into batch files (~40 pieces per batch).
- Dispatch one cheap-model judge (e.g. Sonnet-class) per batch in parallel, same rubric, instructed to judge from the text, use the full range on every dimension, and return strict JSON `[{slug, <one key per dimension>, overall, reason}]` with a one-line reason each.
- Judge tier: a mid-tier model is fine for exploratory runs; escalate to your strongest model when the ranking is a canonical or published artifact (a record others will argue with). Taste judgment is where model quality shows.
- Input length: judging from each piece's first ~450 words is a validated default, not a guess (20-essay stratified experiment, full-text vs excerpt scoring by the same strong judge: median overall delta 0, 17/20 within one point, within-sample Spearman 0.86, top-band membership essentially unchanged). Known small biases: pieces with punchy openings but listy bodies get over-scored; slow-building pieces get under-scored. Reserve full-text judging for rankings whose individual placements will be publicly contested.
- Merge; check per-batch means. If batches are random slices, large mean gaps suggest judge drift (consider z-normalizing per batch). If batches are chronological slices, mean gaps may be real era differences; keep raw scores.
- Sort by overall, descending; tie-break by recency.
- **Propose, then dispose**: show the human the ranked list with reasons BEFORE spending synthesis hours. They approve or adjust. Never skip this gate.
- **Persist the scoring record as a first-class deliverable (non-optional).** Scores that live only in a scratch directory evaporate. After merging, write TWO files next to the built EPUB:
  - `<book>.ranking.json` — machine-readable source of truth: judge model, date, the rubric's full text, and per piece {rank, slug, title, url, per-dimension scores, overall, one-line reason, judge batch}. Future re-orders, rubric-change diffs, and "why did X rank 150" questions all run on this file.
  - `<book>.ranking.md` — the human-readable ranked table.
  A real pair is in this repo: [examples/paul-graham/full-ranking.json](../../examples/paul-graham/full-ranking.json) and [full-ranking.md](../../examples/paul-graham/full-ranking.md).

Ground truth (2026-07-08): the first Paul Graham build was ordered by CATEGORY (writing / thinking / startup tracks), which turned out to be the assistant's assumption. The owner's actual preference was inspiration-descending. **Inspiration-descending is the default; thematic tracks only on explicit request.**

## Stage 4: build the EPUB

`scripts/build_epub.py` takes a JSON manifest (title, author, intro, ordered chapters pointing at .html/.txt/.md sources) and emits a valid EPUB3. See its docstring for the manifest shape; `examples/paul-graham/manifest.example.json` shows a real one.

```bash
python build_epub.py manifest.json --out ~/Downloads/book.epub
```

Hard-won rule baked into the script: every interpolated string is XML-escaped. One unescaped `&` in a title-page sentence once produced an EPUB that Apple Books refused to open.

## Stage 5: audiobook (optional)

`scripts/epub2m4b.py` converts the EPUB to an .m4b with chapter markers using Kokoro-82M locally. Setup, voices, speed estimates, and gotchas live in the `kokoro-local-tts` skill. Key facts:

- Resumable by design: each chapter lands as its own file; re-running skips finished ones. Interruption costs at most one chapter.
- Rule of thumb: total chars ÷ 900 ÷ 60 = audio hours; chars ÷ 85 ÷ 3600 = synthesis hours on an Apple-Silicon GPU.
- **Run anything over ~1 hour of synthesis on an always-on machine** (a home server, a mini PC), not a laptop that sleeps. Launch with `nohup ... &` over ssh.
- **Voice check first**: synthesize `--limit 3` chapters and have the human listen before a full run. A voice change discards all synthesized chapters.
- Re-ordering later is possible without re-synthesis, but use a FRESH work dir: hardlink the existing chapter audio into the new order (map old files to new indices by chapter title), then run `--assemble-only` with the re-ordered EPUB. Never assemble a re-ordered EPUB over the old work dir; files are index-named and would pair with the wrong chapter metadata (the script refuses this unless `--force`).

## Cast mode: multi-voice audiobook from a speaker-labeled transcript

For podcast/interview transcripts whose turns look like `Speaker Name (HH:MM:SS):`, use `scripts/transcript_cast.py` — each speaker gets their own voice:

```bash
python transcript_cast.py transcript.txt            # propose: lists detected speakers, exits
python transcript_cast.py transcript.txt --voices "Host=am_liam,Guest=af_heart" --device mps
```

- Propose-then-dispose built in: without `--voices` it only lists the cast; the human assigns voices (gender by name is a hint; the human ear makes the final pick — synthesize a short sample per candidate voice first).
- Speaker attribution is deterministic for labeled transcripts (a regex, no LLM). Unlabeled prose/fiction dialogue would need an LLM attribution pass, which this repo does not include; note that essays usually should NOT get voice-switching (rhetorical quotes read worse with a cast).
- Chapter markers come from the transcript's own timestamps.
- Resumable per turn, with the same voice-map-change guard as epub2m4b.

## Verify before claiming done

- EPUB: every XML file parses (unzip and run an XML well-formedness loop over `OEBPS/*.xhtml`, the OPF, the NCX). Use `defusedxml` if the sources are untrusted.
- Chapter count and order: extract chapters from the built EPUB and confirm the first content chapter after the title page is the top-ranked piece.
- m4b: ffprobe duration matches the estimate; chapter marker count matches; spot-check one chapter plays.
- The ranked order was shown to and approved by the human before synthesis.
- The `.ranking.json` + `.ranking.md` record exists next to the EPUB. A ranked build without its scoring record is not done.

## Common mistakes

- Ranking from titles instead of text. Judges must read the pieces.
- Skipping the approval gate and burning 10 hours of synthesis on an ordering the reader did not want.
- Treating the bundled rubric as fixed. It is the one thing each user should change.
- Letting front matter into the audiobook (nobody wants a narrated copyright page).
- Building the full audiobook before the voice check.
