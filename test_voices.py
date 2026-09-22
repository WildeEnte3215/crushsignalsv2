import datetime
import shutil
from pathlib import Path

from src.config import Settings
from src.pipeline import clients
from src.voice import Voice


TEST_TEXT = (
    "The world explained in sixty seconds. "
    "Did you know the tiny hole in an airplane window is there on purpose? "
    "Passenger windows are made from multiple layers. "
    "That tiny hole helps balance pressure between them and also lets moisture escape. "
    "So no, your airplane window is not broken. "
    "That tiny hole is actually helping the window do its job."
)


VOICES = {
    "liam": "TX3LPaxmHKxFdv7VOQHJ",
    "will": "bIHbv24MWmeRgasZH58o",
    "chris": "iP95p4xoKVk53GoZ742B",
}


def main():
    settings = Settings()

    http, cache, budget, _ = clients(
        settings,
        "voice-test-" + datetime.datetime.now().isoformat(),
    )

    voice = Voice(
        settings,
        http,
        cache,
        budget,
    )

    output = settings.root / "voice_tests"

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print("=" * 60)
    print("WORLD IN 60 - VOICE TEST")
    print("=" * 60)

    for name, voice_id in VOICES.items():
        print()
        print("Generating:", name)

        audio, meta = voice.generate(
            TEST_TEXT,
            [voice_id],
        )

        destination = (
            output
            / ("%s.mp3" % name)
        )

        shutil.copy2(
            str(audio),
            str(destination),
        )

        print(
            "Saved:",
            destination,
        )

    print()
    print("=" * 60)
    print("DONE")
    print("Open folder:")
    print(output)
    print("=" * 60)


if __name__ == "__main__":
    main()