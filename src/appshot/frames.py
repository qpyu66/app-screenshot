from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from .platforms import DeviceSpec, SizeSpec

SUPERSAMPLE = 2


@dataclass
class FrameGeometry:
    body_box: tuple[int, int, int, int]
    screen_box: tuple[int, int, int, int]
    body_radius: int
    screen_radius: int
    island_box: tuple[int, int, int, int] | None
    home_btn_center: tuple[int, int] | None
    home_btn_radius: int
    side_buttons: list[tuple[int, int, int, int]]


def calculate_geometry(size: SizeSpec, device: DeviceSpec) -> FrameGeometry:
    W, H = size.width, size.height

    bx = int(W * device.body_inset_x_ratio)
    by = int(H * device.body_inset_y_ratio)
    body_box = (bx, by, W - bx, H - by)
    body_w = body_box[2] - body_box[0]
    body_h = body_box[3] - body_box[1]
    body_radius = int(body_w * device.corner_radius_ratio)

    sx = int(body_w * device.screen_inset_x_ratio)
    st = int(body_h * device.screen_inset_top_ratio)
    sb = int(body_h * device.screen_inset_bottom_ratio)
    screen_box = (
        body_box[0] + sx,
        body_box[1] + st,
        body_box[2] - sx,
        body_box[3] - sb,
    )
    screen_w = screen_box[2] - screen_box[0]
    screen_h = screen_box[3] - screen_box[1]
    screen_radius = int(screen_w * device.screen_corner_radius_ratio)

    island_box = None
    if device.has_dynamic_island:
        iw = int(screen_w * device.island_width_ratio)
        ih = int(screen_h * device.island_height_ratio)
        ih = max(ih, 20)
        cx = (screen_box[0] + screen_box[2]) // 2
        iy = screen_box[1] + int(screen_h * 0.015)
        island_box = (cx - iw // 2, iy, cx + iw // 2, iy + ih)

    home_btn_center = None
    home_btn_radius = 0
    if device.has_home_button:
        home_btn_radius = int(body_w * device.home_btn_radius_ratio)
        hx = (body_box[0] + body_box[2]) // 2
        hy = body_box[3] - int((body_box[3] - screen_box[3]) * 0.5)
        home_btn_center = (hx, hy)

    btn_w = max(int(bx * 0.6), 4)
    btn_h = int(body_h * 0.08)
    btn_gap = int(body_h * 0.04)
    vol_top = body_box[1] + int(body_h * 0.30)
    side_buttons = []
    side_buttons.append((
        body_box[2], body_box[1] + int(body_h * 0.25),
        body_box[2] + btn_w, body_box[1] + int(body_h * 0.25) + int(btn_h * 1.5),
    ))
    side_buttons.append((
        body_box[0] - btn_w, vol_top,
        body_box[0], vol_top + btn_h,
    ))
    side_buttons.append((
        body_box[0] - btn_w, vol_top + btn_h + btn_gap,
        body_box[0], vol_top + btn_h * 2 + btn_gap,
    ))

    return FrameGeometry(
        body_box=body_box,
        screen_box=screen_box,
        body_radius=body_radius,
        screen_radius=screen_radius,
        island_box=island_box,
        home_btn_center=home_btn_center,
        home_btn_radius=home_btn_radius,
        side_buttons=side_buttons,
    )


def _resolve_frame_color(frame_color: str, bg_luminance: float) -> tuple[str, str]:
    if frame_color == "auto":
        if bg_luminance > 128:
            return "#1a1a1a", "#333333"
        else:
            return "#f0f0f0", "#cccccc"
    if frame_color == "white":
        return "#f5f5f5", "#cccccc"
    if frame_color == "black":
        return "#1a1a1a", "#333333"
    return frame_color, frame_color


def _scale_box(box: tuple[int, int, int, int], s: int) -> tuple[int, int, int, int]:
    return (box[0] * s, box[1] * s, box[2] * s, box[3] * s)


def draw_frame(
    canvas: Image.Image,
    geometry: FrameGeometry,
    device: DeviceSpec,
    frame_color: str,
    bg_luminance: float,
) -> None:
    W, H = canvas.size
    S = SUPERSAMPLE
    overlay = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    body_color, border_color = _resolve_frame_color(frame_color, bg_luminance)

    body2 = _scale_box(geometry.body_box, S)
    br2 = geometry.body_radius * S

    draw.rounded_rectangle(body2, radius=br2, fill=body_color, outline=border_color, width=max(2, S))

    if geometry.island_box:
        isl2 = _scale_box(geometry.island_box, S)
        isl_r = (isl2[3] - isl2[1]) // 2
        draw.rounded_rectangle(isl2, radius=isl_r, fill="#111111")

    if geometry.home_btn_center:
        hc = (geometry.home_btn_center[0] * S, geometry.home_btn_center[1] * S)
        hr = geometry.home_btn_radius * S
        draw.ellipse(
            (hc[0] - hr, hc[1] - hr, hc[0] + hr, hc[1] + hr),
            fill=body_color,
            outline=border_color,
            width=max(2, S),
        )
        inner = int(hr * 0.65)
        draw.ellipse(
            (hc[0] - inner, hc[1] - inner, hc[0] + inner, hc[1] + inner),
            fill=border_color,
        )

    btn_radius = max(2, S * 2)
    for btn in geometry.side_buttons:
        btn2 = _scale_box(btn, S)
        draw.rounded_rectangle(btn2, radius=btn_radius, fill=body_color, outline=border_color, width=max(1, S))

    overlay = overlay.resize((W, H), Image.LANCZOS)
    canvas.alpha_composite(overlay)


def make_screen_mask(screen_box: tuple[int, int, int, int], radius: int, canvas_size: tuple[int, int]) -> Image.Image:
    mask = Image.new("L", canvas_size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(screen_box, radius=radius, fill=255)
    return mask
