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

시간은 프로세스 전체 wall time(`/usr/bin/time -l`의 `real`)이고, 브라우저는 파싱+`dxfOut()` 구간이다.
피크 RSS는 프로세스(브라우저는 Chromium 프로세스 트리)의 최댓값이다. **실패도 값으로 적는다.**

### 3.1 소형 픽스처 (F03·F06·F10_grid, 3회 중앙값, 24 GB·기본 힙)

| 파일 | 경로 | 시간 | 피크 RSS | 결과 |
|---|---|---:|---:|---|
| F03.dxf (60 KB) | acad (stats) | 0.2 s | 117 MB | ok · truth 완전 일치 |
| F03.dxf | dxfout | 0.1 s | 73 MB | ok · truth 완전 일치 |
| F03.dxf | engine (ezdxf) | 0.4 s | 239 MB | ok · truth 완전 일치 |
| F03.dxf | browser | 0.04 s | 355 MB | ok · truth 완전 일치 |
| F03.dwg (15 KB) | acad (dwg2dxf) | 0.2 s | 116 MB | 변환 ok, **엔진이 산출물 읽기 실패**(`ZeroDivisionError`) |
| F03.dwg | dxfout | 0.03 s | 60 MB | **실패**: `Worker is not defined` (Node에 Web Worker 없음) |
| F03.dwg | browser | 0.3 s | 446 MB | 변환 ok, **엔진이 산출물 읽기 실패**(`ZeroDivisionError`, §4.3) |
| F06.dwg (15 KB) | acad (dwg2dxf) | 0.2 s | 118 MB | 변환 ok, **엔진 읽기 실패**(`AttributeError`) |
| F06.dwg | browser | 0.4 s | 452 MB | ok · SEQEND 7 여분, ATTRIB 10 유실, 해치 부호 |
| F06.dxf (74 KB) | acad (stats) | 0.2 s | 118 MB | ok · `insert_by_block`이 `<unresolved>` |
| F06.dxf | dxfout | 0.1 s | 74 MB | ok · SEQEND 8 여분, ATTRIB 10 유실, 해치 부호 |
| F06.dxf | engine | 0.3 s | 172 MB | ok · truth 완전 일치 |
| F06.dxf | browser | 0.04 s | 354 MB | ok · dxfout와 동일 |
| F10_grid.dwg | acad (dwg2dxf) | 0.2 s | 117 MB | 변환 ok, **엔진 읽기 실패**(`AttributeError`) |
| F10_grid.dwg | browser | 0.2 s | 445 MB | ok · INSERT 5/6, ATTRIB 7 유실 |
| F10_grid.dxf | acad (stats) | 0.2 s | 117 MB | ok · `<unresolved>` |
| F10_grid.dxf | dxfout | 0.1 s | 73 MB | ok · SEQEND 6 여분, ATTRIB 7 유실 |
| F10_grid.dxf | engine | 0.3 s | 172 MB | ok · truth 완전 일치 |

브라우저 기준선(빈 bench 페이지 + 워커 등록만): **Chromium 프로세스 트리 약 348 MB.**
즉 위 브라우저 행의 "순수 도면 비용"은 RSS − 348 MB다(F06.dwg ≈ 104 MB).

### 3.2 F11 — 200 006 엔티티 (DXF 41.4 MB / DWG 5.3 MB)

| 파일 | 경로 | 힙 | 시간 | 피크 RSS | 결과 |
|---|---|---|---:|---:|---|
| F11.dxf | acad (stats) | 기본 | 3.3 s | 1 206 MB | ok · `<unresolved>` 1건 |
| F11.dxf | acad (stats) | 2048 MB | 3.2 s | 1 202 MB | ok |
| F11.dxf | acad (stats) | 1024 MB | 3.3 s | 1 120 MB | ok |
| F11.dxf | dxfout | 기본 | 1.5 s (파싱 763 ms + `dxfOut` 622 ms) | 1 440 MB | ok · 48.4 MB 출력 |
| F11.dxf | dxfout | 2048 MB | 1.5 s | 1 389 MB | ok |
| F11.dxf | dxfout | 1024 MB | 1.6 s | 1 257 MB | ok |
| F11.dxf | engine (ezdxf) | — | 15.5 s | 580 MB | ok · truth 완전 일치 |
| F11.dxf | browser | Chromium 기본 | 1.2 s | 1 433 MB | ok · 48.4 MB 출력 |
| F11.dwg | acad (dwg2dxf) | 기본 | 15.7 s | 2 271 MB | 변환 ok(60 MB DXF), **엔진 읽기 실패** |
| F11.dwg | dxfout | 기본 | 0.03 s | 70 MB | **실패**: `Worker is not defined` |
| F11.dwg | browser | Chromium 기본 | 0.8 s | 704 MB | **조용한 손실: 200 006개 중 85개만 읽힘**(§4.4) |
| F11.dxf → DWG | acad (`dxf2dwg`, 픽스처 생성용) | 16 GB | **358 s** | 1 251 MB | ok(5.3 MB DWG). 쓰기가 읽기보다 23배 느리다 |

