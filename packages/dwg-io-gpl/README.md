# @halo-cad/dwg-io-gpl

**GPL 경계 패키지.** LibreDWG 기반 DWG 변환기를 mlightcad에 등록하고, 그 워커 자산을
배포 디렉터리로 복사한다. 그 두 가지 말고는 아무것도 하지 않는다.

## 라이선스 고지

이 패키지는 **GPL-3.0** 소프트웨어를 임포트한다.

| 의존성 | 라이선스 |
|---|---|
| `@mlightcad/libredwg-converter@3.14.3` | GPL-3.0 |
| `@mlightcad/libredwg-web@0.7.10` | GPL-3.0 (LibreDWG wasm 빌드) |
| `@mlightcad/data-model@1.14.3` | MIT |
| `@mlightcad/mtext-renderer@0.12.4` | MIT (MTEXT 워커 자산 출처) |

Halo CAD는 **대명건설 사내 전용**이며 외부 배포하지 않는다. 그래도 GPL 코드가 어디에 있는지
분명해야 하므로, `CLAUDE.md` 규칙 3이 `@mlightcad/libredwg-*` 임포트를
**`packages/dwg-io-gpl/**`와 `apps/desktop/src/main/ipc/convert.ts` 배선으로 한정**한다.
`tools/verify.sh`가 다른 위치의 임포트를 grep으로 막고, `packages/cad-core`는 로컬 ESLint
`no-restricted-imports`로 아예 금지한다.

**격리 이유:** 경계가 한 패키지에 모여 있으면 (a) 사내 정책이 바뀌거나 외부 배포가 논의될 때
GPL 표면이 이 디렉터리 하나로 특정되고, (b) 비-GPL 변환 경로(acad-ts, mlightcad `dxfOut()`)로
교체할 때 삭제 대상이 명확하며, (c) 상류 `cad-simple-viewer`가 **의도적으로** DWG 변환기를
등록하지 않는 설계(그쪽 JSDoc: "LibreDWG is GPL")와 그대로 맞는다.

## 사용

```ts
import { registerLibreDwgConverter } from '@halo-cad/dwg-io-gpl';

// 브라우저(렌더러)에서만. 워커 자산이 배포된 디렉터리를 가리킨다.
const registration = registerLibreDwgConverter({ workerBaseUrl: 'dmcad://app/workers' });
// … 이제 AcDbDatabase.read(bytes, opts, AcDbFileType.DWG)가 동작한다
registration.unregister();   // 필요하면 해제
```

| 이름 | 설명 |
|---|---|
| `registerLibreDwgConverter({ workerBaseUrl, useWorker?, timeout?, progress? })` | `AcDbDatabaseConverterManager.instance.register(AcDbFileType.DWG, new AcDbLibreDwgConverter({...}))`. `{ parserWorkerUrl, unregister() }`를 돌려준다. |
| `isLibreDwgConverterRegistered()` | 현재 realm에 등록되어 있는지 |
| `WORKER_ASSET_FILES` | 배포에 필요한 세 파일 이름 |

## 워커 자산 복사

```bash
pnpm --filter @halo-cad/dwg-io-gpl copy-worker-assets <target-dir> [--dry-run] [--quiet]
# 예: apps/web/public/workers, 또는 electron-vite 빌드 후 out/renderer/workers
```

복사되는 파일:

| 파일 | 출처 | 라이선스 |
|---|---|---|
| `libredwg-parser-worker.js` | `@mlightcad/libredwg-converter/dist` | GPL-3.0 |
| `libredwg-web.wasm` (약 9.9 MB) | `@mlightcad/libredwg-converter/dist` | GPL-3.0 |
| `mtext-renderer-worker.js` | `@mlightcad/mtext-renderer/dist` | MIT |

**wasm은 워커의 형제 파일이어야 한다.** 번들된 워커가
`new URL('libredwg-web.wasm', import.meta.url)`로 해석하고 인라인돼 있지 않다
(`docs/spikes/mlightcad-api.md` §A). 그래서 세 파일이 한 디렉터리에 평평하게 놓인다.
Electron 커스텀 스킴에서 필요한 조건(스킴 등록 `standard: true`, `.wasm` → `application/wasm`,
CSP `worker-src 'self' blob:`, 워커를 `blob:`으로 감싸지 않기)은 같은 스파이크 §A에 정리돼 있다.

`scripts/copy-worker-assets.mjs`는 라이브러리로도 쓸 수 있다:

```js
import { copyWorkerAssets, ASSETS } from '@halo-cad/dwg-io-gpl/scripts/copy-worker-assets.mjs';
copyWorkerAssets('apps/web/public/workers');
```

## 테스트 범위

LibreDWG는 Web Worker + 9.9 MB wasm 안에서만 파싱하고 3.14.3에 Node 경로가 없다
(스파이크 §C.11). 따라서 Node 테스트는 **export 존재와 등록/해제, 복사 스크립트 동작**만
확인한다. 실제 DWG 파싱 검증은 브라우저 e2e(W2-07)와 대용량 실측(W2-06) 몫이다.

```bash
pnpm --filter @halo-cad/dwg-io-gpl test
```
