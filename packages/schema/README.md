# @halo-cad/schema

뷰어(TypeScript)와 엔진(Python)이 주고받는 문서 형식의 **단일 진실 소스**. `src/`의 JSON Schema(draft 2020-12)가 원본이고, TypeScript 타입과 pydantic v2 모델은 여기서 생성해 커밋한다.

```
src/            JSON Schema 원본 (사람이 고치는 유일한 곳)
examples/       예제 문서. 통과해야 하는 것과 거부돼야 하는 것 둘 다
gen/ts/         json-schema-to-typescript 산출물 (*.d.ts, 커밋됨)
gen/python/     datamodel-code-generator 산출물 + 파이썬 패키지 (커밋됨)
src/validate.ts ajv 2020-12 컴파일 검증기
test/           vitest
scripts/        코드젠·테스트 스크립트
```

## 왜 JSON Schema가 단일 소스인가

같은 형식을 TypeScript 인터페이스와 pydantic 모델로 각각 손으로 쓰면 두 정의는 반드시 갈라진다. 파서 교차검증(ADR-0002)과 높이 4필드 규칙(ADR-0003)은 **두 언어가 같은 문서를 같은 이유로 받아들이거나 거부해야** 성립하므로, 형식 정의는 언어 밖에 있어야 한다. JSON Schema는 (1) 양쪽에 성숙한 검증기(ajv, jsonschema)가 있고, (2) 타입 생성기가 있고, (3) `if`/`then`/`not`으로 값들 사이의 조건까지 표현할 수 있어서, 규칙을 문서가 아니라 **실행되는 제약**으로 남길 수 있다. ADR-0003의 `CH` 등호 비교 금지가 대표적이다. `levels/consistency-check.schema.json`은 그런 검사 정의 자체를 스키마 수준에서 거부한다.

## 스키마 목록

| 파일 | 루트 타입 | 내용 |
|---|---|---|
| `common/primitives.schema.json` | `Primitives` | 공용 `$defs`: ULID, sha256, DXF 핸들, 공간, 텍스트 해시, 점·bbox·변환, `level_kind`(SL/FL/FLOOR_HEIGHT/CH) 등 |
| `common/provenance.schema.json` | `Provenance` | `{file, handle, path[], space, role?}`. 모든 엔티티·근거에 필수 |
| `common/entity-ref.schema.json` | `EntityRef` | 근거 참조 단위. provenance와 같은 구조 |
| `ndj/document.schema.json` | `NdjDocument` | 정규화 문서: 헤더(sha256, `dwg_version`, 코드페이지, `insunits`, 레이어·블록·레이아웃) + `entities[]` |
| `ndj/entity.schema.json` | `NdjEntity` | 엔티티 20종 `oneOf`. 알 수 없는 `type`은 거부 |
| `stats/layer-stats.schema.json` | `LayerStatsDocument` | 파서 교차검증 통계. `stats.ts`와 `stats.py`가 같은 문서를 낸다 |
| `levels/level-observation.schema.json` | `LevelObservation` | 도면 한 곳에서 읽은 높이 값 하나 + 근거 |
| `levels/floor-levels.schema.json` | `FloorLevelsDocument` | 층별 확정 높이 4종 + 출처 관측 + 방법 + 충돌 |
| `levels/consistency-check.schema.json` | `ConsistencyCheckSet` | 레벨 교차검사 정의. **ADR-0003 강제 지점** |
| `sidecar/markup.schema.json` | `MarkupSidecar` | 구름·화살표·메모·자유선 마크업 |
| `sidecar/tags.schema.json` | `TagsSidecar` | 엔티티 태깅과 분류 override(`stable_key` 포함) |
| `bridge/messages.schema.json` | `BridgeMessage` | 3D iframe postMessage(ADR-0004): `ready` `load` `select` `colorize` `camera` `selected` `error` |

## 변경 절차

1. `src/`의 스키마를 고친다. **`gen/` 밑은 절대 손으로 고치지 않는다.**
2. 필요하면 `examples/`에 예제를 추가하고 `test/examples.test.ts`의 표에 등록한다. 표에 없는 예제 파일이 있으면 테스트가 실패한다.
3. 코드젠과 테스트:
   ```bash
   pnpm --filter @halo-cad/schema build   # gen-ts.mjs + tsc → gen/ts, dist
   pnpm --filter @halo-cad/schema test    # vitest
   export PATH="$HOME/.local/bin:$PATH"
   packages/schema/scripts/gen-python.sh  # gen/python/halo_schema/{models,schemas}
   packages/schema/scripts/test-python.sh # pytest
   ```
4. `src/`, `gen/ts/`, `gen/python/`을 **한 커밋에** 담는다. `build`를 두 번 돌려도 `git status`가 깨끗해야 한다(산출물은 결정론적이다).

코드젠이 실패하면 커밋하지 않는다. 이미 커밋한 뒤에 문제가 드러나면 스키마 변경 커밋 전체를 되돌린다(`git revert`). `gen/`만 손으로 고쳐 맞추는 복구는 금지 — 다음 코드젠에서 조용히 덮어써진다.

## 버전 정책

모든 최상위 문서는 `schema_version: "<major>.<minor>"`를 갖는다. 현재 값은 `SCHEMA_VERSION`(= `0.1`).

