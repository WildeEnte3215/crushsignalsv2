# Engine/content separation

`main.py` loads configuration and dotenv before constructing any API client. It takes a project lock, selects/resumes a run, and records completion/failure in `history.json`. Imports do not perform API requests.

| Module | Contract |
|---|---|
| `config.py` | Project-relative paths, keys, validated runtime/branding settings |
| `http.py` | HTTPS REST, redaction, bounded retries, credential redirect protection |
| `budget.py`, `utils.py` | Conservative spend reservations, content cache, atomic JSON/files, process boundary |
| `openai_client.py` | Responses, strict Pydantic schemas, forced web search, image inputs, one JSON repair |
| `topics.py`, `research.py`, `script_generator.py` | Topic choice, source-grounded claims, separate fact check and bounded rewrite |
| `schemas.py` | Required structured fields, no unknown fields, bounded editing enums, safe scene identifiers |
| `stock/pexels.py`, `stock/fallback.py` | Search normalization and per-provider rules |
| `visual_ranker.py` | Metadata shortlist → downloaded preview → three sampled frames → vision score → exact full-quality-frame check |
| `voice.py` | Paginated voice selection, one narration request, character alignment, voice-specific fallback |
| `scene_planner.py` | Narration-to-alignment mapping; integer-frame timeline and short shots |
| `branding.py`, `overlays.py`, `subtitles.py` | Original graphics, subscribe animation, verified markers, ASS word highlighting |
| `sfx.py` | Small shared API-generated preset library, sparse cue placement, original procedural fallback |
| `render.py` | Stock looping/framing, shot caches, motion, concat, captions, loudness normalization and audio mix |
| `quality.py` | Technical decode/timing/audio gates plus optional sampled final AI review |
| `pipeline.py` | Durable stage/scene orchestration and promotion from candidate to final |
| `setup_check.py`, `demo.py` | Current live capability tests and a separate offline diagnostic |

## Structured data

`Research` contains claims with IDs and source URLs. Extracted URLs must have appeared in the actual web tool results; every scene references research claim IDs. The separate fact checker must cover every scene and return evidence URLs grounded in its own search results. A plan is checkpointed only after this gate.

`Plan` contains topic, hook, title, description and 4–9 scenes. Each scene contains narration, claims, visual goal, search queries, schematic nodes and an `Edit` enum structure. `config/plan.schema.json` is generated from the same Pydantic model used by the API; it is documentation, not a second independently maintained validator.

`Assessment` scores relevance, visibility, vertical suitability and quality, plus rejection reasons, focal center and target coordinates. Weighting is 45/25/15/15 percent. Candidate #1 is not automatically selected. Poor footage can fall back to a labeled schematic; excessive fallback stops the project. Ranking uses sampled frames, not exhaustive video understanding.

## Timing and visuals

One TTS request covers intro plus the full narration so the voice stays consistent. Alignment text is compared with the actual script after whitespace/typographic-quote normalization. Numbers are written as spoken words. No approximate live alignment fallback is used.

Scene boundaries follow the first word of each scene. Integer frame boundaries cover the complete audio duration. A scene is split into shots no longer than 2.6 seconds by default. The intro gets its actual spoken length; silent intro padding is explicit. SFX never determine scene duration.

Landscape clips either use an AI-selected focal crop or retain the whole frame against a blurred background. Zooms are modest; crop/pan movement is deterministic. Arrows/circles are drawn into an exact inspected still before crop and appear on the first short shot; there is no claim of object tracking. Later shots resume motion. Diagrams have up to three labeled nodes and progress highlighting.

Transitions are cuts, short fades and dips to black. Overlapping crossfades are deliberately not part of V1: they would require subtracting overlaps from the narration timeline. The code does not pretend to implement complex 3D tracking or editor-grade motion graphics.

## Failure behavior

| Failure | Behavior |
|---|---|
| Temporary HTTP/network error | Up to three attempts with exponential delay/jitter; respects short Retry-After; stops for long waits |
| Authentication/permission/quota | Actionable error; no blind paid retry |
| Invalid JSON | One schema repair, then explicit stop |
| Fact-check disagreement | One script revision, then stop if still unsupported |
| Narration duration mismatch | One rewrite/recheck/regeneration, then stop |
| Poor query or corrupt stock file | Limited query rewrite and next-candidate/provider attempts |
| Voice unavailable | Configured fallback then selected premade voices for voice-specific errors |
| SFX generation unavailable | Original procedural fallback in production; setup requires real API success |
| Interrupted scene | Completed scene checkpoint reused on resume |
| Incomplete encoded shot | Frame count/duration rejected; resume regenerates that shot |
| Final quality rejection | Candidate retained, no promotion; earlier successful final is distinguished by content hash |

Caches depend on request contents, model IDs, prompts, input files and settings as appropriate. Render reuse requires matching input signature **and the actual output SHA-256**, preventing an older final from being accepted as a failed new revision. Clip caches also validate frame counts and durations. A process lock prevents two producers from changing the same project simultaneously.

## Limits of V1

The engine has no YouTube OAuth/upload, scheduler, analytics feedback or web UI. No service account is created by this package. Authenticated live integration remains to be run using the user's keys. Exact stock availability, voice quality, fact correctness and account-specific permissions cannot be established by mocked tests. AI review is an imperfect filter, and rejection can require adjusting content/visual rules rather than endless paid retries.

The repository is designed for macOS/Linux Python 3.9+. Windows locking is not implemented. Paths are absolute inside run checkpoints, so keep an active project at one stable location. The optional demo needs FFmpeg flite; production narration only needs ElevenLabs. The font is bundled with its license. All diagnostic imagery and procedural effects were created by this project.
