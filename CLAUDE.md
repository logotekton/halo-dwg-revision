# Halo DWG Revision — 에이전트 공통 규약 (모든 에이전트는 작업 전에 이 문서를 읽는다)

대명건설 사내 전용 **리비전 도면 관리 앱**. 변경 전·후 DWG 세트를 넣으면 배경 ZWCAD로 DXF 변환 → 도곽(표제란) 단위 짝짓기 → 엔티티 비교 → 사용자 승인·무시 → 마크업 DWG(클라우드 마크 + 리비전 표)·변경 리스트 출력. Windows 10·11 x64 로컬 앱이며 서버가 없다.

정본 문서: 인터뷰 결정 장부 `docs/plans/dms-local/interview-mvp-2026-09-04.md`(최우선) → Seed `docs/seeds/R1-mvp-2026-09-04.yaml` → 개발용 계획서 `docs/plans/dms-local/02-개발용-계획서.html` → 보고용 계획서 `01-보고용-계획서.html`. 결정 근거는 `docs/adr/`, 태스크 브리프는 `docs/briefs/R1-xx.md`.

이 저장소는 `halo-cad`에서 분기했다. 셸·UI·엔진·스키마·브리지는 그대로 이어받았고, 3D 뷰어(`apps/viewer3d`)와 적산 관련 자산은 뺐다. 미병합 브랜치 `task/W3-02`(뷰어 CadHost WIP)·`task/W3-06`(XREF 해석, 검증 완료)은 R1-00a가 병합한다.

## 절대 규칙

1. **원본 도면은 불변.** 사용자가 가져온 DWG/DXF에 쓰지 않는다. 쓰기는 `<프로젝트>/.halo/`와 `<프로젝트>/출력/<날짜>/`에만 하고, `bundle/guard`가 원본 경로 쓰기를 거부해야 한다.
2. **ODA File Converter 금지.** `odafc`, `ODAFileConverter`, `opendesign.com` 참조 금지(CI grep). 변환은 배경 ZWCAD(COM) 우선, 없으면 ADR-0002의 자체 변환기.
3. **GPL 경계.** `@mlightcad/libredwg-*`는 `packages/dwg-io-gpl/**`와 `apps/desktop/src/main/ipc/convert.ts` 배선에서만 임포트한다. 신규 의존성은 MIT/BSD/Apache/MPL/OFL만. COM은 comtypes(MIT), pywin32 금지(ADR-0007).
4. **엔진이 단일 진실 소스.** 도곽·매칭·비교·클러스터·마크업은 파이썬 엔진(`engine/`)만 계산한다. 뷰어는 엔진이 낸 비교 DXF와 JSON을 그리기만 한다.
5. **근거 필수.** 모든 레코드는 `provenance {file, handle, path, space}`를 가진다. 스키마 검증 테스트를 함께 넣는다.
6. **결정론.** 난수·현재 시각 직접 호출 금지. 실행 날짜는 Run의 명시 입력이다. 같은 입력·같은 날짜면 비교 DXF·clusters.json·마크업 DWG가 바이트 동일해야 한다. 룰은 순수 함수 + YAML 설정(`compare.yaml`, `frames.yaml`).
7. **비교 규칙은 장부 값.** 사소한 변경 접기는 이동 0.01mm 이하만, 접기 목록은 구조 규칙. 지문 매칭 1mm. 클라우드 마크 레이어 `REV-<YYYYMMDD>`, 색 1, 호 100mm, 삼각 안 번호. 리비전 표 번호·내용·일자, 표제란 왼쪽. 비교 DXF 계약은 `docs/contracts/compare-dxf.md`.
8. **한국어 UI, 영어 코드.** UI 문자열은 `apps/web/src/i18n/ko.json` 키로만(ESLint `no-literal-string`). 코드 식별자·주석·커밋 메시지는 영어, 사용자 문서·ADR·브리프는 한국어. 사용자 용어(클라우드 마크, 도곽, 승인·무시)를 그대로 쓴다.
9. **보안.** Electron `contextIsolation: true`, `nodeIntegration: false`. 사이드카는 `127.0.0.1` + 실행별 토큰(env). 런타임 외부 네트워크 없음. 텔레메트리 없음.
10. **범위 고정.** Seed 밖의 기능(사전 기반 설명, 래스터 보조, 수동 마크, 이력 엑셀, 선택 도곽, COM 삽입, 애드인, 그룹 보기)은 2주차 Seed로만 들어온다. 새 의존성은 ADR 없이 추가하지 않는다.

## 스택과 버전 핀 (변경은 ADR로만)

