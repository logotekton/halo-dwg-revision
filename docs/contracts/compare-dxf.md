# 비교 DXF 계약 (compare DXF) — R1 정본

작성: Fable 2026-09-04. 출처: 인터뷰 장부 `docs/plans/dms-local/interview-mvp-2026-09-04.md`, Seed `docs/seeds/R1-mvp-2026-09-04.yaml`. 이 문서가 개발용 계획서 §2와 어긋나면 이 문서가 우선한다. 스키마 정본은 `packages/schema/src/compare/*.schema.json`(R1-01).

엔진은 **도곽 짝(sheet pair)마다** 비교 DXF 한 장과 사이드카 `clusters.json`을 만든다. 뷰어는 비교 DXF를 보통 도면처럼 그리기만 하고, 보기 모드(겹쳐 보기·전·후)는 레이어 가시성으로만 바꾼다. 마크업 DWG(R1-09)는 같은 생성기에서 `__CMP_*` 레이어를 빼고 승인된 클러스터만 남긴 결과다.

## 1. 파일과 경로

| 산출물 | 경로 | 만드는 곳 |
|---|---|---|
| 비교 DXF | `<프로젝트>/.halo/compare/<pair_id>/compare.dxf` | `compare/compare_dxf.py` (R1-06) |
| 사이드카 | `<프로젝트>/.halo/compare/<pair_id>/clusters.json` | `compare/cluster.py` + `compare_dxf.py` (R1-06) |
| 마크업 DWG | `<프로젝트>/출력/<YYYY-MM-DD>[-n]/<도면번호>_<후 라벨>_markup.dwg` | `compare/markup.py` + `export.py` (R1-09) |
| 마크업 DXF(중간) | `<프로젝트>/.halo/compare/<pair_id>/markup.dxf` | R1-09 |

- DXF 버전 `AC1032`(R2018), 인코딩 UTF-8(`$DWGCODEPAGE = ANSI_1252`는 ezdxf 기본), 단위 `$INSUNITS = 4`(mm).
- 좌표계: **후(after) 도면의 모델공간 세계 좌표**. 전(before) 도면에서 오는 엔티티는 도곽 원점 차이만큼 평행이동해 후 좌표계로 옮긴다(`frame_offset = after.bbox.min - before.bbox.min`). 회전·축척 차이는 R1에서 다루지 않는다(도곽 크기가 다르면 짝 `status = changed`이되 `offset_only` 경고).
- 한 파일에는 **그 도곽 하나**의 엔티티만 들어간다(도곽 밖 엔티티 제외, `frames.py`의 배정 결과).

## 2. 레이어

| 레이어 | 담기는 것 | 색(ACI) | 겹쳐 보기 | 전 | 후 |
|---|---|---|---|---|---|
| 원래 레이어 그대로 | 전·후 모두 있고 바뀌지 않았거나 사소한(minor) 변경만 있는 엔티티. **후 도면의 엔티티**를 그대로 복사한다 | 원래 색 | 표시 | 표시 | 표시 |
| `__CMP_ADDED` | 후에만 있는 엔티티, `modified`·`text`·`dimension`의 후 상태, `moved`의 이동 후 위치 | 1(빨강) | 표시 | 숨김 | 표시 |
| `__CMP_REMOVED` | 전에만 있는 엔티티, `modified`·`text`·`dimension`의 전 상태, `moved`의 이동 전 위치 | 4(시안) | 표시 | 표시 | 숨김 |
| `REV-<YYYYMMDD>` | 클라우드 마크 LWPOLYLINE과 번호 배지(삼각형 LWPOLYLINE + TEXT). 날짜는 compare_set의 `run_date` | 1(빨강) | 표시 | 표시 | 표시 |
| `__CMP_LABEL` | 클러스터마다 히트 영역 하나: 클러스터 bbox(여백 포함)의 닫힌 LWPOLYLINE. XDATA로 클러스터 번호를 담는다 | 8(회색), 레이어 `off`·`plot=0` | 숨김 | 숨김 | 숨김 |

