# W1-04 mlightcad 통합 스파이크

`@mlightcad` 1.6.3 스택의 실제 API·편집 명령·라이선스를 **사실 확인**하기 위한 일회성 실험이다.
결과 문서는 `docs/spikes/mlightcad-api.md`, `mlightcad-capabilities.md`, `licenses-mlightcad-1.6.3.md`.

> 이 디렉터리는 **pnpm 워크스페이스 밖**이다. 자체 `package.json` + `npm`으로 설치한다.
> `packages/**`, `apps/**`에서 이 코드를 임포트하지 않는다. 채택 후 삭제한다.

## 실행

```bash
cd spikes/mlightcad
npm ci                 # 또는 npm install
npm run assets         # 폰트(SHX/TTF)와 샘플 DWG 다운로드 (git 미포함)
npm run dev            # http://localhost:5178
```

브라우저에서 `http://localhost:5178/?auto=1` 를 열면 모든 프로브가 자동 실행된다.
버튼으로 개별 실행도 된다(픽스처 DXF / R2000 cp949 / canteen.dwg / JSON 덤프).

### 헤드리스 검증과 스크린샷

```bash
npm run probe:node     # Node에서 data-model만 사용 (out/probe-node.json)
npm run licenses       # 의존 트리 라이선스 표 (out/licenses.json)
npx playwright install chromium
npm run dev &          # 5178 포트가 떠 있어야 한다
npm run shots          # out/browser-facts.json + docs/spikes/img/*.png
```

### W2-06 대용량 벤치 계측 (`docs/spikes/large-file.md`)

이 스파이크는 W2-06의 (a) 브라우저 경로와 (c) Node `dxfOut()` 경로 하네스를 함께 담는다.
보통은 저장소 루트의 `node tools/bench-open.mjs`가 이 둘을 호출한다. 직접 실행하려면:

```bash
# (c) Node CJS data-model -> dxfOut()  (DWG 입력은 Worker 전역이 없어 실패하는 것이 정상)
node scripts/bench-dxfout.cjs --in ../../fixtures/generated/F06.dxf \
     --out out/bench/F06.dxfout.dxf --report out/bench/F06.report.json --handles

# (a) headless Chromium + libredwg 워커. Vite 개발 서버를 스크립트가 직접 띄운다(임의 포트).
node scripts/bench-browser.mjs --files F06.dwg,F11.dxf --dxfout --report out/bench/browser.json
node scripts/bench-browser.mjs --files F06.dwg --render     # 뷰어(WebGL)까지 포함한 미리보기 경로
```

| 파일 | 내용 |
|---|---|
| `bench.html` + `src/bench.ts` | 단계별(`fetchFile`/`parse`/`dxfOut`/`render`) 벤치 하네스. 드라이버가 각 단계를 await하며 그 구간의 프로세스 RSS를 샘플링한다. |
| `scripts/bench-browser.mjs` | Playwright 드라이버. `chromium.launchServer()`의 브라우저 pid를 뿌리로 `ps`로 프로세스 트리 RSS를 150 ms마다 샘플링한다. Vite는 `createServer()`로 이 프로세스 안에서 띄운다(포트 0). |
| `scripts/bench-dxfout.cjs` | Node CJS `data-model` 읽기 + `dxfOut()` 쓰기. `/usr/bin/time -l` 아래에서 실행하면 피크 RSS를 얻는다. |
| `vite.config.ts`의 `benchRoutes()` | `GET /gen/<name>`(저장소 `fixtures/generated/` 스트리밍) + `POST /__sink/<name>`(페이지가 만든 DXF를 `out/bench/`에 기록). 개발 서버 전용. |

`out/`은 커밋하지 않는다.

### 타입 선언 조회 도우미

```bash
npm run probe:types cad-simple-viewer/lib/view/AcTrView2d.d.ts
```

## 구성

| 경로 | 내용 |
|---|---|
| `src/main.ts` | 프로브 하네스. 결과는 `window.__spike`에 쌓이고 화면 우측에 로그로 출력된다. |
| `scripts/make-fixtures.mjs` | **손으로 작성한** DXF 픽스처 생성기(그룹 코드 단위). AC1032 UTF-8 + AC1015 CP949. |
| `scripts/copy-worker-assets.mjs` | 워커 JS와 wasm을 `public/workers/`로 복사(형제 파일이어야 로드된다). |
| `scripts/fetch-assets.mjs` | mlightcad `cad-data` 저장소에서 폰트·샘플 DWG 다운로드, `fixtures/assets.lock.json`에 URL+sha256 기록. |
| `scripts/probe-node.cjs` | Node 헤드리스 프로브(사실 11) + `dxfOut()` 왕복. |
| `scripts/license-tree.mjs` | 의존 트리 라이선스 검사(GPL 격리 확인). |
| `scripts/screenshots.mjs` | Playwright 구동, 사실 JSON 덤프 + PNG 3장. |
| `fixtures/` | 픽스처 DXF와 기대값(`F-spike-truth.json`). DWG는 내려받아 쓰며 커밋하지 않는다. |

## 픽스처

`F-spike-r2018.dxf` (AC1032, UTF-8) — 모델공간 9개 최상위 엔티티, 핸들 고정:

| 핸들 | 엔티티 | 레이어 |
|---|---|---|
| `100` | LINE | `A-WALL` |
| `101` | LWPOLYLINE (닫힘, 벌지 0.5) | `A-WALL` |
| `102` | CIRCLE r=20 | `A-WALL` |
| `103` | ARC r=25, 0°~90° | `A-WALL` |
| `104` | TEXT `대명건설 도면` (STYLE `HANGUL`, 빅폰트 `whgtxt.shx`) | `A-TEXT` |
| `105` | MTEXT `지하 1층 평면도\P축척 1:100\P{\C1;검토자 홍길동}` (STYLE `Standard`) | `A-TEXT` |
| `106` | INSERT `TITLEBLK` + ATTRIB `107` + SEQEND `108` | `0` |
| `109` | HATCH SOLID | `A-HATCH` |
| `10A` | DIMENSION (rotated, 블록 `*D1`) | `치수` |

페이퍼공간: VIEWPORT `200`(전체) / `201`(드릴다운) / LINE `202`.
`F-spike-r2000-cp949.dxf`는 같은 내용의 AC1015 + CP949 인코딩 변형이다.