- **1024 MB old-space 상한에서도 두 Node 경로 모두 20만 엔티티를 처리한다.** 즉 16 GB 기기(기본 힙이 이 Mac의
  4 288 MB보다 작다)에서도 20만 엔티티 DXF는 문제가 아니다.
- ezdxf는 **가장 느리지만 가장 가볍다**(580 MB, 2.9 KB/엔티티). JS 쪽은 6–7 KB/엔티티다.

### 3.3 F12 — 1 000 026 엔티티 (DXF 209.3 MB, DWG 없음)

| 파일 | 경로 | 힙 | 시간 | 피크 RSS | 결과 |
|---|---|---|---:|---:|---|
| F12.dxf | acad (stats) | 기본(4 288 MB) | — | 4 038 MB | **실패: `RangeError: Maximum call stack size exceeded`** (17.2 s 만에) |
| F12.dxf | acad (stats) | **16 384 MB** | — | 4 850 MB | **같은 실패.** 메모리를 4배 줘도 동일 → 힙이 아니라 **재귀 깊이 한계** |
| F12.dxf | dxfout | 기본 | 8.3 s (파싱 3 658 ms + `dxfOut` 4 056 ms) | 4 635 MB | ok · 244.6 MB 출력, 1 000 026 엔티티 전부 |
| F12.dxf | engine (ezdxf) | — | 74.0 s | 2 371 MB | ok · truth 완전 일치 |
| F12.dxf | browser | Chromium 기본 | (아래) | (아래) | (아래) |
| F12.dxf → DWG | acad (`dxf2dwg`) | — | — | — | **미생성.** F11(20만)의 DXF→DWG가 이미 358 s였고, DXF 읽기 자체가 위처럼 실패하므로 시도하지 않았다 |

- **1M 엔티티에서 acad-ts는 메모리가 아니라 스택에서 죽는다.** 20만은 통과, 100만은 힙과 무관하게 실패.
  두 값 사이 어딘가에 고정된 상한이 있고 사용자가 RAM으로 해결할 수 없다.
- `dxfOut()`은 100만 엔티티를 기본 힙 안에서 통과하지만 RSS 4.6 GB다 —
  **16 GB 기기에서 이 크기는 위험 구간**(브라우저 렌더러 힙 상한이 4 GB 근처).

<!-- 3-tables -->

## 4. 변환 충실도

### 4.1 acad-ts가 쓴 DXF는 **엔진이 읽지 못한다** (가장 중요한 발견)

`acad-bridge dwg2dxf`가 만든 DXF를 `halo-engine stats`(ezdxf 1.4.4)로 읽으면 **예외로 죽는다.**

| 픽스처 | 엔진 예외 |
|---|---|
| F06.dwg → DXF | `AttributeError: 'Attrib' object has no attribute 'dxf'` |
| F10_grid.dwg → DXF | `AttributeError: 'Attrib' object has no attribute 'dxf'` |
| F03.dwg → DXF | `ZeroDivisionError: float division` |
| F11.dwg → DXF | (§3 참조) |

원인을 그룹코드 수준까지 좁혔다.

1. **ATTRIB/ATTDEF의 서브클래스 마커와 태그가 틀렸다.**
   acad-ts는 ATTRIB의 두 번째 `100`을 `AcDbAttribute`가 아니라 **`AcDbText`로 두 번** 쓰고
   필수 그룹 `2`(tag)와 `70`(flags)을 빼먹는다.

   ```text
   ezdxf가 쓴 F06.dxf   … 100:AcDbText … 1:X1 … 100:AcDbAttribute 2:LABEL 70:0 …
   acad-ts가 쓴 F06.dxf … 100:AcDbText … 1:X1 … 100:AcDbText 73:0        ← 2(tag) 없음
   ```

   ezdxf 감사기는 `Missing mandatory "tag" attribute, entity ATTRIB(#A0) deleted.` 로 **ATTRIB·ATTDEF 11개를 전부 삭제**하고
   (F06 기준), 삭제된 객체가 `insert.attribs`에 그대로 남아 `entity.dxf` 접근에서 위 `AttributeError`가 난다.
   → **표제란 속성값(도면명·축척·검토자)이 통째로 사라진다.**
2. **MTEXT의 x축 방향 벡터를 `11/21/31 = (0,0,0)`으로 쓴다.** 길이 0 벡터라 ezdxf의 bbox 계산이
   `Vec3.normalize()`에서 `ZeroDivisionError`를 낸다(F03).
