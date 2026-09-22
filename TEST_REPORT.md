# Verification report — 14 September 2026

## Confirmed in this delivery

- Runtime: **CPython 3.9.25 on Linux**, with the pinned dependencies installed in a clean Python 3.9 virtual environment.
- Static audit: Ruff `F,E9`, plus parsing every Python source with Python 3.9 grammar. No missing/unused imports or syntax failures remained.
- **22 automated tests passed**: strict schemas; REST request shapes; Responses repair/cache; forced web sources; vision data URLs; Pexels endpoint/auth; Pixabay caching; voice pagination; TTS endpoint/cache; SFX endpoint/fallback; secret redaction; no-retry 401; 503 retries; long 429 stop; budget reservation; corrupt cache; alignment mismatch/NaN; frame coverage; scene-separated captions; disabled intro; subtitle escaping/focal crop; partial scene failure/resume.
- `setup_check.py --offline` passed Python, FFmpeg, ffprobe, all required filter availability, output writing, and an actual H.264/AAC export with ASS/font rendering.
- Full offline diagnostic rendered at **1080×1920, 30 FPS, H.264/yuv420p, AAC 48 kHz stereo**. Actual video and audio streams are **40.000 seconds**, with **1,200 encoded video frames**.
- 19 shots including the intro; story shots are approximately 1.8–2.3 seconds. The local diagnostic's spoken intro is about 2.87 seconds.
- Quality report: **17 technical checks passed**, including complete decode, actual stream durations/frame count, no long black/silent intervals, integrated loudness **−16.49 LUFS**, true peak **−5.97 dBTP**.
- Frames across the beginning, middle and end were visually inspected. The sample exercises portrait footage, landscape containment/blur, focal crop, zoom/pan, freeze markers, labels, diagrams, highlighted subtitles and subscribe animation.
- Identical demo rerun reported **`[CACHE] Complete render`**, followed by successful quality checks.

## Corrections made during audit

A first export had a shorter video stream than audio despite the container showing the intended duration. The original duration check was insufficient. The final gate now checks video duration, audio duration and encoded frame count independently; the delivered sample passes all three. Encoded shot caches now also check actual duration/frame count, so an incomplete shot is not treated as finished.

Other corrections include output-hash validation when resuming a failed revision, separate subtitle chunks at scene boundaries, safe scene ID validation for filesystem paths, dedicated font directories, bounded freeze-frame annotations, conservative retry cost reservation and avoiding charging a separate topic-selection budget cumulatively forever.

## Not claimed as tested

**No paid external API request was executed with a real user key.** API wiring was checked against current official documentation and tested using controlled responses. The live setup checker is implemented, but its authenticated success remains outstanding.

The first live topic is configured as “Why airplane windows have tiny holes”; a fully researched stock-footage/ElevenLabs version was not generated here. The included diagnostic asks that question and then explains/tests the engine itself. Its graphics are synthetic and its voice is locally synthesized word by word. Intra-word timestamps are interpolated only in this isolated fixture; this is not a demonstration of ElevenLabs naturalness or live alignment accuracy.

Python **3.9.6 on macOS** was not available in this environment. Python 3.9 grammar and a real 3.9.25 runtime passed, but run the supplied setup checker on your Mac. There is no Windows runtime guarantee. FFmpeg version tested: **6.1.1-3ubuntu5**.

## Reproduce

```bash
python -m unittest discover -v
python setup_check.py --offline
python main.py --demo
```

`examples/offline_render_demo.mp4` and its JSON quality report are included. The optional demo command requires the FFmpeg `flite` filter; the live engine does not. To finish authenticated integration validation, fill `.env`, run `python setup_check.py`, then `python main.py`. This is the remaining acceptance gate before treating the system as proven on your accounts and machine.
