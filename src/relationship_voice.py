from .voice import Voice, normalize
from .utils import ProductionError, probe


def _spoken(text):
    """
    Prepare one text segment for natural TTS speech.
    """

    text = str(
        text
    ).strip()

    if not text:
        return ""

    if text[-1] not in ".!?":
        text += "."

    return text


def _fallback_timings(
    parts,
    duration,
):
    """
    Fallback timing based on text length.

    Normally ElevenLabs alignment is used instead.
    """

    weights = [
        max(
            1,
            len(
                normalize(
                    part
                )
            ),
        )
        for part in parts
    ]

    total = sum(
        weights
    )

    timings = []

    current = 0.0

    for index, weight in enumerate(
        weights
    ):
        if index == len(
            weights
        ) - 1:
            end = duration

        else:
            end = (
                current
                + (
                    duration
                    * weight
                    / total
                )
            )

        timings.append(
            {
                "start": current,
                "end": end,
            }
        )

        current = end

    return timings


def _alignment_timings(
    parts,
    alignment,
    duration,
):
    """
    Convert ElevenLabs character timestamps into
    timings for hook, individual points and CTA.
    """

    characters = alignment.get(
        "characters",
        [],
    )

    starts = alignment.get(
        "character_start_times_seconds",
        [],
    )

    ends = alignment.get(
        "character_end_times_seconds",
        [],
    )

    if not (
        characters
        and len(
            characters
        )
        == len(
            starts
        )
        == len(
            ends
        )
    ):
        return _fallback_timings(
            parts,
            duration,
        )

    normalized_text = ""
    normalized_to_alignment = []

    for index, character in enumerate(
        characters
    ):
        piece = normalize(
            character
        )

        for char in piece:
            normalized_text += char

            normalized_to_alignment.append(
                index
            )

    if not normalized_text:
        return _fallback_timings(
            parts,
            duration,
        )

    timings = []

    cursor = 0

    for part in parts:
        target = normalize(
            part
        )

        if not target:
            return _fallback_timings(
                parts,
                duration,
            )

        position = normalized_text.find(
            target,
            cursor,
        )

        if position < 0:
            return _fallback_timings(
                parts,
                duration,
            )

        end_position = (
            position
            + len(
                target
            )
            - 1
        )

        if (
            position
            >= len(
                normalized_to_alignment
            )
            or end_position
            >= len(
                normalized_to_alignment
            )
        ):
            return _fallback_timings(
                parts,
                duration,
            )

        first_character = (
            normalized_to_alignment[
                position
            ]
        )

        last_character = (
            normalized_to_alignment[
                end_position
            ]
        )

        start = float(
            starts[
                first_character
            ]
        )

        end = float(
            ends[
                last_character
            ]
        )

        timings.append(
            {
                "start": max(
                    0.0,
                    start,
                ),
                "end": min(
                    duration,
                    end,
                ),
            }
        )

        cursor = (
            end_position
            + 1
        )

    return timings


def generate_relationship_voice(
    settings,
    http,
    cache,
    budget,
    short,
):
    """
    Generate Liam narration for one Relationship Short.

    Spoken order:
    hook
    -> points
    -> optional CTA

    The final SUBSCRIBE animation is intentionally
    not spoken.
    """

    segments = [
        {
            "type": "hook",
            "text": short.hook.strip(),
        }
    ]

    for index, point in enumerate(
        short.points,
        start=1,
    ):
        segments.append(
            {
                "type": "point",
                "index": index,
                "text": point.strip(),
            }
        )

    if short.cta.strip():
        segments.append(
            {
                "type": "cta",
                "text": short.cta.strip(),
            }
        )

    spoken_parts = [
        _spoken(
            segment[
                "text"
            ]
        )
        for segment in segments
    ]

    spoken_text = " ".join(
        spoken_parts
    )

    if not spoken_text.strip():
        raise ProductionError(
            "Relationship narration is empty."
        )

    voice = Voice(
        settings,
        http,
        cache,
        budget,
    )

    preferred = settings.keys[
        "ELEVENLABS_VOICE_ID"
    ]

    fallback = settings.keys[
        "ELEVENLABS_FALLBACK_VOICE_ID"
    ]

    selected = list(
        dict.fromkeys(
            voice_id
            for voice_id in (
                preferred,
                fallback,
            )
            if voice_id
        )
    )

    if not selected:
        selected = voice.select()

    print(
        "[STEP] Relationship voice with ElevenLabs",
        flush=True,
    )

    audio_path, metadata = voice.generate(
        spoken_text,
        selected,
    )

    info = probe(
        audio_path
    )

    try:
        duration = float(
            info[
                "format"
            ][
                "duration"
            ]
        )

    except (
        KeyError,
        TypeError,
        ValueError,
    ):
        raise ProductionError(
            "Could not determine Relationship voice duration."
        ) from None

    if duration <= 0:
        raise ProductionError(
            "Relationship voice has invalid duration."
        )

    alignment = metadata.get(
        "alignment",
        {},
    )

    timings = _alignment_timings(
        spoken_parts,
        alignment,
        duration,
    )

    if len(
        timings
    ) != len(
        segments
    ):
        raise ProductionError(
            "Relationship voice timing count is invalid."
        )

    for segment, timing in zip(
        segments,
        timings,
    ):
        segment[
            "start"
        ] = timing[
            "start"
        ]

        segment[
            "end"
        ] = timing[
            "end"
        ]

    print(
        (
            "[OK] Relationship voice: "
            "%.2fs, %d timed segments"
        )
        % (
            duration,
            len(
                segments
            ),
        ),
        flush=True,
    )

    return {
        "audio_path": str(
            audio_path
        ),
        "duration": duration,
        "segments": segments,
        "voice_id": metadata.get(
            "voice_id",
            "",
        ),
        "text": spoken_text,
    }