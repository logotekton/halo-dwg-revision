# fixtures/ -- 합성 DXF 픽스처 (W1-03)

실제 국내 DWG 샘플이 들어오기 전까지 뷰어·엔진 파서·교차검증·패키징을 검증하기 위한
결정론적 합성 도면 세트. 생성기는 `fixtures/gen/`의 독립 uv 프로젝트(`ezdxf==1.4.4`만 의존,
`engine/`이나 `packages/schema`에 의존하지 않는다).

## 재생성 방법

```bash
cd fixtures/gen
uv sync
uv run python -m fixtures_gen --out ../generated --truth ../truth
# 단일 픽스처만:
uv run python -m fixtures_gen --out ../generated --truth ../truth --only F06
# F12(100만 엔티티, 커밋 금지)까지 포함:
uv run python -m fixtures_gen --out ../generated --truth ../truth --large
```

같은 명령을 몇 번 실행해도 `fixtures/generated/**`와 `fixtures/truth/**`는 바이트 단위로
동일하다 (증명: `fixtures/gen/tests/test_determinism.py`, 그리고 `git status --short`로도
확인 가능 -- 커밋된 파일과 재생성 결과가 다르면 diff가 뜬다).

## 픽스처 목록

각 F01~F10은 R2018(AC1032) UTF-8 정본 `F##.dxf`와 R2000(AC1015) cp949 변형
`F##_r2000_cp949.dxf`로 생성된다. R2000이 표현할 수 없는 엔티티(F04의 그라디언트 HATCH,
F05의 MULTILEADER)는 변형에서 생략되고 truth의 `variants.r2000_cp949.omitted`에 기록된다.

| ID | 내용 | 주요 엔티티(R2018) | 파일 크기(R2018) |
|---|---|---|---|
| F01 | 기본 기하 5개 레이어(색·선종류 다양) | LINE 6, LWPOLYLINE 3(열림/닫힘/벌지), POLYLINE 1, ARC 3, CIRCLE 3, ELLIPSE 2, SPLINE 2, POINT 6 | 58KB |
| F02 | 블록 3종(DOOR_900/WIN_1800/COL_600) + 중첩 블록(COL_PAIR) | INSERT 30(회전·축척, 각 ATTRIB TAG+SIZE) | 78KB |
| F03 | 한글 TEXT/MTEXT, 스타일 2종, 특수문자 | TEXT 20, MTEXT 10(`\P`, `%%d`, `Ø`, `㎡`) | 59KB |
| F04 | 해치: SOLID, ANSI31, 사용자 패턴, 홀, 그라디언트(R2018만) | SOLID 5, HATCH 9(ANSI31×5 + 사용자×1 + 홀×2 + 그라디언트×1) | 58KB |
| F05 | 치수·지시선, 치수 스타일 2종 | DIMENSION 7(선형/정렬/각도/반지름/지름/좌표×2), LEADER 1, MULTILEADER 1(R2018만) | 68KB |
| F06 | 구조평면: 그리드 X1-4/Y1-3, 기둥 12, 보, 슬래브 태그, 도곽 | LINE 24, LWPOLYLINE 12, HATCH 12(기둥 솔리드 채움), INSERT 8(그리드 버블7+도곽1), TEXT 30 | 72KB |
| F07 | 기둥표·보표(LINE+TEXT), 병합 셀 각 1 | LINE 77, TEXT 55 | 72KB |
| F08 | 층고표(B1~4F, SL/FL/층고/CH) + 단면 레벨 라인 | LINE 46, TEXT 36 | 65KB |
| F09 | 실 6개(이중선 벽), 문 6/창 4, 벽 갭 2곳(150mm) | LINE 38, INSERT 10(문6+창4), TEXT 6 | 61KB |
| F10 | XREF: `F10_host.dxf`가 `F10_grid.dxf`를 상대경로로 참조 | grid: LINE 5+INSERT 6 / host: INSERT 1(XREF)+LWPOLYLINE 6+TEXT 6 | 그리드 58KB / 호스트 56KB |
| F11 | 대용량(F06 타일 복제, 기본 생성) | 약 20만 엔티티(2,353 타일) | 약 41MB, **커밋 안 함**(gitignore) |
| F12 | 초대용량(`--large`로만 생성) | 약 100만 엔티티 | **생성만, 커밋 안 함** |

