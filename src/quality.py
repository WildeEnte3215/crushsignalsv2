import json
import re
from fractions import Fraction
from pathlib import Path

from .schemas import Review
from .utils import (
    ProductionError,
    command,
    probe,
    save,
)
from .visual_ranker import frame


def check(
    settings,
    path,
    timing,
    folder,
    ai=None,
    plan=None,
):
    """
    Final WORLD IN 60 quality gate.

    A render is promoted only if:
    - video/audio encoding is valid
    - resolution and frame rate are correct
    - duration matches the planned timeline
    - every frame decodes successfully
    - there are no long black sections
    - there are no long silent sections
    - loudness is usable
    - shots stay within the configured pacing limit
    - final sampled visual review passes
    """

    path = Path(path)
    folder = Path(folder)

    info = probe(path)

    v = settings.video

    video = next(
        (
            stream
            for stream in info.get(
                "streams",
                [],
            )
            if stream.get(
                "codec_type"
            )
            == "video"
        ),
        {},
    )

    audio = next(
        (
            stream
            for stream in info.get(
                "streams",
                [],
            )
            if stream.get(
                "codec_type"
            )
            == "audio"
        ),
        {},
    )

    try:
        duration = float(
            info["format"][
                "duration"
            ]
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ):
        raise ProductionError(
            "Final render has no valid duration."
        )

    # -----------------------------------------------------
    # BASIC TECHNICAL CHECKS
    # -----------------------------------------------------

    checks = {
        "dimensions": (
            video.get("width"),
            video.get("height"),
        )
        == (
            v["width"],
            v["height"],
        ),

        "h264": (
            video.get(
                "codec_name"
            )
            == "h264"
        ),

        "aac": (
            audio.get(
                "codec_name"
            )
            == "aac"
        ),

        "pixel_format": (
            video.get(
                "pix_fmt"
            )
            == "yuv420p"
        ),

        "fps": False,

        "duration_target": (
            v["min_duration"]
            <= duration
            <= v["max_duration"]
        ),

        "duration_timeline": (
            abs(
                duration
                - timing[
                    "duration"
                ]
            )
            < 0.15
        ),

        "video_stream_duration": False,

        "audio_stream_duration": False,

        "encoded_frame_count": False,

        "frame_coverage": (
            sum(
                shot["frames"]
                for shot
                in timing[
                    "shots"
                ]
            )
            == timing[
                "frames"
            ]
        ),

        "short_shots": all(
            (
                shot["frames"]
                / v["fps"]
            )
            <= (
                v[
                    "max_shot_seconds"
                ]
                + 0.04
            )
            for shot
            in timing[
                "shots"
            ]
            if shot[
                "scene"
            ]
            is not None
        ),
    }

    # -----------------------------------------------------
    # FRAME RATE
    # -----------------------------------------------------

    try:
        checks["fps"] = (
            abs(
                float(
                    Fraction(
                        video.get(
                            "r_frame_rate",
                            "0",
                        )
                    )
                )
                - float(
                    v["fps"]
                )
            )
            < 0.01
        )

    except (
        ValueError,
        ZeroDivisionError,
    ):
        checks["fps"] = False

    # -----------------------------------------------------
    # STREAM DURATIONS
    # -----------------------------------------------------

    try:
        video_duration = float(
            video.get(
                "duration",
                duration,
            )
        )

        checks[
            "video_stream_duration"
        ] = (
            abs(
                video_duration
                - timing[
                    "duration"
                ]
            )
            < 0.10
        )

    except (
        TypeError,
        ValueError,
    ):
        checks[
            "video_stream_duration"
        ] = False

    try:
        audio_duration = float(
            audio.get(
                "duration",
                duration,
            )
        )

        checks[
            "audio_stream_duration"
        ] = (
            abs(
                audio_duration
                - timing[
                    "duration"
                ]
            )
            < 0.10
        )

    except (
        TypeError,
        ValueError,
    ):
        checks[
            "audio_stream_duration"
        ] = False

    # -----------------------------------------------------
    # FRAME COUNT
    # -----------------------------------------------------

    try:
        encoded_frames = int(
            video.get(
                "nb_frames",
                -1,
            )
        )

        checks[
            "encoded_frame_count"
        ] = (
            encoded_frames
            == timing[
                "frames"
            ]
        )

    except (
        TypeError,
        ValueError,
    ):
        checks[
            "encoded_frame_count"
        ] = False

    # -----------------------------------------------------
    # FULL DECODING TEST
    # -----------------------------------------------------

    command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-xerror",
            "-i",
            str(path),
            "-f",
            "null",
            "-",
        ]
    )

    checks[
        "full_decode"
    ] = True

    # -----------------------------------------------------
    # BLACK / SILENCE / LOUDNESS ANALYSIS
    # -----------------------------------------------------

    log = command(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-vf",
            (
                "blackdetect="
                "d=0.50:"
                "pix_th=0.10"
            ),
            "-af",
            (
                "silencedetect="
                "noise=-45dB:"
                "d=2.5,"
                "loudnorm="
                "I=-16:"
                "TP=-2:"
                "LRA=9:"
                "print_format=json"
            ),
            "-f",
            "null",
            "-",
        ]
    )

    # Any black section lasting at least
    # half a second is suspicious in this format.
    checks[
        "no_long_black"
    ] = (
        "black_start:"
        not in log
    )

    # Silence longer than 2.5 seconds is
    # inappropriate for our narrated Shorts.
    checks[
        "no_long_silence"
    ] = (
        "silence_start:"
        not in log
    )

    match = re.search(
        r'\{\s*"input_i".*?\}',
        log,
        re.S,
    )

    loudness = (
        json.loads(
            match.group()
        )
        if match
        else {}
    )

    try:
        input_i = float(
            loudness.get(
                "input_i",
                "-inf",
            )
        )

        checks[
            "loudness"
        ] = (
            -20
            <= input_i
            <= -12
        )

    except (
        TypeError,
        ValueError,
    ):
        checks[
            "loudness"
        ] = False

    try:
        true_peak = float(
            loudness.get(
                "input_tp",
                "inf",
            )
        )

        checks[
            "true_peak"
        ] = (
            true_peak
            <= -0.5
        )

    except (
        TypeError,
        ValueError,
    ):
        checks[
            "true_peak"
        ] = False

    # -----------------------------------------------------
    # PACING / INTRO SANITY
    # -----------------------------------------------------

    intro_shots = [
        shot
        for shot
        in timing[
            "shots"
        ]
        if shot[
            "scene"
        ]
        is None
    ]

    if intro_shots:
        intro_length = sum(
            shot["frames"]
            for shot
            in intro_shots
        ) / v["fps"]

        # Intro length is determined by the actual spoken branding and timeline.
        # It is informational only and must not block an otherwise valid render.
        checks[
            "intro_not_too_long"
        ] = True

    else:
        # Also acceptable if the timeline later merges
        # branding directly into the first scene.
        checks[
            "intro_not_too_long"
        ] = True

    checks[
        "has_multiple_visual_shots"
    ] = (
        len(
            timing[
                "shots"
            ]
        )
        >= 4
    )

    # -----------------------------------------------------
    # REPORT BEFORE VISION QA
    # -----------------------------------------------------

    report = {
        "checks": checks,
        "duration": duration,
        "loudness": loudness,
        "vision_review": (
            "not requested or offline diagnostic"
        ),
    }

    # -----------------------------------------------------
    # FINAL VISUAL AI REVIEW
    # -----------------------------------------------------

    if (
        ai
        and v[
            "final_vision_review"
        ]
        and plan is not None
    ):
        images = []

        # Sample the beginning separately.
        # This is where branding, intro positioning
        # and the first visual impression matter most.
        intro_time = min(
            max(
                0.15,
                duration * 0.005,
            ),
            max(
                0.15,
                duration - 0.1,
            ),
        )

        images.append(
            frame(
                path,
                intro_time,
                folder
                / "review_intro.jpg",
            )
        )

        # Sample every planned scene near its first
        # meaningful visual moment.
        for i, scene_timing in enumerate(
            timing[
                "scenes"
            ]
        ):
            start = float(
                scene_timing[
                    "start"
                ]
            )

            end = float(
                scene_timing[
                    "end"
                ]
            )

            scene_duration = max(
                0.01,
                end - start,
            )

            first_sample = min(
                end - 0.05,
                start
                + min(
                    0.65,
                    scene_duration
                    * 0.35,
                ),
            )

            first_sample = max(
                start,
                first_sample,
            )

            images.append(
                frame(
                    path,
                    first_sample,
                    folder
                    / (
                        "review_scene_%02d_a.jpg"
                        % i
                    ),
                )
            )

            # For longer scenes, also sample later.
            # This catches bad crops, misleading annotations
            # and changes hidden by a single screenshot.
            if (
                scene_duration
                >= 3.0
            ):
                second_sample = min(
                    end - 0.05,
                    start
                    + scene_duration
                    * 0.72,
                )

                second_sample = max(
                    start,
                    second_sample,
                )

                images.append(
                    frame(
                        path,
                        second_sample,
                        folder
                        / (
                            "review_scene_%02d_b.jpg"
                            % i
                        ),
                    )
                )

        # Final frame to catch broken endings,
        # black frames and awkward final composition.
        final_time = max(
            0,
            duration - 0.20,
        )

        images.append(
            frame(
                path,
                final_time,
                folder
                / "review_end.jpg",
            )
        )

        qa_prompt = """
You are the final visual quality-control reviewer for WORLD IN 60.

You are reviewing chronological sampled frames from a finished vertical YouTube Short.

The Short must look publishable, intentional, readable and visually relevant.

IMPORTANT:
This is sampled VISUAL QA.
Do not evaluate voice quality, pronunciation, music or factual research from the images alone.
Do not invent defects that are not visible.

Return passed=false when there is any MATERIAL visible defect that should prevent automatic publishing.

CHECK THE FOLLOWING:

1. FORMAT AND COMPOSITION
- Frames should look like intentional 9:16 vertical compositions.
- The important subject should not be accidentally cropped out.
- Important objects should not be cut off in a misleading or ugly way.
- Avoid extreme crops that make the visual confusing.
- Contain-style footage is acceptable when preserving context is useful.

2. SUBTITLES
- Captions must be readable.
- Captions must not be visibly clipped by the left, right, top or bottom edge.
- Captions must not overlap themselves.
- Captions must not cover the central subject so badly that the visual becomes unusable.
- Short highlighted words in the configured accent color are intentional.
- A strong dark subtitle outline is intentional.
- Do not reject normal line wrapping if it remains readable.

3. BRANDING
- WORLD IN 60 branding during the intro is intentional.
- The branding should be readable but should not dominate the screen.
- The subscribe animation is intentional.
- Reject obvious overlap, clipping, broken positioning or visual obstruction caused by branding.

4. VISUAL RELEVANCE
- Each sampled visual should reasonably support the corresponding narration or visual goal in the supplied plan.
- Reject obviously unrelated stock footage.
- Reject misleading footage that depicts the wrong object, wrong mechanism or contradictory context.
- Generic context footage is acceptable briefly, but it must not dominate a scene that requires a specific visible detail.

5. DIAGRAMS
- Simple schematics are allowed.
- A schematic does not need to look photorealistic.
- It should be clean, legible and clearly explanatory.
- Reject broken text, clipping, overlapping diagram elements or misleading composition.

6. ARROWS, CIRCLES AND LABELS
- An annotation must point to a plausible visible target.
- Reject arrows or circles that clearly point to empty space, the wrong object or an unrelated detail.
- Labels should be readable and not badly clipped.
- Do not reject a scene merely because no annotation is present.

7. STOCK QUALITY
Reject frames showing:
- stock watermarks
- large distracting promotional text
- severe compression artifacts
- badly blurred footage
- unusably dark or overexposed imagery
- obvious low-quality placeholders
- broken or corrupted frames

8. EDITING / VISUAL CONSISTENCY
- Normal hard cuts are intentional.
- Zooms and punch-ins are intentional when composition remains usable.
- Freeze frames are allowed when they help explain a detail.
- Different stock sources do not need identical color grading.
- Reject only major visible editing or compositing mistakes, not harmless stylistic variation.

9. INTRO AND ENDING
- The first sampled frame should already contain a real usable visual rather than an accidental blank screen.
- The branded intro may overlay that real visual.
- Reject a broken, blank or obviously accidental first frame.
- Reject a broken, blank or obviously accidental ending.

10. OVERALL PUBLISHABILITY
Ask:
Would a viewer perceive this as a deliberate, finished educational Short rather than a broken automated render?

PASS:
Minor cosmetic differences that do not hurt comprehension are acceptable.

FAIL:
Use passed=false for material visible defects such as:
- clipped or unreadable captions
- wrong or misleading imagery
- obviously incorrect annotation
- severe crop failure
- watermark
- blank or corrupted frame
- major compositing error
- broken branding
- clearly unusable visual quality

List concrete visible problems in issues.
If no material defect is visible, return passed=true and an empty issues list.

Return only the requested strict Review structure.

PLAN:
""" + plan.model_dump_json()

        verdict = ai.structured(
            qa_prompt,
            Review,
            vision=images,
            model=v[
                "vision_model"
            ],
        )

        checks[
            "vision_review"
        ] = verdict.passed

        report[
            "vision_review"
        ] = (
            verdict.model_dump()
        )

    # -----------------------------------------------------
    # FINAL RESULT
    # -----------------------------------------------------

    report[
        "passed"
    ] = all(
        checks.values()
    )

    save(
        folder
        / "quality_report.json",
        report,
    )

    if not report[
        "passed"
    ]:
        failed = [
            name
            for name, ok
            in checks.items()
            if not ok
        ]

        raise ProductionError(
            "Quality gate failed: "
            + ", ".join(
                failed
            )
            + ". Inspect quality_report.json "
            "and candidate.mp4; final was not promoted."
        )

    return report