from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

from .platforms import PLATFORM_REGISTRY


class ConfigError(Exception):
    pass


@dataclass
class BackgroundConfig:
    type: Literal["solid", "gradient"] = "solid"
    color: str = "#6366f1"
    colors: list[str] = field(default_factory=list)
    stops: list[float] = field(default_factory=list)
    direction: str = "vertical"


@dataclass
class ScreenshotConfig:
    input: Path
    caption: str = ""
    caption_position: str = "bottom"
    caption_font_size: int | None = None
    caption_color: str = "auto"
    fit_mode: str = "contain"
    background: BackgroundConfig = field(default_factory=BackgroundConfig)


@dataclass
class GlobalDefaults:
    frame_color: str = "auto"
    font: str | None = None
    font_size: int = 80
    text_color: str = "auto"
    text_align: str = "center"
    text_position: str = "bottom"
    fit_mode: str = "contain"
    output_dir: str = "./output"


@dataclass
class AppShotConfig:
    defaults: GlobalDefaults
    platforms: list[str]
    screenshots: list[ScreenshotConfig]
    config_path: Path


def _parse_background(raw: dict | str | None) -> BackgroundConfig:
    if raw is None:
        return BackgroundConfig()
    if isinstance(raw, str):
        return BackgroundConfig(type="solid", color=raw)
    bg_type = raw.get("type", "solid")
    if bg_type == "solid":
        return BackgroundConfig(type="solid", color=raw.get("color", "#6366f1"))
    if bg_type == "gradient":
        colors = raw.get("colors", ["#6366f1", "#8b5cf6"])
        stops = raw.get("stops", [i / (len(colors) - 1) for i in range(len(colors))])
        if len(stops) != len(colors):
            raise ConfigError("'stops' length must match 'colors' length")
        return BackgroundConfig(
            type="gradient",
            colors=colors,
            stops=stops,
            direction=raw.get("direction", "vertical"),
        )
    raise ConfigError(f"Unknown background type: {bg_type!r}")


def _validate_hex(color: str, field_name: str) -> None:
    if color in ("auto",):
        return
    if not (color.startswith("#") and len(color) in (4, 7)):
        raise ConfigError(f"{field_name}: invalid hex color {color!r}")


def load_config(path: Path) -> AppShotConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML parse error: {e}") from e
    except OSError as e:
        raise ConfigError(f"Cannot read config: {e}") from e

    if not isinstance(raw, dict):
        raise ConfigError("Config must be a YAML mapping")

    base_dir = path.parent

    # Defaults
    raw_defaults = raw.get("defaults", {}) or {}
    defaults = GlobalDefaults(
        frame_color=raw_defaults.get("frame_color", "auto"),
        font=raw_defaults.get("font"),
        font_size=int(raw_defaults.get("font_size", 80)),
        text_color=raw_defaults.get("text_color", "auto"),
        text_align=raw_defaults.get("text_align", "center"),
        text_position=raw_defaults.get("text_position", "bottom"),
        fit_mode=raw_defaults.get("fit_mode", "contain"),
        output_dir=raw_defaults.get("output_dir", "./output"),
    )

    # Platforms
    raw_platforms = raw.get("platforms") or list(PLATFORM_REGISTRY.keys())
    platforms: list[str] = []
    for pid in raw_platforms:
        if pid not in PLATFORM_REGISTRY:
            known = ", ".join(PLATFORM_REGISTRY.keys())
            raise ConfigError(f"Unknown platform {pid!r}. Known: {known}")
        platforms.append(pid)

    # Screenshots
    raw_shots = raw.get("screenshots")
    if not raw_shots:
        raise ConfigError("'screenshots' list is required and must not be empty")

    screenshots: list[ScreenshotConfig] = []
    for i, s in enumerate(raw_shots):
        if "input" not in s:
            raise ConfigError(f"screenshots[{i}]: missing 'input' field")
        input_path = Path(s["input"])
        if not input_path.is_absolute():
            input_path = base_dir / input_path
        if not input_path.exists():
            raise ConfigError(f"screenshots[{i}]: input file not found: {input_path}")

        bg = _parse_background(s.get("background"))
        screenshots.append(ScreenshotConfig(
            input=input_path,
            caption=s.get("caption", ""),
            caption_position=s.get("caption_position", defaults.text_position),
            caption_font_size=s.get("caption_font_size"),
            caption_color=s.get("caption_color", defaults.text_color),
            fit_mode=s.get("fit_mode", defaults.fit_mode),
            background=bg,
        ))

    return AppShotConfig(
        defaults=defaults,
        platforms=platforms,
        screenshots=screenshots,
        config_path=path,
    )


SAMPLE_CONFIG = """\
defaults:
  frame_color: auto        # auto | white | black | "#hex"
  font_size: 80
  text_position: bottom    # top | bottom
  fit_mode: contain        # contain | cover
  output_dir: ./output

platforms:
  - apple_iphone
  - apple_ipad
  - google_phone
  - samsung_phone

screenshots:
  - input: ./screens/home.png
    caption: "모든 것이 한 곳에"
    background:
      type: solid
      color: "#4f46e5"

  - input: ./screens/search.png
    caption: "빠른 검색"
    caption_position: top
    background:
      type: gradient
      direction: vertical
      colors:
        - "#1e1b4b"
        - "#4338ca"

  - input: ./screens/profile.png
    caption: "나만의 프로필"
    background:
      type: solid
      color: "#f8fafc"
    caption_color: "#1e293b"
"""
