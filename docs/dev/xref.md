# XREF 해석 (W3-06)

정본 DXF 생성 단계에서 호스트 도면의 XREF 블록을 어떻게 찾고, 경로를 어떻게 정규화·해석하고,
대상이 DWG일 때 어떻게 재귀적으로 변환·임베드하는지 설명한다. 계약은 `docs/contracts/wave-3.md`
"계약 갱신"/"사용자 판정 반영 2", 결정 근거는 `docs/adr/0002-working-dxf.md`, 실측 배경은
`docs/spikes/real-dwg-measurement.md` §5·§11. 구현은 `engine/src/halo_engine/ingest/xref.py`
(해석·임베드)와 `ingest/pipeline.py`(재귀 변환 훅, 제외 패턴), 배선은 `api/jobs.py`, API는
`api/routers/xrefs.py`. 프런트엔드는 `apps/web/src/features/xref/**`.

## 해석 순서 (`resolve_xref_path`)

1. 저장된 경로가 절대경로이고 존재하면 그 파일.
2. 호스트와 같은 폴더에서, 선언된 경로의 basename으로 찾는다.
3. 선언된(상대) 경로를 호스트 폴더 기준으로 해석한다.
4. `search_paths`에 준 폴더들을(순서대로) 위 3번과 같은 방식으로 시도한다.
5. 호스트 폴더와 모든 `search_paths`에서, 확장자·대소문자 무시 basename 일치를 찾는다.