- `__CMP_ADDED`·`__CMP_REMOVED`로 옮긴 엔티티는 **레이어만 바꾸고** 색·선종류·선굵기는 `BYLAYER`로 강제한다(원래 색이 살아 있으면 빨강·시안이 안 보인다). 원래 레이어 이름은 XDATA에 남긴다(아래).
- 원래 레이어 그대로 두는 엔티티는 후 도면의 레이어 테이블 정의(색·선종류)를 그대로 복사한다. 비교 DXF의 레이어 테이블 = 후 도면 레이어 ∪ 전 도면에만 있는 레이어(전에만 있는 엔티티가 참조할 수 있어서) ∪ 위 4개.
- 레이어 이름 `REV-<YYYYMMDD>`는 비교 DXF에서는 접미사가 없다. 같은 날 두 번째 실행의 `-2` 접미사는 **출력(R1-09)에서만** 붙인다(마크업 DWG 레이어와 출력 폴더).
- 마크업 DWG는 `__CMP_ADDED`·`__CMP_REMOVED`·`__CMP_LABEL`을 만들지 않으며, 원래 레이어 엔티티는 후 도면 전체(도곽 밖 포함)를 그대로 둔다. 즉 마크업 DWG = 후 작업용 DXF 사본 + `REV-<날짜>[-n]` 레이어(승인 클러스터의 클라우드·배지) + 리비전 표.

## 3. 블록

- 후 도면의 블록 정의는 이름 그대로 복사한다.
- 전 도면에서 오는 INSERT가 참조하는 블록 정의는 **이름 앞에 `__B_`를 붙여** 별도로 복사한다(`__B_DOOR_900`). 같은 이름의 정의가 전·후에서 다를 수 있어서 항상 접두를 붙인다(같더라도).
- XREF 임베드 블록(`xref$0$...`, W3-06)도 같은 규칙. 중첩 블록은 재귀적으로 접두를 붙인다.
- `blockdef` 변경(정의가 바뀐 블록)은 인스턴스마다 `__CMP_REMOVED`(전 정의 `__B_` 인스턴스) + `__CMP_ADDED`(후 정의 인스턴스) 쌍으로 그린다.

## 4. XDATA (appid `HALO_CMP`)

모든 `__CMP_*`·`REV-*` 엔티티와 원래 레이어에 남긴 엔티티 중 **변경(사소 포함)에 관여한 것**에 XDATA를 단다. 문자열 태그(그룹 1000)를 `key=value` 형식으로 나열한다.

```
1001 HALO_CMP
1000 cluster=<number>            # 클러스터 번호(1부터). 클러스터에 속하지 않으면 생략
1000 change=<change_id>           # "ch<seq>", 사이드카 changes[].id
1000 kind=<added|removed|modified|moved|text|dimension|blockdef>
1000 side=<before|after>          # 이 엔티티가 전·후 어느 쪽 상태인가
1000 orig_layer=<원래 레이어 이름>
1000 orig_handle=<원 도면 핸들>    # 전 도면 엔티티는 전 파일 핸들, 후는 후 파일 핸들
1000 minor=<0|1>
1000 role=<cloud|badge_shape|badge_text|label>   # REV-·__CMP_LABEL 엔티티만
```

- 클라우드 마크·배지·라벨 엔티티는 `cluster=`와 `role=`만 단다.
- XDATA가 없는 엔티티 = 변경에 관여하지 않은 후 도면 엔티티.

## 5. 클라우드 마크와 배지 (R1-06이 좌표를 만들고 R1-09가 같은 좌표를 쓴다)

값은 `compare.yaml`의 `cloud` 절이며 **1:100 도곽 기준 모델 mm**이다. 실제 크기 = 값 × `scale_factor`, `scale_factor = scale_denominator / 100`(도곽 축척 `1:50` → 0.5, `1:200` → 2.0, 축척을 못 읽으면 1.0). 근거: 장부 "호 100mm, 여백 50mm, 삼각 한 변 200mm, 도곽 축척 배율 적용".