F01~F10의 DXF 합계는 약 1.2MB (< 20MB 예산). F11/F12의 DXF는 `.gitignore`의
`fixtures/**/F11*.dxf`, `fixtures/**/F12*.dxf` 규칙으로 제외된다. F11의 truth
(`fixtures/truth/F11.json`)는 집계 통계만 담아 가볍게 커밋한다 (아래 Decisions 참조).
F12는 truth도 커밋하지 않는다 (`--large` 없이는 아예 생성되지 않으므로 기본 실행에서는
git 상태에 영향이 없다).

## truth JSON 형식 (W2-03, 스키마 형식으로 재작성)

`fixtures/truth/F##.json`은 이제 **`LayerStatsDocument` 그 자체**다
(`packages/schema/src/stats/layer-stats.schema.json`, `docs/contracts/stats-definition.md`).
스키마가 닫혀 있어(`additionalProperties: false`) 픽스처별 부가 정보를 담을 자리가 없으므로,
그 밖의 모든 것(원본/변형 파일 설명, R2000/cp949 변형의 통계와 `omitted` 목록, 부재
배치·표 셀·층고표 4필드·벽 갭 좌표·XREF 관계 등 생성기 설계값)은 `fixtures/truth/F##.extra.json`에
분리해 담는다. **생성된 DXF를 ezdxf로 다시 읽어** 독립적으로 계산한다
(`fixtures_gen.stats.compute_layer_stats`; `engine/src/halo_engine/ingest/stats.py`가 서로
임포트하지 않는 독립 구현으로 같은 계약을 계산하고, F01~F10에서 두 결과가 일치함을
`engine/tests/ingest/test_engine_crosscheck.py`가 검증한다).

`F##.json` (예: F06):

```jsonc
{
  "schema_version": "0.1",
  "file_sha256": "...",                 // F06.dxf(원본, R2018) 자체의 sha256
  "producer": { "name": "engine.ezdxf", "version": "fixtures-gen/0.1.0+ezdxf/1.4.4" },
  "buckets": [
    { "layer": "A-TEXT", "space": "MODEL", "aggregate": { "entity_count": 30, "count_by_type": {"TEXT": 30}, "length_sum_mm": 0, "hatch_area_sum_mm2": 0, "text_count": 30, "text_hash": "...", "insert_by_block": {}, "bbox": {"min": [..], "max": [..]} } },
    ...
  ],
  "totals": { "entity_count": 86, "count_by_type": {...}, "length_sum_mm": ..., "hatch_area_sum_mm2": ..., "text_count": ..., "text_hash": ..., "insert_by_block": {...}, "bbox": {"min": [..], "max": [..]} }
}
```

`F##.extra.json` (같은 F06 예):

```jsonc
{
  "fixture": "F06",
  "primary": { "file": "F06.dxf", "dxf_version": "AC1032", "encoding": "cp1252", "sha256": "...", "size_bytes": ... },
  "variants": { "r2000_cp949": { "file": "F06_r2000_cp949.dxf", ..., "omitted": [], "stats": { /* F06_r2000_cp949.dxf의 LayerStatsDocument 전체 */ } } },
  "extra": { "grid": {...}, "columns": [...], "beams": [...], "slab": {...}, "title_block": {...} }
}
```

- `producer.name`은 스키마의 닫힌 열거값(`viewer.mlightcad`/`engine.ezdxf`/`acad-ts`/`libredwg-web`,
  `packages/schema/src/ndj/document.schema.json` `$defs/producer`) 중 하나여야 하는데
  `"fixtures-gen"`이 없다 -- `"engine.ezdxf"`를 재사용하고 `version`으로 구분한다
  (아래 Decisions, `engine/`의 W2-03 보고서 "Shared-file patch" 참고).
- **F10은 파일 쌍**(grid+host)이라 `F10.json` 대신 `F10_grid.json`/`F10_host.json`(각각 독립된
  `LayerStatsDocument`) + `F10.extra.json`(둘의 파일 설명·변형·`extra`를 함께 담음) 형태다.
- F01~F09/F11은 `F##.json` + `F##.extra.json`, F10은 위 세 파일, F12는 생성만 되고 커밋되지 않는다
  (기존과 동일).

## Decisions (모호함에 대한 선택)