**정규화(W3-06 추가 요구 2, W3-09 실측):** 실제 세트의 XREF 경로 133건은 전부
`..\XR\파일.dwg` 형태의 윈도 상대경로다. 비교 전에 `\` → `/`로 바꾸고, 선언된 문자열과
디렉터리 목록 양쪽을 유니코드 **NFC**로 정규화한다(macOS 파일명은 NFD라서 정규화 없이는
한글 XREF 대상이 "없는 파일"로 보인다). 빈 문자열은 즉시 미해결로 처리하고, 5단계의 디렉터리
스캔은 `import.ignore_patterns`에 매칭되는 항목(기본 `*_recover.dwg`, `*.bak`)을 건너뛴다 —
그렇지 않으면 진짜 대상이 없을 때 같은 stem의 백업 파일이 잘못 선택될 수 있다. 해석 결과가
파일이 아니라 디렉터리면(예: 예전의 `host_dir / ""` 버그) 미해결로 처리한다.

## 재귀 변환 (W3-06 추가 요구 1)

실제 세트의 `XR/` 폴더는 DXF 형제 파일이 아니라 **DWG**다. 해석된 대상의 확장자가 `.dwg`면
`embed_xref`가 주입된 `dwg_converter` 콜백으로 먼저 DXF로 바꾼 다음 그 DXF를 로드해서 임베드한다.

- **콜백은 `ingest/pipeline.py`가 만든다** (`make_dwg_xref_converter`). 오늘은 acad-ts CLI
  서브프로세스만 배선했다 — `build_working_dxf_step`이 이미 `ProcessPoolExecutor` 워커 안에서
  실행되므로(엔진이 데스크톱과 주고받는 `convert.request`/WS 왕복은 워커 프로세스를 건널 수
  없다, `api/jobs.py` 모듈 docstring 참고) 워커 밖으로 나가는 변환 경로는 이 태스크에서 배선하지
  않았다 — 데스크톱이 붙었을 때 XREF 대상도 우선 시도하게 하려면 `api/jobs.py`에 비동기 사전
  패스가 필요하다(Follow-ups).
- 변환 결과는 **대상 DWG의 sha256**로 `cache/dxf/<sha256>.working.dxf`에 캐시한다. 실제
  세트는 XREF 133건이 대상 파일 8종에 몰려 있으므로(예: `TITLE BLOCK-V.dwg`가 호스트 수십
  개에서 참조된다), 콘텐츠 해시 캐시 덕분에 대상마다 딱 한 번만 변환한다.
- 대상 파일 자신이 또 XREF를 갖고 있으면(중첩) `embed_xref`가 그 문서에 대해 다시
  `embed_all_xrefs`를 호출해 **깊이 우선**으로 먼저 처리한다. 처리 중인 파일 집합을
  `_visited`로 들고 다니다가 이미 처리 중인 파일을 다시 만나면(순환 참조) 재귀를 멈추고
  "이미 해석됨"으로 기록한다.
- 변환된 XREF 대상은 `drawing_file(is_xref=1)`로 등록된다(`api/jobs.py`의
  `_register_xref_results`). 같은 드로잉셋 안에서 sha256이 같으면 중복 등록하지 않는다.

## 실패는 "미해결"이지 "임포트 실패"가 아니다

`embed_all_xrefs`는 정의 하나가 해석·변환·임베드에 실패해도 예외를 던지지 않는다 —
`XrefUnresolvedError`로 잡아 `EmbedOutcome.unresolved`에 쌓고 나머지를 계속 처리한다. 이유는
두 가지다.

1. 브리프 Goal: "임포트 결과에 미해결 XREF가 있으면 다이얼로그가... 목록을 보여주고" — 호스트
   임포트 자체는 끝나야 다이얼로그를 띄울 대상(파일 id)이 생긴다.
2. 실측(`docs/spikes/real-dwg-measurement.md`)에서 acad-ts DXF 라이터의 기존 결함
   (ATTRIB 서브클래스 마커 누락)이 XREF **임베드** 단계에서도 나타난다 — `ezdxf.xref.Loader`가
   ATTRIB 서브엔티티를 복제할 때 `'Attrib' object has no attribute 'doc'`로 실패한다. 이 결함은
   `packages/acad-bridge`의 DXF 라이터에 있고 이 태스크의 소유 파일이 아니라서 고치지 않았다 —
   대신 그 실패 하나가 호스트 전체를 무너뜨리지 않도록만 했다(`engine/tests/api/test_real_set_xref_import.py`
   가 이 동작을 그대로 검증한다: `PLAN.dwg`는 미해결로 남고 호스트는 `DONE`).

## 임포트 제외 패턴 (`import.ignore_patterns`)

프로젝트 설정 `ProjectRow.ignore_patterns`(기본 `["*_recover.dwg", "*.bak"]`,
`bundle/create.py`가 프로젝트 생성 시 채운다)에 매칭되는 파일은 `api/jobs.py`가 복사·변환 전에
`import_status=EXCLUDED`로 표시하고 끝낸다(`error_message="제외됨(복구 파일)"`). 원본 바이트는
`originals/`에 전혀 쓰이지 않는다. 같은 패턴을 XREF 해석 5단계 디렉터리 스캔도 쓴다(위 참고).

## API

`engine/src/halo_engine/api/routers/xrefs.py`:

| 메서드/경로 | 용도 |
|---|---|
| `GET /files/{id}/xrefs` | 그 호스트의 최근 임포트 결과(`xref_link` 행) — 블록명·선언 경로·해석 경로·상태 |
| `POST /files/{id}/xrefs/{block_name}/resolve` | "파일을 개별 매칭" — 매칭한 파일의 부모 폴더를 프로젝트 검색 경로에 추가하고 그 호스트만 재임포트 |
| `PUT /projects/{id}/search-paths` | "폴더를 지정" — 프로젝트 검색 경로 전체를 교체하고, `reimport_file_ids`에 준 파일들을 재임포트 |
| `GET`/`PUT /projects/{id}/import-settings` | 검색 경로 + `ignore_patterns`를 한 번에(설정 패널용, "단순 텍스트 목록") |

검색 경로는 **프로젝트에 영구 저장**된다(`ProjectRow.search_paths`) — `api/jobs.py`의
`run_drawing_set_import`가 매 임포트 시작 시 이 값을 읽어 요청의 `search_paths`와 합친다. 즉
한 번 폴더를 추가하면 이후 모든 임포트(다른 호스트 포함)가 그 폴더를 계속 검색한다.

재임포트는 **그 파일 하나만** 다시 돌린다(`api/jobs.py`의 `run_drawing_set_import`를 새 잡으로
한 파일에 대해서만 실행) — 검색 경로 하나를 고치자고 같은 드로잉셋의 다른 파일까지 다시 변환하지
않는다.

## 프런트엔드

`apps/web/src/features/xref/**` (i18n 접두 `xref.*`):

- `api.ts` — 위 다섯 엔드포인트의 클라이언트 + 잡 폴링(`waitForJob`) + "파일 매칭"에 재사용하는
  `window.halocad.files.pickDrawings()` 래퍼(`pickOneFile`).
- `useXrefLinks.ts` — 파일 하나의 XREF 목록을 가져오는 훅.
- `XrefTree.tsx` — 파일 패널의 XREF 트리(호스트 → 참조, 상태 아이콘). 언로드/리로드 토글은
  **표시 전용**이다 — 정본을 다시 만들지 않고 뷰어 레이어 `xref$0$*` 가시성만 바꾸는 용도라서
  `onToggleVisibility` prop으로 실제 뷰어 연결을 위임한다(뷰어/CadHost 배선은 W3-02 소유,
  Follow-ups).
- `UnresolvedXrefDialog.tsx` — 미해결 XREF 다이얼로그. 폴더 경로 입력 → `PUT .../search-paths`,
  "파일 매칭..." 버튼 → 네이티브 파일 선택 → `POST .../resolve`. 둘 다 재임포트 잡이 끝날 때까지
  기다렸다가(`waitForJob`) `onReimported`를 호출한다.
- `ImportSettingsPanel.tsx` — 검색 경로·제외 패턴을 더하고 빼는 단순 텍스트 목록 UI(추가 요구 3).

**아직 앱 셸에 연결되지 않았다.** `apps/web/src/app/App.tsx`/`LeftDock.tsx`/`RightDock.tsx`는
이 태스크의 "Files you own" 밖이라(동시에 도크를 건드리는 W3-04/W3-07과의 충돌을 피하려는
경계) 다이얼로그를 언제 띄울지, 트리를 어느 도크에 넣을지는 그 파일들을 소유한 태스크가
정한다 — 이 모듈은 그 배선이 임포트해서 쓰기만 하면 되는 완결된 기능으로 만들었다(보고서
Follow-ups).

## 테스트

- `engine/tests/ingest/test_xref.py` — 해석 5단계 + 정규화(백슬래시/NFC/빈 문자열/디렉터리) +
  제외 패턴 + 재귀 변환 훅 + 순환 참조.
- `engine/tests/ingest/test_real_set_xref_resolution.py` — 실세트 XREF 선언 경로 전부를
  `acad-bridge info --xrefs`로 뽑아 `XR/`를 검색 경로로 주고 해석률을 잰다(실측 시점 115/115).
  실세트·빌드된 `acad-bridge` CLI가 없으면 skip.
- `engine/tests/api/test_xrefs.py` — 다섯 엔드포인트 + `EXCLUDED` 상태 + DWG XREF 대상
  재귀 변환(합성 픽스처).
- `engine/tests/api/test_real_set_xref_import.py` — 실제 `01_건축/A-100 평면도.dwg`를 `XR/`
  검색 경로로 전체 파이프라인(acad-ts 폴백) 임포트. 알려진 잔여 결함(`PLAN.dwg`가 ATTRIB
  복제 버그로 미해결)을 그대로 검증한다.
- `apps/web/src/features/xref/*.test.{ts,tsx}` — API 클라이언트·훅·다이얼로그·트리·설정
  패널 단위 테스트.
- `tests/e2e/xref.spec.ts` — Playwright. 앱 셸에 다이얼로그가 아직 연결되지 않아 실제 UI
  플로우는 검증하지 못한다(위 참고); 실행 중인 엔진 사이드카에 직접 HTTP로 붙어 브리프의
  시나리오(호스트를 XREF 없이 열면 GET .../xrefs가 미해결을 보여주고, 검색 경로를 추가하면
  해석된다)를 확인한다.
