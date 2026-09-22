import math
from .subtitles import event, safe


def intro_brand_events(settings, timeline):
    """
    Small temporary WORLD IN 60 branding over the actual first visual.
    No separate intro card.
    """
    b = settings.brand
    v = settings.video

    if not b["intro_enabled"]:
        return []

    end = min(
        timeline["duration"],
        timeline.get("intro_end", 0),
    )

    if end <= 0:
        return []

    w = v["width"]
    h = v["height"]

    # Small top branding. Fade in/out via ASS.
    tags = (
        "{"
        "\\an8"
        "\\pos(%d,%d)"
        "\\fs%d"
        "\\bord3"
        "\\shad0"
        "\\c&HFFFFFF&"
        "\\3c&H2B1809&"
        "\\fad(120,180)"
        "}"
        % (
            w * 0.5,
            h * 0.075,
            int(w * 0.036),
        )
    )

    return [
        event(
            0,
            end,
            tags + safe(b["channel_name"]),
            layer=5,
        )
    ]


def subscribe_events(settings, duration):
    b = settings.brand
    v = settings.video

    if not b["subscribe_animation"]:
        return []

    start = b["subscribe_start"]
    end = min(
        duration,
        start + b["subscribe_duration"],
    )

    events = []

    for i in range(
        max(
            0,
            math.ceil(
                (end - start)
                * v["fps"]
            ),
        )
    ):
        t = i / v["fps"]

        remaining = (
            end
            - start
            - t
        )

        # Bounce-in curve.
        p = min(
            1,
            t / 0.4,
        )

        ease = (
            1
            + (
                2.70158
                * (p - 1) ** 3
                + 1.70158
                * (p - 1) ** 2
            )
        )

        y = (
            v["height"]
            * (
                1.08
                - 0.45 * ease
            )
        )

        # Slide back down near the end.
        if remaining < 0.3:
            y += (
                v["height"]
                * 0.5
                * (
                    1
                    - remaining / 0.3
                )
            )

        scale = (
            100
            + 4
            * math.sin(
                min(
                    1,
                    t / 0.45,
                )
                * math.pi
            )
        )

        tags = (
            "{"
            "\\pos(%d,%d)"
            "\\fs%d"
            "\\fscx%d"
            "\\fscy%d"
            "\\bord12"
            "\\shad0"
            "\\3c&HCCF36F&"
            "\\c&H2B1809&"
            "}"
            % (
                v["width"] * 0.5,
                y,
                v["width"] * 0.043,
                scale,
                scale,
            )
        )

        events.append(
            event(
                start + t,
                min(
                    end,
                    start
                    + t
                    + 1 / v["fps"],
                ),
                tags
                + safe(
                    b["subscribe_text"]
                ),
                layer=6,
            )
        )

    return events


def scene_events(
    settings,
    plan,
    timeline,
    selections,
):
    events = []

    w = settings.video["width"]
    h = settings.video["height"]

    for scene, timing in zip(
        plan.scenes,
        timeline["scenes"],
    ):
        if (
            scene.edit.label
            and selections[
                scene.id
            ]["kind"]
            != "diagram"
        ):
            events.append(
                event(
                    timing["start"],
                    min(
                        timing["end"],
                        timing["start"]
                        + 2.5,
                    ),
                    (
                        "{"
                        "\\pos(%d,%d)"
                        "\\fs%d"
                        "\\c&HCCF36F&"
                        "}%s"
                    )
                    % (
                        w * 0.46,
                        h * 0.18,
                        w * 0.041,
                        safe(
                            scene.edit.label
                        ),
                    ),
                )
            )

    return events


def annotation(
    settings,
    scene,
    selection,
    source,
    target,
):
    """
    Draw on the exact verified frozen image before crop.
    Never track guessed coordinates.
    """

    from PIL import (
        Image,
        ImageDraw,
    )

    im = Image.open(
        source
    ).convert(
        "RGB"
    )

    a = selection["assessment"]

    if (
        scene.edit.overlay
        not in (
            "circle",
            "arrow",
        )
        or not a["target_visible"]
        or a[
            "target_confidence"
        ]
        < 0.85
    ):
        im.save(target)
        return

    d = ImageDraw.Draw(im)

    w, h = im.size

    x = (
        a["target_x"]
        * w
    )

    y = (
        a["target_y"]
        * h
    )

    r = (
        a["target_radius"]
        * min(w, h)
    )

    if (
        x - r < 0
        or y - r < 0
        or x + r > w
        or y + r > h
    ):
        im.save(target)
        return

    color = settings.brand[
        "accent"
    ]

    width = max(
        3,
        round(
            w * 0.006
        ),
    )

    if (
        scene.edit.overlay
        == "circle"
    ):
        d.ellipse(
            (
                x - r,
                y - r,
                x + r,
                y + r,
            ),
            outline=color,
            width=width,
        )

    else:
        sx = max(
            10,
            x
            - w * 0.15,
        )

        sy = max(
            10,
            y
            - h * 0.12,
        )

        d.line(
            (
                sx,
                sy,
                x,
                y,
            ),
            fill=color,
            width=width,
        )

        angle = math.atan2(
            y - sy,
            x - sx,
        )

        length = (
            min(w, h)
            * 0.04
        )

        d.polygon(
            [
                (
                    x,
                    y,
                ),
                (
                    x
                    - length
                    * math.cos(
                        angle - 0.5
                    ),
                    y
                    - length
                    * math.sin(
                        angle - 0.5
                    ),
                ),
                (
                    x
                    - length
                    * math.cos(
                        angle + 0.5
                    ),
                    y
                    - length
                    * math.sin(
                        angle + 0.5
                    ),
                ),
            ],
            fill=color,
        )

    im.save(target)