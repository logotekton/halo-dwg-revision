# Wave 3 통합 계약 (Fable 고정, 2026-09-03)

P1 첫 묶음(W3-01 셸, W3-02 CadHost·뷰 통합, W3-03 프로젝트·임포트 API, W3-08 P0 후속)이 공유하는 이름. 두 번째 묶음(W3-04 레이어 패널, W3-05 폰트, W3-06 XREF UI, W3-07 교차검증·속성 패널)은 이 계약 위에서 시작한다.

## 임포트 흐름 (M1 수직 슬라이스)
1. 렌더러 "열기" → preload `window.halocad.files.pickDrawings()` → main 네이티브 다이얼로그 → 절대경로 배열.
2. 렌더러 → 엔진 `POST /api/v1/projects/{id}/drawing-sets {files: [absolute paths], search_paths: []}` → `202 {job_id}`.
3. 엔진 잡: 원본 sha256·복사(`originals/`) → **DWG면 데스크톱에 변환 요청**: 엔진이 `{"type":"convert.request","file_id","dwg_path","out_path"}`를 WS로 보내고 main이 숨김 BrowserWindow에서 `dxfOut()`+후처리 → `POST /api/v1/files/{id}/converted {dxf_path, entity_count}` → 엔진이 정본 DXF 생성(XREF 임베드·인코딩) → stats → 교차검증(변환기 보고 수 vs 엔진 수 ±0.5%, 감사기 삭제 0) 실패 시 폴백(acad-ts) → `drawing_file` 저장 → WS `job.done`.
4. 렌더러가 `GET /api/v1/files/{id}/working-dxf`(바이트)를 받아 `CadHost.open()` → `statsByLayer()` → `POST /api/v1/files/{id}/crosscheck` → 레이어 신호등(패널은 W3-07).
5. DXF 입력은 3의 변환 단계를 건너뛴다.

## 엔진 API (W3-03이 구현, W8-05 이전 최소판)
- `POST /projects` `{name, path?}` → `{id, bundle_path}`; `POST /projects/open {bundle_path}`; `GET /projects/recent`; `GET /projects/{id}`.
- `POST /projects/{id}/drawing-sets` → `202 {job_id}`; `GET /jobs/{id}`; WS `/api/v1/ws` 이벤트 `job.progress|job.done|job.failed|convert.request|model.changed`.
- `POST /files/{id}/converted {dxf_path, entity_count, converter: "mlightcad-dxfout"|"acad-ts"}`.
- `GET /drawing-sets/{id}/files` → `[{id, original_name, format, dwg_version, entity_count, codepage_effective, import_status, working_dxf_path, parser_crosscheck?}]`.
- `GET /files/{id}/working-dxf` (스트림, ETag), `GET /files/{id}/stats`, `POST /files/{id}/crosscheck`(W2-04 존재).
- 잡 러너: `ProcessPoolExecutor(spawn, 2)`, 진행률 큐 → WS.

## IPC 채널 (main ↔ preload ↔ renderer)
- `halocad:files:pick-drawings` (invoke) → `string[]`.
- `halocad:convert:dwg-to-dxf` (invoke, main 내부용; 엔진 WS 요청을 main이 받아 처리) → `{dxf_path, entity_count, converter, warnings[]}`.
- `halocad:viewer:assets-base` (invoke) → `halocad://app/viewer/` (워커·wasm·폰트 루트).
- preload 전역 확장: `window.halocad.files.pickDrawings()`, `window.halocad.viewer.assetsBase()`.

## 뷰어 자산 배치 (`halocad://app/viewer/`)
- `workers/libredwg-parser-worker.js`, `workers/libredwg-web.wasm`(형제 파일 필수), `workers/mtext-renderer-worker.js` — `packages/dwg-io-gpl/scripts/copy-worker-assets.mjs`가 `apps/web/public/viewer/workers/`로 복사.
- `fonts/fonts.json` + SHX/WOFF — W3-05. 그 전까지 `apps/web/public/viewer/fonts/fonts.json`은 Noto Sans KR 1종.
- 커스텀 스킴 핸들러: `.wasm` → `application/wasm`, HEAD 요청 처리(`checkWorkersOnInit`), CSP `worker-src 'self' blob:`.

