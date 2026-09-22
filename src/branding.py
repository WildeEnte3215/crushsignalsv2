from PIL import Image, ImageDraw, ImageFont


def fit(draw, text, font_path, size, width):
    font = ImageFont.truetype(str(font_path), size)
    while draw.textbbox((0, 0), text, font=font)[2] > width and size > 16:
        size -= 2
        font = ImageFont.truetype(str(font_path), size)
    return font


def centered(draw, text, y, font, color, width):
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(((width - (box[2] - box[0])) / 2, y), text, font=font, fill=color)


def background(settings):
    w, h = settings.video["width"], settings.video["height"]
    im = Image.new("RGB", (w, h), settings.brand["background"])
    d = ImageDraw.Draw(im)
    for y in range(h):
        p = y / h
        d.line((0, y, w, y), fill=(9 + int(p * 7), 24 + int(p * 14), 43 + int(p * 15)))
    return im, d


def intro(settings, target):
    im, d = background(settings)
    w, h = im.size
    b = settings.brand
    cx, cy, r = w / 2, h * 0.32, w * 0.18
    for k in [1, 0.6, 0.25]:
        d.ellipse(
            (cx - r * k, cy - r, cx + r * k, cy + r),
            outline=b["accent"],
            width=max(2, int(w * 0.004)),
        )
    d.ellipse(
        (cx - r, cy - r * 0.35, cx + r, cy + r * 0.35), outline=b["accent"], width=3
    )
    centered(
        d,
        b["channel_name"],
        h * 0.48,
        fit(d, b["channel_name"], settings.font, int(w * 0.09), w * 0.85),
        b["text_color"],
        w,
    )
    centered(
        d,
        b["tagline"],
        h * 0.56,
        fit(d, b["tagline"], settings.font, int(w * 0.034), w * 0.85),
        b["accent"],
        w,
    )
    centered(
        d,
        b["footer_text"],
        h * 0.83,
        fit(d, b["footer_text"], settings.font, int(w * 0.025), w * 0.82),
        "#91AABC",
        w,
    )
    im.save(target)


def diagram(settings, scene, target, active=0):
    im, d = background(settings)
    w, h = im.size
    centered(
        d,
        "SCHEMATIC",
        h * 0.12,
        ImageFont.truetype(str(settings.font), int(w * 0.035)),
        "#91AABC",
        w,
    )
    centered(
        d,
        scene.edit.label or "HOW IT WORKS",
        h * 0.19,
        fit(
            d,
            scene.edit.label or "HOW IT WORKS",
            settings.font,
            int(w * 0.055),
            w * 0.8,
        ),
        "#FFFFFF",
        w,
    )
    nodes = scene.diagram_nodes
    for i, node in enumerate(nodes):
        y = h * (0.29 + i * 0.14)
        color = settings.brand["accent"] if i == active % len(nodes) else "#234457"
        d.rounded_rectangle(
            (w * 0.13, y, w * 0.82, y + h * 0.075), radius=int(w * 0.02), fill=color
        )
        font = fit(d, node, settings.font, int(w * 0.043), w * 0.62)
        centered(
            d,
            node,
            y + h * 0.018,
            font,
            "#09182B" if i == active % len(nodes) else "#FFFFFF",
            w * 0.95,
        )
        if i < len(nodes) - 1:
            x = w * 0.475
            d.line(
                (x, y + h * 0.082, x, y + h * 0.122),
                fill=settings.brand["accent"],
                width=5,
            )
            d.polygon(
                [
                    (x, y + h * 0.13),
                    (x - w * 0.012, y + h * 0.116),
                    (x + w * 0.012, y + h * 0.116),
                ],
                fill=settings.brand["accent"],
            )
    im.save(target)