Node 24, pnpm 10 (corepack), Electron 44.1.x, Vite 7, React 19, TypeScript strict.
`@mlightcad/cad-simple-viewer@1.6.3`, `data-model@1.14.3`, `three-renderer@1.6.3`, `libredwg-converter@3.14.3`, `libredwg-web@0.7.10`, `three@0.172.0`(2D 전용).
`@node-projects/acad-ts@3.1.0`.
Python 3.12 (uv), ezdxf 1.4.4, shapely 2.1.x, FastAPI 0.14x, uvicorn(uvloop 제외), SQLAlchemy 2, Alembic, openpyxl 3.1.x, comtypes(Windows 전용), PyInstaller 6.22.
Windows 설치본: electron-builder NSIS x64 + PyInstaller 사이드카. GitHub Actions `windows-latest`가 task 브랜치 푸시마다 아티팩트로 만든다.

## 디렉터리 소유권

| 경로 | 역할 | 비고 |
|---|---|---|
| `apps/desktop/` | Electron main/preload, 사이드카 spawn, IPC(대화상자·클립보드·ZWCAD 상태) | main에 로직을 두지 않는다 |
| `apps/web/` | React UI, i18n, `features/compare/*`(화면 A~D), 다크 테마 | |
| `packages/cad-core/` | mlightcad 유일 임포트(CadHost), 레이어 가시성·히트 테스트 | |
| `packages/dwg-io-gpl/` | libredwg-web 유일 임포트 | GPL |
| `packages/acad-bridge/` | acad-ts 변환·쓰기 CLI(대체 경로) | |
| `packages/schema/` | JSON Schema + 코드젠(`src/compare/*` 포함) | **Fable 소유** |
| `packages/shared-types/`, `packages/diff/`, `packages/testing/` | 공용 타입, diff, 테스트 유틸 | |
| `engine/src/halo_engine/` | `ingest`·`bundle`·`db`·`api`·`validate`(이어받음), `compare/*`(신규: zwcad, ingest_set, frames, match, diff, cluster, compare_dxf, markup, export) | 하위 패키지 단위로 소유 |
| `fixtures/` | 합성 도면 + truth, `fixtures/compare/**` 리비전 쌍 생성기 | `truth/`는 생성기만 쓴다 |
| `samples/` | 실도면 68장(읽기 전용, gitignore), `samples/revision-pairs/`(사용자 제작) | 절대 쓰지 않는다 |
| `docs/plans/dms-local/`, `docs/seeds/` | 계획서·장부·Seed | 사용자 검토 후에만 변경 |
| `tools/`, `CLAUDE.md`, 루트 `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml`, `.github/` | 공유 | **Fable 소유** — 변경은 보고서 "Shared-file patch"로 제안 |

태스크 하나는 브리프의 "Files you own" 글롭 안에서만 파일을 만들고 고친다. 같은 날의 다른 태스크 디렉터리는 읽기만 한다.

## 작업 방식

- 브랜치 `task/<ID>`, 커밋 메시지 `<ID>: <what>` (영어, 명령형). `main`에 직접 커밋하지 않는다. 오케스트레이션은 Fable, 작업은 Sonnet·Opus 서브에이전트가 수동 worktree(`../.worktrees/<ID>`)에서.
- 완료 조건: 브리프의 테스트가 존재하고 통과, `tools/verify.sh` 녹색(종료 코드로 판단), 문서 갱신, 보고서 작성.
- Windows 확인은 사용자가 **설치본으로만** 한다. 확인이 필요한 태스크는 CI 아티팩트 설치본 링크와 확인 절차를 보고서에 적고, 결과는 `docs/gates/R1.md`에 `R1-GATE <항목>: PASS|FAIL` 줄로 남긴다.
- 모호하면 멈추지 말고 브리프의 "Defaults for ambiguity"를 따르고 보고서 "Decisions"에 기록한다. 사용자에게 물을 것은 `docs/gates/R1-questions.md`에 적는다.
- 보고서 형식: Summary / Files changed / Verification(명령+요약 출력) / Decisions / Deviations from brief / Shared-file patch / Questions for gate / Follow-ups.

## 자주 쓰는 명령

```bash
pnpm install --frozen-lockfile        # TS 의존성
pnpm dev                              # Electron + Vite 개발 실행
tools/verify.sh                       # 린트·타입·단위·금지어 검사 (모든 태스크 완료 전 필수)
tools/verify.sh --e2e                 # + Playwright
cd engine && uv sync --frozen && uv run pytest
cd engine && uv run halo-engine serve --dev --port 8765 --token dev   # 브라우저 개발 시 HALO_ENGINE_URL로 부착
```