3. **핸들이 중복된다.** `Found non-unique entity handle #9F …` 7건(F06). ADR-0002 §2가 `(file_id, handle)`을
   뷰어–엔진 공통 키로 쓰기 때문에 그 자체로 계약 위반이다.
4. (기존 W2-05 결함) **블록명 = 레이어명이면 INSERT를 통째로 잃는다.** F06/F10_grid/F11의 `X-TITLE`.

### 4.2 mlightcad `dxfOut()`이 쓴 DXF는 **읽히고, 결함이 플래그 두 개뿐이다**

`dxfOut()` 산출물은 ezdxf가 예외 없이 읽는다. truth와의 차이는 전부 아래 두 그룹코드 누락에서 나온다.

1. **INSERT에 그룹 `66`(attributes follow)을 쓰지 않는다.**

   ```text
   ezdxf   … 100:AcDbBlockReference 66:1 2:GRID-BUBBLE 10:8000.0 …
   dxfOut  … 100:AcDbBlockReference      2:GRID-BUBBLE 10:8000 …   ← 66 없음
   ```

   ENTITIES 섹션의 물리적 순서(`INSERT ATTRIB SEQEND`)와 ATTRIB의 소유자 그룹 `330`은 **정확하다.**
   ATTRIB 레코드 자체도 `100:AcDbAttribute` + `2:<tag>`를 갖춘 정상 레코드다. 하지만 `66`이 없어
   ezdxf의 `EntityLinker`가 ATTRIB을 INSERT에 붙이지 않는다. 그 결과:
   `text_count` 30/40(F06) → ATTRIB 10개 누락, `count_by_type`에 `SEQEND` 8개가 최상위 엔티티로 등장,
   `entity_count` 94≠86. **데이터는 파일 안에 다 있다. 한 그룹코드만 복원하면 원상 복구된다.**
2. **HATCH 경계 경로 플래그 `92`에서 External 비트(1)를 빠뜨린다** (`92:3`(External|Polyline) → `92:2`(Polyline)).
   그래서 부호 있는 면적 합이 부호만 뒤집힌다: `hatch_area_sum_mm2` **−4 320 000 vs +4 320 000**(F06, 크기는 정확히 동일).

그 외는 정확하다 — 특히 **`insert_by_block`이 truth와 일치**한다(`{GRID-BUBBLE: 7, X-TITLE: 1}`).
mlightcad에는 acad-ts의 "블록명=레이어명" 결함이 **없다.**
한글 텍스트(F03: `거실`, `실명: 거실\P면적: 23.4㎡`)는 DXF 입력 경로에서 `text_hash`까지 **완전 일치**한다.

### 4.3 DWG 픽스처는 acad-ts가 쓴 것이라 "DWG 읽기" 비교의 기준으로 쓸 수 없다

`fixtures/generated/*.dwg`는 전부 W2-05의 `acad-bridge dxf2dwg` 산출물이다. 그 쓰기 과정에서
이미 손실·오염이 생긴다는 것이 이 태스크에서 드러났다.

- F06.dwg에는 `X-TITLE` INSERT와 그 ATTRIB 3개가 **애초에 없다**(§4.1 결함 4).
  두 리더 모두 INSERT 7개만 본다: acad-ts self-view 85 엔티티, libredwg+`dxfOut` 85 엔티티(+SEQEND).
  즉 **libredwg-web + `dxfOut()`은 그 DWG에 있는 것을 하나도 잃지 않는다.** truth와의 차이는 전부
  (a) 쓰기 때 이미 없어진 것 + (b) §4.2의 플래그 두 개다.

  | F06 | truth | acad-ts가 그 DWG를 읽은 값 | libredwg + `dxfOut` → ezdxf |
  |---|---:|---:|---:|
  | `entity_count` | 86 | 85 | 92 (= 85 + 고아 SEQEND 7) |
  | `count_by_type.INSERT` | 8 | 7 | 7 |
  | `insert_by_block` | `{GRID-BUBBLE:7, X-TITLE:1}` | `{GRID-BUBBLE:7}` | `{GRID-BUBBLE:7}` |
  | `length_sum_mm` | 299 400 | 299 400 | 299 400 |
  | `hatch_area_sum_mm2` | 4 320 000 | 4 320 000 | −4 320 000 |
  | `text_count` | 40 | 37 | 30 (ATTRIB 7개가 고아) |

- F03.dwg의 MTEXT는 x축 벡터가 `(0,0,0)`이다. 원본 `F03.dxf`에는 그룹 11 자체가 없다.
  **서로 독립인 두 리더(acad-ts, libredwg)가 똑같이 `(0,0,0)`을 돌려준다** → 값은 DWG 안에 있고,
  acad-ts의 DWG 쓰기가 만든 것이다. 그래서 두 경로 모두 산출 DXF에서 엔진이 `ZeroDivisionError`로 죽는다.

