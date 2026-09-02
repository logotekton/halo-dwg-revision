# 대명건설 무료 CAD + 도면관리 + 적산 — 전체 계획

작성 2026-09-02 (v2, 순서 재조정). 가칭 **Halo CAD**(앱), `halo_engine`(파이썬 엔진), 저장소 `halo-cad`. 이름은 사용자가 변경 가능.

## Context

- 사용자 지시 3가지와 **확정 순서: (1) Mac/Windows 호환 무료 CAD → (3) 도면관리 시스템(DMS) → (2) 적산.** (2) 안에서는 **3D 재구성(모델링)을 먼저** 완성하고, 그 위에 적산 기능을 **구조 → 내부마감 → 외부마감** 순으로 붙인다. CAD 범위는 "DWG 세트를 열고 보고 보정하는 수준 + 기본 편집"이며 AutoCAD 드래프팅 대체가 아님.
- 확정 방법론: 도면 세트를 파라메트릭 3D로 재구성 후 결정론적 룰 엔진(국토부 수량산출기준)으로 산출. 구조체=솔리드, 공간=프리즘, 마감=면 속성. 5계층 파이프라인(도면 세트 그래프 → 3중 투표 정규화 → 3트랙 개수/구조/마감 → 룰 엔진 → 교차검증·신뢰도 라우팅). 높이 4개 필드 분리: SL, FL, 층고(SL–SL), 천장고 CH. **입면 레벨과 층고표(CH)의 등호 비교 금지.** 초기 제외: 계단 마감, 우물천장, 커튼월, 변단면. 원본 DWG 불변.
- 제약: 사내 전용(GPL 허용), 개발은 Claude가 전부, 사용자는 스티어링과 게이트 승인. 3D 검수는 같은 앱 안. 상용 과금 불가. **ODA File Converter 사용 금지.** FreeCAD는 기반 아님. UI 한국어.
- 오케스트레이션: **Fable 5.1**이 계획·브리핑·분해·검토·통합·사용자 소통. **Sonnet**은 명세가 분명한 구현(UI 패널, CRUD, 픽스처, 테스트, 문서, 패키징, 서버 CRUD). **Opus**는 판단·알고리즘 난도 높은 모듈(일람표 셀 복원, 3중 투표 정규화, 재구성 기하, 실 폴리곤 폐합, 룰 엔진, 파서 교차검증, 크로스 스택 디버깅, 어댑터·서버 아키텍처).
- 사용자 환경 답변: 실제 DWG 샘플 2~3주 내 확보(그동안 합성 DXF). 검증용 상용 CAD 없음. Windows 검증은 GitHub Actions Windows 러너. 저장소 GitHub 비공개(생성은 사용자).
- 개발 Mac 실측: macOS 26.5.1 arm64, 24GB. Node 24.20 ✓, corepack ✓(pnpm은 외부 경로 잔존 → corepack으로 pnpm 10), Python 시스템 3.9.6만 → **uv 설치 후 Python 3.12**. Homebrew·gh·uv·LibreDWG·Xcode.app 없음(CLT만, codesign/notarytool 있음). 관리자 암호 필요 항목은 사용자 작업.
- 순서 변경의 영향: DMS 서버 인프라(호스트, PostgreSQL, 인증 방식) 결정이 **11월 초**로 앞당겨짐. 골든셋(적산 산출서)은 **3월 초**까지로 늦춰짐. "변경 도면 물량 비교"는 DMS 단계가 아니라 각 적산 트랙 완료 시마다 추가됨(DMS 단계에서는 도면 엔티티 diff까지).

## 1. 확정 스택과 핵심 결정

| 계층 | 선택 | 버전 고정 |
|---|---|---|
| 데스크톱 셸 | Electron + electron-vite + electron-builder | Electron 44.1.x, Node 24, pnpm 10(corepack) |
| UI | Vite 7 + React 19 + TS strict, Zustand, TanStack Query, Tailwind 4 + shadcn/ui, i18next(ko) | |
| 2D 도면 코어 | `@mlightcad/cad-simple-viewer` + `data-model` + `three-renderer` + `mtext-renderer` (MIT) | 1.6.3 / 1.14.3 / 1.6.3 / 0.12.x, `three@0.172.0` |
| DWG 파싱(브라우저) | `@mlightcad/libredwg-converter` + `libredwg-web` (GPL, 사내 OK) | 3.14.3 / 0.7.10, `packages/dwg-io-gpl`에만 임포트 |
| DWG 읽기·쓰기(Node) | `@node-projects/acad-ts` (MIT, ACadSharp 포트, R14~2018) | 3.1.0 |
| 3D 패널 | Three ≥0.182 + `@thatopen/components` 3.4.8 + `web-ifc` 0.0.77, **별도 Vite 엔트리를 iframe으로 격리** | |
| 엔진 | Python 3.12, ezdxf 1.4.4, shapely 2.1.2, manifold3d 3.5.2, trimesh 5.1, ifcopenshell 0.8.5, openpyxl, FastAPI 0.141 + uvicorn 0.52(uvloop 제외), SQLAlchemy 2 + Alembic, SQLite(WAL) 로컬 / PostgreSQL 서버 | uv.lock |
| DMS 서버 | 같은 엔진 코드베이스의 서버 모드(FastAPI) + PostgreSQL 18 + 오브젝트 스토어(파일시스템 또는 MinIO) + 인증 어댑터(LDAP/로컬) | |
| 패키징 | PyInstaller 6.22 onedir 사이드카(플랫폼별, 크로스 컴파일 불가) + electron-builder(dmg/zip arm64·x64, nsis x64) | |
| 선택적 | build123d + cadquery-ocp-novtk(정밀 B-rep 예외), 네이티브 LibreDWG dwg2dxf(3차 대체) | 기본 미포함 |

핵심 결정:
1. **작업용 DXF 정본(working DXF).** 파일마다 R2018 UTF-8, XREF 임베드, 인코딩 보정된 DXF를 만들고 **뷰어와 엔진이 같은 바이트를 파싱**한다 → 핸들 일치. DWG→DXF 변환은 데스크톱 Node utilityProcess에서 acad-ts(1차) 또는 mlightcad data-model `dxfOut()`(2차, 검증 필요). 엔진은 DXF만 읽는다. 브라우저 WASM은 임포트 중 즉시 미리보기(≤60MB)와 변환 실패 대체용. 기본 변환기는 **G0 실측으로 확정**.
2. **엔진이 물량·모델의 단일 진실 소스, 뷰어는 표시·피킹·측정·편집.** 뷰어 측정값은 "측정"으로만 표시.
3. **엔진이 프로젝트 번들 소유**(SQLite 단일 작성자). DMS 서버는 같은 모델을 PostgreSQL에서 운용하고 번들을 리비전 단위로 수용한다.
4. **3D 전달은 glb, 교환·검증은 IFC.** 층별 glb(부재)+실 프리즘 glb+마감 면 glb, 노드 extras에 id/kind/tag/confidence.
5. **원본 불변.** `originals/<sha256>` 읽기전용 복사, 편집은 `derivatives/`(기본 DXF, DWG는 왕복 게이트 통과 시). 원본 경로 쓰기는 가드가 거부. DMS는 내용 주소(sha256) 저장이라 바이트 동일 복원이 자연스럽다.
6. **GPL 경계.** `packages/dwg-io-gpl`과 Electron 배선 외에서 `@mlightcad/libredwg-*` 임포트 금지(ESLint + 라이선스 검사). ODA 문자열은 CI grep 금지.
7. **ML과 룰 분리.** 룰은 YAML 메타(출처 조항) + 순수 함수, formula_trace 필수. 분류 ML은 별도 모듈로 나중에.
8. **3D 재구성은 적산과 분리된 독립 산출물.** P3에서 부재 DB·솔리드·프리즘·면 속성·IFC를 먼저 완성하고 검수한다. 적산 룰(P4~P6)은 이 모델 위에서만 동작하며 모델을 바꾸지 않는다.

## 2. 아키텍처와 저장소

