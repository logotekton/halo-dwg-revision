# 출력: 마크업 DWG·리비전 표·변경 리스트 (R1-09)

`POST /api/v1/compare/sets/{id}/export`가 여는 `compare.export` 잡. 사용자가 화면 C에서 **승인**한
클러스터만 후 도면 사본에 클라우드 마크·번호 배지·리비전 표로 얹어 `<프로젝트>/출력/<날짜>[-n]/`에
DWG(없으면 DXF)로 내고, 같은 폴더에 `changes.tsv`와 `run.json`을 쓴다.

정본은 `docs/contracts/compare-dxf.md` §1·§2·§5·§6·§8과 `docs/contracts/r1.md` §2·§3·§6·§7·§11.
구현은 `engine/src/halo_engine/compare/markup.py`·`export.py`, 라우터
`api/routers/compare_export.py`.

## 흐름도

```
POST /compare/sets/{id}/export  {run_date, scope: "all", method: "auto"}
  ├─ 번들 없거나 없는 id → 404
  ├─ compare_set.status ≠ compared → 409   (비교 전에는 승인할 것이 없다)
  ├─ resolve_output_dir() → 출력 폴더와 레이어 이름을 먼저 정하고 폴더를 만든다
  ├─ repos.create_run(status=running, output_dir, layer_name, method)
  └─ job = jobs.create(compare_set_id=.., kind="compare.export") → 202 {job_id, run_id}

compare.export  # api/jobs.py::run_job이 감싼다
  ├─ 대상 고르기: 짝 정렬 순(sort_key). added·removed·unrecognized·converter_mismatch,
  │    후 도곽이 없는 짝, 작업용 DXF가 없는 짝은 건너뛴다
  ├─ 짝마다 판정 읽기: clusters.json + cluster 행(merge_decisions) → 승인·무시·대기
  ├─ compare_set.status = exporting
  ├─ 승인 클러스터가 있는 짝마다(취소는 짝 사이에서 확인):
  │   ① run_in_executor(ProcessPoolExecutor, export.markup_pair)
  │        markup.write_markup_dxf() → .halo/compare/<pair_id>/markup.dxf
  │        진행률 stage="markup", extra={pair_id, sheet_no, writer}
  │   ② DWG 저장 (아래 표) → 출력 폴더
  │        진행률 stage="dwg", extra={pair_id, sheet_no, writer}
  ├─ write_changes_tsv()  → 출력/<날짜>/changes.tsv   (승인 + 무시)
  ├─ repos.update_run(status=done, files, pair_ids, approved_count, ignored_count)
  ├─ write_run_json()     → 출력/<날짜>/run.json
  └─ compare_set.status = compared,
     stats.export = {run_id, output_dir, layer_name, method, writer, files,
                     approved, ignored, sheets_skipped, warnings[], failed[]}
```

한 짝이 실패해도(`markup_pair`가 예외 대신 `error`를 돌려준다) 그 짝만 빠지고 나머지는 나간다.
68장 세트에서 도면 하나가 깨졌다고 나머지 67장을 못 받으면 안 된다.

## 마크업 DXF (`markup.py`)

계약 §2의 등식 그대로다.

```
마크업 = 후 작업용 DXF 사본 + REV-<YYYYMMDD>[-n] 레이어(클라우드·배지) + 리비전 표
```

- **사본이다.** 후 작업용 DXF를 통째로 읽어 다시 쓴다. 원래 레이어·블록·도곽 밖 엔티티까지 그대로
  남는다(비교 DXF는 도곽 하나만 담지만, 마크업은 사무실에서 원본 대신 여는 파일이다).
- `__CMP_ADDED`·`__CMP_REMOVED`·`__CMP_LABEL`은 만들지 않는다. 검토용 비계는 출력에 나가지 않는다.
- **클라우드 좌표는 사이드카 그대로**(`clusters[].cloud.points`, `[x, y, bulge]`). 다시 계산하지
  않는다 — 화면 C에서 승인한 그 도형이 종이에 찍혀야 한다.
