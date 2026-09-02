# @halo-cad/cad-core

뷰어 쪽 CAD 코어. **mlightcad 임포트를 한 파일에 격리**하고, 파서 교차검증(ADR-0002 §6)의
뷰어 절반인 레이어 통계와 NDJ 내보내기를 제공한다. 뷰(WebGL)는 다루지 않는다 —
`@mlightcad/data-model`만으로 Node(vitest)에서 전부 동작한다.

## 공개 API

```ts
import { openDxf, statsByLayer, exportNdj, curveLength, entityRef, dispose } from '@halo-cad/cad-core';

const bytes = /* ArrayBuffer of the working DXF */;
const doc = await openDxf(bytes, { fileSha256: sha256 });   // Promise<CadDocumentHandle>

const stats = statsByLayer(doc, { file_sha256: sha256 });   // LayerStatsDocument
const ndj   = exportNdj(doc, { file_sha256: sha256 });      // NdjDocument

for (const space of doc.spaces()) {
  for (const entity of space.entities()) {
    curveLength(entity);                 // mm, 커브가 아니면 0
    entityRef(entity, { role: 'boundary' });   // EntityRef (근거 단위)
  }
}

dispose(doc);
```

| 이름 | 설명 |
|---|---|
| `openDxf(bytes, opts?)` | DXF 바이트를 열어 `CadDocumentHandle`을 돌려준다. **입력 버퍼를 먼저 복사한다** — DWG 경로는 버퍼를 워커로 transfer해 호출자 쪽을 detach시킨다(스파이크 §C.7). `opts.encoding`은 헤더에 기록만 되고 디코딩을 바꾸지 않는다(아래 "알려진 한계"). |
| `statsByLayer(doc, { file_sha256 })` | `stats/layer-stats.schema.json`을 만족하는 `LayerStatsDocument`. 정의는 `docs/contracts/stats-definition.md` 그대로. |
| `exportNdj(doc, meta)` | `ndj/document.schema.json`을 만족하는 `NdjDocument`. `toNdjsonLines(doc)`으로 NDJSON 직렬화. |
| `curveLength(entity, path?)` | `'intersect-curves'`(기본) 또는 `'entity-properties'`. 두 경로 모두 구현되어 있고 서로 대조된다(`test/curve-length.test.ts`). |
| `entityRef(entity, opts?)` | `common/entity-ref.schema.json`의 근거 참조. 파일 식별자가 없으면 던진다(CLAUDE.md 6). |
| `dispose(doc)` | 핸들이 붙잡고 있던 데이터베이스를 놓는다. 이후 접근은 예외. |

반환 타입은 전부 `@halo-cad/schema`의 생성 타입이거나 이 패키지가 정의한 평범한 인터페이스다.
**mlightcad 타입은 공개 API에 노출되지 않는다.**

## 격리 규칙

- `src/mlightcad-surface.ts`가 `@mlightcad/*`를 임포트하는 **유일한 파일**이다.
- 나머지 소스(`stats.ts`, `ndj.ts`, `index.ts`, `sha1.ts`)는 `src/surface-types.ts`의
  평범한 인터페이스(`CadEntity`, `CadDocumentHandle`, `CadEntityDetail` …)만 쓴다.
  숫자·문자열·단순 레코드뿐이라 mlightcad의 클래스·enum·기하 타입이 밖으로 새지 않는다.
- 무거운 기하(스플라인 제어점, 해치 루프, 폴리라인 정점)는 `CadEntity.detail()` 뒤에 지연
  평가된다. 통계는 이 비용을 내지 않는다.
- 강제 수단 3중: 로컬 ESLint `no-restricted-imports`(`eslint.config.mjs`),
  `test/isolation.test.ts`, 그리고 브리프의 인수 명령
  `grep -rln "@mlightcad" packages/cad-core/src | grep -v mlightcad-surface.ts | wc -l` → `0`.
  마지막 항목 때문에 **다른 파일에서는 주석에도 이 문자열을 쓰지 않는다.**
- GPL(`@mlightcad/libredwg-*`)은 이 패키지에서 **금지**다. DWG는 `@halo-cad/dwg-io-gpl`가 맡는다.

## 통계 계약

구현은 `docs/contracts/stats-definition.md`를 문자 그대로 따른다. 요약:

- 버킷 키 `(space, layer)`. `space`는 `MODEL` 또는 `PAPER:<레이아웃명>`이며
  `ownerId` → BlockTableRecord로 판정한다(그룹 67은 비공개).
