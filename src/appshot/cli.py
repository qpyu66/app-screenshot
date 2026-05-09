from __future__ import annotations

from pathlib import Path

import click

from .builder import OutputError, build
from .config import SAMPLE_CONFIG, ConfigError, load_config
from .platforms import list_sizes


@click.group()
def main():
    """appshot — 앱스토어 스크린샷 자동 생성 도구"""


@main.command()
@click.option("-c", "--config", "config_path", default="screenshots.yaml", show_default=True,
              help="설정 파일 경로")
@click.option("-p", "--platform", "platform_filter", default=None,
              help="특정 플랫폼만 빌드 (예: apple_iphone)")
def build_cmd(config_path: str, platform_filter: str | None):
    """스크린샷 PNG 생성"""
    path = Path(config_path)
    if not path.exists():
        click.echo(click.style(f"설정 파일을 찾을 수 없습니다: {path}", fg="red"), err=True)
        click.echo("  → appshot init 으로 샘플 설정을 생성하세요", err=True)
        raise SystemExit(1)

    try:
        config = load_config(path)
    except ConfigError as e:
        click.echo(click.style(f"설정 오류: {e}", fg="red"), err=True)
        raise SystemExit(1)

    click.echo(f"빌드 시작: 스크린샷 {len(config.screenshots)}장 × 플랫폼 {len(config.platforms)}개")
    click.echo(f"출력 경로: {config.defaults.output_dir}\n")

    completed = 0

    def progress(label: str):
        nonlocal completed
        completed += 1
        click.echo(f"  [{completed:>3}] {label}")

    try:
        result = build(config, platform_filter=platform_filter, progress_cb=progress)
    except OutputError as e:
        click.echo(click.style(f"\n출력 오류: {e}", fg="red"), err=True)
        raise SystemExit(2)
    except ValueError as e:
        click.echo(click.style(f"\n오류: {e}", fg="red"), err=True)
        raise SystemExit(1)

    click.echo()
    if result.fail_count == 0:
        click.echo(click.style(f"완료: {result.success_count}개 파일 생성", fg="green"))
    else:
        click.echo(click.style(
            f"완료: {result.success_count}개 성공, {result.fail_count}개 실패", fg="yellow"
        ))
        for label, err in result.failed:
            click.echo(click.style(f"  실패: {label} — {err}", fg="red"), err=True)
        raise SystemExit(3)


main.add_command(build_cmd, name="build")


@main.command()
@click.option("-o", "--output", default="screenshots.yaml", show_default=True,
              help="생성할 설정 파일 경로")
def init(output: str):
    """샘플 설정 파일(screenshots.yaml) 생성"""
    out = Path(output)
    if out.exists():
        click.confirm(f"{out} 이미 존재합니다. 덮어쓰겠습니까?", abort=True)
    out.write_text(SAMPLE_CONFIG, encoding="utf-8")
    click.echo(click.style(f"생성됨: {out}", fg="green"))
    click.echo("\n다음 단계:")
    click.echo("  1. ./screens/ 폴더에 앱 스크린샷을 넣으세요")
    click.echo("  2. screenshots.yaml 을 편집하여 캡션과 배경을 설정하세요")
    click.echo("  3. appshot build 를 실행하세요")


@main.command(name="list-sizes")
def list_sizes_cmd():
    """지원 플랫폼 및 이미지 사이즈 목록"""
    click.echo(list_sizes())


if __name__ == "__main__":
    main()
