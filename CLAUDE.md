# DMCAD — 에이전트 공통 규약 (모든 에이전트는 작업 전에 이 문서를 읽는다)

대명건설 사내 전용 워크스테이션. **(1) Mac/Windows 무료 CAD → (2) 도면관리 DMS → (3) 3D 재구성 → (4) 적산(구조 → 내부마감 → 외부마감)** 순서로 만든다.
전체 계획은 `docs/PLAN.md`. 결정 근거는 `docs/adr/`. 태스크 브리프는 `docs/briefs/<ID>.md`.

## 절대 규칙

1. **원본 도면은 불변.** 사용자가 가져온 DWG/DXF에 쓰지 않는다. 편집·결과는 `derivatives/`, 사이드카 JSON, 프로젝트 번들(`*.dmqto/`), DMS 서버 스토어에만 쓴다. 원본 경로 쓰기는 코드 가드가 거부해야 한다.
2. **ODA File Converter 금지.** `odafc`, `ODAFileConverter`, `opendesign.com` 참조 금지(CI grep). 비회원 상업 사용이 라이선스 위반이다.
3. **GPL 경계.** `@mlightcad/libredwg-*`는 `packages/dwg-io-gpl/**`와 `apps/desktop/src/main/ipc/convert.ts` 배선에서만 임포트한다. 신규 의존성은 MIT/BSD/Apache/MPL/OFL만. GPL은 사내 전용이라 허용되지만 위치를 지킨다.
4. **높이 4필드 분리.** `SL`(구조 레벨), `FL`(마감 바닥 레벨), `FLOOR_HEIGHT`(층고 = SL–SL), `CH`(천장고, 층고표 출처). **CH를 SL/FL/FLOOR_HEIGHT와 등호 비교하는 코드를 쓰지 않는다.** 구조체·외벽 면 높이는 SL 기준, 실내 벽 마감 높이는 CH 기준. 다른 기준 사이 검사는 부등식만(CH + 슬래브 + 바닥마감 < 층고).
5. **엔진이 단일 진실 소스.** 물량·모델은 Python 엔진(`engine/`)에서만 계산한다. 뷰어 측정값은 "측정"으로만 표시하고 적산표에 넣지 않는다.
6. **근거 필수.** NDJ/엔티티 생산자는 `provenance {file, handle, path, space}`를, 물량 생산자는 `evidence[] + rule_id + rule_version + formula_trace`를 채운다. 스키마 검증 테스트를 함께 넣는다.
7. **결정론.** 난수는 시드 고정. 같은 입력은 바이트 동일 출력. 룰은 순수 함수 + YAML 메타(출처 조항).
8. **한국어 UI, 영어 코드.** UI 문자열은 `apps/web/src/i18n/ko.json` 키로만(ESLint `no-literal-string`). 코드 식별자·주석·커밋 메시지는 영어, 사용자 문서·ADR·브리프는 한국어.
9. **보안.** Electron `contextIsolation: true`, `nodeIntegration: false`. 사이드카는 `127.0.0.1` + 실행별 토큰(env). 런타임 외부 네트워크는 설정된 DMS 서버만. 텔레메트리 없음.
10. **범위 고정.** 편집 기능은 `docs/PLAN.md` §7의 목록으로 한정. 새 편집 명령·새 의존성은 ADR 없이 추가하지 않는다.

## 스택과 버전 핀 (변경은 ADR로만)

Node 24, pnpm 10 (corepack), Electron 44.1.x, Vite 7, React 19, TypeScript strict.
`@mlightcad/cad-simple-viewer@1.6.3`, `data-model@1.14.3`, `three-renderer@1.6.3`, `libredwg-converter@3.14.3`, `libredwg-web@0.7.10`, `three@0.172.0`(2D 전용).
`apps/viewer3d`만 `three>=0.182`, `@thatopen/components@3.4.8`, `web-ifc@0.0.77` — iframe으로 격리, 두 Three를 한 번들에 섞지 않는다.
`@node-projects/acad-ts@3.1.0`.
Python 3.12 (uv), ezdxf 1.4.4, shapely 2.1.x, manifold3d 3.5.x, trimesh 5.x, ifcopenshell 0.8.5, FastAPI 0.14x, uvicorn(uvloop 제외), SQLAlchemy 2, Alembic, PyInstaller 6.22.

## 디렉터리 소유권

| 경로 | 역할 | 비고 |
|---|---|---|
| `apps/desktop/` | Electron main/preload, 사이드카 spawn, IPC | |
| `apps/web/` | React UI, i18n, features | |
| `apps/viewer3d/` | 3D 패널(iframe) | Three ≥0.182 |
| `packages/cad-core/` | mlightcad 유일 임포트(CadHost), 자체 편집 명령, stats | |
| `packages/dwg-io-gpl/` | libredwg-web 유일 임포트 | GPL |
| `packages/acad-bridge/` | acad-ts 변환·쓰기 CLI | |
| `packages/schema/` | JSON Schema + 코드젠 | **Fable 소유** |
| `packages/shared-types/`, `packages/diff/`, `packages/testing/` | 공용 타입, diff, 테스트 유틸 | |
| `engine/` | Python `dmqto` | 하위 패키지 단위로 소유 |
| `fixtures/` | 합성 도면 + truth | `truth/`는 생성기만 쓴다 |
| `tools/`, `CLAUDE.md`, 루트 `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml` | 공유 | **Fable 소유** — 변경은 보고서 "Shared-file patch"로 제안 |
| `spikes/` | 일회성 실험 | 패키지에서 임포트 금지, 채택 후 삭제 |

태스크 하나는 브리프의 "Files you own" 글롭 안에서만 파일을 만들고 고친다. 같은 웨이브의 다른 태스크 디렉터리는 읽기만 한다.

## 작업 방식

- 브랜치 `task/<ID>`, 커밋 메시지 `<ID>: <what>` (영어, 명령형). `main`에 직접 커밋하지 않는다.
- 완료 조건: 브리프의 테스트가 존재하고 통과, `tools/verify.sh` 녹색, 문서 갱신, 보고서 작성.
- 모호하면 멈추지 말고 브리프의 "Defaults for ambiguity"를 따르고 보고서 "Decisions"에 기록한다. 사용자에게 물을 것은 `docs/gates/G<n>-questions.md`에 적는다.
- 보고서 형식: Summary / Files changed / Verification(명령+요약 출력) / Decisions / Deviations from brief / Shared-file patch / Questions for gate / Follow-ups.

## 자주 쓰는 명령

```bash
pnpm install --frozen-lockfile        # TS 의존성
pnpm dev                              # Electron + Vite 개발 실행
tools/verify.sh                       # 린트·타입·단위·라이선스·금지어 검사 (모든 태스크 완료 전 필수)
tools/verify.sh --e2e                 # + Playwright
cd engine && uv sync --frozen && uv run pytest
cd engine && uv run dmqto serve --dev --port 8765 --token dev   # 브라우저 개발 시 DMCAD_ENGINE_URL로 부착
```
