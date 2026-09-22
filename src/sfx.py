import math
import random
import struct
import wave
from .budget import BudgetError
from .utils import ProductionError, atomic, valid_media

PROMPTS = {
    "whoosh": "Short soft airy transition whoosh, no music, no voice.",
    "click": "One clean quiet interface click, no speech.",
    "pop": "One subtle soft rounded pop, no music.",
    "impact": "Short understated low impact, no music or voices.",
    "riser": "Short gentle airy rising transition, no music or speech.",
}


def procedural(path, kind, duration=0.65):
    rng = random.Random(71)
    with wave.open(str(path), "wb") as f:
        f.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        samples = []
        for i in range(int(duration * 48000)):
            t = i / 48000
            env = math.sin(math.pi * t / duration) ** 2
            signal = (
                rng.uniform(-1, 1) * 0.12
                if kind in ("whoosh", "riser")
                else math.sin(2 * math.pi * (350 - 220 * t) * t) * math.exp(-12 * t)
            )
            samples.append(
                struct.pack("<h", int(max(-1, min(1, signal * env)) * 16000))
            )
        f.writeframes(b"".join(samples))


class SFX:
    def __init__(self, settings, http, cache, budget):
        self.s, self.http, self.cache, self.budget = settings, http, cache, budget

    def generate(self, kind, live_required=False):
        body = {
            "text": PROMPTS[kind],
            "duration_seconds": 0.7,
            "prompt_influence": 0.5,
            "model_id": self.s.video["sfx_model"],
            "loop": False,
        }
        path = self.cache.path("sfx", body, ".mp3")
        if valid_media(path, "audio") and not live_required:
            return path, "ElevenLabs cached generation"
        try:
            raw = self.http.request(
                "POST",
                "https://api.elevenlabs.io/v1/sound-generation?output_format=mp3_44100_128",
                {"xi-api-key": self.s.keys["ELEVENLABS_API_KEY"]},
                body,
                binary=True,
                before=lambda: self.budget.reserve(
                    "ElevenLabs SFX", 0.7 * self.s.video["sfx_usd_per_second"]
                ),
            )
            atomic(path, raw)
            if not valid_media(path, "audio"):
                raise ProductionError("SFX response is not decodable audio.")
            return path, "ElevenLabs generated sound"
        except BudgetError:
            raise
        except ProductionError:
            if live_required:
                raise
            path = self.cache.path("sfx-local", kind, ".wav")
            procedural(path, kind)
            return path, "Original procedural fallback; no stock pack"

    def schedule(self, plan, timeline):
        if not self.s.video["sfx_enabled"]:
            return []
        cues, last = [], -100
        planned = []
        if timeline["intro_end"] > 0:
            planned.append((0.1, self.s.brand["intro_sfx"]))
        planned += [
            (s["start"], scene.edit.sfx)
            for scene, s in zip(plan.scenes, timeline["scenes"])
        ]
        for start, kind in planned:
            if len(cues) >= self.s.video["max_sfx"]:
                break
            if kind == "none" or start - last < self.s.video["sfx_gap_seconds"]:
                continue
            path, origin = self.generate(kind)
            cues.append(
                {"start": start, "path": str(path), "kind": kind, "origin": origin}
            )
            last = start
        return cues