```
Electron 44 main ──spawn(env 토큰)──▶ halo-engine (FastAPI, 127.0.0.1:임의포트, PyInstaller onedir)
  │ halocad://app 렌더러 (apps/web)                 │ REST + WS(진행률·model.changed), 파일은 절대경로 교환
  ├─ packages/cad-core   ← mlightcad 유일 임포트(CadHost 파사드), 자체 편집 명령, stats, 오버레이
  ├─ packages/dwg-io-gpl ← libredwg-web/converter 유일 임포트(브라우저 워커 + Node utilityProcess)
  ├─ packages/acad-bridge← acad-ts: DWG→DXF 변환, 파생 DWG 쓰기, CLI
  ├─ apps/viewer3d       ← iframe, Three≥0.182 + ThatOpen + web-ifc, postMessage 브리지
  ├─ packages/schema     ← JSON Schema(NDJ/사이드카/브리지) → TS·pydantic 코드젠; API 타입은 OpenAPI→TS
  └─ (P2) halo-engine --mode server  ← 같은 코드, PostgreSQL + 오브젝트 스토어 + 인증, 클라이언트 동기화 API
```

```
halo-cad/
├─ CLAUDE.md  package.json  pnpm-workspace.yaml  .nvmrc  .python-version  pyproject.toml  uv.lock
├─ .github/workflows/{ci.yml, package.yml, nightly-golden.yml}     # macos-14(arm64), macos-13(x64), windows-latest
├─ apps/desktop/   src/main/{index,sidecar,windows,menu}.ts  main/ipc/{files,convert,dwgwrite}.ts  preload/  electron-builder.yml  resources/{engine,fonts}
├─ apps/web/       src/{app,api,state,i18n/ko.json,features/{files,layers,view,select,measure,edit,text,markup,crosscheck,dms,model,qto,review,threed,diff},components}
├─ apps/viewer3d/  별도 Vite 엔트리(iframe)
├─ apps/dms-admin/ (P2) 관리 UI, apps/web와 컴포넌트 공유
├─ packages/{cad-core, dwg-io-gpl, acad-bridge, schema, shared-types, diff, testing}
├─ engine/  pyproject.toml  .python-version(3.12)  alembic.ini  halo-engine.spec
│   └─ src/halo_engine/{cli,config}.py  api/{main,ws,jobs,routers/*}  db/{engine,models,repos,alembic}  model/
│       server/{auth,storage,sync,revisions}.py                       # P2 DMS
│       ingest/{dxf_loader,encoding,xref,working_dxf,entity_index,fingerprint,stats}.py
│       sheetgraph/{frames,classify_rules,tags,floors,units_scale}.py
│       normalize/{vote,geometry_features,text_features,layer_dictionary,blocks,dedupe}.py  normalize/dictionaries/*.yaml
│       schedules/{table_detect,cells,semantics,member_schedule,level_table,finish_schedule,window_schedule,legend}.py
│       recon/{levels,openings,track_b_structure,rooms,finish_faces,exterior,linear,carry_forward}.py
│       geometry/{tolerance,solids,booleans,faces,mesh_export}.py
│       rules/{engine,registry}.py  rules/kr_mlit/{concrete,formwork,rebar,finish,openings,exterior}.py  rules/content/*.yaml
│       validate/{crosscheck,confidence,routing}.py  export/{ifc,xlsx,dxf_overlay,pdf}.py  diff/{entity_diff,quantity_diff}.py  fixtures/{apartment,noise,truth}.py
│   └─ tests/{unit,integration,golden/cases/*.yaml}
├─ fixtures/   생성 DXF/DWG(소형 커밋, 대형 gitignore) + truth/ + 스크린샷 베이스라인
├─ tools/      verify.sh  package.sh  crosscheck.sh  bench-open.mjs  golden.py  license-check.mjs  build-libredwg.sh(3차)
├─ tests/e2e/  Playwright(_electron.launch)
├─ spikes/     일회성 스파이크(패키지에서 임포트 금지, 채택 후 삭제)
└─ docs/{adr, briefs, gates, spikes, samples, rules, user/ko, dev}
```

소유권 규칙: 태스크 1개 = 디렉터리 1개 이상. 공유 파일(루트 package.json, pnpm-lock, `packages/schema/**`, `CLAUDE.md`, `tools/verify.sh`)은 Fable 소유. 에이전트는 보고서의 "Shared-file patch" 블록으로 제안.

## 3. 사이드카 프로토콜

1. main이 32바이트 토큰 생성 → `halo-engine serve --data-dir <userData>/engine` 실행. env `HALO_ENGINE_TOKEN`(argv 금지), `HALO_ENGINE_PARENT_PID`, `PYTHONUTF8=1`.
2. 엔진이 `127.0.0.1:0` 바인드 후 stdout 한 줄 `{"event":"ready","port":N,"version":...}`.
3. main이 `/api/v1/system/health` 폴링(30s), 실패 시 로그 tail + "다시 시도".
4. preload `window.dmcad.engine.getConnection()`으로 baseUrl+토큰 1회 전달. 렌더러는 openapi-fetch. WS 첫 프레임 `{"type":"auth","token"}`.
5. 부모 PID 감시(부모 종료 시 5초 내 종료). 종료 `POST /system/shutdown` → 5초 → SIGTERM/taskkill. 크래시 시 3회 백오프 재시작, 진행 중 잡 `FAILED(engine_restart)`.
6. 300ms 초과 작업은 `202 {job_id}`, ProcessPool(spawn, 2), WS `job.progress/done/failed`, `model.changed`. 대용량은 ETag/Range HTTP 스트림.
7. 개발 모드: `HALO_ENGINE_URL` 지정 시 spawn 생략, `uv run halo-engine serve --dev --reload`에 부착. Electron 없이 브라우저에서 UI 개발 가능.
8. (P2) 서버 모드: 같은 라우터 + `server/*`, 인증은 어댑터(LDAP 또는 로컬 계정), 클라이언트 사이드카가 서버와 동기화(체크인/아웃, 리비전 업로드·다운로드). 로컬 사이드카는 오프라인에서도 동작.

## 4. 데이터 모델(부재 DB)

번들 `<name>.halo/`: `project.json`, `project.sqlite`, `originals/<sha256>.dwg`(0444), `cache/dxf/<sha256>.working.dxf`, `cache/mesh/<run>/<floor>.glb`, `derivatives/`, `sidecars/*.json`(핸들 키, git diff 가능), `exports/`. 기하 WKB + bbox + R*Tree. id ULID. SQLite 전용 타입 회피(PostgreSQL 공용).

- 파일: `project`, `drawing_set`(=DMS 리비전 단위), `drawing_file`(sha256, dwg_version, fingerprint_guid, codepage_declared/effective, working_dxf_path, parser_crosscheck), `xref_link`, `xref_handle_map`, `entity_index`(file_id, handle, etype, layer, block_name, bbox, length, area, text, fingerprint).
- **EntityRef** `{file, handle, path[INSERT 체인], space, role}` — 모든 근거(evidence)의 단위.
- **DMS(P2):** `revision`(project_id, set_id, rev_no, label, imported_by, notes, parent_rev), `file_lineage`(fingerprint_guid 또는 사용자 확정), `checkout`(file_lineage_id, user, since, state), `entity_diff`(from_rev, to_rev, lineage, handle, change ADDED|REMOVED|MODIFIED|MOVED, delta), `approval`(revision, state DRAFT|REVIEW|APPROVED|SUPERSEDED, by, at, comment), `audit_log`, `user`, `role`, `notification`.
- 시트: `floor`, `sheet`(파일 안 도곽 영역 단위, sheet_type, floor 다대다, scale, units, classification_source AUTO_RULE|AUTO_ML|USER), `tag_reference`.
- **레벨:** `level_observation`(kind **SL|FL|FLOOR_HEIGHT|CH**, source, evidence) + `floor_levels`(층별 확정값·출처·방법·충돌). 규칙(`recon/levels.py`): 같은 기준 등호(입면 SL↔단면 SL↔구조평면 SL, 5mm), 다른 기준 부등식(CH+슬래브+바닥마감 < 층고). **SL/FL↔CH 등호 비교는 스키마 검증기가 거부.** 실내 벽 마감 높이=CH, 구조체·외벽 면=SL.
- 구조: `section_def`(태그, 종류, 층 범위, 형상, dims, 재료, 출처 셀), `member`(배치, z범위, height_basis, stable_key, evidence, status AUTO|CONFIRMED|EDITED|EXCLUDED), `member_relation`(접합 기하).
- 개구부: `opening_type`(창호일람표), `opening`(호스트 부재/실, 블록 참조), `count_check`(블록 수 vs 일람표 수).
- 실/마감(3D 모델 단계에서 생성, 적산 단계에서 소비): `finish_code`, `room`(polygon, CH override, closing_method, name_match, finish_matrix), `finish_face`(subject, face_kind FLOOR|CEILING|WALL|BASE|EXT_WALL, geometry, gross/deduction/net 면적, finish_code, confidence), `exterior_zone`(입면 좌표 폴리곤, facade_mapping, residual), `linear_item`(경계석·측구·걸레받이 후보 폴리라인), `manual_item`.
- 물량/룰/검수(P4~): `compute_run`, `quantity_item`(subject, work_item_code, unit, gross/deduction/net, rule_id+version, formula_trace, evidence, confidence, review_status), `rule`(예 `KR-MLIT-CONC-COLUMN-HEIGHT`, 출처 조항, impl), `review_action`(감사 로그·carry_forward 원천), `quantity_diff`(from_run, to_run, work_item, subject_stable_key, before, after, cause GEOMETRY|SECTION|LEVEL|RULE|MANUAL), `markup`.
- 재임포트 식별 3단계: `(sha256, handle)` → `($FINGERPRINTGUID, handle)` → 기하 지문(type+layer+1mm 격자 sha1, 최근접). 파생 객체 `stable_key`. `carry_forward.py`가 결정 재부착, 실패분은 "고아 결정" 목록(무단 삭제 없음). DMS 리비전 간 diff도 같은 식별 체계를 쓴다.