## 렌더러 상태·i18n
- Zustand 스토어 `workspace`(project, drawingSet), `documents`(탭, activeFileId), `selection`(handles), `viewer`(status, overlays). W3-01 소유.
- i18n 접두: `app.*`, `menu.*`, `files.*`, `tabs.*`, `viewer.*`, `crosscheck.*`, `layers.*`(W3-04), `fonts.*`(W3-05), `xref.*`(W3-06).
- 캔버스 컨테이너 id `#viewer-root`; CadHost는 W3-02가 `packages/cad-core/src/host/`에 만들고 렌더러는 `apps/web/src/features/viewer/`에서만 사용.

## 테스트 훅
- `window.__haloTest.openFiles(paths: string[])`(HALO_E2E=1) → 임포트 흐름 실행. `getStatus()`, `getDocuments(): {fileId, name, layers: number}[]`, `getCrosscheck(fileId)`.

## 사용자 판정 반영 (2026-09-03)
- **W3-05 폰트:** SHX 동봉 없음. 기본 Noto Sans KR(OFL). **사용자가 폰트 파일(SHX/TTF/WOFF)을 추가하는 UI**를 넣는다: 설정 → 폰트 → 파일 추가 → `<userData>/fonts/`에 복사 + `fonts.json` 갱신 + 워커 폰트 풀 동기화 + SHX 이름 매핑 표 편집. 누락 폰트 패널에서 "이 폰트 추가"로 바로 진입.
- **실제 DWG 세트**가 `samples/2026-09-02-실시도서/`에 있다(gitignore). 모든 P1 태스크는 픽스처 외에 이 세트로도 검증하고 결과를 보고서에 적는다.
- **W3-08 스키마 항목 추가:** `level_source`에 `CEILING_PLAN`, CH↔CH EQ 조건부 허용(ADR-0003 보충).

## 계약 갱신 (2026-09-03, W3-09 실측 반영)
- `POST /files/{id}/converted` 본문에 두 필드 추가: `xrefs: [{block_name, path}]`(원본 DWG의 XREF 참조, 윈도 경로 원문 그대로), `styles: [{name, font, bigfont, typeface?}]`(STYLE 테이블 + XDATA typeface). dxfOut 산출 DXF는 이 둘을 잃으므로 데스크톱 변환기(W3-02)가 acad-ts `info`에서 뽑아 보내고, 엔진(W3-06)이 정본 생성 시 XREF 해석과 폰트 매핑에 쓴다.
- `halocad:convert:dwg-to-dxf` 결과에 같은 두 필드 포함.
- dxfOut 후처리 목록 확장: INSERT `66`, HATCH `92` External 비트, LEADER dimstyle 복원, STYLE bigfont `0`→빈 문자열, 핸들 유일성.
- 시트 단위 = 도곽 INSERT(실세트 68장 전부 모델공간 단독, 표제란 수 = PDF 페이지 수). 시트 그래프(P3)와 DMS 검색(P2)은 도곽 단위로 설계한다.
- XREF 경로는 윈도 상대경로가 표준이며 엔진이 슬래시·NFC 정규화한다.
- 티어 변수는 "렌더 부하(최상위 + 블록 정의 내 엔티티)"로 변경 예정. 헤드리스 실측 A ≤ 5만; 실제 GPU 값은 W3-02가 확정.

## 사용자 판정 반영 2 (2026-09-03, G1 질문 답변)
- **폰트 대체 순서:** 도면 요청 폰트 → 사용자 추가 폰트(`<userData>/fonts`) → **맑은 고딕**(시스템에 설치돼 있을 때: macOS `/Library/Fonts/Malgun Gothic*`, Windows `C:\Windows\Fonts\malgun*.ttf`; 동봉 금지) → Noto Sans KR(동봉). 매핑 표 기본값에 이 순서를 반영(W3-05).
- **설비 도서(기계·전기·통신·소방) 6장은 반드시 열려야 한다**(적산 대상은 아님). W3-02의 렌더 부하 대책(블록 인스턴싱, 도곽 단위 로딩, 단순화 표시)은 이 6장을 기준으로 검증한다.
- **`*_recover.dwg`는 임포트 기본 제외**(설정 `import.ignore_patterns`, 기본 `["*_recover.dwg", "*.bak"]`). 파일 목록에는 "제외됨"으로 표시만(W3-06/W3-03 후속).
- 시트 라벨은 표제란 ATTRIB에서 자동 추출한 초안을 기본값으로 쓴다(P3 시트그래프 입력).
