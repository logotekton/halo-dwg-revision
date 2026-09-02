# 레이어 통계 정의 (파서 교차검증 공통 계약)

Fable 고정, 2026-09-02. 근거: ADR-0002 §6, `packages/schema/src/stats/layer-stats.schema.json`(W1-05), W1-04 실측(`docs/spikes/mlightcad-api.md` C.1~C.2).
세 구현이 이 정의를 그대로 따른다: `packages/cad-core/src/stats.ts`(mlightcad), `engine/src/halo_engine/ingest/stats.py`(ezdxf), `packages/acad-bridge`(acad-ts). 픽스처 truth(`fixtures/truth/F*.json`)도 이 형식이다.

## 문서 형식
`LayerStatsDocument` 스키마를 그대로 쓴다: `{ schema_version, file_sha256, producer, buckets[], totals }`. `producer`는 `"mlightcad"|"ezdxf"|"acad-ts"|"fixtures-gen"` 중 하나. 스키마가 닫혀 있으므로(`additionalProperties: false`) 픽스처별 부가 truth(부재 배치, 셀 격자, 레벨, 갭)는 **별도 파일** `fixtures/truth/F##.extra.json`에 둔다.

## 버킷
버킷 키 = `(space, layer)`. `space`는 `MODEL` 또는 `PAPER:<레이아웃명>`. 블록 정의 내부 엔티티는 세지 않는다(INSERT만 센다).

## 필드 정의
| 필드 | 정의 |
|---|---|
| `count_by_type` | 해당 공간의 **최상위 엔티티**를 DXF 타입명(`dxfTypeName`: LINE, LWPOLYLINE, POLYLINE, ARC, CIRCLE, ELLIPSE, SPLINE, TEXT, MTEXT, INSERT, HATCH, DIMENSION, LEADER, MULTILEADER, SOLID, POINT, 3DFACE, VIEWPORT, ...)로 센다. **ATTRIB·SEQEND·VERTEX는 세지 않는다**(소유 엔티티에 속함). DIMENSION 하위 유형은 모두 `DIMENSION`. |
| `length_sum` | LINE, LWPOLYLINE, POLYLINE(2D), ARC, CIRCLE, ELLIPSE, SPLINE의 길이 합(mm). 벌지는 해석식, 스플라인은 `flattening(0.01)`급 근사. 허용 ±0.1%. |
| `hatch_area_sum` | HATCH 경계 면적 합(외곽 − 구멍). 허용 ±0.5%. |
| `text_count` | TEXT + MTEXT + **ATTRIB**(INSERT의 속성, ATTRIB 자신의 레이어에 귀속) 개수. ATTDEF은 블록 정의 내부라 제외. |
| `text_hash` | 위 텍스트 집합의 해시. 각 텍스트를 NFC 정규화(TEXT는 문자열, MTEXT는 **원본 contents**(제어코드 포함), ATTRIB는 값), 코드포인트 오름차순 정렬, `\n`으로 결합, `sha1` 앞 16 hex. 텍스트가 없으면 빈 문자열의 sha1 앞 16자리. |
| `insert_by_block` | 블록명별 INSERT 개수. XREF 블록도 포함. |
| `bbox` | 해당 버킷 엔티티의 `geometricExtents` 합집합 `[minx, miny, maxx, maxy]`(mm). 허용 ±1mm. |

`totals`는 모든 버킷의 합(해시는 전체 텍스트 집합으로 다시 계산).

## 비교 임계(교차검증)
카운트·`insert_by_block` 정확 일치, `length_sum` ±0.1%, `hatch_area_sum` ±0.5%, `bbox` ±1mm, `text_count` 정확, `text_hash` 정확. 알려진 격차(어느 파서가 지원하지 않는 타입)는 화이트리스트로 적→황.

## 알려진 함정
- mlightcad 모델공간 반복자는 ATTRIB를 내지 않는다 → `AcDbBlockReference.attributeIterator()`로 수집. ezdxf는 `insert.attribs`.
- mlightcad `type`은 클래스명, `dxfTypeName`이 DXF 타입 → 반드시 `dxfTypeName`.
- mlightcad 공간 구분은 `ownerId` → BlockTableRecord 이름(`*Model_Space`/`*Paper_Space*`)으로 판단.
- 곡선 길이: mlightcad는 `subGetIntersectCurves()` 합산 또는 `properties.geometry.length`(두 경로 일치 확인됨).
