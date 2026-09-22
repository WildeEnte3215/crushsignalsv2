from pathlib import Path

from .budget import Budget
from .http import Http
from .openai_client import OpenAI
from .relationship_generator import generate_relationship_short
from .relationship_voice import generate_relationship_voice
from .relationship_music import choose_relationship_music
from .relationship_render import render_relationship_short
from .scam_stock import choose_scam_background
from .schemas import RelationshipShort
from .utils import (
    Cache,
    ProductionError,
    digest,
    read,
    save,
)


def relationship_clients(
    settings,
    run_id,
):
    """
    Create the lightweight clients used by the
    Relationship / Crush production mode.

    This mode uses OpenAI explicitly and does not
    depend on the normal WORLD IN 60 AI provider.
    """

    http = Http(
        settings.keys.values()
    )

    cache = Cache(
        settings.root / ".cache"
    )

    budget = Budget(
        settings,
        run_id,
    )

    ai = OpenAI(
        settings,
        http,
        cache,
        budget,
    )

    return (
        http,
        cache,
        budget,
        ai,
    )


def produce_relationship(
    settings,
    run,
):
    """
    Produce one Relationship / Crush Short.

    Pipeline:

    topic
    -> GPT-5.6 Luna concept
    -> ElevenLabs voice
    -> one unique portrait Pexels background
    -> local rotating background music
    -> synced text renderer
    -> subscribe fly-in
    -> final.mp4

    No Tavily.
    No Gemini.
    No AI vision.
    """

    folder = (
        settings.root
        / "output"
        / run["id"]
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        http,
        cache,
        budget,
        ai,
    ) = relationship_clients(
        settings,
        run["id"],
    )

    # -----------------------------------------------------
    # CONTENT CHECKPOINT
    # -----------------------------------------------------

    key = digest(
        {
            "engine": 2,
            "mode": "relationship",
            "topic": run["topic"],
            "ai_provider": "openai",
            "model": "gpt-5.6-luna",
            "prompt": settings.prompt(
                "relationship"
            ),
        }
    )

    checkpoint_path = (
        folder
        / "relationship_content_checkpoint.json"
    )

    stored = read(
        checkpoint_path,
        {},
    )

    # -----------------------------------------------------
    # GENERATE SHORT CONCEPT
    # -----------------------------------------------------

    if (
        stored.get(
            "key"
        )
        == key
        and stored.get(
            "short"
        )
    ):
        short = (
            RelationshipShort.model_validate(
                stored[
                    "short"
                ]
            )
        )

        print(
            "[CACHE] Relationship concept",
            flush=True,
        )

    else:
        print(
            "[STEP] Relationship Short concept",
            flush=True,
        )

        short = generate_relationship_short(
            ai,
            settings,
            run["topic"],
        )

        save(
            checkpoint_path,
            {
                "key": key,
                "short": (
                    short.model_dump()
                ),
            },
        )

    # -----------------------------------------------------
    # HUMAN-READABLE CONTENT FILE
    # -----------------------------------------------------

    save(
        folder
        / "relationship_short.json",
        short.model_dump(),
    )

    # -----------------------------------------------------
    # ELEVENLABS VOICE
    # -----------------------------------------------------

    voice_info = generate_relationship_voice(
        settings,
        http,
        cache,
        budget,
        short,
    )

    save(
        folder
        / "relationship_voice.json",
        {
            "duration": (
                voice_info[
                    "duration"
                ]
            ),
            "segments": (
                voice_info[
                    "segments"
                ]
            ),
            "voice_id": (
                voice_info.get(
                    "voice_id",
                    ""
                )
            ),
            "text": (
                voice_info[
                    "text"
                ]
            ),
        },
    )

    # -----------------------------------------------------
    # UNIQUE PORTRAIT STOCK BACKGROUND
    # -----------------------------------------------------

    background = choose_scam_background(
        settings,
        http,
        cache,
        short.background_search_query,
        minimum_duration=float(
            voice_info[
                "duration"
            ]
        ),
    )

    stock_metadata = {
        key: value
        for key, value
        in background.items()
        if key != "local_path"
    }

    save(
        folder
        / "relationship_background.json",
        stock_metadata,
    )

    # -----------------------------------------------------
    # BACKGROUND MUSIC
    # -----------------------------------------------------

    music = choose_relationship_music(
        settings,
        run["topic"],
    )

    music_path = Path(
        music[
            "path"
        ]
    )

    if not music_path.exists():
        raise ProductionError(
            "Selected Relationship music file does not exist: "
            + str(
                music_path
            )
        )

    save(
        folder
        / "relationship_music.json",
        {
            "mood": (
                music[
                    "mood"
                ]
            ),
            "requested_mood": (
                music[
                    "requested_mood"
                ]
            ),
            "fallback_used": (
                music[
                    "fallback_used"
                ]
            ),
            "filename": (
                music[
                    "filename"
                ]
            ),
            "volume_db": (
                music[
                    "volume_db"
                ]
            ),
        },
    )

    # -----------------------------------------------------
    # RENDER
    # -----------------------------------------------------

    final = render_relationship_short(
        settings,
        folder,
        short,
        background,
        voice_info,
        music_path=music_path,
    )

    if not Path(
        final
    ).exists():
        raise ProductionError(
            "Relationship renderer did not create final.mp4."
        )

    print(
        (
            "[OK] Relationship music: "
            "%s | %s | %.1f dB"
        )
        % (
            music[
                "mood"
            ],
            music[
                "filename"
            ],
            float(
                music[
                    "volume_db"
                ]
            ),
        ),
        flush=True,
    )

    print(
        "[OK] Relationship pipeline complete",
        flush=True,
    )

    return final