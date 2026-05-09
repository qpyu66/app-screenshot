from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import AppShotConfig, BackgroundConfig, GlobalDefaults, ScreenshotConfig
from .frames import FrameGeometry, calculate_geometry, draw_frame, make_screen_mask
from .platforms import DeviceSpec, PlatformSpec, SizeSpec


class InputError(Exception):
    pass


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _luminance(rgb: tuple[int, int, int]) -> float:
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _interpolate_color(
    colors: list[str], stops: list[float], t: float
) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    for i in range(len(stops) - 1):
        if stops[i] <= t <= stops[i + 1]:
            span = stops[i + 1] - stops[i]
            lt = (t - stops[i]) / span if span > 0 else 0.0
            c0 = _hex_to_rgb(colors[i])
            c1 = _hex_to_rgb(colors[i + 1])
            return tuple(int(c0[j] + (c1[j] - c0[j]) * lt) for j in range(3))  # type: ignore
    return _hex_to_rgb(colors[-1])


def _render_gradient(canvas: Image.Image, bg: BackgroundConfig) -> None:
    W, H = canvas.size
    colors = bg.colors
    stops = bg.stops
    direction = bg.direction

    if direction == "vertical":
        draw = ImageDraw.Draw(canvas)
        for y in range(H):
            t = y / max(H - 1, 1)
            c = _interpolate_color(colors, stops, t)
            draw.line([(0, y), (W, y)], fill=c)
    elif direction == "horizontal":
        draw = ImageDraw.Draw(canvas)
        for x in range(W):
            t = x / max(W - 1, 1)
            c = _interpolate_color(colors, stops, t)
            draw.line([(x, 0), (x, H)], fill=c)
    else:
        scale = 8
        small_w, small_h = max(W // scale, 2), max(H // scale, 2)
        small = Image.new("RGB", (small_w, small_h))
        draw = ImageDraw.Draw(small)
        for sy in range(small_h):
            for sx in range(small_w):
                t = (sx / max(small_w - 1, 1) + sy / max(small_h - 1, 1)) / 2
                c = _interpolate_color(colors, stops, t)
                draw.point((sx, sy), fill=c)
        small = small.resize((W, H), Image.BILINEAR)
        canvas.paste(small)


def _render_background(canvas: Image.Image, bg: BackgroundConfig) -> float:
    if bg.type == "solid":
        rgb = _hex_to_rgb(bg.color)
        canvas.paste(Image.new("RGB", canvas.size, rgb))
        return _luminance(rgb)
    else:
        _render_gradient(canvas, bg)
        w, h = canvas.size
        sample = canvas.crop((w // 3, h // 3, 2 * w // 3, 2 * h // 3)).convert("RGB")
        avg = sample.resize((1, 1), Image.LANCZOS).getpixel((0, 0))
        return _luminance(avg[:3])


def _load_image(path: Path) -> Image.Image:
    try:
        img = Image.open(path)
        img.load()
        return img.convert("RGBA")
    except Exception as e:
        raise InputError(f"Cannot open {path}: {e}") from e


def _fit_screenshot(
    src: Image.Image,
    screen_box: tuple[int, int, int, int],
    fit_mode: str,
) -> tuple[Image.Image, tuple[int, int]]:
    sw = screen_box[2] - screen_box[0]
    sh = screen_box[3] - screen_box[1]
    iw, ih = src.size

    if fit_mode == "cover":
        scale = max(sw / iw, sh / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        resized = src.resize((nw, nh), Image.LANCZOS)
        x_off = (nw - sw) // 2
        y_off = (nh - sh) // 2
        cropped = resized.crop((x_off, y_off, x_off + sw, y_off + sh))
        return cropped, (screen_box[0], screen_box[1])
    else:
        scale = min(sw / iw, sh / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        resized = src.resize((nw, nh), Image.LANCZOS)
        x_off = screen_box[0] + (sw - nw) // 2
        y_off = screen_box[1] + (sh - nh) // 2
        return resized, (x_off, y_off)


_MACOS_FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
]
_LINUX_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _find_system_font() -> str | None:
    paths = _MACOS_FONT_PATHS + _LINUX_FONT_PATHS
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def _load_font(font_path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if font_path and os.path.exists(font_path):
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass

    bundled = Path(__file__).parent / "fonts" / "Inter-Regular.ttf"
    if bundled.exists():
        try:
            return ImageFont.truetype(str(bundled), size)
        except Exception:
            pass

    system = _find_system_font()
    if system:
        try:
            return ImageFont.truetype(system, size)
        except Exception:
            pass

    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        try:
            w = font.getlength(test)  # type: ignore
        except AttributeError:
            w = len(test) * 10
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _render_text(
    canvas: Image.Image,
    text: str,
    position: str,
    geometry: FrameGeometry,
    font_path: str | None,
    font_size: int,
    text_color: str,
    bg_luminance: float,
    text_align: str = "center",
) -> None:
    if not text.strip():
        return

    W, H = canvas.size
    font = _load_font(font_path, font_size)

    max_text_w = int(W * 0.85)
    lines = _wrap_text(text, font, max_text_w)

    try:
        sample_bbox = font.getbbox("Ag")  # type: ignore
        line_height = (sample_bbox[3] - sample_bbox[1]) * 1.35
    except AttributeError:
        line_height = font_size * 1.35

    block_h = int(line_height * len(lines))

    if position == "top":
        zone_top = 0
        zone_bottom = geometry.body_box[1]
    else:
        zone_top = geometry.body_box[3]
        zone_bottom = H

    zone_h = zone_bottom - zone_top
    text_y = zone_top + (zone_h - block_h) // 2

    if text_color == "auto":
        color = "#1a1a1a" if bg_luminance > 128 else "#ffffff"
    else:
        color = text_color

    shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    text_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_layer)

    for i, line in enumerate(lines):
        try:
            lw = font.getlength(line)  # type: ignore
        except AttributeError:
            lw = len(line) * 10
        lw = int(lw)

        if text_align == "left":
            x = (W - max_text_w) // 2
        elif text_align == "right":
            x = W - (W - max_text_w) // 2 - lw
        else:
            x = (W - lw) // 2

        y = int(text_y + i * line_height)

        shadow_draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 153))
        text_draw.text((x, y), line, font=font, fill=color)

    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=4))
    canvas.alpha_composite(shadow_layer)
    canvas.alpha_composite(text_layer)


def render_screenshot(
    shot: ScreenshotConfig,
    size: SizeSpec,
    platform: PlatformSpec,
    defaults: GlobalDefaults,
) -> Image.Image:
    device = size.device_override or platform.device

    canvas = Image.new("RGBA", (size.width, size.height))
    bg_luminance = _render_background(canvas, shot.background)

    geometry = calculate_geometry(size, device)

    src = _load_image(shot.input)
    fitted, paste_pos = _fit_screenshot(src, geometry.screen_box, shot.fit_mode)

    sw = geometry.screen_box[2] - geometry.screen_box[0]
    sh = geometry.screen_box[3] - geometry.screen_box[1]
    mask = make_screen_mask(geometry.screen_box, geometry.screen_radius, canvas.size)

    screen_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    screen_layer.paste(fitted, paste_pos)
    canvas.paste(screen_layer, mask=mask)

    draw_frame(canvas, geometry, device, defaults.frame_color, bg_luminance)

    font_size = shot.caption_font_size or defaults.font_size
    _render_text(
        canvas,
        shot.caption,
        shot.caption_position,
        geometry,
        defaults.font,
        font_size,
        shot.caption_color,
        bg_luminance,
        defaults.text_align,
    )

    return canvas.convert("RGB")
