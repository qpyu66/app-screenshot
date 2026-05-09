from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class SizeSpec:
    width: int
    height: int
    name: str
    label: str
    required: bool = False
    device_override: "DeviceSpec | None" = field(default=None, compare=False)


@dataclass(frozen=True)
class DeviceSpec:
    form_factor: Literal["iphone_modern", "iphone_legacy", "ipad", "android_phone", "android_tablet"]
    body_inset_x_ratio: float = 0.04
    body_inset_y_ratio: float = 0.03
    screen_inset_x_ratio: float = 0.02
    screen_inset_top_ratio: float = 0.05
    screen_inset_bottom_ratio: float = 0.05
    corner_radius_ratio: float = 0.09
    screen_corner_radius_ratio: float = 0.07
    has_dynamic_island: bool = False
    has_home_button: bool = False
    island_width_ratio: float = 0.15
    island_height_ratio: float = 0.035
    home_btn_radius_ratio: float = 0.045


@dataclass(frozen=True)
class PlatformSpec:
    platform_id: str
    store: str
    label: str
    sizes: tuple[SizeSpec, ...]
    device: DeviceSpec


_iphone_modern = DeviceSpec(
    form_factor="iphone_modern",
    body_inset_x_ratio=0.04,
    body_inset_y_ratio=0.025,
    screen_inset_x_ratio=0.015,
    screen_inset_top_ratio=0.04,
    screen_inset_bottom_ratio=0.04,
    corner_radius_ratio=0.09,
    screen_corner_radius_ratio=0.075,
    has_dynamic_island=True,
    has_home_button=False,
    island_width_ratio=0.15,
    island_height_ratio=0.034,
)

_iphone_legacy = DeviceSpec(
    form_factor="iphone_legacy",
    body_inset_x_ratio=0.04,
    body_inset_y_ratio=0.025,
    screen_inset_x_ratio=0.015,
    screen_inset_top_ratio=0.12,
    screen_inset_bottom_ratio=0.16,
    corner_radius_ratio=0.08,
    screen_corner_radius_ratio=0.03,
    has_dynamic_island=False,
    has_home_button=True,
    home_btn_radius_ratio=0.045,
)

_ipad = DeviceSpec(
    form_factor="ipad",
    body_inset_x_ratio=0.03,
    body_inset_y_ratio=0.02,
    screen_inset_x_ratio=0.015,
    screen_inset_top_ratio=0.05,
    screen_inset_bottom_ratio=0.05,
    corner_radius_ratio=0.05,
    screen_corner_radius_ratio=0.02,
    has_dynamic_island=False,
    has_home_button=False,
)

_android_phone = DeviceSpec(
    form_factor="android_phone",
    body_inset_x_ratio=0.04,
    body_inset_y_ratio=0.025,
    screen_inset_x_ratio=0.015,
    screen_inset_top_ratio=0.04,
    screen_inset_bottom_ratio=0.04,
    corner_radius_ratio=0.10,
    screen_corner_radius_ratio=0.08,
    has_dynamic_island=True,
    island_width_ratio=0.10,
    island_height_ratio=0.028,
    has_home_button=False,
)

_android_tablet = DeviceSpec(
    form_factor="android_tablet",
    body_inset_x_ratio=0.03,
    body_inset_y_ratio=0.02,
    screen_inset_x_ratio=0.012,
    screen_inset_top_ratio=0.04,
    screen_inset_bottom_ratio=0.04,
    corner_radius_ratio=0.04,
    screen_corner_radius_ratio=0.02,
    has_dynamic_island=False,
    has_home_button=False,
)


PLATFORM_REGISTRY: dict[str, PlatformSpec] = {
    "apple_iphone": PlatformSpec(
        platform_id="apple_iphone",
        store="apple",
        label="Apple App Store (iPhone)",
        device=_iphone_modern,
        sizes=(
            SizeSpec(1320, 2868, "iphone_69", 'iPhone 6.9"', required=True),
            SizeSpec(1242, 2688, "iphone_65", 'iPhone 6.5"', required=True),
            SizeSpec(1242, 2208, "iphone_55", 'iPhone 5.5"', required=True, device_override=_iphone_legacy),
        ),
    ),
    "apple_ipad": PlatformSpec(
        platform_id="apple_ipad",
        store="apple",
        label="Apple App Store (iPad)",
        device=_ipad,
        sizes=(
            SizeSpec(2064, 2752, "ipad_13", 'iPad Pro 13"', required=True),
            SizeSpec(2048, 2732, "ipad_129", 'iPad Pro 12.9"'),
            SizeSpec(1668, 2388, "ipad_11", 'iPad Pro 11"'),
        ),
    ),
    "google_phone": PlatformSpec(
        platform_id="google_phone",
        store="google",
        label="Google Play Store (Phone)",
        device=_android_phone,
        sizes=(
            SizeSpec(1080, 1920, "phone", "Phone", required=True),
        ),
    ),
    "google_tablet_7": PlatformSpec(
        platform_id="google_tablet_7",
        store="google",
        label="Google Play Store (7\" Tablet)",
        device=_android_tablet,
        sizes=(
            SizeSpec(1080, 1920, "tablet_7", '7" Tablet'),
        ),
    ),
    "google_tablet_10": PlatformSpec(
        platform_id="google_tablet_10",
        store="google",
        label="Google Play Store (10\" Tablet)",
        device=_android_tablet,
        sizes=(
            SizeSpec(1280, 1920, "tablet_10", '10" Tablet'),
        ),
    ),
    "google_feature_graphic": PlatformSpec(
        platform_id="google_feature_graphic",
        store="google",
        label="Google Play Store (Feature Graphic)",
        device=_android_phone,
        sizes=(
            SizeSpec(1024, 500, "feature_graphic", "Feature Graphic"),
        ),
    ),
    "samsung_phone": PlatformSpec(
        platform_id="samsung_phone",
        store="samsung",
        label="Samsung Galaxy Store (Phone)",
        device=_android_phone,
        sizes=(
            SizeSpec(1080, 2340, "galaxy_phone", "Galaxy Phone", required=True),
        ),
    ),
    "samsung_tab": PlatformSpec(
        platform_id="samsung_tab",
        store="samsung",
        label="Samsung Galaxy Store (Tab)",
        device=_android_tablet,
        sizes=(
            SizeSpec(1600, 2560, "galaxy_tab", "Galaxy Tab"),
        ),
    ),
}


def list_sizes() -> str:
    lines = []
    for pid, spec in PLATFORM_REGISTRY.items():
        lines.append(f"\n{spec.label}  [{pid}]")
        for s in spec.sizes:
            req = " *" if s.required else "  "
            lines.append(f"  {req} {s.label:<20} {s.width}×{s.height}  ({s.name})")
    lines.append("\n  * = required by store")
    return "\n".join(lines)
