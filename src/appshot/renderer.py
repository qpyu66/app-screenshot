from __future__ import annotations

import os
from pathlib import Path
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

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


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _mix_hex(a: str, b: str, amount: float) -> str:
    ar, ag, ab = _hex_to_rgb(a)
    br, bg, bb = _hex_to_rgb(b)
    t = max(0.0, min(1.0, amount))
    return _rgb_to_hex((
        int(ar + (br - ar) * t),
        int(ag + (bg - ag) * t),
        int(ab + (bb - ab) * t),
    ))


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


_TONE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "education": ("class", "school", "lesson", "student", "teacher", "study", "수업", "학생", "선생", "학습", "출결", "공지"),
    "finance": ("money", "pay", "bank", "asset", "stock", "budget", "card", "wallet", "금융", "결제", "자산", "투자", "가계부"),
    "health": ("health", "care", "fit", "wellness", "medical", "clinic", "workout", "건강", "운동", "병원", "케어"),
    "commerce": ("shop", "store", "order", "cart", "sale", "delivery", "commerce", "쇼핑", "주문", "배송", "구매"),
    "social": ("chat", "friend", "community", "message", "share", "소셜", "채팅", "친구", "커뮤니티", "메시지"),
    "productivity": ("task", "todo", "calendar", "note", "project", "work", "업무", "일정", "노트", "프로젝트", "관리"),
    "game": ("game", "play", "quest", "level", "battle", "게임", "플레이", "퀘스트", "레벨"),
}

_TONE_PALETTES: dict[str, dict[str, str | tuple[str, str, str]]] = {
    "education": {"bg": ("#fff7d6", "#ffdd8a", "#3267d6"), "accent": "#2f6fed", "text": "#172033", "frame": "black"},
    "finance": {"bg": ("#071b19", "#0f3b33", "#d8b35a"), "accent": "#d8b35a", "text": "#fff9e8", "frame": "black"},
    "health": {"bg": ("#e8fff7", "#80dec3", "#145f68"), "accent": "#10b981", "text": "#10323a", "frame": "white"},
    "commerce": {"bg": ("#fff0e6", "#ff9d68", "#26233d"), "accent": "#ff6a3d", "text": "#271b18", "frame": "black"},
    "social": {"bg": ("#eff4ff", "#8eb5ff", "#5927d9"), "accent": "#4f7cff", "text": "#172033", "frame": "black"},
    "productivity": {"bg": ("#f1f5f9", "#9fb3c8", "#182230"), "accent": "#2563eb", "text": "#111827", "frame": "black"},
    "game": {"bg": ("#12051f", "#4b167b", "#ffb000"), "accent": "#ffb000", "text": "#fff5d6", "frame": "black"},
    "default": {"bg": ("#eff6ff", "#8dd3ff", "#173f7a"), "accent": "#2f80ed", "text": "#102033", "frame": "black"},
}


def _infer_tone(shot: ScreenshotConfig, defaults: GlobalDefaults) -> str:
    configured = (shot.tone or defaults.tone or "auto").lower()
    if configured != "auto":
        return configured if configured in _TONE_PALETTES else "default"

    haystack = " ".join((
        defaults.app_name,
        shot.input.stem,
        shot.headline,
        shot.subtitle,
        shot.caption,
    )).lower()
    for tone, words in _TONE_KEYWORDS.items():
        if any(word in haystack for word in words):
            return tone
    return "default"


def _palette_for(shot: ScreenshotConfig, defaults: GlobalDefaults) -> dict[str, str | tuple[str, str, str]]:
    palette = dict(_TONE_PALETTES[_infer_tone(shot, defaults)])
    accent = shot.accent_color or defaults.accent_color
    if accent and accent != "auto":
        palette["accent"] = accent
    return palette


def _uses_default_background(bg: BackgroundConfig) -> bool:
    return bg.type == "solid" and bg.color.lower() == "#6366f1"