1. **결정론 확보에 `PYTHONHASHSEED` 고정이 필요했다.** ezdxf가 OBJECTS 섹션의 일부
   보조 객체(기본 PaperSpace `LAYOUT`/`ACDBPLACEHOLDER` 부기 항목)를 내부 set/dict 순회로
   정렬하는데, 이 순회 순서가 Python 프로세스별 문자열 해시 시드에 좌우됨을 실측으로 확인했다
   (`ezdxf.options.write_fixed_meta_data_for_testing = True`로 타임스탬프/GUID는 고정되지만
   이 순서는 고정되지 않음). 브리프의 문서화된 실행 명령이 `PYTHONHASHSEED`를 설정하지 않으므로,
   `fixtures_gen.cli.run()`(`python -m fixtures_gen`과 `fixtures-gen` 콘솔 스크립트의 실제 진입점)이
   시작 시 `PYTHONHASHSEED=0`이 아니면 동일 인자로 자기 자신을 한 번 재실행한다
   (`os.execve`). `fixtures_gen.cli.main(argv)`는 재실행 로직이 없는 순수 함수로 남겨
   테스트가 커스텀 `argv`로 직접 호출할 수 있게 했다.
2. **`fixtures/truth/*.json` 필드 이름**은 `packages/schema/stats/layer-stats.schema.json`이
   아직 없어(W1-05 병행 작업) 브리프에 명시된 이름(`count_by_type`, `length_sum`,
   `hatch_area_sum`, `text_count`, `text_hash`, `insert_by_block`, `bbox`, `totals`)을 그대로 썼다.
   스키마가 나오면 필드 이름이 다를 경우 truth 생성부(`fixtures_gen/pipeline.py`,
   `fixtures_gen/stats.py`)만 고치면 된다.
3. **`length_sum`에 SPLINE도 포함**했다. 브리프 Inputs 절의 타입 목록(LINE/LWPOLYLINE/
   POLYLINE/ARC/CIRCLE)에는 SPLINE이 빠져 있지만, Constraints 절이 "스플라인은 ezdxf
   `flattening(0.01)` 근사"라고 명시적으로 계산 방법을 지정하고 있어 포함하는 것이
   브리프의 의도라고 판단했다 (`fixtures_gen/stats.py`의 `LENGTH_TYPES`).
4. **HATCH 경계는 항상 직선(불지 0)인 `PolylinePath`만 사용**한다. 곡선 경계(EdgePath, 불지
   있는 폴리라인 경계)는 만들지 않아 `hatch_area_sum` 계산이 단순 신발끈 공식(구멍은 감산)만으로
   정확하다 -- 근사 오차 없이 검증 가능해야 한다는 브리프의 "독립 검증" 취지에 맞춘 선택이다.
5. **모든 픽스처는 모델공간에만 그린다** (도곽·표까지 포함, F06/F08/F10의 A1 도곽은
   브리프 Defaults의 "축척 1/100로 모델공간에 배치"를 따름). ADR-0002 §6의 "레이어·공간별"
   통계는 이에 따라 `by_space: {"Model": {...}}` 하나로 수렴한다 -- 종이공간을 쓰는 픽스처가
   생기면 `stats.compute_stats`가 이미 다중 레이아웃을 지원하므로 자연히 확장된다.
6. **F11의 truth는 집계 통계만 담고, 타일별 부재 배치는 담지 않는다.** F11은(브리프상
   `--large` 없이도) 기본 생성 대상이라 `fixtures/truth/F11.json`이 커밋되는데, 2,353개
   타일 각각의 columns/beams 배열을 모두 기록하면 truth JSON이 수만 개 항목으로
   부풀어 오른다. 대신 타일 격자 파라미터(`tile_count`, `step_x/y`, `entities_per_tile`)와
   "타일 하나의 스키마는 F06.json의 `extra`와 같다, 오프셋만 다르다"는 재구성 규칙을 적었다.
   F12는 `--large`를 줘야만 생성되므로 기본 실행에서는 git 상태에 전혀 나타나지 않고,
   생성되더라도 커밋하지 않는다(DXF는 `.gitignore`로, truth는 이 저장소에서 add하지 않는
   방식으로).
