from pathlib import Path

from . import branding, overlays
from .subtitles import (
    header,
    subtitle_events,
)
from .utils import (
    atomic,
    command,
    digest,
    file_hash,
    read,
    save,
    valid_media,
    probe,
    ProductionError,
)


def crop_filter(
    selection,
    width,
    height,
):
    a = selection.get(
        "assessment",
        {},
    )

    if (
        a.get("crop")
        == "contain"
    ):
        # Keep explanatory context.
        # A blurred duplicate fills
        # the vertical background.
        return (
            "split[fg][bg];"
            "[bg]"
            "scale=%d:%d:"
            "force_original_aspect_ratio=increase,"
            "crop=%d:%d,"
            "boxblur=20:2[blur];"
            "[fg]"
            "scale=%d:%d:"
            "force_original_aspect_ratio=decrease"
            "[small];"
            "[blur][small]"
            "overlay=(W-w)/2:(H-h)/2"
            % (
                width,
                height,
                width,
                height,
                width,
                height,
            )
        )

    x = a.get(
        "focus_x",
        0.5,
    )

    y = a.get(
        "focus_y",
        0.5,
    )

    return (
        "scale=%d:%d:"
        "force_original_aspect_ratio=increase,"
        "crop=%d:%d:"
        "x='max(0,min(iw-ow,"
        "iw*%.6f-ow/2))':"
        "y='max(0,min(ih-oh,"
        "ih*%.6f-oh/2))'"
        % (
            width,
            height,
            width,
            height,
            x,
            y,
        )
    )


def valid_shot(
    path,
    count,
    fps,
):
    if not valid_media(
        path,
        "video",
    ):
        return False

    stream = next(
        s
        for s in probe(
            path
        )["streams"]
        if s["codec_type"]
        == "video"
    )

    return (
        int(
            stream.get(
                "nb_frames",
                -1,
            )
        )
        == count
        and abs(
            float(
                stream.get(
                    "duration",
                    0,
                )
            )
            - count / fps
        )
        < 0.05
    )