## 5. UI↔엔진 계약, 인입 경로, 기하 엔진

**API** `/api/v1`, pydantic v2 → OpenAPI → `openapi-typescript`(stale이면 CI 실패). 영역: system, jobs+WS, projects, drawing-sets, files(working-dxf/original 스트림, stats, crosscheck, xrefs, encoding, entities, 역방향 근거), **dms(P2: revisions, checkouts, approvals, search, notifications, users)**, sheets, schedules(parse-table, table GET/PUT, section-defs, opening-types, finish-codes, legend-links), levels, **model(P3: reconstruct 잡, members/rooms/openings/finish-faces/exterior-zones/linear CRUD, split/merge/close/map-facade, manifest, glb, ifc)**, compute(P4~: runs, summary, items, evidence, review-queue, compare), review, overlays, export(xlsx, dxf-overlay, pdf), markup, rules, diff(entities P2, quantities P4~).

**뷰어↔엔진 정합:** 키 `(file_id, handle)`. CadHost: `getEntityByHandle/highlight/zoomTo/pick/statsByLayer/onSelectionChanged/runCommand/undo`. 임포트 후 뷰어 `statsByLayer()` → `POST /files/{id}/crosscheck` → 레이어별 녹/황/적, 적색 레이어 근거는 신뢰도 감점. 오버레이는 JSON → transient 엔티티.

**인입 결정 트리:** DXF → ezdxf(실패 시 recover). DWG AC1009 이하 → 거부·안내. AC1014~1032 → 미리보기 WASM(≤60MB) + 변환(acad-ts → data-model dxfOut → 네이티브 dwg2dxf 3차) → 정본 DXF(인코딩 보정 → `ezdxf.xref` 임베드+핸들 맵 → AC1032 저장) → ezdxf. 모두 실패 시 `NEEDS_MANUAL_CONVERSION`. 브라우저 크기 정책: ≤200MB 그대로, 200~600MB 라이트 DXF "대용량 모드", >600MB 엔진 전용(썸네일 + 도곽 단위 시트 추출). 임계값은 G0 실측으로 보정.

**인코딩:** R2007+ UTF-8, 이전 `$DWGCODEPAGE`. 한글은 ANSI_949지만 1252 오표기 흔함 → 모지바케 점수로 cp949 재시도, `\M+1XXXX`·`\U+XXXX` 디코드, 사용자 override. **단위·축척 3중 투표.** **XREF 순서:** 저장 절대경로(세트 내) → 동일 폴더 → 상대경로 → 프로젝트 검색경로 → basename 무시 매칭 → UNRESOLVED(UI). **파서 교차검증:** `stats.ts`/`stats.py` 동일 정의, 카운트 정확, 길이 ±0.1%, 면적 ±0.5%, 화이트리스트(ACAD_TABLE, MLEADER, 프록시) 적→황.

**기하 엔진:** mm float64, 인덱스 0.1mm·위상 1mm 스냅, 반올림은 룰 계층만. `SolidSpec` → manifold3d extrude. 기둥 SL→다음 SL, 보는 지지 부재 내측면 간 순길이 폐쇄식, 슬래브는 보/벽 중심선 polygonize. **접합 공제는 산식 우선, 불리언은 감사자**(층별 union 부피 vs 산식 합 ≤0.5%). 열 기호 그리드 앵커(기둥 50mm, 보 30mm, 이력 trace). **실 폐합:** unary_union → polygonize_full → 갭 300mm → 300~1500mm는 문/창 블록 사이일 때만 → 슬리버·외곽 제거 → 실명(내부 텍스트 → 1m 최근접 → 검수). **외부 존:** 입면 해치+범례, 레벨 라벨 y축 보정(SL 같은 기준만), 입면 제목 → 외벽 변 체인(자동 제안+사용자 확인), 그리드 라벨 affine 정합(residual>100mm 검수), `(s,z)` 전개 좌표, 창호 공제, 돌출부 초기 무시+플래그.

## 6. 단계와 게이트

| 단계 | 기간(예상) | 진입 조건 | 사용자 제공 | 종료 기준(게이트) | 실패 시 대체 |
|---|---|---|---|---|---|
| **P0 스택 스파이크** | 9/3~9/19, G0 9/22 | H0(uv+Py3.12, GitHub 저장소) | uv 설치 승인, 저장소 URL, 샘플 요청 착수 | DXF·DWG 픽스처 한글 렌더; 사이드카 왕복; 3파서 픽스처 일치; 대용량 실측+기본 변환기 결정; mac arm64 패키지 실행; Windows CI 녹색 또는 명시 연기; 편집 capability 매트릭스 | WASM OOM → Node 변환 기본화; acad-ts 실패 → dxfOut → 네이티브 LibreDWG; SHX 실패 → Noto Sans KR 매핑 P0 승격; 뷰어 API 부적합 → mlightcad Vue 셸 임베드 |
| **P1 CAD 워크스테이션** | 9/22~10/31, G1 11/3 | G0 통과, 실제 세트 ≥10 | 실제 세트 ≥30, 폰트, Apple Developer ID 결정, Windows 배포 방식 | 실제 파일 ≥90% 열림; 편집 8그룹 시연; 파생 DWG 재개방·카운트 일치; PDF/SVG; 3D 패널 IFC 로드; 마크업·파일 diff; 3타깃 패키지; 30분 무크래시 | 충실도 실패 → 엔티티 클래스별 Opus 집중; DWG 쓰기 실패 → 파생 DXF만 |
| **P2 도면관리(DMS)** | 11/3~12/19, G2 12/22 | G1 통과, **서버 호스트+PostgreSQL 준비, 인증 방식 결정** | 서버(Linux VM 또는 Mac mini), AD/LDAP 여부, 사용자·권한 정책, 도면번호 체계·승인 절차 | 두 클라이언트 체크인/아웃·충돌 감지; 리비전 체인(해시)·바이트 동일 복원; 임의 두 리비전 시각 diff+변경 목록; 메타데이터 검색(도면번호·제목·층·공종); 승인 워크플로우; 감사 로그; 백업·복원; 20 클라이언트 부하 | 인프라 지연 → SQLite+공유폴더 임시 저장소로 동일 API; 인증 미결 → 로컬 계정 |
| **P3 3D 재구성** | 12/22~3/5, G3 3/9 | G2 통과, 실제 세트(구조+건축) ≥5 프로젝트, 일람표 ≥15장/≥5사 | 도면 세트, 일람표·층고표·마감표·창호표·입면 양식 샘플, 주간 도메인 판정 | 실제 세트: 시트 분류 ≥90%, 일람표 셀 ≥95%·부호+치수 ≥90%, 레벨 ≥95%, 부재 P/R ≥90%; 픽스처 기하 truth ±0.5%; 실 자동 폐합 픽스처 ≥95%·실제 ≥85%; 외벽 매핑 residual<100mm ≥80%; 마감 면 매트릭스 조인 완료; IFC validate 통과·3D 패널 로드; 사용자 육안 검수 "모델이 도면과 같다" | 표 파싱 미달 → **하이브리드**(일람표당 5분 확인 필수); 특정 부재 클래스만 실패 → 해당 클래스 hold 기본; 실 폐합 미달 → 실 승인/분할/병합 UI 필수 단계(층당 ≤10분) |
| **P4 적산 구조** | 3/9~4/24, G4 4/27 | G3 통과, **골든셋 ≥3건**(도면+산출서+적용 기준), 엑셀 템플릿 | 골든셋, 룰 카드 검토, 도메인 판정 | 골든셋 콘크리트·거푸집(철근은 stretch) 항목 ±3%, 총량 ±1.5%, 부호 편향 없음, 자동승인 ≥60%, 근거 점프 정확, 적산 담당 엑셀 수용; **리비전 간 구조 물량 비교** 동작 | 골든셋 <3 → 잠정 게이트; 클래스별 실패 → hold 기본 |
| **P5 적산 내부마감** | 4/27~5/29, G5 6/1 | G4 통과, 마감 골든 데이터 | 마감 산출서, 공제 임계 판정, ±5%/±3% 확인 | 내부 마감 항목 ±5%, 총량 ±3%, 부호 편향 없음, 걸레받이 등 선형재 포함, 개구부 공제 일치; 리비전 간 마감 물량 비교 | 실패 클러스터별 룰·매핑 수정 반복 |
| **P6 적산 외부마감** | 6/1~6/26, G6 6/29 | G5 통과 | 외부 존 관행, 외장 산출서 | 확신 존 면적 ±5%; **저신뢰 라우팅 정확도 ≥80%**(검수 필요 항목을 제대로 골라내는가); 경계석·측구 연장 ±3%; 리비전 간 외부 물량 비교 | 라우팅 미달 → 외부는 전 항목 검수 필수로 릴리스 |

