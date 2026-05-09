from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import AppShotConfig, ScreenshotConfig
from .platforms import PLATFORM_REGISTRY, PlatformSpec, SizeSpec
from .renderer import InputError, render_screenshot


class OutputError(Exception):
    pass


@dataclass
class BuildResult:
    succeeded: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return len(self.succeeded)

    @property
    def fail_count(self) -> int:
        return len(self.failed)


def _output_path(
    output_dir: Path,
    platform_id: str,
    shot_index: int,
    shot: ScreenshotConfig,
    size: SizeSpec,
) -> Path:
    stem = shot.input.stem
    filename = f"{shot_index + 1:02d}_{stem}_{size.name}.png"
    return output_dir / platform_id / filename


def build(
    config: AppShotConfig,
    platform_filter: str | None = None,
    progress_cb=None,
) -> BuildResult:
    output_dir = Path(config.defaults.output_dir)
    if not output_dir.is_absolute():
        output_dir = config.config_path.parent / output_dir

    platforms = config.platforms
    if platform_filter:
        if platform_filter not in PLATFORM_REGISTRY:
            known = ", ".join(PLATFORM_REGISTRY.keys())
            raise ValueError(f"Unknown platform {platform_filter!r}. Known: {known}")
        platforms = [platform_filter]

    tasks: list[tuple[int, ScreenshotConfig, PlatformSpec, SizeSpec]] = []
    for pid in platforms:
        spec = PLATFORM_REGISTRY[pid]
        for shot_i, shot in enumerate(config.screenshots):
            for size in spec.sizes:
                tasks.append((shot_i, shot, spec, size))

    result = BuildResult()

    for shot_i, shot, spec, size in tasks:
        out_path = _output_path(output_dir, spec.platform_id, shot_i, shot, size)
        label = f"{spec.platform_id}/{out_path.name}"

        if progress_cb:
            progress_cb(label)

        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise OutputError(f"Cannot create output directory {out_path.parent}: {e}") from e

        try:
            img = render_screenshot(shot, size, spec, config.defaults)
            img.save(str(out_path), "PNG", optimize=False)
            result.succeeded.append(label)
        except InputError as e:
            result.failed.append((label, str(e)))
        except OSError as e:
            result.failed.append((label, f"Write error: {e}"))

    return result
