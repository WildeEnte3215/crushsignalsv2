from pathlib import Path

from .budget import Budget
from .http import Http
from .openai_client import OpenAI
from .scam_research import research_scam
from .scam_generator import generate_scam_short
from .scam_stock import choose_scam_background
from .scam_render import render_scam_short
from .schemas import Research, ScamShort
from .utils import (
    Cache,
    ProductionError,
    digest,
    read,
    save,
)


def scam_clients(
    settings,
    run_id,
):
    """
    Create clients for Scam / Safety production.

    This mode intentionally uses OpenAI even when the
    normal WORLD IN 60 engine is configured for Gemini.
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


def produce_scam(
    settings,
    run,
):
    """
    Produce one text-only Scam / Safety Short.

    Pipeline:
    topic
    -> Tavily research
    -> GPT-5.6 Luna structured research
    -> GPT-5.6 Luna ScamShort
    -> one Pexels background
    -> text render
    -> final.mp4

    No Gemini.
    No ElevenLabs.
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
    ) = scam_clients(
        settings,
        run["id"],
    )

    # -----------------------------------------------------
    # CONTENT CHECKPOINT
    # -----------------------------------------------------

    key = digest(
        {
            "engine": 2,
            "mode": "scam",
            "topic": run["topic"],
            "ai_provider": "openai",
            "scam_model": "gpt-5.6-luna",
            "research_prompt": settings.prompt(
                "research"
            ),
            "scam_prompt": settings.prompt(
                "scam"
            ),
        }
    )

    checkpoint_path = (
        folder
        / "scam_content_checkpoint.json"
    )

    stored = read(
        checkpoint_path,
        {},
    )

    # -----------------------------------------------------
    # RESEARCH + SHORT GENERATION
    # -----------------------------------------------------

    if (
        stored.get(
            "key"
        )
        == key
        and stored.get(
            "research"
        )
        and stored.get(
            "short"
        )
    ):
        evidence = (
            Research.model_validate(
                stored[
                    "research"
                ]
            )
        )

        short = (
            ScamShort.model_validate(
                stored[
                    "short"
                ]
            )
        )

        print(
            "[CACHE] Scam research and concept",
            flush=True,
        )

    else:
        print(
            "[STEP] Scam research",
            flush=True,
        )

        evidence = research_scam(
            ai,
            settings,
            run["topic"],
            run["created"],
        )

        if not evidence.claims:
            raise ProductionError(
                "Scam research returned no usable claims."
            )

        print(
            "[STEP] Scam Short concept",
            flush=True,
        )

        short = generate_scam_short(
            ai,
            settings,
            run["topic"],
            evidence,
        )

        save(
            checkpoint_path,
            {
                "key": key,
                "research": (
                    evidence.model_dump()
                ),
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
        / "scam_short.json",
        short.model_dump(),
    )

    # -----------------------------------------------------
    # ONE STOCK BACKGROUND
    # -----------------------------------------------------

    background = choose_scam_background(
        settings,
        http,
        cache,
        short.background_search_query,
        minimum_duration=float(
            short.estimated_duration_seconds
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
        / "scam_background.json",
        stock_metadata,
    )

    # -----------------------------------------------------
    # RENDER
    # -----------------------------------------------------

    final = render_scam_short(
        settings,
        folder,
        short,
        background,
        music_path=None,
    )

    if not Path(
        final
    ).exists():
        raise ProductionError(
            "Scam renderer did not create final.mp4."
        )

    print(
        "[OK] Scam pipeline complete",
        flush=True,
    )

    return final