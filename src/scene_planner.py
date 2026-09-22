import math
import re

from .voice import normalize, validate_alignment
from .utils import ProductionError


_SENTENCE_END = re.compile(r"""[.!?]["')\]]*$""")
_SOFT_END = re.compile(r"""[,;:]["')\]]*$""")


def narration(plan, brand):
    parts = [s.narration for s in plan.scenes]

    if brand["intro_enabled"] and brand["intro_spoken"]:
        parts.insert(0, brand["intro_text"])

    return " ".join(parts)


def _punctuation_score(text):
    text = text.strip()

    if _SENTENCE_END.search(text):
        return 1.0

    if _SOFT_END.search(text):
        return 0.65

    if text.endswith(("-", "–")):
        return 0.35

    return 0.0


def _candidate_cuts(local_words, fps, first, last):
    """
    Build cut candidates only BETWEEN spoken words.

    Each candidate contains:
    - frame: cut position between two words
    - pause: actual speech gap in seconds
    - punctuation: strength of the phrase boundary
    """
    candidates = []

    for i in range(len(local_words) - 1):
        left = local_words[i]
        right = local_words[i + 1]

        pause = max(
            0.0,
            float(right["start"]) - float(left["end"]),
        )

        # Cut in the middle of the available inter-word gap.
        # If there is no measurable gap, this still lands exactly
        # between the aligned end/start times rather than blindly
        # inside a spoken word.
        cut_time = (
            float(left["end"]) + float(right["start"])
        ) / 2.0

        frame = int(round(cut_time * fps))
        frame = max(first + 1, min(last - 1, frame))

        candidates.append(
            {
                "frame": frame,
                "pause": pause,
                "punctuation": _punctuation_score(
                    left["text"]
                ),
            }
        )

    # Multiple word boundaries can quantize to the same frame.
    # Keep the strongest version.
    merged = {}

    for candidate in candidates:
        frame = candidate["frame"]
        previous = merged.get(frame)

        if previous is None:
            merged[frame] = candidate
            continue

        old_strength = (
            previous["pause"] * 2.0
            + previous["punctuation"]
        )
        new_strength = (
            candidate["pause"] * 2.0
            + candidate["punctuation"]
        )

        if new_strength > old_strength:
            merged[frame] = candidate

    return sorted(
        merged.values(),
        key=lambda x: x["frame"],
    )


def _scene_boundaries(
    first,
    last,
    local_words,
    fps,
    max_shot_seconds,
):
    """
    Speech-aware shot splitting.

    max_shot_seconds is treated as the style ceiling.
    Within that ceiling we prefer:
    1. sentence / punctuation boundaries,
    2. real speech pauses,
    3. a natural target shot length.

    This avoids the old behaviour where every scene was divided
    mathematically into equally sized chunks regardless of speech.
    """
    total_frames = last - first

    if total_frames <= 0:
        raise ProductionError(
            "Scene has no positive frame duration."
        )

    max_frames = max(
        1,
        int(round(max_shot_seconds * fps)),
    )

    if total_frames <= max_frames:
        return [first, last]

    # We do not want every shot to hug the hard maximum.
    # At 4.0 s max this aims around 3.1 s, with a preferred
    # lower bound around 1.8 s.
    target_seconds = max(
        1.4,
        min(
            max_shot_seconds * 0.78,
            max_shot_seconds - 0.20,
        ),
    )

    min_seconds = max(
        1.0,
        min(
            1.8,
            max_shot_seconds * 0.48,
        ),
    )

    target_frames = max(
        1,
        int(round(target_seconds * fps)),
    )
    min_frames = max(
        1,
        int(round(min_seconds * fps)),
    )

    candidates = _candidate_cuts(
        local_words,
        fps,
        first,
        last,
    )

    boundaries = [first]
    cursor = first

    while last - cursor > max_frames:
        low = cursor + min_frames
        high = min(
            cursor + max_frames,
            last - 1,
        )
        target = min(
            cursor + target_frames,
            high,
        )

        allowed = [
            c
            for c in candidates
            if low <= c["frame"] <= high
        ]

        if allowed:
            def score(candidate):
                frame = candidate["frame"]

                proximity = 1.0 - min(
                    1.0,
                    abs(frame - target)
                    / max(1, max_frames),
                )

                pause_score = min(
                    1.0,
                    candidate["pause"] / 0.35,
                )

                value = (
                    candidate["punctuation"] * 3.0
                    + pause_score * 2.5
                    + proximity * 2.0
                )

                # Avoid leaving a tiny final fragment when another
                # nearby boundary produces a cleaner ending.
                tail = last - frame

                if tail < min_frames:
                    value -= 2.0

                return value

            cut = max(
                allowed,
                key=score,
            )["frame"]

        else:
            # No ideal boundary in the preferred window.
            # Still prefer an actual word boundary to a blind
            # time-based cut.
            fallback = [
                c
                for c in candidates
                if cursor < c["frame"] <= high
            ]

            if fallback:
                cut = min(
                    fallback,
                    key=lambda c: abs(
                        c["frame"] - target
                    ),
                )["frame"]
            else:
                # Extremely unusual case, e.g. a pathological
                # alignment with no usable word boundary.
                cut = high

        if cut <= cursor:
            raise ProductionError(
                "Speech-aware shot planner stalled."
            )

        boundaries.append(cut)
        cursor = cut

    boundaries.append(last)

    # Defensive validation.
    if any(
        b <= a
        for a, b
        in zip(boundaries, boundaries[1:])
    ):
        raise ProductionError(
            "Invalid speech-aware shot boundaries."
        )

    return boundaries


