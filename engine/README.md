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
- `GET /api/v1/system/capabilities` — 토큰 필요. 현재 정직한 기능 플래그
  (`{dwg2dxf: false, ifc_export: true, job_runner: false, websocket: false, dms_sync: false}`).
  잡 러너·WebSocket 라우터는 W2-01·W8-05에서 붙는다(`api/routers/__init__.py`가 자리만 남김).
- `POST /api/v1/system/shutdown` — 토큰 필요. 우아한 종료를 요청한다.
- `POST /api/v1/files/crosscheck` — 토큰 필요. 본문 `{reference, other, whitelist?}`
  (`LayerStatsDocument` 두 개 + 화이트리스트 경로). 응답은 `CrosscheckReport`
  (`halo_engine/validate/crosscheck_report.schema.json`). 아래 "파서 교차검증" 절 참고.

CORS는 `halocad://app`, `http://localhost:5173`, `http://127.0.0.1:5173`만 허용한다.

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
  cli.py           # typer: serve, ingest, stats, crosscheck
  config.py        # pydantic-settings, env prefix HALO_ENGINE_
  api/
    main.py        # FastAPI 앱 팩토리 create_app(settings)
    routers/
      system.py     # health / capabilities / shutdown
      crosscheck.py # POST /api/v1/files/crosscheck
  ingest/          # DXF 로드·인코딩·XREF·정본·통계 (W2-03)
    dxf_loader.py    # ezdxf.readfile -> 실패 시 ezdxf.recover, 헤더/감사 추출
    encoding.py      # R2007 이전 코드페이지 모지바케 점수·cp949 재시도, \M+/\U+ 디코드
    xref.py          # XREF 경로 해석(5단계)·임베드(ezdxf.xref.Loader)·핸들 맵
    entity_index.py  # 최상위 엔티티 레코드 생성기(iterable/JSONL, SQLite는 W6-01)
    stats.py         # LayerStatsDocument (fixtures_gen/stats.py와 독립 구현)
    working_dxf.py   # 위 넷을 조합해 <sha256>.working.dxf/.json 생성
  validate/        # 교차검증 (W2-04)
    crosscheck.py                    # 버킷 비교·임계·화이트리스트·마크다운 렌더
    whitelist.yaml                   # 알려진 파서 격차 (항목마다 reason 필수)
    crosscheck_report.schema.json    # CrosscheckReport의 JSON Schema (모델에서 생성)
  model/           # 부재·공간·면 모델 (W3+); crosscheck.py = CrosscheckReport (mypy strict)
  rules/           # 적산 룰 엔진 (W4+)
  geometry/        # 3D 재구성 기하 (W3+)
tests/
  ingest/          # ingest/** 단위·통합 테스트
  validate/        # 교차검증 단위·API·스키마 테스트
```
