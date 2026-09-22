import base64
import math
import re
from urllib.parse import urlencode, quote
from .http import APIError
from .utils import ProductionError, atomic, valid_media

BASE = "https://api.elevenlabs.io"


def normalize(text):
    return (
        re.sub(r"\s+", "", text)
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
        .lower()
    )


def validate_alignment(alignment, text):
    if not alignment:
        raise ProductionError("ElevenLabs returned no character alignment.")
    chars = alignment.get("characters", [])
    starts, ends = (
        alignment.get("character_start_times_seconds", []),
        alignment.get("character_end_times_seconds", []),
    )
    if not chars or not (len(chars) == len(starts) == len(ends)):
        raise ProductionError("Malformed character alignment lengths.")
    if normalize("".join(chars)) != normalize(text):
        raise ProductionError(
            "TTS alignment text differs from script. Spell numbers and abbreviations out."
        )
    previous = 0
    for start, end in zip(starts, ends):
        if (
            not all(math.isfinite(v) for v in (start, end))
            or start < previous
            or end < start
        ):
            raise ProductionError("Invalid/non-monotonic TTS timestamps.")
        previous = start
    return alignment


class Voice:
    def __init__(self, settings, http, cache, budget):
        self.s, self.http, self.cache, self.budget = settings, http, cache, budget
        self.headers = {"xi-api-key": settings.keys["ELEVENLABS_API_KEY"]}

    def subscription(self):
        return self.http.request("GET", BASE + "/v1/user/subscription", self.headers)

    def voices(self):
        result, token = [], None
        for _ in range(20):
            params = {"page_size": 100}
            if token:
                params["next_page_token"] = token
            data = self.http.request(
                "GET", BASE + "/v2/voices?" + urlencode(params), self.headers
            )
            result.extend(data.get("voices", []))
            if not data.get("has_more"):
                return result
            token = data.get("next_page_token")
            if not token:
                break
        raise ProductionError("Voice pagination incomplete.")

    def select(self):
        voices = self.voices()
        premade = [v for v in voices if v.get("category") == "premade"]

        def score(v):
            labels = str(v.get("labels", {})).lower()
            return sum(
                t in labels for t in ["english", "american", "british", "narration"]
            )

        premade.sort(key=lambda v: (-score(v), v.get("voice_id", "")))
        preferred = self.s.keys["ELEVENLABS_VOICE_ID"]
        fallback = self.s.keys["ELEVENLABS_FALLBACK_VOICE_ID"]
        selected = list(
            dict.fromkeys(
                [v for v in [preferred, fallback] if v]
                + [v["voice_id"] for v in premade]
            )
        )
        if not selected:
            raise ProductionError(
                "No usable voice. Set ELEVENLABS_VOICE_ID to an available licensed voice."
            )
        return selected[:3]

    def generate(self, text, selected):
        for index, voice_id in enumerate(selected):
            body = {
                "text": text,
                "model_id": self.s.video["tts_model"],
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0.1,
                    "use_speaker_boost": True,
                    "speed": self.s.video["voice_speed"],
                },
            }
            key = {"voice": voice_id, "body": body, "format": "mp3_44100_128"}
            path = self.cache.path("voice", key, ".mp3")
            meta = self.cache.get("alignment", key)
            if meta and valid_media(path, "audio"):
                validate_alignment(meta["alignment"], text)
                return path, meta
            try:
                result = self.http.request(
                    "POST",
                    BASE
                    + "/v1/text-to-speech/"
                    + quote(voice_id, safe="")
                    + "/with-timestamps?output_format=mp3_44100_128",
                    self.headers,
                    body,
                    before=lambda: self.budget.reserve(
                        "ElevenLabs TTS",
                        len(text) / 1000 * self.s.video["tts_usd_per_1000_chars"],
                    ),
                )
                alignment = result.get("alignment") or result.get(
                    "normalized_alignment"
                )
                validate_alignment(alignment, text)
                try:
                    audio = base64.b64decode(result["audio_base64"], validate=True)
                except (ValueError, KeyError):
                    raise ProductionError("Invalid TTS audio_base64") from None
                atomic(path, audio)
                if not valid_media(path, "audio"):
                    raise ProductionError("TTS audio cannot be decoded.")
                meta = {
                    "alignment": alignment,
                    "voice_id": voice_id,
                    "model": body["model_id"],
                    "text": text,
                }
                self.cache.put("alignment", key, meta)
                return path, meta
            except APIError as e:
                if (
                    e.status not in (400, 403, 404)
                    or "voice" not in str(e).lower()
                    or index == len(selected) - 1
                ):
                    raise
        raise ProductionError("No narration voice succeeded.")
