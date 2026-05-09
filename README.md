# appshot

앱스토어 배포에 필요한 스크린샷을 자동으로 생성하는 CLI 도구입니다.

원본 앱 스크린샷과 간단한 YAML 설정 파일만으로, Apple App Store · Google Play · Samsung Galaxy Store에서 요구하는 규격의 PNG 파일을 일괄 생성합니다.

---

## 주요 기능

- **디바이스 프레임 자동 합성** — iPhone (Dynamic Island / Home Button), iPad, Android 프레임을 코드로 직접 드로잉
- **배경 커스터마이징** — 단색 또는 그라데이션 (vertical / horizontal / diagonal)
- **텍스트 오버레이** — 캡션 자동 줄바꿈, 드롭섀도우, 배경 밝기에 따른 자동 색상
- **전 플랫폼 지원** — Apple / Google / Samsung 8개 플랫폼 규격 내장
- **외부 에셋 불필요** — Pillow 하나로 모든 렌더링 처리

---

## 지원 플랫폼

| 플랫폼 | 사이즈 | 필수 |
|---|---|---|
| Apple iPhone | 6.9" 1320×2868, 6.5" 1242×2688, 5.5" 1242×2208 | ✅ |
| Apple iPad | 13" 2064×2752, 12.9" 2048×2732, 11" 1668×2388 | ✅ |
| Google Play Phone | 1080×1920 | ✅ |
| Google Play 7" Tablet | 1080×1920 | |
| Google Play 10" Tablet | 1280×1920 | |
| Google Play Feature Graphic | 1024×500 | |
| Samsung Galaxy Phone | 1080×2340 | |
| Samsung Galaxy Tab | 1600×2560 | |

---

## 설치

**Python 3.11 이상** 필요

```bash
git clone https://github.com/qpyu66/app-screenshot.git
cd app-screenshot

python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -e .
```

---

## 빠른 시작

### 1. 설정 파일 생성

```bash
appshot init
```

`screenshots.yaml` 파일이 생성됩니다.

### 2. 스크린샷 준비

`./screens/` 폴더에 앱 스크린샷(PNG/JPG)을 넣습니다.

### 3. 설정 편집

```yaml
defaults:
  frame_color: auto      # auto | white | black | "#hex"
  font_size: 80
  text_position: bottom  # top | bottom
  fit_mode: contain      # contain | cover
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
```

### 4. 빌드

```bash
appshot build
```

`./output/` 폴더에 플랫폼별로 PNG 파일이 생성됩니다.

```
output/
  apple_iphone/
    01_home_iphone_69.png   (1320×2868)
    01_home_iphone_65.png   (1242×2688)
    01_home_iphone_55.png   (1242×2208)
    02_search_iphone_69.png
    ...
  apple_ipad/
    01_home_ipad_13.png     (2064×2752)
    ...
  google_phone/
    01_home_phone.png       (1080×1920)
  samsung_phone/
    01_home_galaxy.png      (1080×2340)
```

---

## CLI 명령어

```bash
# 전체 빌드
appshot build

# 설정 파일 지정
appshot build -c path/to/screenshots.yaml

# 특정 플랫폼만 빌드
appshot build -p apple_iphone
appshot build -p google_phone

# 샘플 설정 파일 생성
appshot init

# 지원 플랫폼 및 사이즈 목록
appshot list-sizes
```

---

## 설정 옵션

### `defaults`

| 키 | 기본값 | 설명 |
|---|---|---|
| `frame_color` | `auto` | 디바이스 프레임 색상. `auto`는 배경 밝기에 따라 자동 선택 |
| `font_size` | `80` | 캡션 폰트 크기 (px, 최종 출력 해상도 기준) |
| `text_position` | `bottom` | 캡션 위치. `top` 또는 `bottom` |
| `fit_mode` | `contain` | 스크린샷 피팅 방식. `contain`(레터박스) 또는 `cover`(크롭) |
| `output_dir` | `./output` | 출력 폴더 경로 |

### `screenshots` 항목별 옵션

| 키 | 설명 |
|---|---|
| `input` | 원본 스크린샷 경로 (필수) |
| `caption` | 표시할 텍스트 |
| `caption_position` | `top` / `bottom` (defaults 값 덮어쓰기) |
| `caption_font_size` | 이 슬라이드만 폰트 크기 지정 |
| `caption_color` | `auto` 또는 `"#hex"` |
| `fit_mode` | `contain` / `cover` |
| `background.type` | `solid` 또는 `gradient` |
| `background.color` | 단색 배경 hex 값 |
| `background.colors` | 그라데이션 색상 배열 |
| `background.direction` | `vertical` / `horizontal` / `diagonal` |
| `background.stops` | 그라데이션 중단점 (0.0 ~ 1.0, colors와 동일 길이) |

---

## 의존성

```
Pillow >= 10.0.0
click  >= 8.1.0
PyYAML >= 6.0
```

---

## 라이선스

MIT