## 7. 웨이브별 작업 분해

표기: **ID 제목** — 담당 · 수용 기준 · 차단. 0.5~2 에이전트일. 에이전트별 worktree, 브랜치 `task/<ID>`.

### Wave 0 — 선행 (Day 0~1)
- **H0 사용자 선행** — 사용자 · uv 설치 승인(Claude 실행) → `uv python install 3.12`; GitHub 비공개 저장소 URL; 샘플 요청 목록 착수 · 차단: W1-02, W1-03, W2-09.
- **W0-01 저장소 부트스트랩** — Fable · `git init`, 루트 package.json(pnpm 10), workspace, `.nvmrc`, `.python-version`, `.gitignore`, `CLAUDE.md`(소유권 맵, 명령, 금지 영역, i18n, GPL 경계, no-ODA), ADR-0001 스택/0002 정본 DXF·NDJ/0003 높이 필드/0004 Three 격리/0005 단계 순서(1→3→2, 3D 먼저), `docs/briefs/TEMPLATE.md`, `docs/gates/G0.md`, `docs/samples/REQUEST.md` · 차단: 모든 W1.

### Wave 1 — 골격과 스파이크 (P0, 5 에이전트, ~7일)
- **W1-01 Electron+Vite 골격** — Sonnet · `pnpm dev`로 "Halo CAD" 창; ESLint(`no-literal-string`, libredwg 임포트 제한), Prettier, Vitest, `tools/verify.sh`; 하드코딩 한글 리터럴 린트 실패 테스트 · 차단: W2-01, W2-07, W3-*.
- **W1-02 Python 엔진 골격** — Sonnet · pyproject 핀, `uv sync` 청결, READY 라인, `/health` deps 버전, 네이티브 dep 임포트 테스트, ruff/mypy · 차단: W2-01, W2-03, W2-08.
- **W1-03 합성 DXF 픽스처 생성기** — Sonnet · F01 기본 기하, F02 블록+속성, F03 한글 텍스트, F04 해치, F05 치수, F06 구조평면, F07 부재일람표(LINE+TEXT), F08 층고표+레벨, F09 실+문, F10 XREF, F11 20만, F12 100만; R2018·R12 cp949 변형; `truth/*.json` · 시드 결정론, ezdxf 재읽기 일치 · 차단: W2-*.
- **W1-04 mlightcad 스파이크 + capability 감사** — Opus · `spikes/mlightcad/`, 워커 배선, `docs/spikes/mlightcad-api.md`, `mlightcad-capabilities.md`, 라이선스 트리 · F03 한글 스크린샷, "unknown" 없음 · 차단: W3-02, W3-05, W3-06, W4-03.
- **W1-05 스키마 v0 + 코드젠** — Opus · `packages/schema/{ndj,qto/levels,bridge,dms}` JSON Schema, TS·pydantic 코드젠, 왕복 테스트, provenance 누락 거부, CH↔SL 등호 거부 · 차단: W2-02, W2-03, W2-05, W6-01, W9-01.
- Fable 통합 0.5일.

### Wave 2 — 왕복·교차검증·실측·패키징 (P0, 6 에이전트, ~13일)
- **W2-01 사이드카 수명주기 + IPC** — Sonnet · `/health` 10초 내, kill 시 재시작+한글 상태바 · 차단: W2-08, W6-*.
- **W2-02 mlightcad DB → stats/NDJ** — Opus · F01~F09 카운트 정확, 길이 ±0.01%, 텍스트 NFC 동일, F11 <15초 · 차단: W2-04, W9-02.
- **W2-03 ezdxf 인입 + 정본 DXF** — Sonnet · 동일 임계, F03 cp949, F10 XREF 임베드 핸들 맵 · 차단: W2-04.
- **W2-04 파서 교차검증 도구** — Opus · `validate/crosscheck.py` + `tools/crosscheck.sh`, 3파서 일치, 손상 검출 · 차단: G0.
- **W2-05 acad-ts 브리지 + DWG 픽스처** — Sonnet · CLI(`dwg2dxf`,`dxf2dwg`,`dwgstats`), `F*.dwg`(AC1027) · 차단: W2-04, W2-06, W4-05.
- **W2-06 대용량/WASM OOM 실측** — Opus · `docs/spikes/large-file.md`(경로별 피크 RSS·시간, 24GB·16GB), 임계값·기본 변환기 결정, `bench-open.mjs` · 차단: G0, W3-02.
- **W2-07 Playwright Electron e2e 골격** — Sonnet · `_electron.launch`, 테스트 IPC 훅, `verify.sh --e2e` · 차단: W3-*.
- **W2-08 패키징 스파이크(mac arm64)** — Sonnet · electron-builder + PyInstaller spec, `package.sh`, `packaged.spec.ts` · 차단: W5-05.
- **W2-09 CI(mac+windows)** — Sonnet · 매트릭스, actionlint, push 후 양 OS 녹색 · 차단: 이후 Windows 검증.
- Fable 통합 1일: `docs/gates/G0.md`.

### Wave 3 — 워크스테이션 기반 (P1, 6 에이전트, ~10일)
- **W3-01 React 셸 + i18n** — Sonnet · 메뉴, MDI 탭, 도크, 명령줄+상태바, 단축키 · 차단: W3-04, W4-*, W5-*.
- **W3-02 CadHost 파사드** — Opus · 경로 자동 선택, 이벤트, 명령 러너, undo, 오버레이, zoomTo, 레이아웃, dispose · 힙 증가 <10% · 차단: W3-04, W3-06, W4-*, W7-01.
- **W3-03 프로젝트 번들 API + 원본 불변** — Sonnet · 번들 생성/열기/저장/최근, 0444 복사, 쓰기 가드, 사이드카 · 차단: W4-05, W5-02, W6-*.
- **W3-04 레이어 패널 + 뷰 토글** — Sonnet · 차단: G1.
- **W3-05 폰트와 인코딩** — Sonnet · Noto Sans KR, SHX 매핑 UI, 코드페이지 override, 누락 폰트 패널 · 차단: G1.
- **W3-06 XREF 해석** — Opus · 해석 순서, 다이얼로그, 중첩, 언로드/리로드 · 차단: W9-02.