| 항목 | 기본값 | 설명 |
|---|---|---|
| `cloud.margin` | 50 | 클러스터 bbox 사방 여백 |
| `cloud.arc` | 100 | 호 하나의 현 길이. 변 길이를 이 값으로 나눠 올림한 개수로 균등 분할(변마다 최소 1개) |
| `cloud.arc_bulge` | 0.5 | LWPOLYLINE bulge(바깥쪽으로 볼록). tan(θ/4), θ ≈ 106° |
| `cloud.badge_side` | 200 | 번호 삼각형 한 변. 정삼각형, 꼭짓점 위 |
| `cloud.badge_text_height` | 90 | 삼각형 안 숫자 높이(가운데 정렬, 기준점은 삼각형 무게중심) |
| `cloud.badge_anchor` | `top_right` | 클라우드 사각형의 오른쪽 위 모서리 바깥에 삼각형 밑변 왼쪽 끝을 붙인다 |
| `cloud.color` | 1 | 레이어 색 |

- 클라우드 사각형 = 클러스터 bbox ± `margin×f`. 폴리라인은 왼쪽 아래 모서리에서 시작해 반시계 방향, 닫힘(`closed=True`), 각 정점의 bulge = `arc_bulge`. 정점 좌표는 소수점 3자리로 반올림해 결정론을 지킨다.
- 배지: 정삼각형 LWPOLYLINE(닫힘, bulge 0) + TEXT(`height = badge_text_height×f`, `halign=CENTER`, `valign=MIDDLE`, 스타일 `Standard`). 번호는 클러스터 번호.
- 이동(`moved`) 클러스터의 bbox = 전 위치 bbox ∪ 후 위치 bbox.

## 6. 리비전 표 (R1-09, 마크업 DWG에만)

`compare.yaml`의 `revtable` 절, 단위 규칙은 5절과 같다(1:100 기준 모델 mm × f).

| 항목 | 기본값 |
|---|---|
| `revtable.columns` | `[번호, 내용, 일자]` (담당 없음) |
| `revtable.col_widths` | `[800, 6000, 2000]` |
| `revtable.row_height` | 400 |
| `revtable.text_height` | 250 |
| `revtable.anchor` | `titleblock_left` — 표제란 블록 bbox의 왼쪽 위 모서리에서 왼쪽으로 붙이고(표 오른쪽 위 = 표제란 왼쪽 위), 아래로 자란다 |
| `revtable.header` | `[번호, 내용, 일자]` 머리글 행 1개 |

- LINE + TEXT로만 그린다(TABLE 엔티티 금지). 레이어 `REV-<YYYYMMDD>[-n]`.
- 행 = 승인된 클러스터(번호 순). 내용 = `user_label`이 있으면 그것, 없으면 `label`. 일자 = `run_date`(`YYYY-MM-DD`).
- 승인 클러스터가 0이면 표를 그리지 않는다(도곽 자체가 출력 대상에서 빠진다).

## 7. 사이드카 `clusters.json` (스키마 `compare/clusters-sidecar.schema.json`)