- `count_by_type` 키는 `dxfTypeName`을 NDJ의 닫힌 20종 enum으로 정규화한 값
  (`MULTILEADER`→`MLEADER`, 매핑 불가 타입은 `PROXY`). ATTRIB·SEQEND·VERTEX·ATTDEF은 세지 않는다.
- `length_sum_mm`: LINE, LWPOLYLINE, POLYLINE, ARC, CIRCLE, ELLIPSE, SPLINE.
- `hatch_area_sum_mm2`: `AcDbHatch.area`(외곽 − 구멍).
- `text_count`/`text_hash`: TEXT(문자열) + MTEXT(**원본 contents**) + ATTRIB(값). NFC 정규화 →
  코드포인트 오름차순 정렬 → `\n` 결합 → sha1 앞 16 hex. `src/sha1.ts`는 브라우저에서도
  동기 동작하도록 자체 구현이며 `node:crypto`와 대조된다.
- `bbox`: `geometricExtents` 합집합.

`buckets`는 `layer` → `space` 순으로 정렬되고 모든 맵은 키 정렬로 직렬화된다. 같은 바이트를
두 번 읽으면 문자열까지 동일하다(CLAUDE.md 7, `test/stats-fixtures.test.ts`).

## 알려진 한계 (교차검증에 직접 영향)

1. **ezdxf가 쓴 ATTRIB을 data-model 1.14.3이 버린다.** `AcDbDxfDocumentReader.linkOrDeferAttribute`가
   ATTRIB의 그룹 330을 **소유 INSERT 핸들**로 해석하는데, ezdxf는 거기에 *공간* 블록 레코드를
   적는다. 그러면 조회 결과가 `AcDbBlockReference`가 아니어서 ATTRIB이 조용히 사라진다.
   ADR-0002의 정본 DXF는 ezdxf가 만들므로 **실서비스 경로에 그대로 해당된다.**
   `test/attrib.test.ts`가 두 소유자 형태를 모두 고정한다.
2. **DIMENSION `measurement`가 항상 `undefined`**이고 `xLine1Point`/`xLine2Point`가 0으로 읽히는
   경우가 있다(그룹 13/14가 파일에 있어도). NDJ `measurement_mm`은 0으로 기록된다.
3. **텍스트·블록 파생 bbox가 ezdxf와 다르다.** 폰트 메트릭·블록 전개·곡선 근사가 달라
   TEXT/MTEXT/INSERT/DIMENSION/LEADER/MLEADER/SPLINE이 든 버킷은 수십~수백 mm 차이가 난다.
   순수 기하만 든 버킷은 ±1 mm 안에서 일치한다.
4. `openDxf`의 `encoding`은 기록 전용이다. 1.14.3의 `AcDbDatabase.read`에 인코딩 강제 옵션이 없다.

## 개발

```bash
pnpm --filter @halo-cad/cad-core test        # vitest (Node)
pnpm --filter @halo-cad/cad-core typecheck
pnpm --filter @halo-cad/cad-core lint
pnpm --filter @halo-cad/cad-core build       # dist/ (CommonJS)

# 성능 측정(옵트인, F11 41MB는 커밋하지 않는다)
cd fixtures/gen && uv run python -m fixtures_gen --out ../generated --truth /tmp/truth-scratch --only F11
HALO_PERF=1 pnpm --filter @halo-cad/cad-core test
```

빌드 출력은 CommonJS다. `@mlightcad/data-model`의 ESM 엔트리가 확장자 없는 디렉터리 임포트를
써서 Node ESM 리졸버가 거부하기 때문이고(스파이크 §C.11), 덕분에 `require('dist/index.js')`가
그대로 동작한다. 번들러(Vite/electron-vite)는 이 출력을 문제없이 처리한다.
`skipLibCheck: true`가 필요한 이유는 **ADR-0006**에 있다.

## 파일

| 파일 | 역할 |
|---|---|
| `src/mlightcad-surface.ts` | 유일한 mlightcad 임포트. DB 열기, 엔티티 투영, 길이·면적·해치 루프 |
| `src/surface-types.ts` | mlightcad가 섞이지 않은 뷰 타입 |
| `src/stats.ts` | 통계 계약 구현 |
| `src/ndj.ts` | NDJ 문서/엔티티 매핑 |
| `src/sha1.ts` | 동기 SHA-1 + `text_hash` |
| `src/constants.ts` | `SCHEMA_VERSION`, `producer` |
| `src/index.ts` | 공개 API |
