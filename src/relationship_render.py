import json
import re
import shutil
import subprocess
from pathlib import Path

from .utils import ProductionError, valid_media


SUBSCRIBE_DURATION = 1.25

WHITE = "&H00FFFFFF&"
YELLOW = "&H0000FFFF&"


HIGHLIGHT_PRIORITY = (
    "secretly",
    "crush",
    "likes",
    "like",
    "love",
    "misses",
    "miss",
    "texts",
    "texting",
    "text",
    "nervous",
    "remembers",
    "remember",
    "details",
    "reaction",
    "reactions",
    "conversation",
    "conversations",
    "attention",
    "smiles",
    "smile",
    "jealous",
    "wants",
    "waits",
    "notices",
    "notice",
    "friends",
    "different",
    "matters",
    "matter",
    "always",
    "never",
    "first",
    "around",
    "eye",
    "eyes",
    "look",
    "looks",
    "laugh",
    "laughs",
    "messages",
    "message",
    "reply",
    "replies",
    "close",
)


STOPWORDS = {
    "about",
    "after",
    "again",
    "around",
    "because",
    "before",
    "being",
    "could",
    "does",
    "doing",
    "from",
    "have",
    "having",
    "into",
    "just",
    "little",
    "more",
    "really",
    "someone",
    "something",
    "their",
    "them",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "very",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "your",
}


