# ADR-0006 mlightcad 타입 결함으로 인한 `skipLibCheck: true` 예외

상태: **초안 (W2-02 제안, Fable 검토 대기)** · 2026-09-02
제안자: W2-02 · 관련: ADR-0001(스택), `docs/spikes/mlightcad-api.md` §D.1

## 맥락

`CLAUDE.md` §스택은 "TypeScript strict"를 요구한다. 루트 `tsconfig.base.json`은 이미
`skipLibCheck: true`를 켜 두었지만, `packages/cad-core`와 `packages/dwg-io-gpl`은
`module: commonjs` + `moduleResolution: node10`이 필요해 base를 상속하지 않고 자체
`tsconfig.json`을 갖는다(사유는 아래 §결과 3). 따라서 두 패키지에서 이 옵션을
**명시적으로 다시 켜야 하는지**를 결정해야 한다.

W1-04 스파이크가 `skipLibCheck: false`로 컴파일을 시도해 상류 패키징 결함 3건을 실측했다
(`docs/spikes/mlightcad-api.md` §D.1). 세 건 모두 **우리 코드가 아니라 배포된 `.d.ts`의
문제**이고, 런타임에는 영향이 없다.

| # | 패키지 | 위치 | 증상 |
|---|---|---|---|
| 1 | `@mlightcad/cad-simple-viewer@1.6.3` | `lib/editor/global/eventBus.d.ts:2`, `lib/index.d.ts:11`, `lib/editor/input/ui/index.d.ts:5`, `lib/editor/input/ui/AcEdMTextEditor.d.ts:2` | 선언되지 않은 의존성 `mitt`, `@mlightcad/mtext-input-box`를 타입에서 임포트한다. 두 이름 모두 `dependencies`/`peerDependencies`에 없다 → `TS2307` |
| 2 | `@mlightcad/data-model@1.14.3` | `lib/entity/AcDbEntity.d.ts:388` | 임포트하지 않은 타입 `AcGePoint3dLike`, `AcDbObjectId`를 사용한다 → `TS2552` 4건 |
| 3 | `@mlightcad/three-renderer@1.6.3` | `lib/viewport/AcTrBaseView.d.ts:3` | 확장자 없는 `three/examples/jsm/controls/OrbitControls`를 임포트해 `@types/three@0.172.0`(bundler resolution)에서 해석되지 않는다 |

**런타임 영향 없음(실측).** `dist/cad-simple-viewer.js`의 bare import는
`@mlightcad/data-model`, `@mlightcad/mtext-renderer`, `@mlightcad/three-renderer`,
`lodash-es`, `three`(+`three/examples/jsm/*` 5개)뿐이고 `mtext-input-box`는 번들에
인라인돼 있다. 즉 결함은 타입 선언 표면에만 있다.

## 결정

1. `packages/cad-core/tsconfig.json`과 `packages/dwg-io-gpl/tsconfig.json`에
   **`skipLibCheck: true`를 유지**한다. 이유를 tsconfig 주석과 이 ADR에 남긴다.
2. **`strict: true`, `noUncheckedIndexedAccess`, `noUnusedLocals/Parameters`,
   `noImplicitOverride`는 그대로 켠다.** `skipLibCheck`는 **우리 소스 타입 검사를 약화시키지
   않는다** — `.d.ts` 파일 자체의 검사만 건너뛴다. 우리 코드에서 mlightcad API를 잘못 쓰면
   여전히 컴파일 에러가 난다(실제로 W2-02에서 `AcDbDatabase.clear()`가 private이라는 오류와
   `acdbDwgCodePageToEncoding`의 인자 타입 오류를 이 설정으로도 잡아냈다).
3. `mitt`는 **명시 의존성으로 추가**한다(MIT). 결함 1의 절반은 이것으로 실제로 해소되고,
   W3-02가 전역 eventBus를 쓸 때 팬텀 의존성에 기대지 않게 된다.
4. 결함 노출 면적을 줄이기 위해 `@mlightcad/*` 임포트는
   `packages/cad-core/src/mlightcad-surface.ts` **한 파일**로 격리한다(W2-02가 구현,
   로컬 ESLint `no-restricted-imports`로 강제).

## 대안과 기각 사유

- **`skipLibCheck: false` + `paths` 스텁.** 세 결함을 우리 쪽 shim `.d.ts`로 덮는 방법.
  상류 버전을 올릴 때마다 스텁이 조용히 낡고, 실제 타입과 어긋나면 `skipLibCheck: true`보다
  **위험한 거짓 안전**이 된다. 기각.
- **패치 패키지(`pnpm patch`)로 `.d.ts` 수정.** 결함 3건 모두 한 줄 수정이지만, 패치는
  버전 핀마다 재작성해야 하고 락파일에 바이너리 diff가 들어간다. 상류 PR이 머지되면 그때
  제거한다는 전제라면 유지 비용이 이익보다 크다. 기각(단, §후속의 상류 이슈는 낸다).
- **`@ts-expect-error`로 개별 억제.** `.d.ts` 내부 오류에는 적용할 수 없다. 기각.

## 결과

1. 두 패키지의 tsconfig에 `skipLibCheck: true`와 이 ADR 링크가 들어간다.
2. **우리 소스에 대한 타입 안전은 유지된다.** 검사에서 빠지는 것은 `node_modules/**/*.d.ts`뿐이다.
3. 두 패키지는 `tsconfig.base.json`을 상속하지 않는다. base는 `module: ESNext` +
   `moduleResolution: Bundler`인데, cad-core는 (a) `require('packages/cad-core/dist/index.js')`가
   동작해야 하고(W2-02 인수 조건), (b) `@mlightcad/data-model`의 ESM 엔트리가 확장자 없는
   디렉터리 임포트를 써서 Node ESM 리졸버가 거부하기 때문에(스파이크 §C.11) CommonJS 출력이
   필요하다. base 상속 재개는 W3-02가 번들 전략을 확정할 때 재검토한다.
4. 상류가 세 결함을 고치면 이 ADR을 "대체됨"으로 바꾸고 `skipLibCheck`를 끈다.

## 후속

- [ ] 상류 이슈 3건 등록: `mlightcad/realdwg-web` 저장소. 각각 §맥락 표의 파일·줄 번호와
      재현용 `tsc --noEmit` 로그를 첨부한다. **이슈 URL이 확정되면 이 문단에 링크를 채운다**
      (초안 상태에서 확정으로 넘어가는 조건).
- [ ] W3-02: `apps/web`이 cad-core를 번들할 때 CJS 출력으로 충분한지 확인하고, 필요하면
      ESM 출력을 추가한다(`tsc` 2회 또는 tsup).
