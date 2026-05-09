# appshot — 앱스토어 스크린샷 생성 CLI 도구

## Context
앱 배포 시 Apple App Store, Google Play, Samsung Galaxy Store 각각 요구하는 엄격한 픽셀 규격의 PNG 스크린샷이 필요하다. 현재는 이를 수작업으로 준비해야 하므로, 원본 스크린샷 + 간단한 YAML 설정만으로 모든 플랫폼 규격 이미지를 자동 생성해주는 CLI 도구를 만든다.

---

## 최종 결과물

```bash
appshot build            # YAML 기반 전체 빌드
appshot build -p apple_iphone  # 특정 플랫폼만
appshot init             # 샘플 config 생성
appshot list-sizes       # 지원 플랫폼/사이즈 목록 출력
```

출력 구조:
```
output/
  apple_iphone/
    01_home_iphone_69.png   (1320×2868)
    01_home_iphone_65.png   (1242×2688)
    01_home_iphone_55.png   (1242×2208)
  apple_ipad/
    01_home_ipad_13.png     (2064×2752)
  google_phone/
    01_home_phone.png       (1080×1920)
  samsung_phone/
    01_home_galaxy.png      (1080×2340)
```

---

## 지원 플랫폼 규격

| platform_id | 사이즈 | 필수 |
|---|---|---|
| apple_iphone | 6.9" 1320×2868, 6.5" 1242×2688, 5.5" 1242×2208 | ✅ |
| apple_ipad | 13" 2064×2752, 12.9" 2048×2732, 11" 1668×2388 | ✅ |
| google_phone | 1080×1920 | ✅ |
| google_tablet_7 | 1080×1920 | |
| google_tablet_10 | 1280×1920 | |
| google_feature_graphic | 1024×500 (가로 배너) | |
| samsung_phone | 1080×2340 | |
| samsung_tab | 1600×2560 | |

---

## 프로젝트 구조

```
app-screen-shot/
├── src/appshot/
│   ├── __init__.py
│   ├── cli.py          # Click CLI (init, build, list-sizes)
│   ├── builder.py      # 빌드 오케스트레이션
│   ├── renderer.py     # 이미지 합성 (배경, 스크린샷 피팅, 텍스트)
│   ├── frames.py       # 디바이스 프레임 프로그래매틱 드로잉
│   ├── platforms.py    # 플랫폼 스펙 데이터
│   ├── config.py       # YAML 파싱 & 검증
│   └── fonts/
│       └── Inter-Regular.ttf   # 번들 폰트
├── example/
│   └── screenshots.yaml
├── pyproject.toml
├── requirements.txt
└── plan.md
```

---

## YAML 설정 스키마

```yaml
defaults:
  frame_color: auto        # auto | white | black | "#hex"
  font_size: 80            # px (최종 출력 해상도 기준)
  text_position: bottom    # top | bottom
  fit_mode: contain        # contain (레터박스) | cover (크롭)
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
      direction: vertical     # vertical | horizontal | diagonal
      colors: ["#1e1b4b", "#4338ca"]
```

---

## 렌더링 파이프라인 (스크린샷 1장 × 사이즈 1개)

```
1. 캔버스 생성 (SizeSpec.width × height, RGBA)
2. 배경 렌더링 (solid color 또는 gradient)
3. 디바이스 프레임 지오메트리 계산
     body_rect  = 캔버스 inset 4%/3%
     screen_rect = body_rect에서 추가 inset
4. 스크린샷 피팅 → screen_rect에 contain/cover
     → 라운드 코너 마스크 적용 후 합성
5. 디바이스 프레임 드로잉 (Pillow, 2× 수퍼샘플링 후 다운스케일)
     - rounded_rectangle (body)
     - dynamic island 또는 home button
     - 사이드 버튼
6. 텍스트 오버레이
     - 텍스트 영역: body 위/아래 빈 공간
     - word wrap + 세로 중앙 정렬
     - auto color = 배경 휘도 기반 흑/백
7. RGBA → RGB 변환 후 PNG 저장
```

---

## 핵심 구현 포인트

### 디바이스 프레임 (frames.py)
- 외부 에셋 없음, 100% Pillow `ImageDraw`로 직접 드로잉
- 2× 수퍼샘플 레이어에 그린 후 LANCZOS 다운스케일 → 안티앨리어싱
- 프레임 색상 `auto`: 배경 휘도 > 128이면 dark(`#1a1a1a`), 아니면 light(`#f0f0f0`)
- iPhone 6.9"/6.5" → Dynamic Island (pill 모양, 화면 상단 중앙)
- iPhone 5.5" → Home button (하단 원형)

### 그라데이션 (renderer.py)
- vertical/horizontal: 라인 단위 `draw.line` → O(H) or O(W), 충분히 빠름
- diagonal: 1/8 해상도로 렌더 후 BILINEAR 업스케일 (64× 빠름)
- 색상 보간: `interpolate_color(colors, stops, t)` → RGB 선형 보간

### 텍스트 (renderer.py)
- 폰트 탐색 순서: config 지정 → macOS 시스템 폰트 → 번들 Inter → PIL default
- `ImageDraw.textbbox`로 측정 후 word wrap
- 드롭섀도우: 오프셋 2px, Gaussian blur r=4, alpha 60%

### 에러 처리
- `ConfigError` (YAML 검증 실패) → exit code 1
- `InputError` (이미지 파일 없음/손상) → 경고 후 계속, exit code 3
- `OutputError` (쓰기 권한 없음) → exit code 2
- 부분 실패 허용: 성공한 파일은 저장, 마지막에 에러 요약 출력

---

## 기술 스택

```toml
[project]
name = "appshot"
requires-python = ">=3.11"
dependencies = [
    "Pillow>=10.0.0",
    "click>=8.1.0",
    "PyYAML>=6.0",
]

[project.scripts]
appshot = "appshot.cli:main"
```

의존성 최소화: NumPy 없음, 외부 프레임 에셋 없음, 순수 Pillow + Click + PyYAML

---

## 구현 순서

1. `platforms.py` — 데이터만, 의존성 없음
2. `config.py` — YAML 파싱, platforms 검증
3. `frames.py` — Pillow 프레임 드로잉, 독립 테스트 가능
4. `renderer.py` — 배경/피팅/텍스트/프레임 합성
5. `builder.py` — (screenshot × platform × size) 루프 오케스트레이션
6. `cli.py` — Click 진입점, 에러 출력, 프로그레스바

---

## 검증 방법

```bash
# 설치
pip install -e .

# 샘플 config 생성
appshot init

# 빌드
appshot build -c example/screenshots.yaml

# 특정 플랫폼만
appshot build -p apple_iphone
appshot build -p google_phone

# 사이즈 목록
appshot list-sizes

# 출력 크기 확인
python3 -c "from PIL import Image; img=Image.open('output/apple_iphone/01_home_iphone_69.png'); print(img.size)"
# → (1320, 2868)
```
