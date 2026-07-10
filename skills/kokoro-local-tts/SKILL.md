---
name: kokoro-local-tts
description: Use when deploying or running the Kokoro-82M local text-to-speech model - setting it up on a new machine, choosing voices, synthesizing long texts or audiobooks, or debugging a Kokoro/TTS pipeline failure. Triggers on "deploy Kokoro", "local TTS", "text to speech locally", "本地语音模型", "部署这个 TTS 模型", "which Kokoro voice". Skip for cloud TTS APIs (different tradeoffs) and for languages Kokoro does not cover.
---

# Kokoro-82M Local TTS (deployment reference)

## Overview

Kokoro-82M (hexgrad/Kokoro-82M on Hugging Face) is an 82M-parameter, Apache-2.0 TTS model whose quality approaches commercial APIs at zero marginal cost. It runs comfortably on any Apple-Silicon Mac or modest GPU. This skill is the deployment recipe plus the operational facts a model card never tells you.

## Setup (once per machine)

```bash
brew install espeak-ng ffmpeg python@3.12 atomicparsley mp4v2          # Linux: apt install espeak-ng ffmpeg python3.12
mkdir -p ~/tts && cd ~/tts
python3.12 -m venv .venv
.venv/bin/pip install "kokoro>=0.9.4" soundfile numpy
```

First synthesis auto-downloads the model weights (~330 MB) from Hugging Face into `~/.cache/huggingface`, plus spaCy's `en_core_web_sm`. No account or token needed.

Why each piece (the parts the model card assumes you know):

- **Python 3.12, not the newest**: torch and friends ship prebuilt wheels one or two versions behind the latest Python. Chasing 3.14 fails at install time.
- **espeak-ng even though the model is neural**: misaki (the grapheme-to-phoneme layer, i.e. text → pronunciation symbols) falls back to it for out-of-vocabulary words. Missing it fails at runtime on rare words, not at import.
- **ffmpeg**: not for the model itself; for encoding waveforms into AAC/m4b and anything container-related.
- The model card's install commands use `!pip` / `!apt-get` prefixes, meaning they were written for Colab (Linux notebook). Translate `apt-get` → `brew` on macOS and drop the `!`.

## Minimal usage

```python
from kokoro import KPipeline
import soundfile as sf
import numpy as np

p = KPipeline(lang_code="a", device="mps")   # a=American English; cpu also works
chunks = [audio for _, _, audio in p("Text to speak.", voice="af_heart")]
sf.write("out.wav", np.concatenate([c.numpy() for c in chunks]), 24000)
```

Output is always 24 kHz mono. The pipeline auto-splits long text and yields per-segment audio; pass `split_pattern=r"\n+"` to split on paragraphs.

## Voices

~54 voices ship with the model (downloaded with the weights; switching is free). Naming: first letter a=American, b=British; second f=female, m=male. Highest-rated per the model card's VOICES.md:

| Voice | Notes |
|---|---|
| `af_heart` | American female, top-rated overall, good default |
| `af_bella` | American female, warmer |
| `am_michael` | Best American male |
| `bf_emma`, `bm_george` | British female / male |

Other languages via `lang_code`: `b` British, `z` Mandarin (needs `pip install misaki[zh]` and a `zf_*`/`zm_*` voice), `j` Japanese, and more per the model card. Mixed-language text needs per-chunk routing; the model does not code-switch within one call.

## Operational facts (measured, not from the card)

- **Speed**: ~5.7x realtime on an M5 Pro with `device="mps"`; roughly 4x on an M4. Rule of thumb for planning: ~85 chars/second of processing.
- **Sizing**: chars ÷ 900 ÷ 60 ≈ hours of audio. A 590k-word essay collection ≈ 65 hours of audio ≈ 10-15 hours of synthesis.
- **MPS warnings**: torch prints `stft`/`istft` UserWarnings on every chunk. Harmless (CPU fallback for those two ops); filter them from logs.
- **Long jobs belong on an always-on machine.** A laptop that sleeps kills the run. Launch over ssh with `nohup ... > run.log 2>&1 < /dev/null &`.
- **nohup/ssh/launchd shells often lack `/opt/homebrew/bin` on PATH.** If your pipeline shells out to ffmpeg, resolve it to an absolute path in code. This exact bug once left a "launched" audiobook job dead for 15 hours with a `FileNotFoundError: 'ffmpeg'` buried in the log. If a launched job shows no progress after 20 minutes, read the log for a traceback first; "the process started" is not "the process is alive".
- **Make long syntheses resumable**: write output per chapter/segment and skip existing files on re-run (see `scripts/epub2m4b.py` in this repo for the pattern). Interruptions then cost one segment, not the run.

## It must be an audiobook, not a giant audio file

A plain ffmpeg `.m4b` has chapters, but iOS still treats it as one long track (no chapter list, no per-chapter skip, no resume) unless the iTunes media-kind atom `stik` is set to Audiobook, which ffmpeg never writes. Apple Books also prefers Nero-format chapters over ffmpeg's QuickTime ones. `epub2m4b.py` auto-finalizes: it sets `stik=Audiobook` (AtomicParsley) and rewrites chapters as QuickTime + Nero (mp4chaps). Install `atomicparsley` and `mp4v2`; without them the file is valid but iOS may treat it as one track. Verify: `AtomicParsley file.m4b -t | grep stik` and `mp4chaps -l file.m4b`.

## How to open it on iPhone (Apple Books)

AirDrop's share sheet often does not offer Apple Books for an `.m4b`. Reliable routes: (1) double-click the file on a Mac so it enters Mac Books, then let Books iCloud sync carry it to the iPhone under the same Apple ID; (2) accept AirDrop, Save to Files, then in Files long-press the file, Share, and pick Books; (3) use BookPlayer, a free app purpose-built for `.m4b`. Delete any older copy from Books first.

## Verify before claiming done

- The output file has the expected duration (`ffprobe -show_entries format=duration`).
- A human listens to a sample before long runs commit to a voice. Audio quality sign-off cannot be automated.

## Related

- `curated-epub-audiobook` skill (this repo): the full book/blog → ranked EPUB → audiobook pipeline that uses this model.
- Model card: https://huggingface.co/hexgrad/Kokoro-82M (Usage section + VOICES.md).
