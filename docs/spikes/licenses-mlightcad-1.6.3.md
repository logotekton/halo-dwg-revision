# mlightcad 1.6.3 스택 라이선스 트리 (W1-04)

작성: 2026-09-02 · 근거: `spikes/mlightcad/results/licenses.json` (재생성 `cd spikes/mlightcad && npm run licenses`)
검사 명령: `npm ls --all --json --omit=dev` + 각 패키지의 `package.json.license` / 동봉 라이선스 파일
관련 규칙: **CLAUDE.md 절대 규칙 3(GPL 경계)**, PLAN §1 결정 6, ADR-0001

## 1. 결론

| 질문 | 답 |
|---|---|
| MIT 뷰어 스택(`cad-simple-viewer` / `data-model` / `three-renderer` / `mtext-renderer`) 의존 트리에 GPL 패키지가 있는가? | **없다.** 해당 트리 20개 패키지 전부 MIT / ISC / 0BSD |
| 전체 프로덕션 트리에서 copyleft 패키지는? | `@mlightcad/libredwg-converter@3.14.3`, `@mlightcad/libredwg-web@0.7.10` 둘뿐 |
| 새 전이 의존성 중 예상 밖의 것은? | 없음. 프로덕션 22개 패키지 전부 확인됨 |
| 위험 신호 | **`libredwg-converter`의 동봉 LICENSE 파일이 MIT 본문이다**(§4 참조) |

→ CLAUDE.md 3의 격리 규칙(`packages/dwg-io-gpl/**` + `apps/desktop/src/main/ipc/convert.ts`)은 **유효하고 충분하다.** 상류도 같은 의도로 설계했다(§3).

## 2. 프로덕션 의존 트리 (22개)