```json
{
  "schema_version": "0.1",
  "pair_id": "<sheet_pair ULID>",
  "pair_key": "<정규화 도면번호 또는 파일명>",
  "run_date": "2026-09-04",
  "layer": "REV-20260904",
  "frame": { "bbox": [x0, y0, x1, y1], "scale_denominator": 100, "scale_factor": 1.0, "offset_before": [dx, dy] },
  "clusters": [
    { "id": "c1", "number": 1, "bbox": [x0, y0, x1, y1], "kind": "moved",
      "label": "이동 1,250mm 동", "user_label": null, "decision": "pending", "note": null,
      "change_ids": ["ch3", "ch4"],
      "cloud": { "handle": "2F1", "points": [[x, y, bulge], ...] },
      "badge": { "shape_handle": "2F2", "text_handle": "2F3", "center": [x, y] } }
  ],
  "changes": [
    { "id": "ch1", "seq": 1, "kind": "modified", "etype": "LINE", "layer": "A-WALL",
      "before_handle": "1A3", "after_handle": "1A3", "bbox": [x0, y0, x1, y1],
      "delta": { "move": [dx, dy], "distance": 1250.0, "before": {...}, "after": {...} },
      "minor": false, "minor_reason": null, "cluster_id": "c1",
      "compare_handles": { "added": ["2A1"], "removed": ["2A2"] },
      "provenance": { "before": {"file": "...", "handle": "1A3", "path": [], "space": "MODEL"},
                      "after":  {"file": "...", "handle": "1A3", "path": [], "space": "MODEL"} } }
  ],
  "handle_to_cluster": { "2F1": "c1", "2F2": "c1", "2F3": "c1", "2A1": "c1", "2A2": "c1" },
  "counts": { "clusters": 1, "changes": 1, "minor": 0, "approved": 0, "ignored": 0 }
}
```

- `id`는 `c<number>`·`ch<seq>`로 **결정론적**이다. DB의 ULID는 파일에 쓰지 않는다.
- `handle_to_cluster`의 키는 **비교 DXF 안의 핸들**이다(원 도면 핸들이 아님). 뷰어 히트 테스트 → 이 표 → 클러스터.
- `decision`·`user_label`·`note`는 사용자 편집값이다. 엔진은 비교를 다시 돌릴 때 같은 `pair_key`·같은 클러스터 서명(정렬된 `change_ids`의 `(kind, before_handle, after_handle)` 튜플 해시)이면 이전 판정을 이어받는다.
- 정렬: `clusters`는 `number` 순, `changes`는 `seq` 순, `handle_to_cluster`는 키 정렬. JSON은 `ensure_ascii=False, indent=2, sort_keys=False`, 줄 끝 `\n`, 개행 LF.

## 8. 결정론

같은 전·후 작업용 DXF + 같은 `compare.yaml`·`frames.yaml` + 같은 `run_date`면 `compare.dxf`·`clusters.json`·`markup.dxf`(그리고 자체 변환기로 만든 마크업 DWG)가 **바이트 동일**해야 한다.

- 엔티티 순서: 후 도면 순서 → 전에서 온 엔티티(전 도면 순서) → 클라우드·배지·라벨(클러스터 번호 순). 핸들은 ezdxf가 이 순서대로 발급하므로 결정된다.
- ezdxf 헤더 변수 고정: `$FINGERPRINTGUID`·`$VERSIONGUID` = `{00000000-0000-0000-0000-000000000000}`, `$TDCREATE`·`$TDUPDATE`·`$TDUCREATE`·`$TDUUPDATE` = `run_date` 00:00의 율리우스일, `$TDINDWG` = 0. ezdxf가 저장 시 덮어쓰는 변수가 있으면 텍스트를 스트림에 쓴 뒤 그 줄만 정규화한다(R1-06이 확인).
- 부동소수: 좌표는 소수점 3자리(`round(x, 3)`), 거리·각도는 6자리로 반올림해 쓴다. `-0.0`은 `0.0`으로.
- 난수·현재 시각·`dict` 순서 의존 금지. 모든 집합 순회는 정렬한다.

## 9. 뷰어 사용 규칙 (R1-08)

- 보기 모드: 겹쳐 보기 = `__CMP_ADDED`·`__CMP_REMOVED` 표시, 전 = `__CMP_ADDED` 숨김, 후 = `__CMP_REMOVED` 숨김. `REV-*`는 항상 표시, `__CMP_LABEL`은 항상 숨김.
- 번호 배지 클릭: 히트 테스트 핸들 → `handle_to_cluster`. 리스트에서 번호 선택: `clusters[].bbox`(여백 포함)로 `zoomTo`.
- 뷰어는 파일을 바꾸지 않는다. 판정은 `PATCH /compare/pairs/{id}/clusters/{number}`로만.