7. **텍스트 스타일 폰트 파일은 만들지 않는다** (`whgtxt.shx` 빅폰트, `malgun.ttf`는 이름만
   참조). 브리프 Defaults for ambiguity에 명시된 대로다.
8. **R2000 cp949 변형은 `doc.encoding = "cp949"` 후 저장**한다. ezdxf가 `$DWGCODEPAGE`를
   해당 인코딩으로 맞추고, 읽을 때도 자동으로 cp949로 디코드함을 실측으로 확인했다
   (`fixtures/gen/tests/test_cp949_roundtrip.py`).
9. **DIMENSION 렌더링**: `add_*_dim()`이 반환하는 `DimStyleOverride`에 `.render()`를 호출해야
   실제 도형 블록이 생성된다. `.render()` 없이도 `DIMENSION` 엔티티 자체는 모델공간에
   존재하지만, 브리프의 "치수" 픽스처 취지(뷰어에서 실제로 보이는 도형)에 맞춰 모든
   치수에 `.render()`를 호출했다.
10. **DXF 엔티티 타입 이름 표기**: 브리프는 "MLEADER"라 부르지만 실제 DXF 엔티티 타입명은
    `MULTILEADER`다 (AutoCAD UI 명칭과 DXF 그룹코드 상 타입명이 다름). truth와 코드 전반에서
    `MULTILEADER`를 쓰고 F05의 docstring에 이 차이를 적어 두었다. `packages/schema`의
    `entity_type` 열거값은 여전히 `MLEADER`라 F05.json은 스키마 검증에서 이 한 항목만
    화이트리스트 처리한다 (W2-03, `engine/tests/ingest/test_truth_schema.py`의
    `KNOWN_SCHEMA_GAPS`).
11. **(W2-03) `producer.name`은 `"engine.ezdxf"`를 재사용한다.** `docs/contracts/stats-definition.md`는
    `producer`가 `"mlightcad"|"ezdxf"|"acad-ts"|"fixtures-gen"` 중 하나라고 적었지만, 실제
    스키마(`packages/schema/src/ndj/document.schema.json` `$defs/producer`)는 `{name, version}`
    객체이고 `name`은 `viewer.mlightcad`/`engine.ezdxf`/`acad-ts`/`libredwg-web` 중 하나로 닫혀
    있어 `"fixtures-gen"`을 쓸 수 없다. `fixtures_gen.stats.producer_info()`는 `name`을
    `"engine.ezdxf"`로(엔진과 동일 -- 둘 다 결국 ezdxf 기반 판독기다), `version`을
    `f"fixtures-gen/{버전}+ezdxf/{버전}"`으로 써서 스키마를 통과시키면서 출처를 구분한다.
    F01~F10 교차검증 테스트(`engine/tests/ingest/test_engine_crosscheck.py`)는 애초에
    `producer`를 비교 대상에서 제외한다(엔진과 생성기가 서로 다른 producer인 것 자체가
    맞는 설계이므로). packages/schema에 `"fixtures-gen"` enum 값을 추가하는 편이 근본
    해결책이라 W2-03 보고서의 "Shared-file patch"로 제안한다.
12. **(W2-03) truth 형식을 스키마 형식으로 교체**: `fixtures/truth/F##.json`이 이제
    `LayerStatsDocument` 그 자체이고(스키마가 닫혀 있어 부가 필드를 못 담는다), 예전에
    `primary`/`variants`/`extra`에 있던 모든 것은 `fixtures/truth/F##.extra.json`으로
    옮겼다. `F10`은 파일이 둘(grid+host)이라 `F10_grid.json`/`F10_host.json` + 공용
    `F10.extra.json`으로 나눴다 (스키마가 `file_sha256` 하나만 허용하므로 한 문서에 두 파일의
    통계를 담을 수 없다). 위 "truth JSON 형식" 절 참고.
13. **(W2-03) `length_sum_mm`에 ELLIPSE를 추가하고 POLYLINE은 2D만 잰다.** 계약
    (`docs/contracts/stats-definition.md`)이 명시적으로 `LINE, LWPOLYLINE, POLYLINE(2D), ARC,
    CIRCLE, ELLIPSE, SPLINE`이라 적어, ELLIPSE 누락(이전 `stats.py`는 ELLIPSE 처리가 없었다 --
    F01의 ELLIPSE 2개가 길이 0으로 집계됐었다)을 고치고 3D POLYLINE은 계약의 "(2D)" 표기를
    문자 그대로 따라 제외했다(현재 픽스처는 3D POLYLINE을 쓰지 않아 수치 영향은 없다).
    ELLIPSE는 SPLINE과 같은 방식(`flattening(0.01)`)으로 근사한다.