`spikes/mlightcad/package.json`의 `dependencies`만 기준. 개발 도구(vite/typescript/playwright/@types/*/iconv-lite)는 제외.

| 패키지 | 버전 | 라이선스 | 끌어오는 곳 | 라이선스 파일 |
|---|---|---|---|---|
| `@mlightcad/cad-simple-viewer` | 1.6.3 | **MIT** | (직접) | `LICENSE` |
| `@mlightcad/data-model` | 1.14.3 | **MIT** | `cad-simple-viewer`, `three-renderer`, `libredwg-converter` | `LICENSE` |
| `@mlightcad/three-renderer` | 1.6.3 | **MIT** | `cad-simple-viewer` | `LICENSE` |
| `@mlightcad/mtext-renderer` | 0.12.4 | **MIT** | `cad-simple-viewer`, `three-renderer` | `LICENSE` |
| `@mlightcad/common` | 1.14.3 | **MIT** | `data-model`, `geometry-engine`, `graphic-interface` | `LICENSE` |
| `@mlightcad/geometry-engine` | 3.14.3 | **MIT** | `data-model`, `graphic-interface` | `LICENSE` |
| `@mlightcad/graphic-interface` | 3.14.3 | **MIT** | `data-model` | `LICENSE` |
| `@mlightcad/mtext-parser` | 1.5.0 | **MIT** | `mtext-renderer` | (없음) |
| `@mlightcad/shx-parser` | 1.4.5 | **MIT** | `mtext-renderer` | `LICENSE` |
| `@velipso/polybool` | 1.1.1 | **0BSD** | `three-renderer` | — |
| `tslib` | 2.8.1 | **0BSD** | `@velipso/polybool` | — |
| `three` | 0.172.0 | **MIT** | `cad-simple-viewer`, `three-renderer`, `mtext-renderer` | `LICENSE` |
| `lodash-es` | 4.17.21 | **MIT** | `cad-simple-viewer` | — |
| `loglevel` | 1.9.2 | **MIT** | `@mlightcad/common` | — |
| `opentype.js` | 2.0.0 | **MIT** | `mtext-renderer` | `LICENSE` |
| `iconv-lite` | 0.7.3 | **MIT** | `mtext-renderer` | `LICENSE` |
| `safer-buffer` | 2.1.2 | **MIT** | `iconv-lite` | — |
| `idb` | 8.0.3 | **ISC** | `mtext-renderer` | — |
| `uid` | 2.0.2 | **MIT** | `data-model` | — |
| `@lukeed/csprng` | 1.1.0 | **MIT** | `uid` | — |
| `@mlightcad/libredwg-converter` | 3.14.3 | **GPL-3.0** (선언) | (직접, DWG 전용) | `LICENSE`(**MIT 본문** — §4) |
| `@mlightcad/libredwg-web` | 0.7.10 | **GPL-3.0** (선언) | `libredwg-converter` | (없음) |

**MIT 뷰어 스택만 따라가면(= `libredwg-*`를 건드리지 않으면) 도달 가능한 패키지는 20개이고, 그중 copyleft는 0개다.**

## 3. GPL 격리는 상류가 의도한 설계다

근거 두 가지:

1. `@mlightcad/cad-simple-viewer/lib/app/AcApDocManager.d.ts`, `AcApWebworkerFiles.dwgParser` JSDoc:
   > "The viewer does **not** register a DWG converter by default (LibreDWG is GPL). Hosts that opt into DWG support should register their own converter (e.g. `@mlightcad/libredwg-converter`)…"
2. `@mlightcad/libredwg-converter/README.md`:
   > "**This converter is intended for Web Worker use only.** … LibreDWG and its WebAssembly wrapper are copyleft (GPL), and loading them in a separate worker bundle helps keep that parser code apart from the main MIT-licensed application so license obligations are easier to manage."

즉 GPL 코드는 **별도 워커 번들(`libredwg-parser-worker.js` + `libredwg-web.wasm`)** 로만 실행되고, MIT 애플리케이션 번들에 링크되지 않는다.

### 우리 쪽 경계 (CLAUDE.md 3 구현 지점)

| 항목 | 위치 |
|---|---|
| `@mlightcad/libredwg-converter` import | `packages/dwg-io-gpl/**` 만 |
| `AcDbDatabaseConverterManager.instance.register(AcDbFileType.DWG, …)` 호출 | `apps/desktop/src/main/ipc/convert.ts` 배선 또는 `packages/dwg-io-gpl` |
| 워커·wasm 파일 배치 | 앱 번들과 분리된 정적 자산 디렉터리(`workers/`). **번들러가 wasm을 인라인하지 못하게 한다** — wasm은 `import.meta.url` 상대 해석이 필요하다 |
| CI 검사 | `tools/verify.sh`의 "GPL boundary" 스텝(이미 존재, `apps`·`packages` 대상 grep) |

**주의:** `tools/verify.sh`의 현재 grep은 `apps`/`packages`만 본다. 스파이크(`spikes/mlightcad/src/main.ts`)는 검사 대상이 아니라 통과하지만, 이는 스파이크가 워크스페이스 밖 일회용이기 때문이다. 스파이크는 채택 후 삭제한다(CLAUDE.md 디렉터리 소유권 표).

### 사내 전용 사용과 GPL

PLAN §1과 CLAUDE.md 3이 정한 대로 **사내 배포에 한정**하므로 GPL-3.0의 배포 조항이 발동하지 않는다. 다만:
- 사외(협력업체·발주처)에 설치본을 넘기는 순간 GPL 의무(대응 소스 제공)가 생긴다. 릴리스 파이프라인(W5-05)에 **"DWG 변환기 포함 빌드는 사내 채널 전용"** 게이트가 필요하다.
- 대안 경로가 이미 계획에 있다: 1차 변환기 `@node-projects/acad-ts`(MIT). `libredwg-*` 없이 DWG를 다룰 수 있으면 GPL 의무 자체가 사라진다. 기본 변환기 확정은 W2-06(G0).

## 4. 위험 신호 — `libredwg-converter`의 라이선스 표기 불일치

| 근거 | 값 |
|---|---|
| `package.json` → `"license"` | `GPL-3.0` |
| `README.md` 배지 + 본문 | GPL v3, "copyleft (GPL)" |
| 동봉 `LICENSE` 파일 (21줄) | **`MIT License` / `Copyright (c) 2026 mlightcad`** |
| `@mlightcad/libredwg-web@0.7.10` | 라이선스 파일 **없음**, `package.json`만 `GPL-3.0` |

LibreDWG 본체가 GPL-3.0-or-later이므로 그 WASM 포팅이 MIT일 수는 없다. **동봉 LICENSE 파일 쪽이 실수로 보인다.**

**우리의 처리:** 더 엄격한 쪽(GPL-3.0)을 기준으로 취급하고 격리를 유지한다. 상류에 이슈를 올려 확정하는 것이 좋다 → 보고서 "Questions for gate" 참조.

## 5. 선언되지 않은 참조 패키지

`cad-simple-viewer@1.6.3`의 **타입 선언**이 `dependencies`/`peerDependencies`에 없는 두 패키지를 참조한다(런타임 번들에는 인라인되어 있어 실행에는 영향 없음, 상세는 `mlightcad-api.md` §D.1):

| 패키지 | 라이선스 | 참조 위치 |
|---|---|---|
| `mitt` | MIT | `lib/editor/global/eventBus.d.ts:2` |
| `@mlightcad/mtext-input-box@0.2.23` | MIT | `lib/index.d.ts:11`, `lib/editor/input/ui/index.d.ts:5`, `lib/editor/input/ui/AcEdMTextEditor.d.ts:2` |

둘 다 MIT라 라이선스 위험은 없다. `packages/cad-core`에서 `skipLibCheck: true`를 쓰거나 두 패키지를 명시 의존성으로 추가하면 된다.

## 6. 런타임에 받아오는 제3자 자산

코드 의존성은 아니지만 **런타임 네트워크 정책(CLAUDE.md 9)** 에 걸린다.

| 자산 | 기본 출처 | 우리 처리 |
|---|---|---|
| 폰트 매니페스트 + SHX/WOFF 폰트 | `https://cdn.jsdelivr.net/gh/mlightcad/cad-data/fonts/` | **자체 호스팅 필수.** `AcApDocManagerOptions.baseUrl`을 로컬(`dmcad://app`)로 지정 |
| 새 도면 템플릿 | `${baseUrl}/templates/acadiso.dxf` | 동일. 앱 리소스에 동봉 |

`cad-data` 저장소 자체는 **라이선스 파일이 없다.** 특히 SHX 폰트(`whgtxt.shx`, `txt.shx`, `romans.shx`, `simsun.woff` …)는 AutoCAD 시대의 제3자 폰트로 **재배포 권한이 불분명하다.**

| 파일 | 바이트 | sha256 |
|---|---|---|
| `fonts/whgtxt.shx` (한글 빅폰트, euc-kr) | 196 069 | `e79cb17836aae79fc58469aa81d556cd042035351548d9a04ae9c1b476c3c225` |
| `fonts/whgdtxt.shx` (한글 빅폰트, euc-kr) | 223 699 | `58e4e5d098631afb2047f46858942d59ee84d1a7a4eeb4486628ed9527048286` |
| `fonts/txt.shx` | 8 489 | `2280abc0bc7b827c21ae43a651a8dfbc14873550ff61b123a72773a5dbce0d8f` |
| `fonts/romans.shx` | 16 086 | `b22f4abadf72c9184c6c33dbf159b504cc09185a4c24102223afbe58b400f9bd` |
| `fonts/amgdt.shx` | 5 419 | `ea6a91de27922f33dc6bd0e34388b503d4f73df98ba0a84bb869d1f58e51bc87` |
| `fonts/hztxt.shx` | 1 171 617 | `95f9ec57eede9095a2dc738ef5034887dc42c3dece048724bc602ff7994144c7` |
| `fonts/simsun.woff` | 6 431 956 | `7d5b337b4f5e4c9f79bce9f34d520c3586d7e0972c11d4e4f4ae3021e9741cea` |
| `fonts/arial.woff` | 177 132 | `2de77c0bba01187df214f3f8c5ee229617706182c29f6a46a9a3d5d16c8f8226` |
| `data/canteen.dwg` (스파이크 샘플) | 2 618 816 | `818f54cd3b413ce3ab00a6aa849bc29cd8cc8581a39fc31a723691f40141fdbc` |

전부 `https://cdn.jsdelivr.net/gh/mlightcad/cad-data/<경로>` 에서 받았다(스파이크 `fixtures/assets.lock.json`에 동일 기록). **스파이크는 이 파일들을 저장소에 커밋하지 않는다**(`spikes/mlightcad/.gitignore`).

**W3-05 권고:**
1. **동봉 가능한 폰트는 OFL/Apache 계열만.** 한글 텍스트의 안전한 기본값은 **Noto Sans KR (SIL OFL 1.1)** 이며, 이는 CLAUDE.md 3의 "신규 의존성은 MIT/BSD/Apache/MPL/OFL만" 규칙과 일치한다.
2. **SHX 폰트는 동봉하지 않는다.** 사용자가 자기 AutoCAD 설치본에서 가져와 `CACHEFONT` / `FontManager.cacheFont()`(IndexedDB)로 등록하는 경로만 제공한다. 회사가 폰트 라이선스를 보유한 경우에만 사내 배포본에 포함한다.
3. 스파이크에서 mesh(TTF) 대체 경로 검증에 쓴 `AppleGothic.ttf`는 **macOS 시스템 폰트**이며 재배포 대상이 아니다(로컬 복사만, `.gitignore`).