### Wave 4 — 선택·측정·편집·저장·내보내기 (P1, 6 에이전트, ~11일)
- **W4-01 선택·속성·측정** — Sonnet · 차단: W7-02.
- **W4-02 텍스트·핸들 검색** — Sonnet · 차단: W7-02, W15-02.
- **W4-03 기하 편집 명령 보충** — Opus(2일) · scale, mirror, stretch, trim, extend, join, break, explode, 폴리라인 정점(fillet/chamfer 제외) · 차단: G1.
- **W4-04 생성 명령 + 레이어 CRUD** — Sonnet · 차단: G1.
- **W4-05 파생 저장(DXF/DWG)** — Opus · 왕복 테스트, 드롭 목록 · 차단: G1.
- **W4-06 PDF/SVG 내보내기** — Sonnet · 차단: W5-02.

### Wave 5 — 3D 패널·마크업·diff·릴리스 (P1, 6 에이전트, ~10일)
- **W5-01 3D 패널(iframe)** — Opus(2일) · ThatOpen, web-ifc, glb, 단면, 하이라이트, 브리지, 2D↔3D 동기 · 차단: W11-03, W13-01.
- **W5-02 마크업 목록·상태·PDF** — Sonnet · 차단: G1, W7-03.
- **W5-03 파일 diff + 변경 목록** — Sonnet · `packages/diff`, 뷰어 diff, 변경 패널 · F06 vs 수정본 3/2/4 · 차단: W7-01.
- **W5-04 설정·로깅·한글 문서** — Sonnet · 차단: G1.
- **W5-05 릴리스 엔지니어링** — Sonnet · 3타깃, 설치 문서 · 차단: G1.
- **W5-06 P1 통합·RC** — Fable(1.5일) · `docs/gates/G1.md`.

### Wave 6 — DMS 서버·모델 (P2, 5 에이전트, ~10일)
- **W6-01 엔진 영속성 기반** — Sonnet · SQLAlchemy 2 모델(§4 파일·DMS 테이블), Alembic up/down, 리포지토리, SQLite/PostgreSQL DSN 스위치, 동일 테스트 양 DB 통과 · 차단: W6-02~.
- **W6-02 DMS 서버 서비스** — Opus(2일) · `halo-engine --mode server`: PostgreSQL, 오브젝트 스토어(파일시스템/MinIO 어댑터, sha256 주소), 인증 어댑터(LDAP + 로컬), 역할(관리자/편집자/열람), API 버저닝, 감사 로그 미들웨어, docker-compose 개발용 · 계약 테스트, 두 어댑터 모두 로그인 e2e · 차단: W6-03, W7-*.
- **W6-03 클라이언트 동기화** — Sonnet · 체크인/아웃, 해시 기반 충돌 감지, 오프라인 큐·재시도, 진행률 WS, 서버 연결 설정 UI · 두 클라이언트 동시 체크아웃 시 두 번째 거부, 오프라인 후 재동기화 e2e · 차단: W7-*.
- **W6-04 리비전·계보·복원** — Sonnet · 리비전 체인(parent_rev), 파일 계보(fingerprint_guid, 사용자 확정), 임의 리비전 바이트 동일 복원, 리비전 라벨·노트 · 복원 sha256 일치 테스트 · 차단: W7-01.
- **W6-05 DMS 픽스처** — Sonnet · F06 기반 리비전 A/B/C(기둥 이동, 보 단면 변경, 시트 추가·삭제, 파일명 변경) + 기대 diff · 차단: W7-01.

### Wave 7 — DMS 기능 (P2, 5 에이전트, ~10일)
- **W7-01 리비전 간 시각 diff + 변경 목록** — Sonnet · `packages/diff` 재사용, 리비전 선택 UI, 추가/삭제/수정/이동 색, 변경 목록 점프, 시트 추가·삭제 표시 · DMS 픽스처 기대 diff 일치 · 차단: G2, W15-05.
- **W7-02 검색·메타데이터·태깅** — Sonnet · 도곽 블록 속성에서 도면번호·제목·층·공종 자동 추출(P3 시트그래프의 간이판), 수동 편집, 전문 검색, 필터, 태그 · 실제 세트 도면번호 추출 ≥90% · 차단: G2.
- **W7-03 승인 워크플로우** — Sonnet · 리비전 상태 DRAFT→REVIEW→APPROVED→SUPERSEDED, 담당 지정, 코멘트(마크업 연동), 이력 · 상태 전이 규칙 테스트 · 차단: G2.
- **W7-04 관리 UI(한글) + 권한** — Sonnet · `apps/dms-admin`: 사용자·역할·프로젝트·저장소 용량, 권한 매트릭스 적용 테스트 · 차단: G2.
- **W7-05 알림·구독** — Sonnet · 리비전 업로드·승인 요청·체크아웃 알림(앱 내 + 이메일 어댑터 옵션), 구독 설정 · 차단: G2.

### Wave 8 — DMS 하드닝·운영 (P2, 4 에이전트, ~7일)
- **W8-01 백업·복원·마이그레이션** — Sonnet · pg_dump+오브젝트 스토어 스냅샷, 복원 스크립트, 무결성 검사 · 복원 후 전체 sha256 검증 · 차단: G2.
- **W8-02 다중 사용자 e2e·부하** — Sonnet · 로컬 서버 대상 2클라이언트 Playwright, locust 20 클라이언트 · 차단: G2.
- **W8-03 배포 문서·운영 매뉴얼(한글)** — Sonnet · 서버 설치, 계정, 백업, 장애 대응 · 차단: G2.
- **W8-04 P2 통합·G2 스크립트** — Fable(1.5일).

### Wave 9 — 3D 재구성 데이터 기반 (P3, 6 에이전트, ~10일)
- **W9-01 모델 도메인 스키마** — Opus · §4 시트·레벨·구조·개구부·실·마감 테이블 정의, CH/SL 등호 거부 테스트 · 차단: W10~W13.
- **W9-02 시트 분류(계층 1)** — Opus(2일) · 도곽 검출, 유형 사전, 층 정규식, 축척, 모델공간 다중 도곽, 3중 투표, 세트 그래프 · F06~F09 정확, 실제 ≥90%(라벨 CSV 사용자 교정) · 차단: W10-*.
- **W9-03 레이어/명칭 사전** — Sonnet · YAML 사전, 부호 문법, 단위 패턴 · ≥200 문자열 테스트 · 차단: W10-02, W10-03.
- **W9-04 일람표 픽스처** — Sonnet · 8 변형+truth · 차단: W10-01.
- **W9-05 apartment 픽스처 확장** — Sonnet · 건축평면 이중선 벽·문/창 블록·실명, 실내재료마감표+범례, 입면 4장(해치 존·레벨 라벨), 창호일람표, 노이즈 모드(분해 블록·오도 레이어·벽 갭·중복선·태그 오프셋), `truth.py` 기하 truth(부재 배치·치수·실 폴리곤·면) · 차단: W11-*, W12-*.
- **W9-06 시트·층 보정 UI** — Sonnet · 시트 유형/층 배지+override, 층 드래그, 영속 · 차단: G3.

### Wave 10 — 일람표·레벨·정규화 (P3, 6 에이전트, ~12일)
- **W10-01 표 격자 복원** — Opus(2일) · 합성 ≥98%, 실제 ≥15장 ≥95%, <2초/시트 · 차단: W10-02, W10-05, W12-03.
- **W10-02 일람표 의미 파서** — Opus(2일) · 합성 ≥98%, 실제 부호+치수 ≥90% · 차단: W11-01.
- **W10-03 3중 투표 엔티티 정규화** — Opus(2일) · F06 100%, 실제 ≥90% P/R, 불일치 confidence<0.6 · 차단: W11-01, W12-01.
- **W10-04 레벨·천장고 표** — Sonnet · F08 정확, 실제 ≥95%, 등호 비교 금지 가드 · 차단: W11-01.
- **W10-05 일람표 셀 보정 편집기(UI)** — Sonnet · 차단: G3 하이브리드.
- **W10-06 부재 태깅·레벨 매핑 UI** — Sonnet · 클릭→부호/유형/층, SL/FL/CH 편집기(출처 점프), 영속 · 차단: G3.