def timeline(
    plan,
    brand,
    video,
    alignment,
    audio_duration,
):
    text = narration(plan, brand)
    validate_alignment(alignment, text)

    chars = alignment["characters"]

    start_times = alignment[
        "character_start_times_seconds"
    ]
    end_times = alignment[
        "character_end_times_seconds"
    ]

    # Map non-whitespace normalized characters back to
    # original alignment indices.
    mapping = []

    for i, char in enumerate(chars):
        mapping.extend(
            [i] * len(normalize(char))
        )

    offset = 0
    words = []
    scenes = []
    scene_words = []

    has_intro = (
        brand["intro_enabled"]
        and brand["intro_spoken"]
    )

    if has_intro:
        offset = len(
            normalize(brand["intro_text"])
        )

    pad = (
        brand["intro_duration"]
        if (
            brand["intro_enabled"]
            and not brand["intro_spoken"]
        )
        else 0
    )

    total = audio_duration + pad
    fps = video["fps"]
    total_frames = int(
        math.ceil(total * fps)
    )

    for scene in plan.scenes:
        local_words = []

        for match in re.finditer(
            r"\S+",
            scene.narration,
        ):
            n = len(
                normalize(match.group())
            )

            if offset + n > len(mapping):
                raise ProductionError(
                    "Alignment ended before script."
                )

            a = mapping[offset]
            b = mapping[offset + n - 1]

            word = {
                "text": match.group(),
                "start": start_times[a] + pad,
                "end": end_times[b] + pad,
                "scene": scene.id,
            }

            local_words.append(word)
            words.append(word)
            offset += n

        if not local_words:
            raise ProductionError(
                "Empty scene narration"
            )

        scene_words.append(local_words)

        scenes.append(
            {
                "id": scene.id,
                "speech_start": local_words[0][
                    "start"
                ],
                "speech_end": local_words[-1][
                    "end"
                ],
            }
        )

    intro_end = (
        round(
            scenes[0]["speech_start"] * fps
        )
        / fps
        if brand["intro_enabled"]
        else 0
    )

    if (
        not has_intro
        and brand["intro_enabled"]
    ):
        intro_end = pad

    if (
        intro_end <= 0
        and brand["intro_enabled"]
    ):
        raise ProductionError(
            "Spoken intro has no positive duration."
        )

    boundaries = [
        round(intro_end * fps)
    ]

    boundaries += [
        round(
            scene["speech_start"] * fps
        )
        for scene
        in scenes[1:]
    ]

    boundaries.append(total_frames)

    shots = []

    if intro_end:
        shots.append(
            {
                "id": "intro",
                "scene": None,
                "start": 0,
                "frames": boundaries[0],
            }
        )

    for i, scene in enumerate(scenes):
        first = boundaries[i]
        last = boundaries[i + 1]

        scene.update(
            start=first / fps,
            end=last / fps,
        )

        shot_boundaries = _scene_boundaries(
            first=first,
            last=last,
            local_words=scene_words[i],
            fps=fps,
            max_shot_seconds=float(
                video["max_shot_seconds"]
            ),
        )

        for k, (a, b) in enumerate(
            zip(
                shot_boundaries,
                shot_boundaries[1:],
            )
        ):
            shots.append(
                {
                    "id": "%s_%d"
                    % (
                        scene["id"],
                        k,
                    ),
                    "scene": i,
                    "start": a / fps,
                    "frames": b - a,
                    "variant": k,
                }
            )

    if (
        any(
            shot["frames"] <= 0
            for shot in shots
        )
        or sum(
            shot["frames"]
            for shot in shots
        )
        != total_frames
    ):
        raise ProductionError(
            "Invalid frame coverage."
        )

    return {
        "words": words,
        "scenes": scenes,
        "shots": shots,
        "duration": total_frames / fps,
        "frames": total_frames,
        "intro_end": intro_end,
        "audio_pad": pad,
    }