def render(
    settings,
    plan,
    timing,
    selections,
    audio,
    cues,
    folder,
):
    v = settings.video

    w = v["width"]
    h = v["height"]
    fps = v["fps"]

    work = (
        folder
        / "render"
    )

    work.mkdir(
        parents=True,
        exist_ok=True,
    )

    # -----------------------------------------------------
    # SUBTITLES + BRANDING + OVERLAYS
    # -----------------------------------------------------

    ass = (
        header(settings)
        + "\n".join(
            subtitle_events(
                settings,
                timing["words"],
            )
            + overlays.intro_brand_events(
                settings,
                timing,
            )
            + overlays.subscribe_events(
                settings,
                timing["duration"],
            )
            + overlays.scene_events(
                settings,
                plan,
                timing,
                selections,
            )
        )
        + "\n"
    )

    atomic(
        folder
        / "subtitles.ass",
        ass,
    )

    signature = digest(
        {
            "engine": 4,
            "v": v,
            "b": settings.brand,
            "font": file_hash(
                settings.font
            ),
            "plan": (
                plan.model_dump()
            ),
            "timing": timing,
            "selections": selections,
            "source_hashes": {
                k: [
                    file_hash(
                        x["path"]
                    ),
                    file_hash(
                        x["frame"]
                    ),
                ]
                for k, x
                in selections.items()
                if x["kind"]
                == "stock"
            },
            "audio": file_hash(
                audio
            ),
            "sfx": [
                (
                    cue,
                    file_hash(
                        cue["path"]
                    ),
                )
                for cue in cues
            ],
        }
    )

    manifest = read(
        folder
        / "render_manifest.json",
        {},
    )

    if (
        manifest.get(
            "signature"
        )
        == signature
    ):
        for name in [
            "candidate.mp4",
            "final.mp4",
        ]:
            p = (
                folder
                / name
            )

            if (
                valid_media(
                    p,
                    "video",
                )
                and file_hash(
                    p
                )
                == manifest.get(
                    "sha256"
                )
            ):
                print(
                    "[CACHE] Complete render"
                )

                return p

    clips = []

    # -----------------------------------------------------
    # INDIVIDUAL SHOTS
    # -----------------------------------------------------

    for shot in timing["shots"]:
        dest = (
            work
            / (
                shot["id"]
                + ".mp4"
            )
        )

        still = False

        # -------------------------------------------------
        # INTRO
        #
        # IMPORTANT:
        # Do NOT show a separate branding card.
        # The first real scene visual already runs
        # underneath the spoken intro.
        # -------------------------------------------------

        if shot["scene"] is None:
            scene = (
                plan.scenes[0]
            )

            selection = (
                selections[
                    scene.id
                ]
            )

            motion = "zoom_in"
            transition = "cut"

            if (
                selection["kind"]
                == "diagram"
            ):
                source = (
                    work
                    / "intro_first_scene.png"
                )

                branding.diagram(
                    settings,
                    scene,
                    source,
                    0,
                )

                still = True

            else:
                source = Path(
                    selection[
                        "path"
                    ]
                )

        else:
            scene = (
                plan.scenes[
                    shot["scene"]
                ]
            )

            selection = (
                selections[
                    scene.id
                ]
            )

            motion = (
                scene.edit.motion
            )

            transition = (
                scene.edit.transition
            )

            if (
                selection["kind"]
                == "diagram"
            ):
                source = (
                    work
                    / (
                        shot["id"]
                        + ".png"
                    )
                )

                branding.diagram(
                    settings,
                    scene,
                    source,
                    shot["variant"],
                )

                still = True

            else:
                source = Path(
                    selection[
                        "path"
                    ]
                )

                a = (
                    selection[
                        "assessment"
                    ]
                )

                mark = (
                    scene.edit.overlay
                    in (
                        "arrow",
                        "circle",
                    )
                    and a[
                        "target_visible"
                    ]
                    and a[
                        "target_confidence"
                    ]
                    >= 0.85
                )

                if (
                    shot["variant"]
                    == 0
                    and (
                        motion
                        == "freeze"
                        or mark
                    )
                ):
                    source = (
                        work
                        / (
                            shot["id"]
                            + ".png"
                        )
                    )

                    overlays.annotation(
                        settings,
                        scene,
                        selection,
                        selection[
                            "frame"
                        ],
                        source,
                    )

                    still = True
                    motion = "none"

                elif (
                    motion
                    == "freeze"
                ):
                    motion = (
                        "zoom_in"
                    )

        key = digest(
            {
                "shot": shot,
                "input": file_hash(
                    source
                ),
                "motion": motion,
                "transition": transition,
                "selection": selection,
                "v": v,
                "animation": (
                    settings.brand[
                        "animation_seconds"
                    ]
                ),
            }
        )

        meta = read(
            dest.with_suffix(
                ".json"
            ),
            {},
        )

        if (
            meta.get("key")
            == key
            and valid_shot(
                dest,
                shot["frames"],
                fps,
            )
        ):
            print(
                "[CACHE] "
                + shot["id"]
            )

            clips.append(dest)
            continue

        count = (
            shot["frames"]
        )

        duration = (
            count / fps
        )

        print(
            "[RENDER] %s %.2fs"
            % (
                shot["id"],
                duration,
            ),
            flush=True,
        )

        args = [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-filter_complex_threads",
            "1",
        ]

        if still:
            args += [
                "-loop",
                "1",
                "-framerate",
                str(fps),
                "-i",
                str(source),
            ]

        else:
            # For the intro use the same
            # selected first-scene clip,
            # starting near its chosen offset.
            intro_extra = (
                0
                if shot["scene"]
                is None
                else (
                    shot[
                        "variant"
                    ]
                    * 0.8
                )
            )

            args += [
                "-stream_loop",
                "-1",
                "-ss",
                str(
                    selection.get(
                        "offset",
                        0,
                    )
                    + intro_extra
                ),
                "-i",
                str(source),
            ]

        base = crop_filter(
            selection,
            w,
            h,
        )

        # zoompan emits exactly one
        # frame per input frame.
        n = max(
            1,
            count - 1,
        )

        if (
            shot["scene"]
            is None
        ):
            n = max(
                1,
                round(
                    settings.brand[
                        "animation_seconds"
                    ]
                    * fps
                ),
            )

        zoom = {
            "zoom_in": (
                "1+0.07*min(on/%d,1)"
                % n
            ),
            "zoom_out": (
                "1.07-0.07*min(on/%d,1)"
                % n
            ),
            "punch": "1.12",
            "pan_left": "1.08",
            "pan_right": "1.08",
        }.get(
            motion,
            "1",
        )

        x = (
            "iw/2-iw/zoom/2"
        )

        if (
            motion
            == "pan_left"
        ):
            x = (
                "(iw-iw/zoom)"
                "*(1-on/%d)"
                % max(
                    1,
                    count - 1,
                )
            )

        if (
            motion
            == "pan_right"
        ):
            x = (
                "(iw-iw/zoom)"
                "*on/%d"
                % max(
                    1,
                    count - 1,
                )
            )

        filt = (
            base
            + (
                ",fps=%d,"
                "zoompan="
                "z='%s':"
                "x='%s':"
                "y='ih/2-ih/zoom/2':"
                "d=1:"
                "s=%dx%d:"
                "fps=%d,"
                "setsar=1"
            )
            % (
                fps,
                zoom,
                x,
                w,
                h,
                fps,
            )
        )

        if (
            transition
            in (
                "fade",
                "dip_black",
            )
        ):
            filt += (
                ",fade=t=in:"
                "st=0:"
                "d=0.10"
            )

        if (
            transition
            == "dip_black"
        ):
            filt += (
                ",fade=t=out:"
                "st=%.5f:"
                "d=0.10"
                % max(
                    0.1,
                    duration
                    - 0.1,
                )
            )

        filt += (
            ",format=yuv420p[out]"
        )

        args += [
            "-filter_complex",
            "[0:v]"
            + filt,
            "-map",
            "[out]",
            "-an",
            "-frames:v",
            str(count),
            "-c:v",
            "libx264",
            "-preset",
            v["preset"],
            "-crf",
            str(
                v["crf"]
            ),
            "-threads",
            str(
                v["threads"]
            ),
            str(dest),
        ]

        command(args)

        if not valid_shot(
            dest,
            count,
            fps,
        ):
            raise ProductionError(
                (
                    "Shot is incomplete: "
                    + shot["id"]
                    + ". Resume to "
                    "regenerate this shot."
                )
            )

        save(
            dest.with_suffix(
                ".json"
            ),
            {
                "key": key,
            },
        )

        clips.append(dest)

    # -----------------------------------------------------
    # CONCAT SHOTS
    # -----------------------------------------------------

    atomic(
        work
        / "concat.txt",
        "\n".join(
            (
                "file '%s'"
                % p.name
            )
            for p in clips
        ),
    )

    joined = (
        work
        / "joined.mp4"
    )

    command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "1",
            "-i",
            "concat.txt",
            "-c",
            "copy",
            "joined.mp4",
        ],
        cwd=work,
    )

    # -----------------------------------------------------
    # FINAL SUBTITLE / AUDIO MIX
    # -----------------------------------------------------

    atomic(
        work
        / "captions.ass",
        ass,
    )

    (
        work
        / "fonts"
    ).mkdir(
        exist_ok=True
    )

    atomic(
        work
        / "fonts/font.ttf",
        settings.font.read_bytes(),
    )

    args = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-filter_complex_threads",
        "1",
        "-i",
        joined,
        "-i",
        audio,
    ]

    for cue in cues:
        args += [
            "-i",
            cue["path"],
        ]

    delay = round(
        timing[
            "audio_pad"
        ]
        * 1000
    )

    filters = [
        (
            "[0:v]"
            "ass=filename=captions.ass:"
            "fontsdir=fonts,"
            "scale=in_range=auto:out_range=tv,"
            "format=yuv420p,"
            "setparams=range=tv[v]"
        ),
        (
            "[1:a]"
            "loudnorm="
            "I=-16:"
            "TP=-2:"
            "LRA=9,"
            "aresample=48000,"
            "adelay=%d:all=1,"
            "apad[voice]"
            % delay
        ),
    ]

    audio_labels = [
        "[voice]"
    ]

    for i, cue in enumerate(
        cues
    ):
        label = (
            "[s%d]"
            % i
        )

        filters.append(
            (
                "[%d:a]"
                "aresample=48000,"
                "volume=%.5f,"
                "adelay=%d:all=1"
                "%s"
            )
            % (
                i + 2,
                v[
                    "sfx_volume"
                ],
                round(
                    cue["start"]
                    * 1000
                ),
                label,
            )
        )

        audio_labels.append(
            label
        )

    filters.append(
        "".join(
            audio_labels
        )
        + (
            "amix="
            "inputs=%d:"
            "duration=first:"
            "normalize=0,"
            "alimiter="
            "limit=0.891:"
            "level=false:"
            "latency=1[a]"
            % len(
                audio_labels
            )
        )
    )

    candidate = (
        folder
        / "candidate.mp4"
    )

    args += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-t",
        str(
            timing[
                "duration"
            ]
        ),
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-preset",
        v["preset"],
        "-crf",
        str(
            v["crf"]
        ),
        "-threads",
        str(
            v["threads"]
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
        str(candidate),
    ]

    command(
        args,
        cwd=work,
    )

    save(
        folder
        / "render_manifest.json",
        {
            "signature": signature,
            "sha256": file_hash(
                candidate
            ),
        },
    )

    return candidate