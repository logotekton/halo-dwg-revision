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