def _render_modern_background(canvas: Image.Image, shot: ScreenshotConfig, defaults: GlobalDefaults) -> float:
    palette = _palette_for(shot, defaults)
    colors = palette["bg"]
    assert isinstance(colors, tuple)

    if (defaults.design_style or "modern") == "classic":
        return _render_background(canvas, shot.background)

    if not _uses_default_background(shot.background):
        bg_luminance = _render_background(canvas, shot.background)
    else:
        bg_luminance = _render_background(
            canvas,
            BackgroundConfig(type="gradient", colors=list(colors), stops=[0.0, 0.55, 1.0], direction="diagonal"),
        )

    _draw_ambient_shapes(canvas, str(palette["accent"]), seed=f"{shot.input.stem}:{shot.headline}:{canvas.size}")
    return bg_luminance


def _draw_ambient_shapes(canvas: Image.Image, accent: str, seed: str) -> None:
    W, H = canvas.size
    rng = random.Random(seed)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    accent_rgb = _hex_to_rgb(accent)

    blobs = [
        (-int(W * 0.20), int(H * 0.05), int(W * 0.58), int(W * 0.58), 72),
        (int(W * 0.55), -int(H * 0.10), int(W * 0.56), int(W * 0.56), 56),
        (int(W * 0.08), int(H * 0.73), int(W * 0.46), int(W * 0.46), 38),
    ]
    for x, y, bw, bh, alpha in blobs:
        dx = rng.randint(-int(W * 0.03), int(W * 0.03))
        dy = rng.randint(-int(H * 0.02), int(H * 0.02))
        draw.ellipse((x + dx, y + dy, x + dx + bw, y + dy + bh), fill=(*accent_rgb, alpha))

    draw.rounded_rectangle(
        (int(W * 0.07), int(H * 0.14), int(W * 0.93), int(H * 0.36)),
        radius=int(W * 0.08),
        fill=(255, 255, 255, 24),
        outline=(255, 255, 255, 36),
        width=max(2, int(W * 0.002)),
    )
    layer = layer.filter(ImageFilter.GaussianBlur(radius=max(18, int(W * 0.035))))
    canvas.alpha_composite(layer)

    sheen = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(sheen)
    sdraw.polygon(
        [(-int(W * 0.15), int(H * 0.34)), (int(W * 1.12), int(H * 0.04)), (int(W * 1.20), int(H * 0.14)), (-int(W * 0.05), int(H * 0.45))],
        fill=(255, 255, 255, 22),
    )
    canvas.alpha_composite(sheen)


def _draw_device_shadow(canvas: Image.Image, geometry: FrameGeometry, accent: str) -> None:
    W, H = canvas.size
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    box = geometry.body_box
    dx = int(W * 0.025)
    dy = int(H * 0.028)
    shadow_box = (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)
    draw.rounded_rectangle(shadow_box, radius=geometry.body_radius, fill=(0, 0, 0, 120))
    shadow = layer.filter(ImageFilter.GaussianBlur(radius=max(24, int(W * 0.045))))
    canvas.alpha_composite(shadow)

    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    ar, ag, ab = _hex_to_rgb(accent)
    gdraw.rounded_rectangle(
        (box[0] - dx, box[1] + int(dy * 0.4), box[2] + dx, box[3] + int(dy * 1.4)),
        radius=geometry.body_radius,
        fill=(ar, ag, ab, 40),
    )
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(radius=max(20, int(W * 0.035)))))


