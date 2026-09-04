# halo_engine

Halo CAD의 Python 사이드카. FastAPI 기반 로컬 서버로, Electron이 spawn하거나(운영) 개발자가
직접 `uv run`으로 실행해(개발) 브라우저 UI에서 `HALO_ENGINE_URL`로 붙는다. 물량·모델 계산의
단일 진실 소스이며(`CLAUDE.md` 규칙 5), DXF만 읽는다(`docs/adr/0002-working-dxf.md`).

## 설치

```bash
cd engine
uv sync --frozen
```

`requires-python = ">=3.12,<3.13"`. 시스템 Python(3.9)이 아니라 `uv python install 3.12`로 설치된
인터프리터를 쓴다 — `uv sync`가 `.python-version`(3.12)을 보고 알아서 고른다.

## 실행

```bash
uv run halo-engine serve --dev --port 8765 --token dev
```

- `--data-dir PATH`: 번들·캐시·SQLite가 저장될 디렉터리(기본 `~/.halo-cad/engine`).
- `--dev`: 개발 모드. 토큰이 없을 때만 `dev`를 기본 토큰으로 허용한다.
- `--port N`: `127.0.0.1`에 바인드할 포트. `0`이면 OS가 임의 포트를 배정한다(운영 시 기본값).
- `--token T`: Bearer 토큰. 환경변수 `HALO_ENGINE_TOKEN`이 있으면 그쪽이 우선한다(argv에 토큰을
  남기지 않으려는 운영 경로를 위함).
- `--reload`: 소스 변경 시 자동 재시작(개발 전용, Electron이 spawn하는 경로에서는 쓰지 않는다).
- `--log-dir PATH`: 지정하면 사람이 읽는 로그 라인을 이 아래 회전 파일에도 남긴다(`stderr`에는
  항상 남는다).
- `--converter-fallback acad-ts`: DWG→DXF 변환이 필요한데 WS로 연결된 데스크톱이 없을 때,
  엔진이 acad-ts CLI를 subprocess로 직접 실행한다(아래 "DWG 변환과 임포트 잡" 절). 드로잉셋
  임포트 요청 본문의 `converter_fallback` 필드가 이 서버 기본값을 요청 단위로 덮어쓴다.

포트를 바인드한 직후, **다른 어떤 로그보다 먼저** stdout 한 줄에 READY JSON을 찍고 flush한다:

```json
{"event": "ready", "port": 54213, "pid": 41213, "version": "0.0.1"}
```

Electron main 프로세스는 이 줄을 파싱해 실제 포트를 알아낸다(`docs/PLAN.md` §3.2). 그 이후의
uvicorn/애플리케이션 로그는 모두 `stderr`로 간다 — stdout은 이 한 줄 전용이다.

## 사이드카 프로토콜 요약 (`docs/PLAN.md` §3)

1. 부모(main)가 32바이트 토큰을 생성해 `HALO_ENGINE_TOKEN` 환경변수로 넘기고
   `HALO_ENGINE_PARENT_PID`에 자기 pid를 넣은 뒤 `halo-engine serve`를 실행한다.
2. 엔진은 `127.0.0.1:0`에 바인드하고 READY 줄을 stdout에 찍는다.
3. 부모는 `GET /api/v1/system/health`를 폴링해 기동을 확인한다(`health`는 토큰 없이 열려 있다).
4. 그 외 모든 API는 `Authorization: Bearer <token>`이 필요하다(없거나 틀리면 401).
5. `HALO_ENGINE_PARENT_PID`가 주어지면 5초마다 그 pid의 생존을 확인하고, 죽어 있으면 즉시
   종료한다(부모 없는 좀비 프로세스 방지). 정상 종료는 `POST /api/v1/system/shutdown`으로
   요청한다(토큰 필요).
6. 개발 모드에서는 `HALO_ENGINE_URL`을 프런트엔드에 지정하면 Electron 없이 브라우저에서
   `uv run halo-engine serve --dev --reload`에 직접 붙을 수 있다.

## API

- `GET /api/v1/system/health` — 토큰 불필요. `{status, version, python, deps:{ezdxf, shapely,
  manifold3d, trimesh, ifcopenshell, numpy, fastapi}}`.