- 배지 삼각형은 `cluster.badge_geometry(bbox, config, scale_factor)`로 다시 만들고(사이드카에는
  중심점만 있다), 번호 TEXT는 사이드카의 `badge.center`에 가운데 정렬로 놓는다.
- XDATA `HALO_CMP`: `cluster=<번호>`, `role=cloud|badge_shape|badge_text` (계약 §4).
- 크기는 모두 `compare.yaml` 값 × `scale_factor`(`scale_denominator/100`). 1:50 도곽이면 절반이다.
- 승인 0건이면 **파일을 만들지 않는다**(`write_markup_dxf`가 `None`을 돌려준다). 그 도곽은 출력에서
  통째로 빠진다.
- `pin_header_for_determinism` + `serialize`로 쓴다. 같은 입력·같은 `run_date`·같은 판정이면
  바이트가 같다(계약 §8, `tests/compare/test_markup_determinism.py`).

### 리비전 표 (계약 §6)

`revtable` 설정만 쓰고 LINE + TEXT로만 그린다(TABLE 엔티티·프록시 금지 — ZWCAD와 뷰어가 둘 다 읽어야
한다).

| 항목 | 규칙 |
|---|---|
| 위치 | 표제란 INSERT bbox의 **왼쪽 위 모서리 = 표의 오른쪽 위 모서리**. 왼쪽·아래로 자란다 |
| 열 | `revtable.columns`(`번호`·`내용`·`일자`) — 머리글 행이 곧 이 값이다 |
| 열 너비·행 높이·글자 높이 | `col_widths`·`row_height`·`text_height` × `scale_factor` |
| 행 | 승인된 클러스터, 번호 순. `내용` = `user_label` 있으면 그것, 없으면 `label`. `일자` = `run_date` |
| 긴 내용 | 열 너비에 맞춰 자르고 `…`를 붙인다(한글은 글자 높이만큼, 로마자는 0.6배로 폭을 어림한다) |
| 정렬 | 머리글과 첫·마지막 열은 가운데, `내용`은 왼쪽 |

표제란 핸들로 bbox를 못 재면(`titleblock_bbox_unknown`) 도곽 오른쪽 아래 모서리에 붙이고, 표가
도곽 밖으로 나가면 그대로 그리되 `revtable_outside_frame` 경고를 남긴다(브리프 Defaults).

## DWG 저장 경로 선택

`method`는 요청이 `auto`면 `compare.yaml`의 `output.dwg_writer`를, 그 밖이면 요청 값을 쓴다.
실제로 무엇이 썼는지는 `run.files[].writer`에 남는다.

| `method` | ZWCAD 있음 | ZWCAD 없음 | 결과 파일 | `writer` | 경고 |
|---|---|---|---|---|---|
| `auto` | 배경 ZWCAD `convert_dxf_to_dwg` | 마크업 DXF를 출력 폴더로 복사 | `.dwg` / `.dxf` | `zwcad-com` / `dxf-only` | `zwcad_unavailable` |
| `zwcad` | 같음 | 같음(실행 자체를 막지는 않는다) | `.dwg` / `.dxf` | 같음 | `zwcad_unavailable` |
| `acad-ts` | acad-bridge `dxf2dwg` (빌드돼 있을 때) | 같음 | `.dwg` / `.dxf` | `acad-ts` / `dxf-only` | `acad_ts_titleblock_risk`, `acad_ts_unavailable` |
| `dxf-only` | 복사 | 복사 | `.dxf` | `dxf-only` | — |