**따라서 "DWG → DXF 변환 품질"의 최종 판정은 제3자가 만든 실제 DWG가 있어야 한다.** (G0 질문)

### 4.4 libredwg-web이 F11.dwg에서 20만 엔티티 중 85개만 조용히 반환한다

| | 값 |
|---|---|
| 입력 | `F11.dwg` 5.3 MB (acad-ts가 쓴 것), 원본 DXF 기준 200 006 엔티티 |
| acad-ts가 같은 DWG를 읽으면 | 200 005 엔티티 |
| libredwg-web 워커가 읽으면 | **85 엔티티** (F06 한 타일 분량) |
| 파싱 시간 | 775 ms, 피크 RSS 704 MB |
| `AcDbDatabase.lastOpenError` | **`null`** (오류 없음) |
| 3초 대기 후 재집계 | 여전히 85 (data-model의 비동기 배치 변환이 아직 진행 중이라서가 아니다) |

둘 중 하나다: (i) acad-ts의 DWG 쓰기가 libredwg만 엄격히 검사하는 부분을 망가뜨렸거나,
(ii) libredwg-web이 이 파일을 조용히 잘라 읽는다. **가진 픽스처로는 판별할 수 없다**(§4.3).

어느 쪽이든 결론 하나는 확정이다: **변환기가 "성공"을 반환해도 믿으면 안 된다.**
ADR-0002 §6의 stats 교차검증은 "레이어별 녹/황/적 표시"가 아니라 **임포트를 막는 게이트**여야 한다.
`entity_count`가 예상과 자릿수로 다르면 그 변환은 실패로 처리한다(§5.2).

<!-- 4-fidelity -->

## 5. 결정

<!-- 5-decision -->

### 5.3 게이트를 무엇으로 걸 것인가 (크기 vs 엔티티 수)

- **비용을 결정하는 것은 엔티티 수다. 파일 크기는 그 대리 변수일 뿐이고, 형식에 따라 배율이 8배까지 달라진다.**
  같은 F11이 DXF 41.4 MB / DWG 5.3 MB다(약 8:1). 그래서 **하나의 MB 임계값을 DWG와 DXF에 같이 쓰면 안 된다.**
- 그러나 파싱 전에 알 수 있는 값은 **바이트 크기뿐이다.** 그러므로 2단 게이트를 쓴다.
  1. **1단(열기 전, O(1))** — 원본 바이트 크기 × 형식별 계수로 엔티티 수를 추정한다.
     실측 밀도: DXF 약 **207 B/엔티티**, acad-ts DWG 약 **26 B/엔티티**(F11 기준, F12에서도 같은 자릿수).
     추정치가 티어 경계를 넘으면 **파싱을 시작하기 전에** 경고하고 사용자에게 경로를 고르게 한다.
  2. **2단(정본 생성 후, 정확)** — `<sha256>.stats.json`의 `totals.entity_count`.
     추정과 실제가 다른 티어로 갈리면 그때 한 번 더 알린다(예: 블록 참조가 많아 DWG가 작지만 엔티티가 많은 도면).
- **경고 문구 시점**: (a) 임포트 대화상자에서 파일을 고른 직후(1단), (b) 정본 생성 완료 직후 티어가 바뀐 경우에만(2단).
  진행 중에는 진행률만 보여주고 경고를 반복하지 않는다.

## 6. 남은 것

1. **실제 도면으로 재보정.** 이 문서의 수치는 전부 합성 픽스처다. 실무 DWG(외주 XREF, 프록시 엔티티,
   OLE, 이미지, 커스텀 객체)에서는 파서별 결함 분포가 달라질 수 있다. G0 질문 참조.
2. **네이티브 LibreDWG `dwg2dxf` 미측정.** `brew install libredwg` 후 같은 하네스로 한 줄 추가하면 된다
   (`tools/bench-open.mjs`에 `native` 경로 자리만 있고 구현은 없다).
3. **`dxfOut()`의 두 그룹코드 결함을 상류에 보고**하거나 우리 쪽 후처리로 고칠지 결정(§5).
4. **엔진 방어 코드.** `halo_engine.ingest.stats`가 `insert.attribs`의 죽은 엔티티(ezdxf 감사기가 지운 것)와
   길이 0 OCS 벡터에서 예외로 죽는다. 변환기를 바꿔도 "읽을 수 없는 DXF를 만나면 예외 대신 진단"이 되어야 한다(W2-04/W6 소관).
5. **`--browser-render`(뷰어 WebGL 경로) 대용량 측정**은 이 문서에서 소량만 다뤘다. 실제 미리보기 상한은
   렌더 프레임 예산까지 포함해 W3-02가 재확인해야 한다.