- `GET /api/v1/system/capabilities` — 토큰 필요. `job_runner`·`websocket`은 W3-03에서 실제로
  붙었지만 이 엔드포인트의 플래그 값 자체는 `api/routers/system.py` 소유라 이 태스크가 고치지
  않는다(보고서 "Shared-file patch" 참고 — 값이 아직 `false`로 남아 있다).
- `POST /api/v1/system/shutdown` — 토큰 필요. 우아한 종료를 요청한다.
- `POST /api/v1/files/crosscheck` — 토큰 필요. 본문 `{reference, other, whitelist?}`
  (`LayerStatsDocument` 두 개 + 화이트리스트 경로). 응답은 `CrosscheckReport`
  (`halo_engine/validate/crosscheck_report.schema.json`). 상태를 저장하지 않는 범용 비교
  (W2-04). 파일에 저장하는 버전은 아래 `POST /api/v1/files/{id}/crosscheck` 참고.
- `POST /api/v1/projects` `{name, path?}` → `201 {id, bundle_path}`. `path` 생략 시
  `~/Documents/Halo CAD/<name>.halo`. 새 번들을 만들고 바로 연다(엔진 워크스페이스는 한 번에
  프로젝트 하나).
- `POST /api/v1/projects/open` `{bundle_path}` → `200 {id, bundle_path}`. 기존 번들을 연다
  (Alembic 마이그레이션을 최신으로 올린 뒤).
- `GET /api/v1/projects/recent` — 이 엔진의 `--data-dir`에 저장된 최근 프로젝트 목록
  (`<data-dir>/recent-projects.json`, 프로세스 재시작에도 유지).
