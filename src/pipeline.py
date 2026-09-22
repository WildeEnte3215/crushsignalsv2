import datetime
import os
import shutil
from pathlib import Path

from .budget import Budget
from .http import Http
from .openai_client import OpenAI
from .gemini_client import Gemini
from .research import research, fact_check
from .script_generator import generate
from .schemas import Plan, Research
from .scene_planner import narration, timeline
from .voice import Voice
from .visual_ranker import Ranker
from .sfx import SFX
from .render import render
from .quality import check
from .utils import (
    Cache,
    ProductionError,
    atomic,
    digest,
    read,
    save,
    probe,
    valid_media,
)


def clients(settings, run_id):
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

    if settings.ai_provider == "gemini":
        ai = Gemini(
            settings,
            http,
            cache,
            budget,
        )

    elif settings.ai_provider == "openai":
        ai = OpenAI(
            settings,
            http,
            cache,
            budget,
        )

    else:
        raise ProductionError(
            "Unsupported AI provider: "
            + settings.ai_provider
        )

    return (
        http,
        cache,
        budget,
        ai,
    )


def produce(
    settings,
    run,
):
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
    ) = clients(
        settings,
        run["id"],
    )

    voice = Voice(
        settings,
        http,
        cache,
        budget,
    )

    # -----------------------------------------------------
    # ELEVENLABS SUBSCRIPTION CHECK
    # -----------------------------------------------------

    subscription = (
        voice.subscription()
    )

    if subscription.get(
        "tier"
    ) in (
        None,
        "free",
    ):
        raise ProductionError(
            "Commercial pipeline requires a paid "
            "ElevenLabs subscription. "
            "See API_SETUP.md."
        )

    save(
        folder
        / "license_metadata.json",
        {
            "elevenlabs_tier": (
                subscription.get(
                    "tier"
                )
            ),
            "checked_at": (
                datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat()
            ),
            "terms": (
                "https://elevenlabs.io/terms-of-use-eu"
            ),
        },
    )

    # -----------------------------------------------------
    # CONTENT CHECKPOINT KEY
    # -----------------------------------------------------

    key = digest(
        {
            "topic": run["topic"],
            "date": run["created"],
            "ai_provider": settings.ai_provider,
            "research": settings.prompt(
                "research"
            ),
            "content": settings.prompt(
                "content"
            ),
            "model": settings.video[
                "research_model"
            ],
            "words": settings.video[
                "target_words"
            ],
        }
    )

    stored = read(
        folder
        / "content_checkpoint.json",
        {},
    )

    # -----------------------------------------------------
    # RESEARCH + SCRIPT + FACT CHECK
    # -----------------------------------------------------

    if (
        stored.get(
            "key"
        )
        == key
    ):
        evidence = (
            Research.model_validate(
                stored[
                    "research"
                ]
            )
        )

        plan = (
            Plan.model_validate(
                stored[
                    "plan"
                ]
            )
        )

        print(
            "[CACHE] Researched and fact-checked plan",
            flush=True,
        )

    else:
        print(
            "[STEP] Research and script",
            flush=True,
        )

        evidence = research(
            ai,
            settings,
            run["topic"],
            run["created"],
        )

        plan = generate(
            ai,
            settings,
            run["topic"],
            evidence,
        )

        # -------------------------------------------------
        # ROBUST INITIAL FACT-CHECK + REVISION LOOP
        # -------------------------------------------------

        max_fact_attempts = 2
        fact_passed = False

        for fact_attempt in range(
            1,
            max_fact_attempts + 1,
        ):
            verdict = fact_check(
                ai,
                plan,
            )

            save(
                folder
                / (
                    "fact_check_%02d.json"
                    % fact_attempt
                ),
                verdict.model_dump(),
            )

            if (
                verdict.passed
                and not verdict.issues
            ):
                print(
                    "[OK] Script passed independent fact check",
                    flush=True,
                )

                fact_passed = True
                break

            print(
                (
                    "[RETRY] Script fact-check failed "
                    "(attempt %d/%d)"
                )
                % (
                    fact_attempt,
                    max_fact_attempts,
                ),
                flush=True,
            )

            if verdict.issues:
                for issue in verdict.issues:
                    print(
                        "        - " + issue,
                        flush=True,
                    )

            if (
                fact_attempt
                >= max_fact_attempts
            ):
                break

            issue_text = (
                "\n".join(
                    "- " + issue
                    for issue
                    in verdict.issues
                )
                if verdict.issues
                else (
                    "- The independent fact checker "
                    "did not approve the script."
                )
            )

            fact_feedback = (
                "The previous script failed an independent "
                "fact check.\n\n"
                "Fix EVERY issue below:\n"
                + issue_text
                + "\n\n"
                "STRICT REVISION RULES:\n"
                "- Use ONLY facts supported by the supplied research claims.\n"
                "- Remove unsupported causal explanations instead of guessing.\n"
                "- Preserve factual nuance where the evidence requires it.\n"
                "- Do not invent replacement facts.\n"
                "- Do not add new numbers unless they already exist in the research.\n"
                "- Keep every scene grounded in valid claim IDs.\n"
                "- Keep the script concise and suitable for a 30-50 second Short.\n"
                "- The hook may be rewritten if necessary for factual accuracy."
            )

            plan = generate(
                ai,
                settings,
                run["topic"],
                evidence,
                fact_feedback,
            )

        if not fact_passed:
            raise ProductionError(
                "Script still failed independent "
                "fact checking after %d attempts. "
                "See fact_check_*.json."
                % max_fact_attempts
            )

        save(
            folder
            / "content_checkpoint.json",
            {
                "key": key,
                "research": (
                    evidence.model_dump()
                ),
                "plan": (
                    plan.model_dump()
                ),
            },
        )

    # -----------------------------------------------------
    # VOICE SELECTION
    # -----------------------------------------------------

    selected_voices = (
        voice.select()
    )

    # -----------------------------------------------------
    # NARRATION + DURATION SELF-CORRECTION
    # -----------------------------------------------------

    max_duration_attempts = 4

    duration_feedback = ""

    timing = None
    text = None
    audio = None
    alignment = None

    for duration_attempt in range(
        1,
        max_duration_attempts + 1,
    ):

        # -------------------------------------------------
        # IF PREVIOUS VERSION WAS TOO SHORT / TOO LONG,
        # GENERATE A NEW PLAN AND FACT-CHECK IT AGAIN.
        # -------------------------------------------------

        if duration_feedback:
            revision_feedback = (
                duration_feedback
            )

            fact_passed = False

            for fact_attempt in range(
                1,
                3,
            ):
                print(
                    (
                        "[RETRY] Duration-aware "
                        "script revision "
                        "(attempt %d/2)"
                    )
                    % fact_attempt,
                    flush=True,
                )

                plan = generate(
                    ai,
                    settings,
                    run["topic"],
                    evidence,
                    revision_feedback,
                )

                verdict = fact_check(
                    ai,
                    plan,
                )

                save(
                    folder
                    / (
                        "fact_check_duration_"
                        "%02d_%02d.json"
                        % (
                            duration_attempt,
                            fact_attempt,
                        )
                    ),
                    verdict.model_dump(),
                )

                if (
                    verdict.passed
                    and not verdict.issues
                ):
                    fact_passed = True

                    print(
                        "[OK] Duration rewrite passed fact check",
                        flush=True,
                    )

                    break

                issue_text = (
                    "; ".join(
                        verdict.issues
                    )
                    if verdict.issues
                    else (
                        "fact checker did not "
                        "approve the rewrite"
                    )
                )

                print(
                    (
                        "[RETRY] Duration rewrite "
                        "had factual issues: %s"
                    )
                    % issue_text,
                    flush=True,
                )

                revision_feedback = (
                    duration_feedback
                    + "\n\n"
                    + (
                        "The previous rewrite failed "
                        "independent fact checking."
                    )
                    + "\n"
                    + (
                        "Fix these factual issues while "
                        "keeping the required duration:"
                    )
                    + "\n"
                    + (
                        "\n".join(
                            "- " + issue
                            for issue
                            in verdict.issues
                        )
                        if verdict.issues
                        else (
                            "- Rewrite conservatively "
                            "using only the supplied "
                            "supported research claims."
                        )
                    )
                    + "\n"
                    + (
                        "Do not invent new facts, "
                        "numbers or unsupported "
                        "causal explanations."
                    )
                )

            if not fact_passed:
                raise ProductionError(
                    "Could not produce a "
                    "duration-correct rewrite "
                    "that also passed independent "
                    "fact checking."
                )

        # -------------------------------------------------
        # GENERATE REAL TTS + ALIGNMENT
        # -------------------------------------------------

        print(
            "[STEP] Narration and exact alignment",
            flush=True,
        )

        text = narration(
            plan,
            settings.brand,
        )

        (
            audio,
            alignment,
        ) = voice.generate(
            text,
            selected_voices,
        )

        audio_duration = float(
            probe(
                audio
            )[
                "format"
            ][
                "duration"
            ]
        )

        timing = timeline(
            plan,
            settings.brand,
            settings.video,
            alignment[
                "alignment"
            ],
            audio_duration,
        )

        actual_duration = float(
            timing[
                "duration"
            ]
        )

        print(
            (
                "[INFO] Actual narration/video "
                "duration: %.2f seconds"
            )
            % actual_duration,
            flush=True,
        )

        # -------------------------------------------------
        # DURATION PASSES
        # -------------------------------------------------

        if (
            settings.video[
                "min_duration"
            ]
            <= actual_duration
            <= settings.video[
                "max_duration"
            ]
        ):
            print(
                "[OK] Duration within target range",
                flush=True,
            )

            break

        # -------------------------------------------------
        # DURATION TOO SHORT
        # -------------------------------------------------

        if (
            actual_duration
            < settings.video[
                "min_duration"
            ]
        ):
            direction = (
                "The narration is too short. "
                "Add useful supported explanatory "
                "detail using ONLY the supplied "
                "research claims. "
                "Do not add filler, repetition "
                "or unsupported trivia."
            )

        # -------------------------------------------------
        # DURATION TOO LONG
        # -------------------------------------------------

        else:
            direction = (
                "The narration is too long. "
                "Shorten sentences and remove "
                "non-essential context while "
                "preserving the mechanism, "
                "hook and payoff. "
                "Do not remove facts required "
                "for correctness."
            )

        duration_feedback = (
            (
                "The previous narrated version "
                "lasted %.2f seconds. "
            )
            + (
                "The required final range is "
                "%d-%d seconds. "
            )
            + (
                "Target approximately 38-42 "
                "seconds with the configured "
                "voice speed. "
            )
            + "%s "
            + (
                "Keep the hook concise. "
                "Keep every factual statement "
                "grounded in the supplied "
                "claim IDs."
            )
        ) % (
            actual_duration,
            settings.video[
                "min_duration"
            ],
            settings.video[
                "max_duration"
            ],
            direction,
        )

        print(
            (
                "[RETRY] Duration outside "
                "target range: %.2fs"
            )
            % actual_duration,
            flush=True,
        )

    else:
        raise ProductionError(
            (
                "Narration remained outside "
                "the %d-%d second target "
                "after %d duration attempts."
            )
            % (
                settings.video[
                    "min_duration"
                ],
                settings.video[
                    "max_duration"
                ],
                max_duration_attempts,
            )
        )

    # -----------------------------------------------------
    # SAVE FINAL CONTENT CHECKPOINT
    # -----------------------------------------------------

    save(
        folder
        / "content_checkpoint.json",
        {
            "key": key,
            "research": (
                evidence.model_dump()
            ),
            "plan": (
                plan.model_dump()
            ),
        },
    )

    # -----------------------------------------------------
    # SAVE SCRIPT / PLAN / SOURCES / TIMING
    # -----------------------------------------------------

    save(
        folder
        / "plan.json",
        plan.model_dump(),
    )

    save(
        folder
        / "sources.json",
        evidence.model_dump(),
    )

    save(
        folder
        / "timeline.json",
        timing,
    )

    atomic(
        folder
        / "script.txt",
        text,
    )

    (
        folder
        / "voice"
    ).mkdir(
        exist_ok=True
    )

    shutil.copy2(
        str(
            audio
        ),
        str(
            folder
            / "voice"
            / "narration.mp3"
        ),
    )

    save(
        folder
        / "voice"
        / "alignment.json",
        alignment,
    )

    # -----------------------------------------------------
    # VISUAL SELECTION
    # -----------------------------------------------------

    print(
        (
            "Stock footage provided by Pexels: "
            "https://www.pexels.com"
        ),
        flush=True,
    )

    ranker = Ranker(
        settings,
        http,
        cache,
        ai,
    )

    selections = {}

    for scene in plan.scenes:
        print(
            (
                "[STEP] Visual selection "
                + scene.id
            ),
            flush=True,
        )

        scene_folder = (
            folder
            / "clips"
            / scene.id
        )

        scene_key = digest(
            {
                "scene": (
                    scene.model_dump()
                ),
                "prompt": settings.prompt(
                    "vision"
                ),
                "model": settings.video[
                    "vision_model"
                ],
                "threshold": settings.video[
                    "min_visual_score"
                ],
            }
        )

        stored = read(
            scene_folder
            / "selection.json",
            {},
        )

        value = stored.get(
            "value"
        )

        usable = (
            value
            and (
                value[
                    "kind"
                ]
                == "diagram"
                or (
                    valid_media(
                        value.get(
                            "path",
                            "",
                        ),
                        "video",
                    )
                    and Path(
                        value[
                            "frame"
                        ]
                    ).is_file()
                )
            )
        )

        if (
            stored.get(
                "key"
            )
            == scene_key
            and usable
        ):
            selections[
                scene.id
            ] = value

            print(
                "[CACHE] Visual selection "
                + scene.id,
                flush=True,
            )

            continue

        value = ranker.select(
            scene,
            scene_folder,
        )

        # Keep run self-contained:
        # copy selected source out of shared cache.
        if (
            value[
                "kind"
            ]
            == "stock"
        ):
            selected_path = (
                scene_folder
                / "selected.mp4"
            )

            shutil.copy2(
                value[
                    "path"
                ],
                selected_path,
            )

            value[
                "path"
            ] = str(
                selected_path
            )

        save(
            scene_folder
            / "selection.json",
            {
                "key": scene_key,
                "value": value,
            },
        )

        selections[
            scene.id
        ] = value

    # -----------------------------------------------------
    # DIAGRAM LIMIT
    # -----------------------------------------------------

    diagrams = sum(
        selection[
            "kind"
        ]
        == "diagram"
        for selection
        in selections.values()
    )

    if (
        diagrams
        / len(
            selections
        )
        > settings.video[
            "max_diagram_fraction"
        ]
    ):
        raise ProductionError(
            (
                "Too much schematic fallback. "
                "Inspect scene candidates/queries "
                "before raising "
                "max_diagram_fraction."
            )
        )

    save(
        folder
        / "selections.json",
        selections,
    )

    # -----------------------------------------------------
    # ATTRIBUTION
    # -----------------------------------------------------

    credits = [
        selection[
            "candidate"
        ]
        for selection
        in selections.values()
        if selection[
            "kind"
        ]
        == "stock"
    ]

    save(
        folder
        / "attribution.json",
        credits,
    )

    # -----------------------------------------------------
    # DESCRIPTION / TITLE
    # -----------------------------------------------------

    description = (
        plan.description
        + "\n\nSources:\n"
        + "\n".join(
            source.url
            for source
            in evidence.sources
        )
    )

    description += (
        "\n\n"
        "Stock footage: Pexels - "
        "https://www.pexels.com\n"
    )

    description += "\n".join(
        (
            "%s / %s: %s"
            % (
                credit[
                    "provider"
                ],
                credit[
                    "author"
                ],
                credit[
                    "url"
                ],
            )
        )
        for credit
        in credits
    )

    atomic(
        folder
        / "description.txt",
        description,
    )

    atomic(
        folder
        / "title.txt",
        plan.title,
    )

    # -----------------------------------------------------
    # SOUND EFFECTS
    # -----------------------------------------------------

    cues = SFX(
        settings,
        http,
        cache,
        budget,
    ).schedule(
        plan,
        timing,
    )

    (
        folder
        / "sfx"
    ).mkdir(
        exist_ok=True
    )

    for i, cue in enumerate(
        cues
    ):
        dest = (
            folder
            / "sfx"
            / (
                "%02d%s"
                % (
                    i,
                    Path(
                        cue[
                            "path"
                        ]
                    ).suffix,
                )
            )
        )

        shutil.copy2(
            cue[
                "path"
            ],
            dest,
        )

        cue[
            "path"
        ] = str(
            dest
        )

    save(
        folder
        / "sfx"
        / "cues.json",
        cues,
    )

    # -----------------------------------------------------
    # RENDER
    # -----------------------------------------------------

    candidate = render(
        settings,
        plan,
        timing,
        selections,
        audio,
        cues,
        folder,
    )

    # -----------------------------------------------------
    # FINAL QUALITY GATE
    # -----------------------------------------------------

    check(
        settings,
        candidate,
        timing,
        folder,
        ai,
        plan,
    )

    # -----------------------------------------------------
    # PROMOTE TO FINAL
    # -----------------------------------------------------

    final = (
        folder
        / "final.mp4"
    )

    if candidate != final:
        os.replace(
            candidate,
            final,
        )

    # -----------------------------------------------------
    # COST REPORT
    # -----------------------------------------------------

    save(
        folder
        / "cost_estimates.json",
        budget.summary(),
    )

    return final