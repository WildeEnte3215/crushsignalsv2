# World in 60 — reusable production engine V1

Python 3.9 compatible. English curiosity Shorts, initially 30–50 seconds, local FFmpeg rendering, no YouTube upload.

**Start with [API_SETUP.md](API_SETUP.md).** The engine is implemented and locally tested; your authenticated end-to-end API run is still required. No API keys are included. The included video is a clearly labeled offline diagnostic, not a researched airplane explainer or an ElevenLabs voice sample.

## Start

Use your existing Python 3.9 environment and installed FFmpeg. From the extracted `world_in_60` directory:

```bash
python -m pip install -r requirements.txt
cp .env.example .env
```

Fill in the three required keys in `.env`, then:

```bash
python setup_check.py
python main.py
```

`SETUP READY` means the current keys passed actual model, web-search, vision, stock, TTS and SFX requests, plus local rendering checks. This checker makes small paid requests. `--offline` never claims API readiness.

The first new run uses **Why airplane windows have tiny holes**. After a completed run, another `python main.py` chooses a different topic. After failure, it resumes the latest unfinished run. Only one process may use a project directory at once.

```bash
python main.py --topic "Why manhole covers are round"
python main.py --resume RUN_ID_FROM_HISTORY
python main.py --new
python setup_check.py --offline
python main.py --demo
python -m unittest discover -v
```

`--new` intentionally starts a separate project; it does not abandon/delete earlier work. `--topic` also creates a new run. No scheduled execution or publishing is installed.

## What changes where

| Change | File |
|---|---|
| Hooks, narrative structure, vocabulary, content rules | `config/prompts/content_prompt.txt` |
| Source requirements | `config/prompts/research_prompt.txt` |
| Stock relevance and framing instructions | `config/prompts/vision_prompt.txt` |
| Channel identity, intro wording/timing, subscribe animation, font/colors | `config/branding.json` |
| Duration, shot length, models, search limits, SFX, subtitles, budgets | `config/video.json` |
| Strict structured plan contract | `src/schemas.py`, exported `config/plan.schema.json` |
| Accounts and keys | `.env` |

The intro animation defaults to one second. **Spoken intro duration follows actual narration**: the seven-word tagline cannot sound natural in 1.2 seconds. Shorten `intro_text`, disable `intro_spoken` for a fixed silent `intro_duration`, or disable `intro_enabled`. The default subscribe graphic slides up, bounces slightly and exits; its timing is independent of the intro.

Subtitles use actual ElevenLabs character alignment, grouped into up to four words with width fitting and active-word color. Chunks never cross scene boundaries. Position and size are configurable; the default leaves space at the bottom and right for Shorts controls. Very long words may form single-word chunks.

## Output and review

Every production run gets `output/<timestamp_topic>/` containing:

- `final.mp4` only after quality checks; `candidate.mp4` if a new render fails review.
- `title.txt`, `description.txt`, `script.txt`, `plan.json`, `sources.json`, `fact_check.json`.
- `timeline.json`, `subtitles.ass`, `quality_report.json`, `cost_estimates.json`.
- `clips/<scene>/selected.mp4`, extracted frames, `candidates.json`, `candidates.html`, `selection.json`.
- `voice/narration.mp3`, alignment; `sfx/` and cue provenance; stock attribution and subscription metadata.

The console and candidate galleries link prominently to Pexels; `description.txt` preserves contributor/source credits for later publication. Keep these credits. Schematics are original programmatic graphics, clearly labeled. The system does not download sound packs.

A quality gate checks dimensions, codecs, pixel format, FPS, actual stream durations and frame count, full decode, long black/silent intervals, loudness, peak level and (live mode) sampled visual review. AI factual and visual review reduce errors but are not guarantees. There is no object tracking; precise markers use a verified frozen frame for the first shot only.

## Resume and caches

Requests, speech, SFX and downloads use content-addressed caches. Successful content and scene selections are checkpointed separately. Editing branding rebuilds the render without paying again for unchanged research. Editing the content prompt invalidates the plan; only changed narration is synthesized again. A failed scene does not discard completed selections.

Stock search responses are cached for 24 hours. Delete a specific scene's `selection.json` after changing its query/selection policy if you need to retry a saved schematic fallback. A plan edited only in `plan.json` is an output artifact; change the prompt or the content checkpoint deliberately instead. Do not remove the whole cache simply to retry one render.

The default stops when more than half the scenes require schematics, rather than outputting a misleading stock montage. Inspect the scene candidates and adjust visual requirements. Raising `max_diagram_fraction` to 1 is an explicit editorial choice. Pixabay is only activated when its optional key is set, with bounded fallback searches; this is not a bulk-harvesting tool.

An older successful `final.mp4` can remain during a failed revision. Check `quality_report.json` and run status: the engine's hash check will not mistake it for the new candidate. Moving a partly completed project changes saved absolute paths and can require reselecting clips. Complete/cache use is reliable when the extracted project stays in one location.

## Troubleshooting

| Message | Action |
|---|---|
| Missing dependency | Install `requirements.txt` with the same `python` used to run the app. |
| HTTP 401 | Replace the named service's invalid key in `.env`. |
| HTTP 403/model unavailable | Check key scopes, project model access and billing; run checker again. |
| HTTP 429 | Check quota versus temporary rate limiting; resume after indicated wait. |
| Local estimated spend limit | Inspect provider billing and local ledger before changing `video.json` budgets. |
| Alignment differs from script | Spell numbers/abbreviations in the prompt; no guessed live subtitle timing. |
| Duration outside target | Adjust target words/voice speed; one automatic rewrite is already attempted. |
| Quality gate failed | Read `quality_report.json`, inspect `candidate.mp4`; corrected inputs invalidate render cache. |
| FFmpeg lacks ASS/libx264 | Use an FFmpeg build with libass/libx264/AAC; the setup checker exercises them. |
| Demo lacks `flite` | Only the optional offline voice fixture needs FFmpeg's flite filter. Live TTS does not. The ready-made diagnostic is in `examples/`. |

Dependencies avoid vendor SDKs and urllib3, using the documented REST APIs with Python's HTTPS client and certifi. No application-level secrets are written to logs, examples or the ZIP. Keep `.env` local. Python 3.9.25/Linux was tested; exact Python 3.9.6/macOS runtime validation remains on your machine.