- `GET /api/v1/projects/{id}` — 현재 열린 프로젝트만(다른 id는 404, 연 프로젝트가 없으면 409).
- `POST /api/v1/projects/{id}/drawing-sets` `{files: [절대경로...], search_paths?, converter_fallback?}`
  → `202 {job_id, drawing_set_id}`. 임포트 잡을 예약하고 즉시 반환한다(아래 "DWG 변환과 임포트
  잡" 절).
- `GET /api/v1/jobs/{id}` — `{id, status, progress, message, drawing_set_id, error}`.
- `POST /api/v1/jobs/{id}/cancel` — 다음 파일로 넘어가기 전에 협조적으로 취소한다(진행 중인
  파일은 끝까지 마친다).
- `GET /api/v1/drawing-sets/{id}/files` — `[{id, original_name, format, dwg_version,
  entity_count, codepage_effective, import_status, error_message, working_dxf_path,
  parser_crosscheck?}]`.
- `GET /api/v1/files/{id}/working-dxf` — 정본 DXF 바이트 스트림. `ETag`(mtime+size 기반)와
  `If-None-Match` 조건부 GET(304) 지원.
- `GET /api/v1/files/{id}/stats` — `ingest/working_dxf.py`가 만든 `LayerStatsDocument` 그대로.
- `POST /api/v1/files/{id}/converted` `{dxf_path, entity_count, converter}` — 데스크톱이
  `convert.request` WS 이벤트에 대한 답으로 부른다.
- `POST /api/v1/files/{id}/crosscheck` `{other, whitelist?}` — 뷰어의 `statsByLayer()` 결과를
  이 파일의 엔진 stats와 비교해 `drawing_file.parser_crosscheck`에 저장한다
  (ADR-0002 결정 6).

CORS는 `halocad://app`, `http://localhost:5173`, `http://127.0.0.1:5173`만 허용한다.
WebSocket `/api/v1/ws`는 첫 프레임 `{"type":"auth","token":...}`으로 인증한다(계약,
"Defaults for ambiguity"); 이벤트는 `job.progress` / `job.done` / `job.failed` /
`convert.request`.

```bash
uv run halo-engine openapi --out <경로>
```

FastAPI 앱의 OpenAPI 스키마를 JSON으로 내보낸다(`packages/shared-types/openapi.json`으로
`openapi-typescript` 타입 생성을 거는 것은 W3-08 몫 — `packages/**`는 이 태스크 소유가 아니라서
`--out`은 기본값 없이 매번 명시해야 한다). stdout에는 쓴 경로 한 줄만 찍는다.

## 프로젝트 번들 (bundle, `docs/PLAN.md` §4, W3-03)

```
<name>.halo/
  project.json          # id, name, created_at (사람이 읽을 수 있는 사본)
  project.sqlite        # SQLAlchemy 2 + Alembic, project/drawing_set/drawing_file/xref_link/entity_index
                        #   + compare_set/sheet_frame/sheet_pair/change/cluster/run (R1)
  originals/<sha256>.<ext>   # 원본 복사본, 0444(CLAUDE.md 규칙 1 — 원본 자체는 절대 쓰지 않는다)
  cache/dxf/<sha256>.working.dxf   # 정본 DXF (ADR-0002)
  cache/mesh/                       # (P3+)
  derivatives/  sidecars/  exports/
  compare/<pair_id>/compare.dxf, clusters.json, markup.dxf   # 리비전 비교 산출물 (R1)
  compare.yaml  frames.yaml         # 처음 비교할 때 기본값이 복사된다. 사람이 고쳐도 된다
  log/<compare_set_id>.log          # 변환 로그·교차검증 불일치·COM 실패 (R1)
```

R1은 번들을 `<프로젝트>/.halo`에 두고, 출력은 `<프로젝트>/출력/<YYYY-MM-DD>[-n]/`에 쓴다
(`docs/contracts/r1.md` §2). 이 둘이 유일한 쓰기 허용 루트다.

엔진 워크스페이스는 한 번에 프로젝트 하나만 연다(`bundle.create.BundleHandle`,
`app.state.bundle`) — `apps/web`의 `workspace` Zustand 스토어(단수 project)와 대응.
`bundle/guard.py`의 `assert_writable_path()`가 원본 쓰기 가드다: `originals/` 바깥 경로에
쓰려고 하면 무조건 예외. "최근 프로젝트" 목록은 번들이 아니라 엔진 자신의 `--data-dir`
아래 `recent-projects.json`에 저장한다(어느 번들도 열려 있지 않아도 나열할 수 있어야 하므로).

## DWG 변환과 임포트 잡 (`docs/contracts/wave-3.md`, ADR-0002 2026-09-02 개정)

`POST /projects/{id}/drawing-sets`가 예약하는 잡은 파일마다 다음을 순서대로 한다
(`ingest/pipeline.py`의 순수 단계 + `api/jobs.py`의 오케스트레이션):

1. **복사** — 원본을 `originals/<sha256><ext>`로 복사하고 0444로 잠근다.
2. **DXF면 3으로.** DWG면 **변환**: WS로 연결된 데스크톱이 있으면 `convert.request`
   `{file_id, dwg_path, out_path}`를 보내고 `POST /files/{id}/converted`를 최대 10분
   기다린다. 없으면(또는 응답이 없으면) `--converter-fallback acad-ts`(서버 기본값 또는
   요청의 `converter_fallback` 필드)가 설정된 경우에만 엔진이
   `node packages/acad-bridge/bin/acad-bridge.mjs dwg2dxf`를 subprocess로 직접 실행한다.
   둘 다 아니면 `NEEDS_MANUAL_CONVERSION`.
3. **정본 DXF 생성** — `ingest/working_dxf.py`로 XREF 임베드 + 인코딩 보정 +
   R2018/UTF-8 업그레이드, 통계 계산까지 한 번에.
4. **교차검증 게이트**(DWG만, ADR-0002 개정 4항) — 감사기 삭제 건수 > 0 이거나 변환기가
   보고한 엔티티 수와 엔진이 센 수의 차이가 ±0.5%를 넘으면 **그 변환은 실패**(경고 아님).
   실패하면 다음 후보(데스크톱 실패 → acad-ts 폴백)로 넘어가고, 후보가 더 없으면
   `NEEDS_MANUAL_CONVERSION` + 각 후보가 실패한 이유.
5. 결과를 `drawing_file`에 쓰고 `job.progress`/`job.done` WS 이벤트를 보낸다.

**중요한 실측:** acad-ts CLI 폴백은 알려진 이유로 실제 도면에서 종종
`NEEDS_MANUAL_CONVERSION`으로 끝난다 — ADR-0002 개정 1항이 이미 문서화한 대로 acad-ts가
쓴 DXF에 ezdxf가 못 읽는 결함이 있다(ATTRIB 서브클래스 마커 누락, 중복 핸들 — `fixtures/generated`의
F01/F02/F06.dwg로 재현). `fixtures/generated/F10_host.dwg`처럼 그 결함을 피해가는 도면은
폴백으로 끝까지 성공한다. 결론은 ADR-0002가 이미 내린 것과 같다: **실제 운영 경로는 데스크톱의
`dxfOut()`**이고, acad-ts subprocess 폴백은 데스크톱이 없는 개발/CI 환경에서 "아무것도 안
하는 것보다 낫다" 수준의 보조 수단이다.

**W3-06(2026-09-03)이 XREF DWG 대상 재귀 변환을 넣었다** — 예전에는 여기서
"`ingest/xref.py`의 XREF 임베드가 ezdxf 기반이라 DXF만 읽을 수 있는데 실제 도면은 XR/ 폴더의
DWG를 XREF로 물어 FileNotFoundError로 실패한다"고 적혀 있었다. 지금은 해석된 XREF 대상이
`.dwg`면 `ingest/pipeline.py`의 `make_dwg_xref_converter`가 (오늘은 acad-ts 폴백으로) 먼저
DXF로 바꿔 `cache/dxf/<대상 sha256>.working.dxf`에 캐시해 두고 그 DXF를 임베드한다 — 데스크톱
`convert.request` 경로는 아직 XREF 대상까지는 배선하지 않았다(호스트 자신의 변환에만 쓰인다,
`docs/dev/xref.md` 참고). 대상 파일 자신의 중첩 XREF도 깊이 우선으로 재귀 처리하고, 순환
참조는 감지해서 멈춘다. 해석·변환·임베드 중 어느 하나라도 실패하면(예: 실측으로 새로 발견한
`ezdxf.xref.Loader`의 ATTRIB 서브엔티티 복제 결함 — `'Attrib' object has no attribute 'doc'`,
acad-ts DXF 라이터의 같은 계열 결함이 임베드 단계에서도 나타난 경우) 그 XREF 하나만
"미해결"로 남고 호스트 임포트 전체는 실패하지 않는다(`GET /files/{id}/xrefs`로 노출, UI
다이얼로그가 검색 경로 추가·수동 매칭을 받는다). 실측: `01_건축/A-100 평면도.dwg`를 `XR/`를
검색 경로로 주고 임포트하면 XREF 3건 중 2건(`TITLE BLOCK-V.dwg`, `단위세대_평면.dwg`)이
끝까지 임베드되고 `PLAN.dwg`는 위 ATTRIB 결함으로 미해결로 남는다 — 자세한 내용은
`docs/dev/xref.md`.

## 리비전 비교 (compare, `docs/contracts/r1.md`)

R1의 파이프라인이 사는 패키지다. 세트 인입 → 도곽 추출 → 짝짓기 → 엔티티 비교 → 클러스터 →
비교 DXF·사이드카 → 마크업 DWG·출력까지 모두 `compare/` 아래에서 계산하고(CLAUDE.md 규칙 4),
API 라우터와 잡 러너는 순서만 맡는다. 모듈별 소유 태스크는 계약 §6 표에 있다.

R1-01이 넣은 것:

- `compare/config.py` — `compare.yaml`·`frames.yaml`을 읽는다. 번들에 파일이 없으면
  `compare/defaults/`의 기본값을 **주석까지 그대로** 복사하고(사람이 고치는 파일이다),
  있으면 기본값 위에 키 단위로 덮는다(중첩 매핑은 병합, 리스트는 통째 교체). 모르는 키·틀린
  타입은 `CompareConfigError`로 파일 이름과 경로를 담아 실패한다. 인자는 `BundleHandle`·
  `BundleLayout`·번들 경로 아무거나 받는다.
  - `load_compare_config(bundle) -> CompareConfig`, `load_frames_config(bundle) -> FramesConfig`
  - `scale_factor(scale_denominator)` — 1:100 기준 값에 곱할 배율(`1:50` → 0.5, 못 읽으면 1.0).
  - `CompareConfig.revision_layer(run_date, suffix=None)` — `REV-20260904[-n]`.
  - ezdxf를 임포트하지 않는다(테스트가 검사한다). pyyaml·pydantic만 쓴다.
- DB(마이그레이션 `0003_compare_records`) — `compare_set` → `sheet_frame` → `sheet_pair` →
  `change`·`cluster`, 그리고 출력 1회를 담는 `run`. 기존 `drawing_set`에 `role`·`source_dir`,
  `drawing_file`에 `converter_meta`·`excluded_reason`·`font_names`가 붙는다. 0003의 모든 문장은
  존재 검사로 감싸져 있다 — `0001_initial`이 살아 있는 `Base.metadata`로 테이블을 만들기 때문에
  새로 만든 번들은 0001만으로 이미 여섯 테이블을 갖고 있고, 0002에 멈춰 있던 번들만 실제로 할 일이
  있다. 양쪽 모두 같은 스키마로 끝나야 한다(`tests/bundle/test_compare_db.py`).
- `db/repos.py`의 비교 함수 — 단계마다 한 층을 통째로 다시 쓰는 모양(`replace_frames`·
  `replace_pairs`·`replace_changes`·`replace_clusters`)이다. 다시 돌렸을 때 어제 행이 오늘 행
  옆에 남는 일을 막는다. `replace_changes`·`replace_clusters`는 짝의 집계(`change_count`·
  `minor_count`·`cluster_count`)도 같이 갱신하고, `replace_clusters(..., keep_decisions=True)`는
  같은 `signature`의 이전 `decision`·`user_label`·`note`를 새 클러스터로 이어받는다 —
  비교를 다시 돌려도 사용자의 승인·무시가 살아남는 이유다.
- 번들 경로 — `BundleLayout`에 `compare_dir`·`log_dir`·`compare_yaml`·`frames_yaml`과
  `compare_pair_dir(pair_id)`(ULID가 아니면 `ValueError`). `ensure_dirs()`가 `compare/`·`log/`도
  만든다.
- `model/compare.py` — 라우터 요청 본문(`CompareSetCreateRequest`, `ManualPairRequest`,
  `ClusterDecisionRequest`, `ExportRequest` 등). 응답 **레코드**는 여기 두지 않고
  `halo_schema.models.compare.*`(스키마에서 생성)를 쓴다.

R1-03이 넣은 것 (세트 인입 잡, 자세한 흐름은 `docs/dev/compare-ingest.md`):

- `compare/ingest_set.py` — `POST /compare/sets`가 시작하는 `compare.ingest` 잡의 몸통.
  `plan_set_files(dir, ignore_patterns)`(1단계만, `.dwg`/`.dxf`만, 이름 대소문자 무시 정렬),
  `pick_converter(zwcad_status, option)`(`auto`/`zwcad`/`builtin`), `enforce_same_converter(...)`
  (같은 이름 파일 하나가 `builtin`이면 상대 세트 것도 `builtin`으로), 그리고
  `run_compare_set_ingest(app, *, job, bundle, compare_set_id, zwcad_com=None)`. `zwcad_com`은
  테스트 전용 주입점(`ComBackend`)이며 운영 호출은 넘기지 않는다. sha256 캐시는 원본 파일의
  sha256 기준이라, DWG 입력은 `ingest/working_dxf.py`가 실제로 쓰는(변환된 DXF 기준) 경로 옆에
  같은 내용을 원본 sha256 이름으로도 복사해 둔다(`_mirror_working_dxf_to_original_sha`) — 그래야
  같은 원본으로 두 번째 인입할 때 변환을 다시 돌리지 않는다.
- `api/routers/compare_sets.py` — `POST /compare/sets`(202), `GET /compare/sets`,
  `GET /compare/sets/{id}`, `GET /compare/sets/{id}/files`. `CompareSetSummary`는 `halo_schema`가
  아직 엔진 의존성으로 배선되지 않아(Follow-up) 같은 필드의 평범한 `dict`로 낸다.
- `api/jobs.py` 확장 — `JobRecord`/`JobSummary`에 `compare_set_id`·`kind`·`stage`,
  `JobManager.create(..., compare_set_id=, kind=)`·`latest_for_compare_set(id)`, 그리고
  모든 `compare.*` 잡이 같이 쓰는 `run_job(app, job, work)`/`ProgressReporter`/`JobCancelled`
  (계약 §6.2). 기존 `run_drawing_set_import`는 그대로 자기 루프를 쓴다.

```bash
uv run pytest tests/compare tests/bundle -q
uv run pytest tests/api/test_compare_sets.py -q
HALO_REAL_SET=1 uv run pytest tests/compare/test_real_set_ingest.py -q -s   # opt-in, 실도면 필요
```

## 파일 인입 (ingest, `docs/adr/0002-working-dxf.md`)

```bash
uv run halo-engine stats <dxf 경로> --out <json 경로>
uv run halo-engine ingest <dxf 경로> --out <출력 디렉터리> [--search-path P]...
```

두 서브커맨드 모두 stdout에 결과 경로만 찍는다(사이드카 프로토콜의 READY 줄과 마찬가지로
로그는 stderr, 결과는 stdout 한 줄).

- `stats` — `halo_engine.ingest.stats.compute_layer_stats()`로 `LayerStatsDocument`
  (`packages/schema/src/stats/layer-stats.schema.json`)를 계산해 `--out`에 쓴다.
- `ingest` — 작업용 DXF 정본(`docs/adr/0002-working-dxf.md`)을 만든다: `ezdxf.readfile` →
  실패 시 `ezdxf.recover.readfile`(`ingest/dxf_loader.py`), R2007 이전 코드페이지 모지바케
  보정(`ingest/encoding.py`), XREF 임베드(`ingest/xref.py`, `ezdxf.xref.Loader` 기반, 5단계
  경로 해석), R2018(AC1032) UTF-8로 업그레이드해 저장한다. `--out` 아래 원본 sha256을 키로
  네 파일을 쓴다: `<sha256>.working.dxf`, `<sha256>.working.json`(메타: 원본/작업 sha256,
  코드페이지, 감사 오류 수, 핸들 맵·통계 경로), `<sha256>.stats.json`(LayerStatsDocument),
  `<sha256>.xref-handles.json`(임베드 시 재번호된 `{xref_file, original_handle,
  bound_handle}` 목록).

레이아웃(아래 "레이아웃" 절 참고): `ingest/dxf_loader.py`, `ingest/encoding.py`,
`ingest/xref.py`, `ingest/entity_index.py`(최상위 엔티티 레코드 생성기, SQLite 저장은
W6-01), `ingest/stats.py`, `ingest/working_dxf.py`. `ingest/stats.py`는 `fixtures_gen/stats.py`
(`fixtures/gen/`, 독립 uv 프로젝트)와 서로 임포트하지 않는 별도 구현이며, 두 결과는
F01~F10에서 정렬 직렬화 기준으로 일치해야 한다(`tests/ingest/test_engine_crosscheck.py`).

## 파서 교차검증 (crosscheck, `docs/adr/0002-working-dxf.md` 6, W2-04)

```bash
uv run halo-engine crosscheck --ref <stats.json> --other <stats.json> --out <경로 스템> \
  [--whitelist <yaml> | --no-whitelist] [--allow-sha-mismatch] [--fail-on-red]
```

세 파서(mlightcad / ezdxf / acad-ts)가 같은 정본 바이트에서 낸 `LayerStatsDocument`를
`(space, layer)` 버킷 단위로 비교해 레이어별 GREEN/AMBER/RED를 판정한다. 임계는
`docs/contracts/stats-definition.md` "비교 임계" 그대로다(카운트·`insert_by_block`·
`text_count`·`text_hash` 정확, 길이 ±0.1%, 해치 면적 ±0.5%, bbox ±1mm).

- `--out`은 **스템**이다: `<스템>.json`(`CrosscheckReport`)과 `<스템>.md`(한국어 레이어 표)를 쓴다.
- 종료 코드는 RED에서도 0이다(셸에서 `&& grep RED <스템>.md`로 이어 붙일 수 있게).
  CI에서 실패시키려면 `--fail-on-red`.
- 화이트리스트는 기본값이 `src/halo_engine/validate/whitelist.yaml`(알려진 파서 격차,
  항목마다 `reason` 필수). **카운트 격차는 절대 낮출 수 없다** — `count_by_type`·`text_count`·
  한쪽에만 있는 버킷은 로더가 거부하고, `insert_by_block`은 INSERT 총개수가 같을 때
  (= 블록 이름만 못 푼 경우)만 낮춰진다.
- `file_sha256`이 서로 다르면 경고만 남기고 비교는 진행한다(`--allow-sha-mismatch`로 경고 억제).
- `red_layers`가 신뢰도 라우팅(P4) 입력이다: 적색 레이어에 근거를 둔 물량은 감점된다.

픽스처 전체 실행은 저장소 루트의 `tools/crosscheck.sh`(결과표는
`docs/spikes/crosscheck-fixtures.md`에 재생성된다).

## 테스트

```bash
uv run pytest -q
```

- `tests/test_imports.py` — 네이티브 의존성(ezdxf, shapely, manifold3d, trimesh, ifcopenshell,
  numpy)이 임포트되고 최소 1개 연산이 실제로 동작하는지 확인한다.
- `tests/test_api.py` — `TestClient`로 인증·라우팅을 검증한다(실제 소켓 없음).
- `tests/test_serve.py` — 설치된 `halo-engine` 콘솔 스크립트를 서브프로세스로 띄워 READY 핸드셰이크,
  `/health`, `/shutdown`, 부모 PID 감시(부모가 죽으면 5초 내 종료)를 end-to-end로 검증한다.
- `tests/ingest/` — 로더 복구·감사(`test_dxf_loader.py`), 인코딩 보정·MIF/유니코드
  디코드(`test_encoding.py`), XREF 경로 해석 5단계·임베드·핸들 맵(`test_xref.py`), 통계
  계약(ATTRIB 처리·해시·bbox·entity_count 불변식, `test_stats.py`), 엔티티 인덱스
  JSONL(`test_entity_index.py`), 작업용 DXF 산출물·결정론(`test_working_dxf.py`),
  `fixtures/truth/F*.json`이 `LayerStatsDocument` 스키마를 통과하는지(`jsonschema` +
  `referencing`, `test_truth_schema.py`), 엔진 stats와 `fixtures_gen.stats`가 F01~F10에서
  일치하는지(`test_engine_crosscheck.py`)를 검증한다. `fixtures/generated`·`fixtures/truth`가
  없으면(`cd fixtures/gen && uv run python -m fixtures_gen` 실행 전) 해당 테스트는 skip된다.
- `tests/bundle/` (W3-03) — 번들 레이아웃(`test_layout.py`), 원본 쓰기 가드
  (`test_guard.py`), 원본 복사·불변성·0444(`test_originals.py`), 번들 생성/열기·Alembic
  마이그레이션(`test_create.py`), `db/repos.py`·`db/ids.py` CRUD(`test_db.py`).
- `tests/api/` (W3-03) — httpx `TestClient` 통합: 프로젝트 CRUD(`test_projects.py`),
  DXF 임포트 end-to-end + F10 XREF 세트 + 파일별 crosscheck 저장(`test_drawing_sets_import.py`),
  WS 인증 + `convert.request`/`converted` 왕복(가짜 변환기, `test_ws_convert.py`), acad-ts
  CLI 폴백(빌드돼 있으면, `test_converter_fallback.py`), 잡 취소(`test_jobs_cancel.py`),
  교차검증 게이트 순수 함수(`test_pipeline_gate.py`). acad-ts CLI가 빌드돼 있지 않으면
  (`pnpm --filter @halo-cad/acad-bridge build` 전) 폴백 테스트만 skip된다.

## 린트·타입

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

`halo_engine.model`, `halo_engine.rules`, `halo_engine.geometry`는 (지금은 빈 패키지지만)
strict mypy가 적용된다 — 첫 실제 모듈부터 타입 검사가 걸린다.

## 레이아웃

```
src/halo_engine/
  __init__.py      # __version__
  cli.py           # typer: serve, ingest, stats, crosscheck, openapi
  config.py        # pydantic-settings, env prefix HALO_ENGINE_
  api/
    main.py        # FastAPI 앱 팩토리 create_app(settings) -- 라우터 등록만
    jobs.py        # JobManager(ProcessPoolExecutor spawn,2), 임포트 잡 오케스트레이션, GET/POST /jobs/* (W3-03)
    ws.py          # /api/v1/ws, ConnectionManager(convert.request<->converted) (W3-03)
    routers/
      system.py       # health / capabilities / shutdown
      crosscheck.py   # POST /api/v1/files/crosscheck (상태 없음, W2-04)
      projects.py     # POST /projects, /projects/open, GET /projects/recent, /projects/{id} (W3-03)
      drawing_sets.py # POST /projects/{id}/drawing-sets, GET /drawing-sets/{id}/files (W3-03)
      files.py        # working-dxf 스트림, stats, converted 콜백, 파일별 crosscheck 저장 (W3-03)
  bundle/          # <name>.halo 번들 (W3-03)
    layout.py        # 고정 디렉터리 레이아웃 + 기본 위치
    guard.py          # assert_writable_path -- 원본 쓰기 가드 (CLAUDE.md 규칙 1)
    originals.py      # 원본 복사 -> originals/<sha256><ext>, 0444
    create.py         # create_bundle / open_bundle -> BundleHandle
  compare/         # 리비전 비교 (R1) — 계약 docs/contracts/r1.md §6
    config.py         # compare.yaml/frames.yaml 로더 + scale_factor (R1-01)
    defaults/         # 기본 compare.yaml·frames.yaml (번들로 복사되는 원본)
  db/              # SQLite 영속화 (파일 계열 W3-03 + 비교 계열 R1-01)
    models.py         # SQLAlchemy 2 ORM: project/drawing_set/drawing_file/xref_link/entity_index
                      #   + compare_set/sheet_frame/sheet_pair/change/cluster/run
    session.py        # 번들별 engine/session factory
    repos.py          # ORM을 직접 만지는 유일한 곳
    ids.py            # ULID
    migrate.py        # 이 패키지의 Alembic 마이그레이션을 project.sqlite에 적용
    alembic/          # env.py + versions/0001_initial.py … 0003_compare_records.py
                      #   (alembic.ini 없음, Config는 코드로 구성)
  ingest/          # DXF 로드·인코딩·XREF·정본·통계 (W2-03)
    dxf_loader.py    # ezdxf.readfile -> 실패 시 ezdxf.recover, 헤더/감사 추출
    encoding.py      # R2007 이전 코드페이지 모지바케 점수·cp949 재시도, \M+/\U+ 디코드
    xref.py          # XREF 경로 해석(5단계)·임베드(ezdxf.xref.Loader)·핸들 맵
    entity_index.py  # 최상위 엔티티 레코드 생성기(iterable/JSONL, SQLite는 W6-01)
    stats.py         # LayerStatsDocument (fixtures_gen/stats.py와 독립 구현)
    working_dxf.py   # 위 넷을 조합해 <sha256>.working.dxf/.json 생성
    pipeline.py      # 임포트 잡의 순수 단계: 복사/acad-ts 폴백/working-dxf/교차검증 게이트 (W3-03)
  validate/        # 교차검증 (W2-04)
    crosscheck.py                    # 버킷 비교·임계·화이트리스트·마크다운 렌더
    whitelist.yaml                   # 알려진 파서 격차 (항목마다 reason 필수)
    crosscheck_report.schema.json    # CrosscheckReport의 JSON Schema (모델에서 생성)
  model/           # 부재·공간·면 모델 (W3+); mypy strict
    crosscheck.py    # CrosscheckReport
    project.py       # 프로젝트 API 리소스 모델 (W3-03)
    drawing.py       # 드로잉셋/파일/잡 API 리소스 모델 (W3-03)
    compare.py       # /compare/* 요청 본문·202 응답 (R1-01)
  rules/           # 적산 룰 엔진 (W4+)
  geometry/        # 3D 재구성 기하 (W3+)
tests/
  ingest/          # ingest/** 단위·통합 테스트
  validate/        # 교차검증 단위·API·스키마 테스트
  bundle/          # bundle/** + db/** 단위 테스트 (W3-03, + test_compare_db.py R1-01)
  compare/         # compare/** 단위 테스트 (R1); conftest.py가 임시 번들 픽스처 제공
  api/             # projects/drawing-sets/files/jobs/ws 통합 테스트 (W3-03)
```