def _draw_screen_highlight(canvas: Image.Image, geometry: FrameGeometry) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    sx0, sy0, sx1, sy1 = geometry.screen_box
    draw.polygon(
        [(sx0, sy0), (sx0 + int((sx1 - sx0) * 0.52), sy0), (sx0, sy0 + int((sy1 - sy0) * 0.34))],
        fill=(255, 255, 255, 24),
    )
    mask = make_screen_mask(geometry.screen_box, geometry.screen_radius, canvas.size)
    clipped_alpha = ImageChops.multiply(layer.getchannel("A"), mask)
    layer.putalpha(clipped_alpha)
    canvas.alpha_composite(layer)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_width: int) -> list[str]:
    manual = text.split("\n") if "\n" in text else [text]
    lines: list[str] = []
    for part in manual:
        if _text_width(font, part) <= max_width:
            lines.append(part)
            continue
        words = part.split(" ")
        if len(words) > 1:
            current = ""
            for word in words:
                candidate = word if not current else f"{current} {word}"
                if _text_width(font, candidate) <= max_width:
                    current = candidate
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)
            continue

        current = ""
        for ch in part:
            candidate = current + ch
            if current and _text_width(font, candidate) > max_width:
                lines.append(current)
                current = ch
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines


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
    bg_luminance = _render_modern_background(canvas, shot, defaults)
    palette = _palette_for(shot, defaults)
    accent = str(palette["accent"])

    geometry = calculate_geometry(size, device, layout="ad")
    _draw_device_shadow(canvas, geometry, accent)

    src = _load_image(shot.input)
    fitted, paste_pos = _fit_screenshot(src, geometry.screen_box, "cover")
    mask = make_screen_mask(geometry.screen_box, geometry.screen_radius, canvas.size)
    screen_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    screen_layer.paste(fitted, paste_pos)
    canvas.paste(screen_layer, mask=mask)
    _draw_screen_highlight(canvas, geometry)

    frame_color = defaults.frame_color
    if frame_color == "auto" and (defaults.design_style or "modern") != "classic":
        frame_color = str(palette["frame"])
    draw_frame(canvas, geometry, device, frame_color, bg_luminance)

    # 텍스트 색상 결정
    if shot.caption_color and shot.caption_color != "auto":
        text_color = shot.caption_color
    elif defaults.text_color != "auto":
        text_color = defaults.text_color
    else:
        text_color = str(palette["text"]) if (defaults.design_style or "modern") != "classic" else ("#1a1a1a" if bg_luminance > 128 else "#ffffff")

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
        headline_size = int(W * 0.125)
        headline_font = _load_font(defaults.headline_font or defaults.font, headline_size, bold=True)

        hl_lines = _wrap_text(headline_text, headline_font, available_w)
        while len(hl_lines) > 4 and headline_size > int(W * 0.085):
            headline_size = int(headline_size * 0.92)
            headline_font = _load_font(defaults.headline_font or defaults.font, headline_size, bold=True)
            hl_lines = _wrap_text(headline_text, headline_font, available_w)
        hl_lh = _line_height(headline_font)
        total_hl_h = hl_lh * len(hl_lines)

        sub_lines: list[str] = []
        sub_lh = 0
        total_sub_h = 0
        if subtitle_text:
            sub_size = int(headline_size * 0.38)
            sub_font = _load_font(defaults.font, sub_size, bold=False)
            sub_lines = _wrap_text(subtitle_text, sub_font, available_w)
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
            sub_color = _mix_hex(text_color, "#ffffff" if _luminance(_hex_to_rgb(text_color)) < 128 else "#000000", 0.18)
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
    bg_luminance = _render_modern_background(canvas, shot, defaults)
    palette = _palette_for(shot, defaults)
    accent = str(palette["accent"])
    geometry = calculate_geometry(size, device, layout="centered")
    _draw_device_shadow(canvas, geometry, accent)

    src = _load_image(shot.input)
    fitted, paste_pos = _fit_screenshot(src, geometry.screen_box, shot.fit_mode)
    mask = make_screen_mask(geometry.screen_box, geometry.screen_radius, canvas.size)
    screen_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    screen_layer.paste(fitted, paste_pos)
    canvas.paste(screen_layer, mask=mask)
    _draw_screen_highlight(canvas, geometry)

    frame_color = defaults.frame_color
    if frame_color == "auto" and (defaults.design_style or "modern") != "classic":
        frame_color = str(palette["frame"])
    draw_frame(canvas, geometry, device, frame_color, bg_luminance)

    caption = shot.headline or shot.caption
    if caption:
        font_size = shot.caption_font_size or defaults.font_size
        font = _load_font(defaults.font, font_size)
        W = size.width
        if shot.caption_color == "auto":
            color = str(palette["text"]) if (defaults.design_style or "modern") != "classic" else ("#1a1a1a" if bg_luminance > 128 else "#ffffff")
        else:
            color = shot.caption_color

        if shot.caption_position == "top":
            zone_top, zone_bottom = 0, geometry.body_box[1]
        else:
            zone_top, zone_bottom = geometry.body_box[3], size.height

        lines = _wrap_text(caption, font, int(W * 0.85))
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
