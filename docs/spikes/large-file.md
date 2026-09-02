# W2-06 대용량 / WASM OOM 실측과 기본 변환기 결정

작성 2026-09-02 · 브랜치 `task/W2-06` · 재현 `node tools/bench-open.mjs` · 원자료 `tools/bench/results-2026-09-02.json`

## 0. 요약

<!-- 0-summary -->

## 1. 측정 환경과 방법

| 항목 | 값 |
|---|---|
| 기기 | Apple Silicon(arm64) macOS 24 GB |
| Node | v24.20.0 (기본 V8 old-space 한도 **4 288 MB**, `v8.getHeapStatistics().heap_size_limit` 실측) |
| Python | 3.12 (uv 0.12.9), ezdxf 1.4.4 |
| Chromium | Playwright 1.62.1 번들, headless, `--use-gl=swiftshader` |
| acad-ts | `@node-projects/acad-ts@3.1.0` (`packages/acad-bridge`, main `1ca713a` 텍스트 디코드 수정 포함) |
| mlightcad | `data-model@1.14.3`, `libredwg-converter@3.14.3`, `libredwg-web@0.7.10` |

측정 경로 (브리프 (a)~(d)):

| 경로 키 | 내용 | 구현 |
|---|---|---|
| `browser` | (a) headless Chromium. DWG는 libredwg-web WASM 워커, DXF는 data-model 내장 리더. 이어서 `dxfOut()`으로 DXF 산출 | `spikes/mlightcad/bench.html` + `src/bench.ts` + `scripts/bench-browser.mjs` |
| `acad` | (b) Node utilityProcess 상당. DWG 입력이면 `acad-bridge dwg2dxf`, DXF 입력이면 `acad-bridge stats`(읽기 전용 오픈) | `packages/acad-bridge/bin/acad-bridge.mjs` |
| `dxfout` | (c) Node CJS `@mlightcad/data-model` → `AcDbDatabase.dxfOut()` | `spikes/mlightcad/scripts/bench-dxfout.cjs` |
| `engine` | (추가) 엔진 ezdxf 읽기 비용. 변환기는 아니지만 "엔진 전용" 티어 임계값의 근거 | `uv run halo-engine stats` |
| `native` | (d) 네이티브 LibreDWG `dwg2dxf` | **미측정 — 사용자 Homebrew 설치 시 재측정**(`brew install libredwg`, no `sudo` 정책상 이 태스크에서 설치하지 않음) |

- **시간·피크 RSS**: Node/Python 프로세스는 `/usr/bin/time -l`의 `real` / `maximum resident set size`.
  Chromium은 `chromium.launchServer()`가 주는 브라우저 프로세스 pid를 뿌리로 **프로세스 트리 전체**(브라우저+렌더러+GPU+워커 유틸리티)의 RSS를 150 ms 간격으로 `ps -axo pid=,ppid=,rss=` 샘플링해 최댓값을 쓴다.
  `performance.memory`는 W1-04에서 고정값(델타 0)으로 확인되어(스파이크 C.12) 쓰지 않는다.
- **반복**: 20 MB 이하 입력은 3회 중앙값, 그보다 크면 1회(`--repeat`/`--repeat-large`).
- **24 GB vs 16 GB**: Node 경로는 `--max-old-space-size`를 바꿔가며 재실행(`--heap`).
  Chromium은 힙 상한을 밖에서 줄 수 없으므로 브리프대로 **파일 크기를 줄여가며** 한계를 찾는다.
- **충실도**: 각 경로가 만든 DXF를 **엔진 `halo-engine stats`(ezdxf)** 로 읽어 `fixtures/truth/<F>.json`
  (`LayerStatsDocument`)과 비교한다. 비교 필드는 `entity_count`, `count_by_type`, `length_sum_mm`(±0.1 %),
  `hatch_area_sum_mm2`(±0.1 %), **`text_count`·`text_hash`**, **`insert_by_block`**, 그리고 (space, layer) 버킷별 일치.
  구현 `tools/bench/compare-stats.mjs`.
- DXF를 만들지 않는 셀(`acad`의 DXF 입력, `engine`)은 그 파서가 **직접 낸 `LayerStatsDocument`** 를 truth와 비교한다.
  DWG 입력의 `acad` 행에는 "parser self-view"(acad-ts가 그 DWG를 읽었을 때의 stats) 열을 따로 둔다.

## 2. 픽스처

| 파일 | 엔티티 | DXF | DWG | 비고 |
|---|---:|---:|---:|---|
| F03 | 21 | 60 KB | 15 KB | 한글 TEXT/MTEXT(`거실`, `실명: 거실\P면적: 23.4㎡`) |
| F06 | 86 | 74 KB | 15 KB | 표제란 INSERT `X-TITLE`(블록명 = 레이어명), ATTRIB 10개 |
| F10_grid | 11 | 59 KB | 14 KB | XREF 대상 도면, `X-TITLE` 동일 문제 |
| F11 | 200 006 | **41.4 MB** | **5.3 MB** | F06 타일 2 353개 복제 |
| F12 | 1 000 026 | **209.3 MB** | (아래 §3.4) | `--large` 로만 생성 |

- **실제 도면 샘플은 없다.** `samples/`는 비어 있고 `.gitignore` 대상이다. 브리프의 "Defaults for ambiguity"에 따라
  합성 픽스처만으로 결정하고, 실제 파일로의 재보정을 G0 질문으로 올린다.
- **DWG 픽스처는 전부 acad-ts가 쓴 것이다**(W2-05 `dxf2dwg`). 즉 DWG 입력 행의 truth 대비 차이에는
  *쓰기* 쪽 결함이 이미 섞여 있다. 그래서 DWG 입력은 "truth 대비"와 "그 DWG 자체 대비" 두 가지로 나눠 읽어야 한다(§4.3).
- F11/F12의 DXF·DWG와 `/tmp/truth-scratch`의 F11/F12 truth는 커밋하지 않는다(`.gitignore`, 브리프).
  F11 truth는 저장소의 `fixtures/truth/F11.json`과 바이트 동일함을 확인했다(생성 결정론).

## 3. 측정표

<!-- 3-tables -->

## 4. 변환 충실도

<!-- 4-fidelity -->

## 5. 결정

<!-- 5-decision -->

## 6. 남은 것

<!-- 6-open -->