def _ass_time(seconds):
    """
    Convert seconds to ASS timestamp:
    H:MM:SS.CS
    """

    seconds = max(
        0.0,
        float(seconds),
    )

    centiseconds = int(
        round(
            seconds * 100
        )
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

    return (
        "%d:%02d:%02d.%02d"
        % (
            hours,
            minutes,
            secs,
            cs,
        )
    )


def _safe_text(text):
    """
    Prevent generated text from injecting ASS formatting.
    """

    return (
        str(text)
        .replace("\\", "/")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )


def _wrap_text(
    text,
    max_chars,
):
    """
    Deterministically wrap text for vertical video.
    """

    words = (
        _safe_text(text)
        .split()
    )

    if not words:
        return ""

    lines = []
    current = ""

    for word in words:
        candidate = (
            word
            if not current
            else current + " " + word
        )

        if (
            len(candidate)
            <= max_chars
        ):
            current = candidate

        else:
            if current:
                lines.append(
                    current
                )

            current = word

    if current:
        lines.append(
            current
        )

    return "\\N".join(
        lines
    )


def _highlight_candidates(
    text,
    maximum=2,
):
    """
    Pick 1-2 visually useful words without another AI call.

    Priority relationship words are preferred.
    If none exist, fall back to meaningful longer words.
    """

    raw_words = re.findall(
        r"[A-Za-z']+",
        str(text),
    )

    lower_words = [
        word.lower()
        for word in raw_words
    ]

    chosen = []

    # -----------------------------------------------------
    # PRIORITY WORDS
    # -----------------------------------------------------

    for priority in HIGHLIGHT_PRIORITY:
        if (
            priority in lower_words
            and priority not in chosen
        ):
            chosen.append(
                priority
            )

        if len(chosen) >= maximum:
            return chosen

    # -----------------------------------------------------
    # FALLBACK: LONG MEANINGFUL WORDS
    # -----------------------------------------------------

    fallback = sorted(
        {
            word.lower()
            for word in raw_words
            if (
                len(word) >= 6
                and word.lower()
                not in STOPWORDS
            )
        },
        key=lambda word: (
            -len(word),
            word,
        ),
    )

    for word in fallback:
        if word not in chosen:
            chosen.append(
                word
            )

        if len(chosen) >= maximum:
            break

    return chosen


def _highlight_wrapped(
    text,
    max_chars,
    maximum=2,
):
    """
    Wrap text first, then color selected words yellow.
    """

    wrapped = _wrap_text(
        text,
        max_chars,
    )

    chosen = _highlight_candidates(
        text,
        maximum=maximum,
    )

    for word in chosen:
        pattern = re.compile(
            r"\b"
            + re.escape(
                word
            )
            + r"\b",
            flags=re.IGNORECASE,
        )

        wrapped = pattern.sub(
            lambda match: (
                "{\\c"
                + YELLOW
                + "}"
                + match.group(0)
                + "{\\c"
                + WHITE
                + "}"
            ),
            wrapped,
            count=1,
        )

    return wrapped


def _build_ass(
    short,
    voice_info,
    total_duration,
    width,
    height,
    font_name,
):
    """
    Build all text events directly from ElevenLabs timing.
    """

    voice_duration = float(
        voice_info[
            "duration"
        ]
    )

    segments = voice_info[
        "segments"
    ]

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Category,{font},58,&H00101010,&H00101010,&H0000FFFF,&H0000FFFF,-1,0,0,0,100,100,1,0,3,14,0,8,120,120,150,1
Style: Hook,{font},68,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,0,5,100,100,0,1
Style: Point,{font},70,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,0,5,110,110,0,1
Style: CTA,{font},52,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,5,110,110,0,1
Style: Subscribe,{font},68,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00202020,-1,0,0,0,100,100,1,0,3,0,0,5,90,90,0,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
""".format(
        width=width,
        height=height,
        font=font_name,
    )

    lines = [
        header
    ]

    # -----------------------------------------------------
    # CATEGORY BADGE
    # -----------------------------------------------------

    category_end = _ass_time(
        voice_duration
    )

    category = (
        short.category_label
        .strip()
        .upper()
    )

    lines.append(
        (
            "Dialogue: 2,0:00:00.00,%s,"
            "Category,,0,0,0,,"
            "{\\fad(120,120)}%s\n"
        )
        % (
            category_end,
            category,
        )
    )

    # -----------------------------------------------------
    # HOOK / POINTS / CTA
    # -----------------------------------------------------

    point_total = len(
        short.points
    )

    for segment in segments:
        start = float(
            segment[
                "start"
            ]
        )

        end = float(
            segment[
                "end"
            ]
        )

        if end <= start:
            continue

        segment_type = segment[
            "type"
        ]

        # -------------------------------------------------
        # HOOK
        # -------------------------------------------------

        if segment_type == "hook":
            text = _highlight_wrapped(
                short.hook.upper(),
                27,
                maximum=2,
            )

            style = "Hook"

        # -------------------------------------------------
        # POINT
        # -------------------------------------------------

        elif segment_type == "point":
            index = int(
                segment[
                    "index"
                ]
            )

            number = (
                "{\\c"
                + YELLOW
                + "}"
                + "%d/%d"
                % (
                    index,
                    point_total,
                )
                + "{\\c"
                + WHITE
                + "}"
            )

            point_text = _highlight_wrapped(
                segment[
                    "text"
                ],
                30,
                maximum=2,
            )

            text = (
                number
                + "\\N\\N"
                + point_text
            )

            style = "Point"

        # -------------------------------------------------
        # CTA
        # -------------------------------------------------

        elif segment_type == "cta":
            text = _highlight_wrapped(
                segment[
                    "text"
                ],
                36,
                maximum=1,
            )

            style = "CTA"

        else:
            continue

        lines.append(
            (
                "Dialogue: 1,%s,%s,"
                "%s,,0,0,0,,"
                "{\\fad(90,110)}%s\n"
            )
            % (
                _ass_time(
                    start
                ),
                _ass_time(
                    end
                ),
                style,
                text,
            )
        )

    # -----------------------------------------------------
    # SUBSCRIBE FLY-IN
    # -----------------------------------------------------

    subscribe_start = (
        voice_duration
        + 0.05
    )

    subscribe_end = (
        total_duration
    )

    center_x = (
        width
        // 2
    )

    center_y = int(
        height
        * 0.54
    )

    start_x = (
        width
        + 500
    )

    fly_ms = 280

    subscribe_override = (
        "{"
        "\\move(%d,%d,%d,%d,0,%d)"
        "\\fad(80,180)"
        "\\bord0"
        "}"
        % (
            start_x,
            center_y,
            center_x,
            center_y,
            fly_ms,
        )
    )

    lines.append(
        (
            "Dialogue: 3,%s,%s,"
            "Subscribe,,0,0,0,,"
            "%sSUBSCRIBE FOR MORE\n"
        )
        % (
            _ass_time(
                subscribe_start
            ),
            _ass_time(
                subscribe_end
            ),
            subscribe_override,
        )
    )

    return "".join(
        lines
    )


def _run_ffmpeg(
    args,
    cwd,
):
    """
    Run FFmpeg and expose useful errors.
    """

    result = subprocess.run(
        args,
        cwd=str(
            cwd
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        message = (
            result.stderr.strip()
            or "Unknown FFmpeg error."
        )

        raise ProductionError(
            "Relationship render failed: "
            + message[-4000:]
        )


def render_relationship_short(
    settings,
    folder,
    short,
    background,
    voice_info,
    music_path=None,
):
    """
    Render one Relationship / Crush Short.

    Video:
    - one looping aesthetic background
    - category badge
    - ElevenLabs-synced text
    - yellow keyword highlights
    - subscribe fly-in

    Audio:
    - ElevenLabs voice
    - optional background music
    """

    folder = Path(
        folder
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    work = (
        folder
        / "relationship_render_work"
    )

    work.mkdir(
        parents=True,
        exist_ok=True,
    )

    source = Path(
        background[
            "local_path"
        ]
    )

    voice_path = Path(
        voice_info[
            "audio_path"
        ]
    )

    # -----------------------------------------------------
    # VALIDATE INPUTS
    # -----------------------------------------------------

    if not valid_media(
        source,
        "video",
    ):
        raise ProductionError(
            "Relationship background video is invalid."
        )

    if not valid_media(
        voice_path,
        "audio",
    ):
        raise ProductionError(
            "Relationship voice audio is invalid."
        )

    voice_duration = float(
        voice_info[
            "duration"
        ]
    )

    if voice_duration <= 0:
        raise ProductionError(
            "Relationship voice duration is invalid."
        )

    total_duration = (
        voice_duration
        + SUBSCRIBE_DURATION
    )

    # -----------------------------------------------------
    # VIDEO SETTINGS
    # -----------------------------------------------------

    v = settings.video

    width = int(
        v.get(
            "width",
            1080,
        )
    )

    height = int(
        v.get(
            "height",
            1920,
        )
    )

    fps = int(
        v.get(
            "fps",
            30,
        )
    )

    # -----------------------------------------------------
    # FONT
    # -----------------------------------------------------

    font_source = Path(
        settings.font
    )

    if not font_source.exists():
        raise ProductionError(
            "Configured font does not exist: "
            + str(
                font_source
            )
        )

    fonts_dir = (
        work
        / "fonts"
    )

    fonts_dir.mkdir(
        exist_ok=True,
    )

    shutil.copyfile(
        font_source,
        fonts_dir / "font.ttf",
    )

    font_name = settings.brand.get(
        "font_name",
        "DejaVu Sans",
    )

    # -----------------------------------------------------
    # TEXT TIMELINE
    # -----------------------------------------------------

    ass = _build_ass(
        short,
        voice_info,
        total_duration,
        width,
        height,
        font_name,
    )

    ass_path = (
        work
        / "relationship_text.ass"
    )

    ass_path.write_text(
        ass,
        encoding="utf-8-sig",
    )

    # -----------------------------------------------------
    # OUTPUT
    # -----------------------------------------------------

    final = (
        folder
        / "final.mp4"
    )

    args = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(
            source
        ),
        "-i",
        str(
            voice_path
        ),
    ]

    using_music = (
        music_path is not None
        and Path(
            music_path
        ).exists()
    )

    if using_music:
        args += [
            "-stream_loop",
            "-1",
            "-i",
            str(
                music_path
            ),
        ]

    # -----------------------------------------------------
    # VIDEO FILTER
    # -----------------------------------------------------

    video_filter = (
        "[0:v]"
        "scale=%d:%d:"
        "force_original_aspect_ratio=increase,"
        "crop=%d:%d,"
        "setsar=1,"
        "eq=brightness=-0.05:"
        "saturation=0.92,"
        "drawbox="
        "x=0:y=0:"
        "w=iw:h=ih:"
        "color=black@0.18:"
        "t=fill,"
        "ass=filename=relationship_text.ass:"
        "fontsdir=fonts,"
        "scale=in_range=auto:"
        "out_range=tv,"
        "format=yuv420p,"
        "setparams=range=tv"
        "[v]"
        % (
            width,
            height,
            width,
            height,
        )
    )

    # -----------------------------------------------------
    # VOICE
    # -----------------------------------------------------

    filters = [
        video_filter,
        (
            "[1:a]"
            "loudnorm="
            "I=-16:"
            "TP=-2:"
            "LRA=9,"
            "aresample=48000,"
            "apad"
            "[voice]"
        ),
    ]

    # -----------------------------------------------------
    # OPTIONAL MUSIC
    # -----------------------------------------------------

    if using_music:
        fade_out_start = max(
            0.0,
            total_duration
            - 0.4,
        )

        filters.append(
            (
                "[2:a]"
                "aresample=48000,"
                "volume=0.10,"
                "atrim=0:%.3f,"
                "asetpts=PTS-STARTPTS,"
                "afade=t=in:"
                "st=0:d=0.25,"
                "afade=t=out:"
                "st=%.3f:d=0.4"
                "[music]"
            )
            % (
                total_duration,
                fade_out_start,
            )
        )

        filters.append(
            (
                "[voice][music]"
                "amix="
                "inputs=2:"
                "duration=first:"
                "normalize=0,"
                "alimiter="
                "limit=0.891:"
                "level=false:"
                "latency=1"
                "[a]"
            )
        )

    else:
        filters.append(
            (
                "[voice]"
                "atrim=0:%.3f,"
                "asetpts=PTS-STARTPTS"
                "[a]"
            )
            % total_duration
        )

    # -----------------------------------------------------
    # FFMPEG EXPORT
    # -----------------------------------------------------

    args += [
        "-filter_complex",
        ";".join(
            filters
        ),
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-t",
        "%.3f"
        % total_duration,
        "-r",
        str(
            fps
        ),
        "-c:v",
        "libx264",
        "-preset",
        str(
            v.get(
                "preset",
                "fast",
            )
        ),
        "-crf",
        str(
            v.get(
                "crf",
                20,
            )
        ),
        "-threads",
        str(
            v.get(
                "threads",
                2,
            )
        ),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(
            final
        ),
    ]

    print(
        "[STEP] Rendering Relationship Short",
        flush=True,
    )

    _run_ffmpeg(
        args,
        work,
    )

    # -----------------------------------------------------
    # VALIDATE OUTPUT
    # -----------------------------------------------------

    if not valid_media(
        final,
        "video",
    ):
        raise ProductionError(
            "Rendered Relationship Short is invalid."
        )

    # -----------------------------------------------------
    # METADATA
    # -----------------------------------------------------

    metadata = {
        "youtube_title": (
            short.youtube_title
        ),
        "category_label": (
            short.category_label
        ),
        "hook": (
            short.hook
        ),
        "points": list(
            short.points
        ),
        "cta": (
            short.cta
        ),
        "background_search_query": (
            short.background_search_query
        ),
        "voice_duration": (
            voice_duration
        ),
        "subscribe_duration": (
            SUBSCRIBE_DURATION
        ),
        "duration": (
            total_duration
        ),
        "voice_id": (
            voice_info.get(
                "voice_id",
                ""
            )
        ),
        "background": {
            "provider": (
                background.get(
                    "provider"
                )
            ),
            "id": (
                background.get(
                    "id"
                )
            ),
            "url": (
                background.get(
                    "url"
                )
            ),
            "author": (
                background.get(
                    "author"
                )
            ),
            "license": (
                background.get(
                    "license"
                )
            ),
        },
        "music": (
            str(
                music_path
            )
            if using_music
            else None
        ),
    }

    (
        folder
        / "relationship_metadata.json"
    ).write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "[OK] Relationship Short rendered: "
        + str(
            final
        ),
        flush=True,
    )

    return final