- **minor**는 하위 호환 변경에만 올린다: 선택 필드 추가, `description` 보강, enum에 값 추가(생산자 쪽이 먼저 배포될 때만), 새 스키마 파일 추가.
- **major**는 그 외 전부: 필드 삭제·이름 변경, 필수 필드 추가, enum 값 제거, 타입 변경, 제약 강화.
- 소비자는 **major가 같을 때만** 문서를 받아들인다. minor가 자기보다 높아도 읽는다(모르는 필드는 `additionalProperties: false` 때문에 거부되므로, 소비자를 먼저 배포한다).
- 3D 브리지는 별도로 `protocol_version`(`BRIDGE_PROTOCOL_VERSION`)을 갖고 `const`로 고정한다. 값이 다르면 핸드셰이크가 즉시 실패한다 — iframe이 낡은 채로 조용히 오작동하는 것보다 낫다.
- `v0` 동안(P0~P1)은 major를 올리지 않고 필요한 만큼 깨뜨린다. 소비 코드가 아직 트리 안에만 있어서 한 커밋으로 같이 고칠 수 있기 때문. G1 이후에는 위 규칙을 그대로 지킨다.

## 스키마 작성 규약

- **`$ref`는 항상 절대 URI**(`https://schema.halo-cad.internal/v0/...`). 자기 파일 안을 가리킬 때도 마찬가지다. `.internal`은 사설 용도로 예약된 TLD여서 절대 실제로 조회되지 않고, 스키마는 언제나 이 패키지에서 읽힌다. 상대 `$ref`와 맨 포인터(`#/$defs/x`)는 다른 파일에서 끌어다 쓸 때 기준 URI가 흔들려 코드젠이 엉뚱한 경로를 찾는다.
- **`allOf`는 `properties`와 형제로 두지 않는다.** 조건 규칙은 별도 `$defs`(`*_rules`)로 빼고 `allOf: [<fields>, <rules>]` + `unevaluatedProperties: false`로 합친다. 형제로 두면 `json-schema-to-typescript`가 `properties`를 통째로 버리고 `{[k: string]: unknown}`을 낸다.
- **분기(`oneOf`)는 `type`/`kind`에 `const`를 둔다.** `discriminator`는 JSON Schema 표준이 아니라 OpenAPI 키워드이므로, 문서용으로만 `x-discriminator`를 둔다.
- 분기가 `const`로 덮어쓰는 속성은 베이스에서 `$ref`로 정의하지 않는다(`entity.schema.json`의 `type`이 평범한 문자열인 이유). `datamodel-code-generator`가 이 조합에서 `$ref` 경로를 잘못 계산한다.
- `tsType`은 `json-schema-to-typescript` 확장 키다. 필드가 없는 규칙 전용 `$defs`에 `"tsType": "unknown"`을 붙여 교집합 타입이 오염되지 않게 한다.
- 객체는 `additionalProperties: false`(또는 `unevaluatedProperties: false`)로 닫는다. 오타 필드는 조용히 무시되지 않고 거부돼야 한다.

## 런타임 사용

TypeScript:

```ts
import { assertValid, validateNdjDocument, SCHEMA_VERSION } from "@halo-cad/schema";
import type { NdjDocument } from "@halo-cad/schema";

const doc: NdjDocument = assertValid(validateNdjDocument, JSON.parse(text), "F06 NDJ");
```

내부 타입은 생성된 모듈에서 직접 가져온다: `import type { LineEntity } from "@halo-cad/schema/gen/ts/ndj/entity";`

Python:

```python
from halo_schema.models.ndj.document_schema import NdjDocument
from halo_schema.validation import assert_valid

assert_valid("ndj_document", payload, "F06 NDJ")
document = NdjDocument.model_validate(payload)
```

pydantic 모델은 **형태**만 담는다. `if`/`then` 조건(ADR-0003 높이 규칙, 근거 필수, 마크업 점 개수)은 pydantic으로 표현할 수 없으므로 `halo_schema.validation`이 스키마 원본으로 검증한다. `allOf`로 합성된 모델(`Check`, `Floor`, `Markup`, `LevelObservation`, `Classification`)은 `unevaluatedProperties: false`가 코드젠에 전달되지 않아 모르는 필드를 거부하는 대신 조용히 버린다 — **엔진 경계에서는 pydantic 로드 전에 `assert_valid`를 먼저 부른다.** 스키마 원본은 `halo_schema/schemas/`에 패키지 데이터로 함께 실린다(`src/`와 바이트 동일, vitest가 검사).

## ADR-0003이 스키마에 박혀 있는 방식

`levels/consistency-check.schema.json`의 `$defs.height_rules`:

- `operator`가 `EQ`이면 `left_kind`와 `right_kind`는 `SL↔SL`, `FL↔FL`, `FLOOR_HEIGHT↔FLOOR_HEIGHT` 중 하나여야 한다.
- `CH`가 어느 한쪽에 오면 `operator`는 `EQ`가 **아니어야** 한다(`not`).

따라서 `{left_kind: "CH", right_kind: "SL", operator: "EQ"}` 같은 정의는 파일에 적는 순간 검증에서 떨어진다. 증거: `examples/levels.bad-ch-eq-sl.json`, `test/height-rule.test.ts`, `gen/python/tests/test_schema_rules.py`.

`floor-levels.schema.json`은 같은 규칙을 데이터 쪽에서 받친다. `ch_method`는 `DERIVED_SL_DIFF`가 될 수 없고(구조 레벨 차이에서 천장고를 유도하지 않는다), 대체값을 쓸 때는 `ch_is_fallback: true`로 표시해 저신뢰로 분류한다.
