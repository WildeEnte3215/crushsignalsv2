"""
ASS subtitle generation for WORLD IN 60.

Features:
- Mobile-first large captions
- Configurable words per chunk
- Current spoken word highlighted
- Centered placement
- Strong black outline
- No drop shadow
- Uses ElevenLabs word timestamps
"""


def safe(text):
    """
    Make plain text safe for ASS subtitles.

    Prevents accidental ASS tags from appearing in generated text.
    """
    if text is None:
        return ""

    text = str(text)

    text = text.replace("\\", "/")
    text = text.replace("{", "(")
    text = text.replace("}", ")")
    text = text.replace("\r\n", "\\N")
    text = text.replace("\n", "\\N")
    text = text.replace("\r", "\\N")

    return text


def ass_time(seconds):
    """
    Convert seconds to ASS timestamp format:
    H:MM:SS.cc
    """
    seconds = max(
        0.0,
        float(seconds),
    )

    centiseconds = round(
        seconds * 100
    )

    hours = (
        centiseconds
        // 360000
    )

    centiseconds %= 360000

    minutes = (
        centiseconds
        // 6000
    )

    centiseconds %= 6000

    secs = (
        centiseconds
        // 100
    )

    cs = (
        centiseconds
        % 100
    )

    return "%d:%02d:%02d.%02d" % (
        hours,
        minutes,
        secs,
        cs,
    )


def event(
    start,
    end,
    text,
    layer=0,
    style="Default",
):
    """
    Create one ASS dialogue event.
    """
    start = max(
        0.0,
        float(start),
    )

    end = max(
        start + 0.01,
        float(end),
    )

    return (
        "Dialogue: %d,%s,%s,%s,,0,0,0,,%s"
        % (
            int(layer),
            ass_time(start),
            ass_time(end),
            style,
            text,
        )
    )


def hex_to_ass(hex_color):
    """
    Convert standard RGB hex color to ASS BGR format.

    Example:
        #6FF3CC -> &H00CCF36F&
    """
    value = str(
        hex_color
    ).strip()

    if value.startswith("#"):
        value = value[1:]

    if len(value) != 6:
        value = "FFFFFF"

    try:
        r = value[0:2]
        g = value[2:4]
        b = value[4:6]

        int(
            r + g + b,
            16,
        )

    except ValueError:
        return "&H00FFFFFF&"

    return (
        "&H00"
        + b.upper()
        + g.upper()
        + r.upper()
        + "&"
    )


def header(settings):
    """
    Build ASS file header and default WORLD IN 60 caption style.
    """
    video = settings.video
    brand = settings.brand

    width = int(
        video["width"]
    )

    height = int(
        video["height"]
    )

    subtitles = video.get(
        "subtitles",
        {},
    )

    font_size = int(
        subtitles.get(
            "font_size",
            76,
        )
    )

    font_name = brand.get(
        "font_name",
        "DejaVu Sans",
    )

    primary = hex_to_ass(
        brand.get(
            "text_color",
            "#FFFFFF",
        )
    )

    secondary = hex_to_ass(
        brand.get(
            "accent",
            "#6FF3CC",
        )
    )

    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: %d\n"
        "PlayResY: %d\n"
        "ScaledBorderAndShadow: yes\n"
        "WrapStyle: 2\n"
        "YCbCr Matrix: TV.709\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: "
        "Name,"
        "Fontname,"
        "Fontsize,"
        "PrimaryColour,"
        "SecondaryColour,"
        "OutlineColour,"
        "BackColour,"
        "Bold,"
        "Italic,"
        "Underline,"
        "StrikeOut,"
        "ScaleX,"
        "ScaleY,"
        "Spacing,"
        "Angle,"
        "BorderStyle,"
        "Outline,"
        "Shadow,"
        "Alignment,"
        "MarginL,"
        "MarginR,"
        "MarginV,"
        "Encoding\n"
        "Style: "
        "Default,"
        "%s,"
        "%d,"
        "%s,"
        "%s,"
        "&H00000000,"
        "&H00000000,"
        "-1,"
        "0,"
        "0,"
        "0,"
        "100,"
        "100,"
        "0,"
        "0,"
        "1,"
        "5,"
        "0,"
        "5,"
        "70,"
        "70,"
        "0,"
        "1\n"
        "\n"
        "[Events]\n"
        "Format: "
        "Layer,"
        "Start,"
        "End,"
        "Style,"
        "Name,"
        "MarginL,"
        "MarginR,"
        "MarginV,"
        "Effect,"
        "Text\n"
        % (
            width,
            height,
            font_name,
            font_size,
            primary,
            secondary,
        )
    )