### Wave 11 — 구조 3D (P3, 6 에이전트, ~13일)
- **W11-01 구조 재구성 솔리드** — Opus(2일×2회) · shapely 평면 폴리곤·스냅·벽 중심선, manifold3d 돌출(SL 사이), 우선순위 접합 불리언 검증, 면 분류, glb · F06 부피/면적 ±0.5%, non-manifold 0, <30초/층 · 차단: W11-03, W11-06, W13-01, W14-*.
- **W11-02 모델 API·잡** — Sonnet · reconstruct 잡, members CRUD, split/merge, manifest, glb 스트림, OpenAPI, TS 클라이언트 · 차단: W11-03, W11-05.
- **W11-03 3D 패널 솔리드 로드·동기** — Sonnet · 유형/상태 색, 2D 근거 동기, 층 필터, 단면 · F06 선택 왕복 e2e · 차단: G3.
- **W11-04 개구부 검출·창호 매칭** — Opus · 문/창 블록 ↔ 창호일람표 치수, 호스트 벽/실 배정, `count_check` 이중장부 · F02/F09 정확, 실제 ≥95% · 차단: W12-05, W14-04.
- **W11-05 부재 검수 UI + carry-forward** — Sonnet · 부재 목록·오버레이(인식/투표 불일치 색), 재태깅·유형 변경·제외·사유, 재실행 시 결정 유지, 고아 결정 목록 · 재태깅 후 재실행 유지 e2e · 차단: G3.
- **W11-06 구조 기하 교차검증** — Sonnet · 일람표 vs 평면 부재 수, 기둥 vs 그리드 교점, 슬래브 vs 외곽, 층별 부피 타당성, 산식 vs 불리언 · 기둥 누락 주입 검출 · 차단: G3, W14-03.

### Wave 12 — 공간·마감·외부 3D (P3, 7 에이전트, ~14일)
- **W12-01 실 폴리곤 폐합·명명** — Opus(2일) · 픽스처 ≥95%, 주입 갭이 정확히 후보로 노출 · 차단: W12-02, W12-05.
- **W12-02 실 승인·분할·병합·원클릭 폐합 UI** — Sonnet · 차단: G3.
- **W12-03 마감표·범례 파서** — Opus · 격자 엔진 재사용, 실별 바닥/걸레받이/벽/천장 코드, 범례 2단 조인 · 픽스처 100%, 실제 ≥90% · 차단: W12-05.
- **W12-04 마감 매트릭스·코드 편집 UI** — Sonnet · 차단: G3.
- **W12-05 실 프리즘 + 마감 면 속성** — Opus · 실 폴리곤×CH 프리즘, 면 생성(FLOOR/CEILING/WALL/BASE), 개구부 면 차감 기하, 마감 코드 매핑, glb(면 색=자재) · truth 면적 ±0.5% · 차단: W13-01, W17-*.
- **W12-06 외부 존 기하** — Opus(2일) · 입면 해치 존, 레벨 보정, 외벽 변 체인 자동 제안, affine 정합, 투영 면, 창호 공제 기하, residual · 픽스처 ±0.5%, 실제 residual<100mm ≥80% · 차단: W12-07, W19-*.
- **W12-07 외벽 매핑 UI** — Sonnet · 입면↔변 체인 지정, 존 경계 이동·병합·분할, 재료 지정 · 차단: G3.
- **W12-08 선형재 추출** — Sonnet · 부지·토목 폴리라인 타입 텍스트 매칭(경계석·측구), 걸레받이 후보(실 둘레−문폭) · 차단: W17-03, W19-03.

### Wave 13 — IFC·3D 골든·하드닝 (P3, 4 에이전트, ~8일)
- **W13-01 IFC 내보내기·검증** — Opus · IfcColumn/Beam/Wall/Slab 돌출 솔리드, IfcBuildingStorey(SL), IfcSpace+Qto_SpaceBaseQuantities, IfcCovering 면 기하, IfcOpening, Halo CAD id Pset; ifcopenshell validate; 3D 패널 web-ifc 로드 · Bonsai에서 열림 · 차단: G3.
- **W13-02 3D 재구성 골든(기하) 하네스** — Opus · 부재 배치·단면·레벨·실 폴리곤·면적을 truth와 비교(위치 ±20mm, 치수 정확, 면적 ±0.5%), 실제 세트는 사용자 라벨 대비 P/R, HTML 리포트, 야간 CI · 차단: G3.
- **W13-03 하드닝·문서·G3 스크립트** — Sonnet · `docs/user/ko/10-model-workflow.md`, `docs/gates/G3.md`.
- **W13-04 mlightcad 업그레이드 평가** — Sonnet+Fable(단계 경계 전용).

### Wave 14 — 적산 구조 엔진 (P4, 6 에이전트, ~12일)
- **W14-01 룰 엔진** — Opus(2일) · YAML 룰, 안전 표현식, 근거 방출, 결정론, 높이 가드 · 동일 입력=바이트 동일 · 차단: W14-02, W17-01, W19-01.
- **W14-02 룰 콘텐츠(구조)** — Sonnet · 콘크리트(접합 우선), 거푸집(개구부/접면 공제 임계 파라미터), 철근 단위중량(stretch), 룰당 ≥1 테스트, `docs/rules-ko.md` · 차단: W16-01.
- **W14-03 신뢰도·라우팅** — Sonnet · 신뢰도 집계(파서 교차검증·투표 불일치·표 신뢰도·기하 스냅량), 임계 auto ≥0.85/review/hold · 차단: W15-01.
- **W14-04 개수형 트랙 A 항목** — Sonnet · W11-04 결과 → quantity_item(개소), 이중장부 불일치 라우팅 · 차단: W15-01.
- **W14-05 compute API·잡** — Sonnet · runs/summary/items/evidence/review-queue/compare · 차단: W15-*.
- **W14-06 엑셀 내보내기** — Sonnet · 집계표/층별/산출근거(시트·핸들 id 링크), 사용자 템플릿 · 차단: W15-04.

### Wave 15 — 검수 UI·출력·비교 (P4, 5 에이전트, ~9일)
- **W15-01 물량 검수 패널** — Sonnet · 차단: G4.
- **W15-02 근거 양방향 점프·오버레이** — Opus · 항목→시트→핸들→상태색; 객체→항목; hover rule id · 차단: G4.
- **W15-03 제외·수동 항목** — Sonnet · 차단: G4.
- **W15-04 엑셀·PDF 최종** — Sonnet · 차단: G4.
- **W15-05 리비전 간 물량 비교(구조)** — Opus · 두 리비전 각각 재구성+산출, 항목 stable_key 매칭, 델타 원인 분류(GEOMETRY/SECTION/LEVEL/RULE/MANUAL), 양측 근거 점프, 리포트 · DMS 픽스처 A/B에서 모든 델타 원인 부여 · 차단: G4.

### Wave 16 — 골든 하네스·하드닝 (P4, ~10일 + 반복)
- **W16-01 골든셋 하네스** — Opus · 항목 코드 매핑 표, 헤드리스 파이프라인, 항목/총량 오차, 부호 편향 검정, 자동승인율, HTML · 차단: G4.
- **W16-02 실패 클러스터 수정** — Fable 분해, Opus/Sonnet · 지표 전후 명시.
- **W16-03 성능·캐시** — Sonnet · 2회차 <20%.
- **W16-04 문서·G4 스크립트** — Sonnet.

### Wave 17~18 — 적산 내부마감 (P5, ~8 태스크)
W17-01 마감 룰 YAML(Sonnet: 바닥·천장=면적, 벽=둘레×CH−개구부(임계), 걸레받이=둘레−문폭, 몰딩) / W17-02 개구부 공제 룰·임계 파라미터(Sonnet) / W17-03 선형재 룰(Sonnet) / W17-04 마감 골든 확장(Sonnet) / W17-05 마감 검수 UI 확장(실×부위 표, 면 하이라이트)(Sonnet) / W17-06 리비전 간 마감 물량 비교(Sonnet) / W18-01 실패 클러스터 수정(Opus/Sonnet) / W18-02 하드닝·문서·G5 스크립트(Sonnet).

### Wave 19~20 — 적산 외부마감 (P6, ~7 태스크)
W19-01 외부 존 룰 YAML(Sonnet: 존 면적−창호, 파라펫·발코니 분리) / W19-02 저신뢰 라우팅 정확도 측정·튜닝(Opus: 검수 필요 항목 재현율 ≥80%) / W19-03 경계석·측구 연장 룰(Sonnet) / W19-04 외장 골든 확장(Sonnet) / W19-05 리비전 간 외부 물량 비교(Sonnet) / W20-01 실패 클러스터 수정 / W20-02 하드닝·문서·G6 스크립트(Sonnet).

