# One-time API setup

You already have Python 3.9 and FFmpeg. There is no need to reinstall them. Three accounts are required: OpenAI API, Pexels and ElevenLabs. Pixabay is optional.

## 1. OpenAI

1. Sign in to the [OpenAI API platform](https://platform.openai.com/).
2. Create/select a project named `World in 60` in the project selector.
3. In platform **Settings → Billing**, enable API billing and add an initial **$10 prepaid credit**, if available for your account. Review auto-reload and turn it off for initial testing if you do not want automatic top-ups. [Prepaid billing instructions](https://help.openai.com/en/articles/8264644-setting-up-and-managing-prepaid-api-billing).
4. In the selected project, open **API keys → Create new secret key**. Name it `world-in-60-local`. Use a project key, not an organization-admin key.
5. Required access: write/create Responses, read Models, access `gpt-5-mini` and `gpt-4.1-mini`; the Responses call must permit the built-in web-search tool. Choose a restricted key with those endpoint permissions where available, or a standard project key for initial setup. No Files, fine-tuning or image-generation endpoint is needed.
6. Put the secret into `OPENAI_API_KEY=` in `.env`.
7. Set a project budget alert around **$30/month** initially. This is an alert, **not a hard cutoff**. The application adds its own conservative estimated spend guard. [Project management and budget behavior](https://help.openai.com/en/articles/9186755-managing-projects-in-the-api-platform).

**Your ChatGPT subscription does not include OpenAI API usage.** API billing is separate. [Official billing explanation](https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform).

The setup checker performs model retrieval, small strict-JSON Responses requests, a web search and an image-color test. Account-specific rate limits/model access are checked live; the code does not assume an account tier.

## 2. Pexels

1. Create/sign in to a Pexels account at the [Pexels API page](https://www.pexels.com/api/).
2. Request an API key. Describe the use truthfully: local editorial workflow that selects and edits stock into narrated educational Shorts, retains attribution and links back to Pexels.
3. Put the key into `PEXELS_API_KEY=`. There is no `Bearer` prefix; the engine supplies the raw Authorization header.
4. No paid stock subscription is needed for this implementation. Default documented allowance: 200 requests/hour, 20,000/month. Do not create extra accounts to evade limits. [API documentation and requirements](https://www.pexels.com/api/documentation/).
5. Keep generated Pexels and creator credits in the eventual YouTube description. The API requirements are stricter about attribution than the general content license.

The general license permits modification and commercial uses, subject to restrictions such as endorsements, trademarks and identifiable people. Stock availability does not itself clear every third-party right. [Pexels license](https://www.pexels.com/license/).

## 3. ElevenLabs

1. Create/sign in at [ElevenLabs](https://elevenlabs.io/).
2. Start with the **paid Starter plan, currently $6/month**, for the first test batch. Upgrade only when your actual usage needs it; Creator is $22/month before introductory discounts. Check the API allowance in your account, not a different Creative product's credit table. [API pricing](https://elevenlabs.io/pricing/api).
3. Open **Developers → API Keys** in your ElevenLabs account and create a dedicated key. Enable Text to Speech, Sound Generation, Voices read, Models read, and User/Subscription read permissions. Give it a modest credit quota. Interface labels can differ; the checker names any denied endpoint.
4. Put the key in `ELEVENLABS_API_KEY=`. [Authentication and scoped keys](https://elevenlabs.io/docs/api-reference/authentication).
5. Leave `ELEVENLABS_VOICE_ID=` blank for automatic selection from available premade voices, prioritizing English/US/UK/narration labels. Or copy a voice ID from your available voices into that variable.
6. Optionally set `ELEVENLABS_FALLBACK_VOICE_ID=`. The engine then tries this before additional premade voices for voice-specific availability errors. It does not clone voices.

For the commercial channel, generate speech and API SFX while on a qualifying paid subscription. The EU terms distinguish free noncommercial use from paid commercial use. The checker rejects the free tier; it does not treat an arbitrary voice or stock asset as automatically cleared. [ElevenLabs EU terms, section 1(c)](https://elevenlabs.io/terms-of-use-eu).

Voice and SFX use the same key. The checker actually generates a short sentence with timestamps and one short SFX; a successful voices-list request alone is insufficient. SFX permission failure blocks `SETUP READY` while SFX is enabled, even though production supports an original procedural fallback for temporary generation failures.

## 4. Optional Pixabay

Sign in at [Pixabay API documentation](https://pixabay.com/api/docs/) to get your API key. Put it in `PIXABAY_API_KEY=` to enable fallback. Leave it blank initially: Pexels is enough to test the basic workflow. No additional subscription is required.

The provider uses the video API, safe search and mandatory 24-hour query caching. It performs only limited fallback searches for the requested project; Pixabay prohibits systematic mass downloads and large volumes of automated queries. Review the [content license](https://pixabay.com/service/license-summary/) and preserve metadata. Logos, brands and recognizable people can involve separate rights.

## Verify and run

From the project directory with your existing environment active:

```bash
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` locally. Do not paste secrets into chat. Then:

```bash
python setup_check.py
```

Only proceed to production after `SETUP READY`:

```bash
python main.py
```

Small test generations consume API credits; repeated setup runs intentionally recheck current paid permissions. Typical setup cost should be well below $1, but the provider's invoice is authoritative. `python setup_check.py --offline` is free and tests only local capabilities.

If a check fails, correct that service's key, permissions or billing and rerun. You can share the redacted error text and `setup_report.json` for diagnosis. Never share `.env` or an API secret.
