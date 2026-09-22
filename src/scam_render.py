import json
import shutil
import subprocess
from pathlib import Path

from .utils import ProductionError, valid_media


WARNING_SYMBOL = "\u26A0"


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
    Keep model text from injecting ASS control codes.
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
    Simple deterministic wrapping for vertical video.
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


def _build_ass(
    short,
    duration,
    width,
    height,
    font_name,
):
    """
    Build the complete text timeline.
    """

    point_count = len(
        short.points
    )

    hook_only_seconds = 2.0

    cta_seconds = (
        1.8
        if short.cta
        else 0.0
    )

    points_end = (
        duration
        - cta_seconds
    )

    available_for_points = max(
        1.0,
        points_end
        - hook_only_seconds,
    )

    point_seconds = (
        available_for_points
        / point_count
    )

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Warning,{font},58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H003030D8,-1,0,0,0,100,100,0,0,3,0,0,8,90,90,145,1
Style: Hook,{font},68,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,0,8,90,90,330,1
Style: Point,{font},72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,0,5,100,100,0,1
Style: CTA,{font},52,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,2,100,100,260,1

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

    full_end = _ass_time(
        duration
    )

    warning_text = (
        "SCAM WARNING "
        + WARNING_SYMBOL
    )

    lines.append(
        (
            "Dialogue: 0,0:00:00.00,%s,"
            "Warning,,0,0,0,,"
            "{\\fad(120,120)}%s\n"
        )
        % (
            full_end,
            warning_text,
        )
    )

    hook_text = _wrap_text(
        short.hook.upper(),
        27,
    )

    lines.append(
        (
            "Dialogue: 0,0:00:00.00,%s,"
            "Hook,,0,0,0,,"
            "{\\fad(140,140)}%s\n"
        )
        % (
            full_end,
            hook_text,
        )
    )

    current_start = (
        hook_only_seconds
    )

    for index, point in enumerate(
        short.points,
        start=1,
    ):
        current_end = (
            points_end
            if index == point_count
            else (
                current_start
                + point_seconds
            )
        )

        number = (
            "%d/%d"
            % (
                index,
                point_count,
            )
        )

        point_text = (
            number
            + "\\N\\N"
            + _wrap_text(
                point,
                30,
            )
        )

        lines.append(
            (
                "Dialogue: 0,%s,%s,"
                "Point,,0,0,0,,"
                "{\\fad(120,120)}%s\n"
            )
            % (
                _ass_time(
                    current_start
                ),
                _ass_time(
                    current_end
                ),
                point_text,
            )
        )

        current_start = (
            current_end
        )

    if short.cta:
        cta_text = _wrap_text(
            short.cta,
            36,
        )

        lines.append(
            (
                "Dialogue: 0,%s,%s,"
                "CTA,,0,0,0,,"
                "{\\fad(120,120)}%s\n"
            )
            % (
                _ass_time(
                    points_end
                ),
                full_end,
                cta_text,
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
    Run FFmpeg and expose a useful error message.
    """

    result = subprocess.run(
        args,
        cwd=str(cwd),
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
            "Scam render failed: "
            + message[-4000:]
        )


def render_scam_short(
    settings,
    folder,
    short,
    background,
    music_path=None,
):
    """
    Render one text-only SCAM / SAFETY Short.

    One looping 9:16 background video.
    No voiceover.
    Optional background music.
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
        / "scam_render_work"
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

    if not valid_media(
        source,
        "video",
    ):
        raise ProductionError(
            "Scam background video is invalid."
        )

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

    point_count = len(
        short.points
    )

    minimum_duration = (
        2.0
        + (
            point_count
            * 2.0
        )
        + (
            1.8
            if short.cta
            else 0.0
        )
    )

    duration = max(
        float(
            short.estimated_duration_seconds
        ),
        minimum_duration,
    )

    duration = min(
        duration,
        16.0,
    )

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

    font_target = (
        fonts_dir
        / "font.ttf"
    )

    shutil.copyfile(
        font_source,
        font_target,
    )

    font_name = (
        settings.brand.get(
            "font_name",
            "DejaVu Sans",
        )
        if hasattr(
            settings,
            "brand",
        )
        else "DejaVu Sans"
    )

    ass = _build_ass(
        short,
        duration,
        width,
        height,
        font_name,
    )

    ass_path = (
        work
        / "scam_text.ass"
    )

    ass_path.write_text(
        ass,
        encoding="utf-8-sig",
    )

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

    else:
        args += [
            "-f",
            "lavfi",
            "-i",
            (
                "anullsrc="
                "channel_layout=stereo:"
                "sample_rate=48000"
            ),
        ]

    video_filter = (
        "[0:v]"
        "scale=%d:%d:"
        "force_original_aspect_ratio=increase,"
        "crop=%d:%d,"
        "setsar=1,"
        "eq=brightness=-0.08:"
        "saturation=0.88,"
        "drawbox="
        "x=0:y=0:"
        "w=iw:h=ih:"
        "color=black@0.24:"
        "t=fill,"
        "ass=filename=scam_text.ass:"
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

    if using_music:
        fade_out_start = max(
            0.0,
            duration
            - 0.4,
        )

        audio_filter = (
            "[1:a]"
            "aresample=48000,"
            "volume=0.12,"
            "atrim=0:%.3f,"
            "asetpts=PTS-STARTPTS,"
            "afade=t=in:"
            "st=0:d=0.25,"
            "afade=t=out:"
            "st=%.3f:d=0.4"
            "[a]"
            % (
                duration,
                fade_out_start,
            )
        )

    else:
        audio_filter = (
            "[1:a]"
            "atrim=0:%.3f,"
            "asetpts=PTS-STARTPTS"
            "[a]"
            % duration
        )

    args += [
        "-filter_complex",
        (
            video_filter
            + ";"
            + audio_filter
        ),
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-t",
        "%.3f"
        % duration,
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
        "[STEP] Rendering Scam Short",
        flush=True,
    )

    _run_ffmpeg(
        args,
        work,
    )

    if not valid_media(
        final,
        "video",
    ):
        raise ProductionError(
            "Rendered Scam Short is not a readable video."
        )

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
        "duration": (
            duration
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
        / "scam_metadata.json"
    ).write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "[OK] Scam Short rendered: "
        + str(
            final
        ),
        flush=True,
    )

    return final