- **`acad-ts`는 명시 설정일 때만.** acad-ts의 DWG 라이터는 블록 이름과 레이어 이름이 같은 INSERT를
  조용히 빠뜨리는데(`packages/acad-bridge/README.md` "Known acad-ts gaps" #1) 그게 바로 표제란이다.
  표제란이 사라진 도면을 기본값으로 낼 수는 없다.
- ZWCAD 인스턴스는 **하나**, 전용 단일 스레드(`ThreadPoolExecutor(max_workers=1)`)에서만 쓴다. COM
  STA 객체는 만든 스레드에서만 쓸 수 있다(`compare/zwcad.py`). 잡이 끝나면 `__exit__`으로 닫는다.
- 파일 하나가 ZWCAD에서 실패하면(`ZwcadError`, 타임아웃 포함) 그 파일만 DXF로 떨어지고
  `zwcad_failed` 경고가 붙는다. 나머지는 계속 DWG로 나간다.

## 파일 이름과 폴더

- 폴더: `<프로젝트>/<output.dir_name>/<run_date>`. 이미 있으면 `-2`, `-3`… 을 붙이고 **레이어에도 같은
  접미사**를 붙인다(`REV-20260904-2`). 같은 날 다시 뽑아도 앞서 보낸 사본을 덮어쓰지 않는다(계약 §11).
  폴더는 202를 돌려주기 전에 만든다 — 같은 초에 시작한 두 출력이 서로 첫 번째라고 우기면 안 된다.
- 파일 이름: `output.file_pattern`(`{sheet_no}_{after_label}_markup`).
  - `sheet_no` = 도곽의 도면번호, 없으면 후 파일 이름(확장자 제외).
  - `after_label` = 후 `drawing_set.label` = 후 세트 폴더 이름.
  - `<>:"/\|?*`와 제어문자는 `_`로 바꾼다. 같은 이름이 두 번 나오면 `-2`를 붙이고
    `duplicate_file_name` 경고를 남긴다.
- 중간 산출물 `markup.dxf`는 번들 안(`.halo/compare/<pair_id>/markup.dxf`)에 남는다. 다음 실행에서
  덮어쓰이고, 문제가 생겼을 때 무엇을 ZWCAD에 넘겼는지 볼 수 있다.

## `changes.tsv`

열은 `도면번호 · 도면명 · 번호 · 종류 · 내용 · 판정 · 일자`, UTF-8(**BOM 없음**), 줄 끝 LF, 탭 구분.
바이트로 쓰기 때문에 Windows에서도 CRLF가 되지 않는다.

- **승인과 무시를 모두 담는다.** 판정 열이 둘을 가른다 — 무시한 변경도 "봤다"는 기록이 남아야 한다.
  대기(`pending`)는 결과가 아니므로 빠진다.
- 승인 0건인 도곽도 무시 행은 나온다(도면은 안 나온다).
- 종류는 `cluster.kind`의 한국어(`이동`·`신설`·`삭제`·`수정`·`문구`·`치수`·`블록 정의`·`혼합`).
- 값 안의 탭·줄바꿈은 공백으로 바꾼다.

## `run.json`과 API

`run.json`은 스키마 `compare/run`(`packages/schema/src/compare/run.schema.json`) 그대로다. 디스크와
API에서 두 가지 모양을 쓴다.

| | `run.json` | `GET /compare/runs/{id}` |
|---|---|---|
| `schema_version` | 있음 | 없음 |
| `files[].path` | 출력 폴더 기준 **상대 경로** | 절대 경로 |
| `created_at` | 없음(현재 시각을 산출물에 넣지 않는다) | 있음(DB 타임스탬프) |

경고(`zwcad_unavailable` 등)는 스키마에 자리가 없어 `compare_set.stats.export.warnings`와 잡 진행률
`extra`에 남는다.

| 엔드포인트 | 응답 |
|---|---|
| `POST /compare/sets/{id}/export` | `202 {job_id, run_id}` / 409(=`compared` 아님) / 404 / 422 |
| `GET /compare/runs/{run_id}` | `Run` (위 표의 API 모양) / 404 |
| `GET /compare/runs/{run_id}/tsv` | `text/tab-separated-values; charset=utf-8`, 파일 바이트 그대로 / 404 / 409(아직 안 씀) |

## 쓰기 허용 경로

모든 쓰기 앞에 `bundle.guard.assert_writable_path(path, allowed_roots=[bundle.root, output_dir])`.
전·후 세트 폴더는 읽기만 한다(`CLAUDE.md` 규칙 1). `tests/compare/test_export.py`가 출력 전후로 두 소스
폴더의 파일 해시를 비교한다.

## 실패 모드

| 증상 | 원인 | 다음 수 |
|---|---|---|
| 출력 폴더에 도면이 하나도 없다 | 승인한 클러스터가 없다 | 화면 C에서 승인. `changes.tsv`에는 무시 행이 있을 수 있다 |
| 전부 `.dxf`로 나왔다 | 이 PC에 ZWCAD가 없다(`zwcad_unavailable`) | Windows + ZWCAD 2026에서 다시 출력. DXF도 ZWCAD에서 열린다 |
| 도면 하나만 `.dxf` | 그 파일에서 ZWCAD가 실패·타임아웃(`zwcad_failed`) | `.halo/compare/<pair_id>/markup.dxf`를 직접 열어 본다 |
| 표가 도곽 밖으로 나갔다 | 표제란 왼쪽에 공간이 없다(`revtable_outside_frame`) | 정상 동작. `compare.yaml`의 `revtable.col_widths`를 줄이면 들어온다 |
| 표가 엉뚱한 자리에 있다 | 표제란 bbox를 못 쟀다(`titleblock_bbox_unknown`) | `frames.yaml`의 표제란 인식 설정 확인 |
| 같은 날 두 번째 출력이 첫 번째를 덮어썼다 | 있어서는 안 된다 | 버그. `resolve_output_dir`와 `출력/` 폴더 목록을 확인 |

## Windows 확인 절차 (사용자)

CI 아티팩트 설치본으로만 확인한다(`CLAUDE.md` 작업 방식). 결과는 `docs/gates/R1.md`에
`R1-GATE <항목>: PASS|FAIL` 한 줄로 남긴다.

1. 설치본을 켜고 전·후 세트를 지정해 비교까지 돌린 뒤, 화면 C에서 클라우드 마크 두어 개를 **승인**하고
   한 개는 **무시**한다. 하나에는 직접 문구를 적어 둔다.
2. 화면 D에서 실행 날짜를 그대로 두고 출력한다. `<프로젝트>/출력/<날짜>/`가 생기고 도면 파일이
   `.dwg`인지 본다(`.dxf`면 ZWCAD 감지 실패 — `zwcad_unavailable`).
3. 출력 DWG를 **ZWCAD 2026에서 연다.**
   - 레이어 목록에 `REV-<YYYYMMDD>`가 있고 **색이 빨강(1)**인가.
   - 승인한 자리마다 **구름 표시**가 있고, 그 오른쪽 위에 **삼각형 + 번호**가 있는가. 무시한 자리에는
     아무것도 없는가.
   - 표제란 **왼쪽에 리비전 표**가 붙어 있고, 머리글이 `번호·내용·일자`, 행이 승인 개수만큼이며,
     직접 적은 문구와 실행 날짜가 그대로인가.
   - `REV-<YYYYMMDD>` 레이어를 끄면 **원래 도면 그대로**가 남는가(원본과 같아야 한다).
   - 도곽 밖 요소·다른 레이어·표제란 글자가 그대로 살아 있는가(특히 표제란 ATTRIB).
4. 같은 날 한 번 더 출력해 `출력/<날짜>-2/`가 새로 생기고 레이어가 `REV-<YYYYMMDD>-2`인지,
   첫 번째 폴더가 그대로 남아 있는지 본다.
5. `changes.tsv`를 Excel에서 연다. 한글이 깨지지 않는지, 승인·무시가 판정 열로 구분되는지 본다.
   (BOM 없는 UTF-8이라 Excel 버전에 따라 "데이터 → 텍스트/CSV 가져오기"로 UTF-8을 골라야 할 수 있다 —
   깨지면 게이트에 적어 주면 BOM 여부를 다시 정한다.)
6. 전·후 원본 폴더의 파일이 하나도 바뀌지 않았는지(수정 시각) 확인한다.