14. **(W2-03) ATTRIB는 `insert.attribs`로 수집해 자신의 레이어에 귀속시킨다.** `count_by_type`에서는
    제외하고(계약: "ATTRIB·SEQEND·VERTEX는 세지 않는다") `text_count`/`text_hash`에는 포함한다.
    `text_hash` 알고리즘도 계약대로 바꿨다: 텍스트마다 NFC 정규화 후 문자열 자체를 코드포인트
    오름차순 정렬, `\n`으로 결합, `sha1` 앞 16 hex (이전 구현은 텍스트별로 먼저 해시하고 그
    해시 문자열들을 이어붙여 다시 해시했다 -- 계약과 다른 방식이었다).

## DWG 픽스처 (W2-05)

`fixtures/generated/F##.dwg`(F01~F09, F10_host, F10_grid; AC1027)는 대응하는 R2018 `F##.dxf`를
`@node-projects/acad-ts`의 `dxf2dwg`로 저장한 것이다 (`packages/acad-bridge`, ADR-0002 1차
변환기 후보). 생성기·truth와 달리 acad-ts는 결정론적이지 않을 수 있어(DWG 헤더 타임스탬프 등)
`fixtures/generated/*.dwg`는 **재생성 시 바이트 동일성을 보장하지 않는다** -- truth와 달리
diff 검사 대상이 아니다. 11개 파일 합계 180KB (< 10MB 예산).

재생성:
```bash
pnpm --filter @halo-cad/acad-bridge build
for f in F01 F02 F03 F04 F05 F06 F07 F08 F09; do
  node packages/acad-bridge/bin/acad-bridge.mjs dxf2dwg "fixtures/generated/$f.dxf" "fixtures/generated/$f.dwg"
done
node packages/acad-bridge/bin/acad-bridge.mjs dxf2dwg fixtures/generated/F10_grid.dxf fixtures/generated/F10_grid.dwg
node packages/acad-bridge/bin/acad-bridge.mjs dxf2dwg fixtures/generated/F10_host.dxf fixtures/generated/F10_host.dwg
```

F11/F12는 DWG로도 만들지 않는다 (브리프 W2-05 범위 밖, `.gitignore`의 `fixtures/**/F11*.dwg`,
`fixtures/**/F12*.dwg` 규칙으로도 제외됨).

**주의 -- F06.dwg와 F10_grid.dwg는 acad-ts의 알려진 버그로 원본과 완전히 같지 않다.** 두 픽스처
모두 도곽(title block)의 INSERT가 자신과 같은 이름의 레이어(`X-TITLE`)를 쓰는데, acad-ts의
`DxfReader`가 이 경우 INSERT의 블록 참조를 `null`로 남긴다(최소 재현: 레이어와 블록이 같은 이름을
쓰는 문서를 만들어 DXF 왕복 시 재현됨). 결과: `F06.dxf`를 직접 읽으면 `count_by_type.INSERT`는
`fixtures/truth/F06.json`과 똑같이 8이지만, `F06.dwg`를 만든 뒤 다시 읽으면(`dxf2dwg`가 DWG로
쓸 때 이 INSERT를 조용히 버린다) 7이 된다 -- `packages/acad-bridge/README.md` "Known acad-ts
gaps" #1, 이 태스크 보고서의 "Deviations from brief"/"Questions for gate"에 근거를 남겼다.

## 테스트

```bash
cd fixtures/gen
uv sync
uv run pytest -q      # 결정론, 재읽기=truth, cp949 왕복, F09 갭, truth 필드/ADR-0003 검증
uv run ruff check .
```

`tests/test_determinism.py`는 `python -m fixtures_gen`을 서브프로세스로 두 번 실행해
(브리프의 수용 기준 명령과 동일한 진입점) 바이트 동일성을 검증한다. F11/F12는 속도를 위해
이 테스트에서 제외했지만 저장 경로(`fixtures_gen.common.save`)는 다른 모든 픽스처와
동일하므로 별도 검증이 필요하지 않다.
