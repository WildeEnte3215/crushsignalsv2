# Fixed API decisions — checked 14 September 2026

All integrations use official REST endpoints. No guessed ChatGPT/internal model identifiers, no publishing API and no paid video editor.

| Service | Chosen model / endpoint | Purpose | Published cost, USD | Important limits |
|---|---|---|---|---|
| OpenAI | `gpt-5-mini`; `POST /v1/responses` | Research, fact check, structured script | $0.25 input / $2 output per million tokens; search extra | Account/model rate limits; search bounded to five tool calls per research request |
| OpenAI | `gpt-4.1-mini`; same endpoint | Vision ranking, simple topic/query tasks, final sampled review | $0.40 input / $1.60 output per million tokens | Image inputs, not direct video analysis; representative frames can miss events |
| Pexels | `GET https://api.pexels.com/v1/videos/search` | Primary stock video source | Free API | 200/hour, 20,000/month by default; attribution/API terms |
| Pixabay, optional | `GET https://pixabay.com/api/videos/` | Limited stock fallback | Free API | Default 100/60 seconds; cache 24 hours; no bulk automated harvesting |
| ElevenLabs | `eleven_multilingual_v2`; `POST /v1/text-to-speech/{voice_id}/with-timestamps` | English narration and subtitle alignment | API table: $0.10/1,000 characters; paid Starter $6/month | 10,000-character model limit; voice availability and account quota |
| ElevenLabs | `eleven_text_to_sound_v2`; `POST /v1/sound-generation` | Reusable whoosh/click/pop/impact/riser | API table: $0.12/minute generated | Endpoint duration 0.5–30 seconds; scoped key permission; paid-use terms |
| FFmpeg + Pillow | Local libx264, AAC, libass, zoompan, audio filters | All editing, typography and export | No API charge | Runtime/disk/CPU on your Mac; relevant filters must be compiled in |

Model prices/capabilities: [GPT-5 mini](https://developers.openai.com/api/docs/models/gpt-5-mini), [GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini). These are budget-oriented supported choices, not claims to be the newest models. Model changes are configuration changes; update rates too and rerun the checker.

The current Responses shape is `text.format` with `type: json_schema`, `strict: true`, a named schema and required fields. Vision uses `input_image` plus a base64 data URL. Research forces `web_search`, collects `web_search_call.action.sources` and URL citations, then validates extracted URLs against that evidence. [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [vision](https://developers.openai.com/api/docs/guides/images-vision), [web search](https://developers.openai.com/api/docs/guides/tools-web-search), [Responses reference](https://developers.openai.com/api/reference/resources/responses/methods/create/).

OpenAI web search is $10/1,000 tool calls plus applicable model input costs. Reasoning/output tokens also count. [Pricing](https://developers.openai.com/api/docs/pricing). Local reservations intentionally overestimate routine usage and count uncertain retries; they are not billing measurements.

Pexels uses raw `Authorization: API_KEY`; the current video endpoint includes `/v1/`. Pixabay uses `key` as a query parameter, which is redacted in diagnostics. The provider architecture separates searching/normalization from ranking and downloading. [Pexels documentation](https://www.pexels.com/api/documentation/), [Pixabay documentation](https://pixabay.com/api/docs/).

ElevenLabs uses `xi-api-key`, one whole-narration request for voice consistency, MP3 44.1 kHz/128 kbps output, and the returned character alignment. Automatic voice selection paginates `GET /v2/voices`. The multilingual model is sent without an unsupported language override. [Timed speech](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps), [voices](https://elevenlabs.io/docs/api-reference/voices/search), [SFX endpoint](https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert).

The current API pricing table differs from older credit-based capability descriptions and the Creative subscription table. The engine's rates use the API table; confirm the effective quota/product in your account. [ElevenAPI pricing](https://elevenlabs.io/pricing/api).

Licensing boundaries and setup steps are in [API_SETUP.md](API_SETUP.md). These sources establish general API/content rules, not that every search result is appropriate for every commercial context.
