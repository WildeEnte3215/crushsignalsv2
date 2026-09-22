# Test budget

The €150/month budget is a ceiling, not a subscription shopping list. Start with OpenAI $10 prepaid, ElevenLabs Starter, free Pexels and local rendering. Add no other paid service for V1.

## Planning estimates, not measured invoices

For a typical 30–50-second Short, expect roughly 600–850 narration characters, two web research/audit passes, structured planning, and about 20–35 small visual assessments. Search rewrites and a duration rewrite increase usage.

| Test volume | OpenAI planning allowance | Narration planning amount at $0.10/1k chars | SFX | Stock/render |
|---|---:|---:|---:|---:|
| 20 Shorts | $4–$12 | $1.20–$1.70 usage equivalent, subject to subscription | Usually pennies; cached effects reused | $0 API; local CPU/storage |
| 100 Shorts | $20–$60 | $6–$8.50 usage equivalent, subject to subscription | Usually under $1 for this small preset library | $0 API; local CPU/storage |

These are deliberately broad engineering allowances, not claims about measured model usage. Actual OpenAI calls often cost less; image dimensions, reasoning, source length and rejected candidates matter. A typical six-scene run evaluates up to three candidates with three frames each, then rechecks one exact full-quality frame per selected scene. Failed query rounds/providers can multiply this.

An illustrative calculation: 30k GPT-5 mini input + 15k output tokens = $0.0375; 80k GPT-4.1 mini input + 8k output = $0.0448; six search calls = $0.06 before search-content tokens. Total about $0.14 before other requests/retries. Budget $0.20–$0.60 per Short for planning headroom, not as a guaranteed ceiling. [OpenAI model/tool pricing](https://developers.openai.com/api/docs/pricing).

ElevenLabs Starter is $6/month in the current API table. The usage equivalent above should not be blindly added on top of already included allowance. Verify the product and remaining characters shown in your subscription. Upgrade to Creator only if necessary for the desired test volume. SFX API pricing is currently $0.12/minute: a 0.7-second effect is about $0.0014 at that rate, then reused from cache. [ElevenLabs API pricing](https://elevenlabs.io/pricing/api).

Allow for taxes and USD/EUR conversion; no exchange rate is assumed here. Even a $60 OpenAI test month plus a $22 ElevenLabs plan is intended to leave room within €150 for retries and tax, but your actual billing determines the outcome.

## Application guard

`video.json` defaults to $2 estimated API spend per production run and $100/month across this project's calls, leaving budget room for subscriptions and taxes. Before each paid request/retry, the engine reserves a conservative amount in SQLite. It does not credit back a timed-out request because the provider may already have processed it. OpenAI reserves maximum output and estimated input/tool costs; ElevenLabs uses configured character/second rates.

`cost_estimates.json` therefore reports **reservations**, not actual charges. Current OpenAI response usage is retained with cached raw responses for further accounting work. The guard excludes subscriptions, other applications/projects, storage/electricity and taxes. It is not an account-wide hard billing cap. Do not delete the cost database to work around a limit; check provider usage first. Repeated full setup checks also consume credits.
