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


def _interpolate_color(colors: list[str], stops: list[float], t: float) -> tuple[int, int, int]:
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
    colors, stops, direction = bg.colors, bg.stops, bg.direction

    if direction == "vertical":
        draw = ImageDraw.Draw(canvas)
        for y in range(H):
            t = y / max(H - 1, 1)
            draw.line([(0, y), (W, y)], fill=_interpolate_color(colors, stops, t))
    elif direction == "horizontal":
        draw = ImageDraw.Draw(canvas)
        for x in range(W):
            t = x / max(W - 1, 1)
            draw.line([(x, 0), (x, H)], fill=_interpolate_color(colors, stops, t))
    else:
        scale = 8
        sw, sh = max(W // scale, 2), max(H // scale, 2)
        small = Image.new("RGB", (sw, sh))
        draw = ImageDraw.Draw(small)
        for sy in range(sh):
            for sx in range(sw):
                t = (sx / max(sw - 1, 1) + sy / max(sh - 1, 1)) / 2
                draw.point((sx, sy), fill=_interpolate_color(colors, stops, t))
        canvas.paste(small.resize((W, H), Image.BILINEAR))


def _render_background(canvas: Image.Image, bg: BackgroundConfig) -> float:
    if bg.type == "solid":
        rgb = _hex_to_rgb(bg.color)
        canvas.paste(Image.new("RGB", canvas.size, rgb))
        return _luminance(rgb)
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


def _fit_screenshot(src: Image.Image, screen_box: tuple, fit_mode: str) -> tuple[Image.Image, tuple[int, int]]:
    sw = screen_box[2] - screen_box[0]
    sh = screen_box[3] - screen_box[1]
    iw, ih = src.size

    if fit_mode == "cover":
        scale = max(sw / iw, sh / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        resized = src.resize((nw, nh), Image.LANCZOS)
        cropped = resized.crop(((nw - sw) // 2, (nh - sh) // 2, (nw - sw) // 2 + sw, (nh - sh) // 2 + sh))
        return cropped, (screen_box[0], screen_box[1])
    else:
        scale = min(sw / iw, sh / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        resized = src.resize((nw, nh), Image.LANCZOS)
        return resized, (screen_box[0] + (sw - nw) // 2, screen_box[1] + (sh - nh) // 2)


# ── 폰트 탐색 ────────────────────────────────────────────────────────────────

_BOLD_FONTS = [
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 7),   # Bold
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 3),
    ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
    ("/Library/Fonts/Arial Bold.ttf", 0),
]
_REGULAR_FONTS = [
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc", 0),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", 0),
    ("/Library/Fonts/Arial.ttf", 0),
    ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
]


def _load_font(
    font_path: str | None,
    size: int,
    bold: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if font_path and os.path.exists(font_path):
        candidates.append((font_path, 0))
    candidates += (_BOLD_FONTS if bold else _REGULAR_FONTS)

    for path, index in candidates:
        if not os.path.exists(path):
            continue
        try:
            return ImageFont.truetype(path, size, index=index)
        except Exception:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

    bundled = Path(__file__).parent / "fonts" / "Inter-Regular.ttf"
    if bundled.exists():
        try:
            return ImageFont.truetype(str(bundled), size)
        except Exception:
            pass
    return ImageFont.load_default()


def _text_width(font: ImageFont.FreeTypeFont | ImageFont.ImageFont, text: str) -> int:
    try:
        return int(font.getlength(text))  # type: ignore
    except AttributeError:
        return len(text) * (font.size if hasattr(font, "size") else 10)


def _line_height(font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    try:
        bb = font.getbbox("가Ag")  # type: ignore
        return int((bb[3] - bb[1]) * 1.3)
    except AttributeError:
        return (font.size if hasattr(font, "size") else 14) + 4


def _draw_text_block(
    canvas: Image.Image,
    lines: list[str],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    color: str,
    x: int,
    y: int,
    align: str = "left",
    max_width: int | None = None,
    shadow: bool = True,
) -> int:
    lh = _line_height(font)
    shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    text_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow_layer)
    tdraw = ImageDraw.Draw(text_layer)

    cy = y
    for line in lines:
        lw = _text_width(font, line)
        if align == "center" and max_width:
            lx = x + (max_width - lw) // 2
        elif align == "right" and max_width:
            lx = x + max_width - lw
        else:
            lx = x
        if shadow:
            sdraw.text((lx + 2, cy + 2), line, font=font, fill=(0, 0, 0, 100))
        tdraw.text((lx, cy), line, font=font, fill=color)
        cy += lh

    if shadow:
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=4))
        canvas.alpha_composite(shadow_layer)
    canvas.alpha_composite(text_layer)
    return cy  # y 끝 위치 반환


# ── AD 레이아웃 ───────────────────────────────────────────────────────────────

def _render_ad(
    shot: ScreenshotConfig,
    size: SizeSpec,
    platform: PlatformSpec,
    defaults: GlobalDefaults,
) -> Image.Image:
    W, H = size.width, size.height
    device = size.device_override or platform.device

    canvas = Image.new("RGBA", (W, H))
    bg_luminance = _render_background(canvas, shot.background)

    geometry = calculate_geometry(size, device, layout="ad")

    src = _load_image(shot.input)
    fitted, paste_pos = _fit_screenshot(src, geometry.screen_box, "cover")
    mask = make_screen_mask(geometry.screen_box, geometry.screen_radius, canvas.size)
    screen_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    screen_layer.paste(fitted, paste_pos)
    canvas.paste(screen_layer, mask=mask)

    draw_frame(canvas, geometry, device, defaults.frame_color, bg_luminance)

    # 텍스트 색상 결정
    if shot.caption_color and shot.caption_color != "auto":
        text_color = shot.caption_color
    elif defaults.text_color != "auto":
        text_color = defaults.text_color
    else:
        text_color = "#1a1a1a" if bg_luminance > 128 else "#ffffff"

    # 헤드라인 (headline 없으면 caption 폴백)
    headline_text = shot.headline or shot.caption
    subtitle_text = shot.subtitle
    text_align = shot.text_align or defaults.text_align or "left"

    pad_x = int(W * 0.06)
    text_start_y = int(H * 0.06)
    text_zone_bottom = geometry.body_box[1] - int(H * 0.02)
    text_zone_h = text_zone_bottom - text_start_y
    available_w = W - pad_x * 2

    if headline_text:
        headline_size = int(W * 0.13)
        headline_font = _load_font(defaults.headline_font or defaults.font, headline_size, bold=True)

        hl_lines = headline_text.split("\n") if "\n" in headline_text else [headline_text]
        hl_lh = _line_height(headline_font)
        total_hl_h = hl_lh * len(hl_lines)

        sub_lines: list[str] = []
        sub_lh = 0
        total_sub_h = 0
        if subtitle_text:
            sub_size = int(headline_size * 0.38)
            sub_font = _load_font(defaults.font, sub_size, bold=False)
            sub_lines = subtitle_text.split("\n") if "\n" in subtitle_text else [subtitle_text]
            sub_lh = _line_height(sub_font)
            total_sub_h = sub_lh * len(sub_lines) + int(headline_size * 0.2)

        total_text_h = total_hl_h + total_sub_h
        # 텍스트 존 내에서 수직 중앙 정렬
        text_y = text_start_y + max(0, (text_zone_h - total_text_h) // 2)

        end_y = _draw_text_block(
            canvas, hl_lines, headline_font, text_color,
            pad_x, text_y, align=text_align, max_width=available_w,
        )

        if sub_lines:
            gap = int(headline_size * 0.2)
            sub_color = text_color  # 서브타이틀은 약간 투명하게
            _draw_text_block(
                canvas, sub_lines, sub_font, sub_color,
                pad_x, end_y + gap, align=text_align, max_width=available_w,
                shadow=False,
            )

    return canvas.convert("RGB")


# ── SIMPLE 레이아웃 (기존) ────────────────────────────────────────────────────

def _render_simple(
    shot: ScreenshotConfig,
    size: SizeSpec,
    platform: PlatformSpec,
    defaults: GlobalDefaults,
) -> Image.Image:
    device = size.device_override or platform.device
    canvas = Image.new("RGBA", (size.width, size.height))
    bg_luminance = _render_background(canvas, shot.background)
    geometry = calculate_geometry(size, device, layout="centered")

    src = _load_image(shot.input)
    fitted, paste_pos = _fit_screenshot(src, geometry.screen_box, shot.fit_mode)
    mask = make_screen_mask(geometry.screen_box, geometry.screen_radius, canvas.size)
    screen_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    screen_layer.paste(fitted, paste_pos)
    canvas.paste(screen_layer, mask=mask)

    draw_frame(canvas, geometry, device, defaults.frame_color, bg_luminance)

    caption = shot.headline or shot.caption
    if caption:
        font_size = shot.caption_font_size or defaults.font_size
        font = _load_font(defaults.font, font_size)
        W = size.width
        if shot.caption_color == "auto":
            color = "#1a1a1a" if bg_luminance > 128 else "#ffffff"
        else:
            color = shot.caption_color

        if shot.caption_position == "top":
            zone_top, zone_bottom = 0, geometry.body_box[1]
        else:
            zone_top, zone_bottom = geometry.body_box[3], size.height

        lines = caption.split("\n") if "\n" in caption else [caption]
        lh = _line_height(font)
        block_h = lh * len(lines)
        text_y = zone_top + (zone_bottom - zone_top - block_h) // 2
        _draw_text_block(canvas, lines, font, color, W // 2, text_y, align="center", max_width=int(W * 0.85))

    return canvas.convert("RGB")


# ── 공개 인터페이스 ───────────────────────────────────────────────────────────

def render_screenshot(
    shot: ScreenshotConfig,
    size: SizeSpec,
    platform: PlatformSpec,
    defaults: GlobalDefaults,
) -> Image.Image:
    layout = shot.layout or defaults.layout or "ad"
    if layout == "ad":
        return _render_ad(shot, size, platform, defaults)
    return _render_simple(shot, size, platform, defaults)