## 8. 오케스트레이션 프로토콜(Fable)

**브리프 템플릿** `docs/briefs/<ID>.md`(서브에이전트 프롬프트에 그대로 붙임): Context(3~8줄, 읽을 ADR/스파이크 문서) / Goal / Inputs(정확한 파일·스키마 버전·픽스처) / **Files you own**(글롭) / **Forbidden**(루트 package.json, lockfile, `packages/schema/**`, 타 패키지, `fixtures/truth` 쓰기 → "Shared-file patch"로 제안) / Constraints(핀 버전, 신규 dep 목록화, GPL 경계, no-ODA, i18n 키만, provenance/evidence 필수, 시드 결정론, 런타임 네트워크는 127.0.0.1과 설정된 DMS 서버만) / Definition of done(테스트 이름, `tools/verify.sh` 녹색, 문서, 브랜치 `task/<ID>` 커밋 `"<ID>: ..."`) / Acceptance checks(Fable이 실행할 명령과 기대값) / **Defaults for ambiguity**(멈추지 말고 선택 후 "Decisions"에 기록) / Report format(Summary/Files/Verification/Decisions/Deviations/Shared-file patch/Questions for gate/Follow-ups). Opus 브리프는 "Design notes required", Sonnet 브리프는 복제할 참조 구현·패턴 파일 포함.

**충돌 방지:** 에이전트별 git worktree, 브랜치 `task/<ID>`, 웨이브 통합 커밋 기준. 같은 웨이브에서 디렉터리 공유 금지. 통합 지점(스키마, API 경로·예시 `docs/contracts/<wave>.md`, IPC 채널명, i18n 키 접두)은 웨이브 시작 전 Fable이 고정. 의존 순서 병합, 병합마다 verify, 태그 `v0.<phase>.<wave>`. 신규 의존성은 MIT/BSD/Apache/MPL/OFL만(GPL은 `dwg-io-gpl` 내부만).

**반환 태스크 검토 체크리스트(Fable 실행, 실패 시 델타 브리프):** (1) worktree에서 `tools/verify.sh` 녹색을 Fable이 직접 실행 (2) 새 테스트가 구현 되돌리면 실패하는지 1건 확인 (3) 소유 파일만 변경 (4) 라이선스 경계·ODA grep (5) i18n 린트, 신규 키 존재·미사용 없음 (6) NDJ 생산자 provenance, 물량 생산자 evidence+rule_id (7) CH↔SL/층고 비교 코드 없음, 구조체 SL·마감 CH (8) `derivatives/`·사이드카·`.halo/`·서버 스토어 외 쓰기 없음, 원본 해시 불변 (9) 시드 결정론 (10) contextIsolation on, nodeIntegration off, 127.0.0.1+토큰, DMS 서버는 TLS+인증, 텔레메트리 없음 (11) 성능 예산 (12) ADR/문서·`G<n>-questions.md` (13) 품질 드리프트: jscpd >50줄 없음, 주석 없는 `any`/`type: ignore` 없음, 함수 ≤~80줄, 파일 2개 샘플링.

**Fable이 직접 하는 것:** 계약 정의(부트스트랩, ADR, `CLAUDE.md`, 다중 패키지 스키마, API 계약 문서, 브리프), 통합(병합, lockfile, 스파이크 이식, 태그, 게이트 보고서), ~30줄 미만 델타, 골든 실패 클러스터 분류와 대체 프로토콜 결정, 사용자 소통. **하지 않는 것:** 기능 모듈·파서·UI 패널·테스트 스위트 직접 작성. 1시간 넘게 손코딩하면 멈추고 브리프 작성.

**리듬:** 월 병합+진행 노트+질문 / 월~목 4~6 에이전트 병행 / 금 검토·재브리프 / 사용자는 주말 또는 게이트 미팅에서 답변·go/no-go. Opus 동시 태스크는 P0~P2 웨이브당 최대 2, P3~P4는 3~4.

## 9. 검증 계획

**공통** `tools/verify.sh`: pnpm install frozen → eslint → tsc → vitest → ruff → mypy → pytest → license-check → i18n 미사용 키 → jscpd. `--e2e`로 Playwright. 오프라인 실행 가능.

**P0** 3파서 stats vs truth, `crosscheck.sh` 전 픽스처+실제 샘플, `bench-open.mjs` 표, Playwright(F01/F03/F06 DXF·F06 DWG), 패키징 스모크, Windows CI. 사용자 수동(15분): dmg 실행 / F06.dwg·F03.dxf / 한글 판독 / "엔진 연결됨" / 실제 DWG 1개 / `large-file.md` 결정 동의 / `G0-questions.md`.

**P1** 명령별 부정밀 입력 단위, 원본 불변, 폰트, diff; Playwright 25 시나리오(8 편집 그룹, 파생 저장·재개방, PDF/SVG, 3D IFC, 마크업, diff); 파생 DWG 재읽기 일치; 실제 10장 렌더 vs 원본 체크리스트(`G1-fidelity/`); 3타깃 스모크. 사용자 수동(40분): 설치 / 실제 세트 5개(XREF) / 레이어·레이아웃 / 벽 측정 / "C1" 검색 / 편집 4종 후 undo / 문자·해치·치수 / 파생 저장·재개방 / PDF 한글 / 샘플 IFC / 마크업 재개방 / 두 파일 diff / 크래시 로그.

**P2 DMS** 단위: 리비전 체인, 복원 sha256, 충돌 감지, 권한 매트릭스, 상태 전이. 통합: PostgreSQL 컨테이너 대상 API 계약, 두 어댑터 로그인. Playwright: 2클라이언트 체크아웃 충돌, 오프라인 재동기화, 리비전 diff, 검색, 승인 흐름. 부하: locust 20 클라이언트 업로드·다운로드. 백업·복원 후 전체 해시 검증. 사용자 수동(40분): 서버에 프로젝트 생성 / 두 PC에서 같은 세트 체크아웃(두 번째 거부 확인) / 수정 후 체크인 → 리비전 2 / 리비전 1↔2 diff 보기·변경 목록 점프 / 도면번호로 검색 / 승인 요청→승인 / 감사 로그 확인 / 리비전 1 복원 후 파일 열기.

**P3 3D** 단위: 격자 복원(합성+hypothesis 지터), 의미 파서, 레벨+높이 가드, 투표, 재구성 vs truth, 폐합 랜덤 갭 복원, 외부 정합, carry-forward, IFC validate. 기하 골든 하네스(W13-02) 야간. Playwright: 셀 보정, 층 배정, 태깅, 레벨 매핑, 실 폐합 원클릭, 외벽 매핑, 3D 동기. 교차: 뷰어 stats 경로 vs ezdxf 경로 부재 수 동일. 사용자 수동(60분/세트): 세트 열기·"3D 재구성" 실행 / 시트 분류 확인(수정 ≤3) / 일람표별 확인·보정(시간 측정) / 레벨 표 SL/FL/CH / 3D에서 층별 육안 대조(기둥·보·벽·슬래브 배치·크기) / 실 폴리곤·실명 확인, 미닫힘 실 원클릭 폐합 / 마감 면 색 확인 / 외벽 존 매핑 확인 / IFC를 Bonsai에서 열기 / "모델이 도면과 같은가" 판정.

**P4 구조 적산** 단위: 룰 결정론·표 기반 케이스, 라우팅, 엑셀 구조, 물량 diff 원인 분류. 골든 `golden.py` 야간(`G4-golden/`). Playwright: 검수 큐, 승인/반려/보류, 근거 점프 스크린샷, 리비전 물량 비교. 교차: 뷰어 경로 vs ezdxf 경로 항목 값 0.1%. 사용자/적산 담당 수동(60분/골든): "수량산출" 실행 / hold 항목 검수·5건 근거 점프 / 승인·반려 / 엑셀 10항목 비교 / 리비전 A/B 물량 비교 리포트 원인 확인 / "30분 이내 수정으로 사용 가능한가" 판정.

**P5/P6** P4와 동일 패턴에 마감·외부 골든, 저신뢰 라우팅 재현율 측정, 외부 존 육안 확인 추가.

## 10. 리스크 레지스터

