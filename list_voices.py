from src.config import Settings
from src.http import Http
from src.utils import Cache
from src.pipeline import clients
from src.voice import Voice
from pathlib import Path
import datetime


settings = Settings()
http = Http(settings.keys.values())

_, _, budget, _ = clients(
    settings,
    "voice-list-" + datetime.datetime.now().isoformat(),
)

voice = Voice(
    settings,
    http,
    Cache(settings.root / ".cache"),
    budget,
)

voices = voice.voices()

print()
print("=" * 80)
print("AVAILABLE ELEVENLABS VOICES")
print("=" * 80)

for v in voices:
    if v.get("category") != "premade":
        continue

    print()
    print("NAME:     ", v.get("name"))
    print("VOICE ID: ", v.get("voice_id"))
    print("LABELS:   ", v.get("labels"))
    print("-" * 80)