def _get_value(
    item,
    names,
    default=None,
):
    """
    Read timestamp data from either dicts or objects.
    """
    for name in names:
        if isinstance(
            item,
            dict,
        ):
            if name in item:
                return item[name]

        else:
            if hasattr(
                item,
                name,
            ):
                return getattr(
                    item,
                    name,
                )

    return default


def _word_text(word):
    value = _get_value(
        word,
        (
            "word",
            "text",
            "value",
        ),
        "",
    )

    return str(
        value
    ).strip()


def _word_start(word):
    value = _get_value(
        word,
        (
            "start",
            "start_time",
            "start_seconds",
        ),
        0.0,
    )

    return float(
        value
    )


def _word_end(word):
    start = _word_start(
        word
    )

    value = _get_value(
        word,
        (
            "end",
            "end_time",
            "end_seconds",
        ),
        start + 0.15,
    )

    return max(
        start + 0.01,
        float(value),
    )


def _caption_text(
    chunk,
    active_index,
    highlight_color,
):
    """
    Build one caption line and highlight only
    the currently spoken word.
    """
    pieces = []

    for index, word in enumerate(
        chunk
    ):
        text = safe(
            _word_text(
                word
            )
        )

        if not text:
            continue

        if (
            index
            == active_index
        ):
            pieces.append(
                (
                    "{\\c%s}"
                    "%s"
                    "{\\c&H00FFFFFF&}"
                )
                % (
                    highlight_color,
                    text,
                )
            )

        else:
            pieces.append(
                text
            )

    return " ".join(
        pieces
    )


def subtitle_events(
    settings,
    words,
):
    """
    Generate word-synchronised ASS captions.

    Example with words_per_chunk = 3:

        DID YOU KNOW
        YOU KNOW THE
        KNOW THE TINY

    A chunk itself stays fixed while the currently
    spoken word changes colour.
    """
    if not words:
        return []

    video = settings.video

    subtitles = video.get(
        "subtitles",
        {},
    )

    words_per_chunk = max(
        1,
        int(
            subtitles.get(
                "words_per_chunk",
                3,
            )
        ),
    )

    x_ratio = float(
        subtitles.get(
            "x",
            0.50,
        )
    )

    y_ratio = float(
        subtitles.get(
            "y",
            0.70,
        )
    )

    highlight_enabled = bool(
        subtitles.get(
            "highlight",
            True,
        )
    )

    width = int(
        video["width"]
    )

    height = int(
        video["height"]
    )

    x = round(
        width
        * x_ratio
    )

    y = round(
        height
        * y_ratio
    )

    accent = hex_to_ass(
        settings.brand.get(
            "accent",
            "#6FF3CC",
        )
    )

    cleaned = []

    for word in words:
        text = _word_text(
            word
        )

        if not text:
            continue

        start = _word_start(
            word
        )

        end = _word_end(
            word
        )

        cleaned.append(
            {
                "word": text,
                "start": start,
                "end": end,
            }
        )

    if not cleaned:
        return []

    events = []

    # Fixed groups of N words.
    # This avoids captions jumping around wildly.
    for chunk_start in range(
        0,
        len(cleaned),
        words_per_chunk,
    ):
        chunk = cleaned[
            chunk_start:
            chunk_start
            + words_per_chunk
        ]

        if not chunk:
            continue

        for local_index, word in enumerate(
            chunk
        ):
            start = word[
                "start"
            ]

            if (
                local_index
                + 1
                < len(chunk)
            ):
                end = max(
                    word["end"],
                    chunk[
                        local_index
                        + 1
                    ][
                        "start"
                    ],
                )

            else:
                end = word[
                    "end"
                ]

            if (
                end
                <= start
            ):
                end = (
                    start
                    + 0.05
                )

            if highlight_enabled:
                text = _caption_text(
                    chunk,
                    local_index,
                    accent,
                )

            else:
                text = " ".join(
                    safe(
                        item[
                            "word"
                        ]
                    )
                    for item in chunk
                )

            tags = (
                "{"
                "\\an5"
                "\\pos(%d,%d)"
                "}"
                % (
                    x,
                    y,
                )
            )

            events.append(
                event(
                    start,
                    end,
                    tags + text,
                    layer=10,
                )
            )

    return events