| # | 리스크 | 트리거 | 대응·대체 | 담당 |
|---|---|---|---|---|
| 1 | 실제 DWG 샘플 부재 | 9/12까지 <10, P1 중반 <30, P3 진입 시 <5 프로젝트 | 합성 F01~F12 + acad-ts DWG로 P0; `REQUEST.md` 주간 추적; G1·G3 샘플 없이는 잠정 | 사용자/Fable |
| 2 | DMS 서버 인프라 지연(순서 변경으로 11월 초 필요) | G1 시점에 호스트·PostgreSQL·인증 미결 | SQLite+공유폴더 임시 저장소로 동일 API 개발, 로컬 계정 인증 기본, 서버 준비 시 마이그레이션 스크립트 | 사용자/Fable |
| 3 | 일람표 양식 다양성 | 격자 <95%, 의미 <90% | 양식 조사서 패턴별 픽스처; **하이브리드 프로토콜**(5분 확인) G3 대체; 저신뢰 표 부재는 hold | Opus/Fable |
| 4 | mlightcad API 변동(3일마다 릴리스) | peer 불일치, breaking | 정확 핀, CadHost 유일 임포트, 단계 경계 전용 업그레이드, 타르볼 캐시 | Fable |
| 5 | WASM OOM | bench 피크 >3GB, >50MB 실패 | 임계 기반 Node 변환, 3차 네이티브 LibreDWG, 시트 단위 로드 | Opus/Fable |
| 6 | Three 두 버전 | 런타임 오류, 번들 팽창 | iframe 격리, `pnpm why three`, 경계 넘어 객체 공유 금지 | Opus |
| 7 | LibreDWG 엔티티 격차 | 교차검증 누락 | 파서 무관 파이프라인(acad-ts/ezdxf 정본), 미지원 목록 UI | Opus |
| 8 | acad-ts 쓰기 충실도·신생 | 왕복 불일치 | 왕복 게이트, 드롭 리포트, 대체 파생 DXF, 사내 포크 | Opus |
| 9 | 한글 폰트 | tofu | Noto Sans KR, SHX 매핑, override, 누락 리포트, 사내 폰트, `wh*txt.shx` 라이선스 확인 | Sonnet |
| 10 | Gatekeeper/SmartScreen | 실행 불가 | ad-hoc+문서 → G1에서 Developer ID/MDM·Windows 인증서 결정, 비밀은 CI만 | 사용자/Sonnet |
| 11 | 1인 유지보수 의존성 | 90일 무활동 | 핀+타르볼, 파사드, mlightcad 유료 파서 탈출구(ODA 아님) | Fable |
| 12 | 에이전트 코드 품질 드리프트 | jscpd·any 증가, 반송 >30% | 체크리스트 13, 웨이브별 리팩터 미니태스크, dependency-cruiser | Fable |
| 13 | 이 Mac에 Python 3.12·도구 없음 | Wave 1 불가 | H0 uv(승인 후 Claude 실행), Homebrew는 필요 시 사용자 | 사용자 |
| 14 | Windows 미검증 | CI 없음 | 크로스빌드 설정 검사, 게이트에 "미검증" 표기, Plan B VM | 사용자/Sonnet |
| 15 | 골든셋 항목 매핑 모호 | >10% 정렬 불가 | 매핑 표 적산 담당 검토, 미매핑 제외·보고 | Opus/사용자 |
| 16 | 3D 모델은 맞는데 적산이 늦어 보이는 인식 | P3 종료 시 물량 0 | P3 게이트 정의를 "모델 정확도"로 사용자와 사전 합의(이 계획), 3D 검수 UI로 가치 조기 시연 | Fable |
| 17 | ezdxf XREF 핸들 재번호 | 확정 | `xref_handle_map`, EntityRef 원본·바운드 핸들 | Sonnet |
| 18 | Windows 비ASCII 경로 | 한글 사용자명 | ASCII 캐시 경로 복사, 스모크 | Sonnet |
| 19 | 드래프팅 툴로 범위 확장 | 새 편집 명령 요청 | 편집 범위 고정, ADR 필수 | Fable |
| 20 | DMS 보안(사내 네트워크) | 인증 우회·권한 오류 | TLS, 역할 매트릭스 테스트, 감사 로그, 비밀은 서버 env | Opus |

## 11. 공수·일정

| 단계 | 에이전트일(Sonnet/Opus/Fable) | 기간 | 게이트 |
|---|---|---|---|
| P0 스택 스파이크 | ~27 (14/8/5) | 2026-09-03 ~ 09-19 (2.5주) | G0 ~09-22 |
| P1 CAD 워크스테이션 | ~58 (30/16/12) | 09-22 ~ 10-31 (6주, 추석 포함) | G1 ~11-03 |
| P2 도면관리 DMS | ~55 (38/8/9) | 11-03 ~ 12-19 (7주) | G2 ~12-22 |
| P3 3D 재구성 | ~85 (34/40/11) | 12-22 ~ 2027-03-05 (10.5주, 연말·설 포함) | G3 ~03-09 |
| P4 적산 구조 | ~60 (26/24/10) | 03-09 ~ 04-24 (7주) | G4 ~04-27 |
| P5 적산 내부마감 | ~35 (22/8/5) | 04-27 ~ 05-29 (5주) | G5 ~06-01 |
| P6 적산 외부마감 | ~25 (14/7/4) | 06-01 ~ 06-26 (4주) | G6 ~06-29 |
| 합계 | ~345 에이전트일 | 약 10개월 | |

가정: 평균 4~5 에이전트 병행(최대 6), 검토 반송·통합·재브리프 35%, 주 1일 게이트 지연. 지배적 일정 리스크는 샘플·서버·골든셋 도착 시점. 중간 릴리스 가능 지점: G1(11월 초) CAD 단독, G2(12월 말) CAD+DMS, G3(3월 초) 3D 모델 검수, G4(4월 말) 구조 적산.

## 12. 사용자가 제공·수행해야 하는 것

- **즉시:** uv 설치 승인(실행은 Claude); GitHub 비공개 저장소 URL; 앱 이름(기본 Halo CAD).
- **샘플 요청(`docs/samples/REQUEST.md`):** 국내 DWG ~100개, ≥5 설계사무소·2008~2026, AC1021~1032; ≥20개는 AutoCAD 내보낸 DXF 동반; XREF 세트 ≥10; >50MB ≥5; 한글 SHX/빅폰트·cp949; 구조 일람표 ≥15장; 층고표 ≥10; 실내재료마감표·창호일람표 ≥10; 입면도 세트; 사무소 폰트 파일.
- **P1까지(10월 말):** Apple Developer ID(연 99달러) vs MDM, Windows 서명 방식, Windows PC 유무.
- **P2 진입(11월 초):** 서버 호스트(Linux VM 또는 Mac mini)+PostgreSQL, AD/LDAP 여부, 사용자·역할 정책, 도면번호 체계, 승인 절차.
- **P3(12월~):** 구조+건축 완비 세트 ≥5 프로젝트, 시트 분류·부재 라벨 CSV 교정, 주간 도메인 판정, "모델이 도면과 같은가" 육안 검수.
- **P4 진입(3월 초):** 골든셋 3~5건(도면+적산 담당 엑셀 산출서+적용 산출기준), 수량산출서 템플릿, 룰 카드 검토.
- **P5/P6:** 마감·외장 산출서, 공제 임계와 외부 존 관행 판정.
- 관리자 암호 필요 항목(필요해질 때만): Homebrew, 네이티브 LibreDWG.

## 13. 승인 직후 첫 실행 순서

1. uv 설치 승인 요청 → `uv python install 3.12` → `uv --version`, `uv python find 3.12`. corepack으로 pnpm 10.
2. W0-01 부트스트랩(Fable 직접): `git init`, 워크스페이스, `CLAUDE.md`, ADR 5건(0005 단계 순서 포함), 브리프 템플릿, `docs/gates/G0.md`, `docs/samples/REQUEST.md`. 첫 커밋.
3. Wave 1 브리프 5건 후 병행 실행: W1-01·W1-02·W1-03(Sonnet), W1-04·W1-05(Opus). 각자 worktree.
4. 저장소 URL 수신 시 원격 연결·push, W2-09 CI.
5. Wave 1 통합 → Wave 2 → `docs/gates/G0.md`와 질문 목록으로 G0.
