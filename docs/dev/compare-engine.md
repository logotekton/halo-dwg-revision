# 비교 엔진 (R1-06)

`POST /api/v1/compare/sets/{id}/run`이 여는 `compare.run` 잡. 짝지어진 도곽마다 전·후 엔티티를
비교해 **변경**(`change`)과 **클러스터**(`cluster`)를 만들고, 뷰어가 그대로 그릴 **비교 DXF**와
사이드카 **`clusters.json`**을 쓴 뒤 `compare_set.status`를 `compared`로 둔다.

정본은 `docs/contracts/compare-dxf.md`(전부)와 `docs/contracts/r1.md` §3·§4·§5·§6·§7·§11.
구현은 `engine/src/halo_engine/compare/`의 `signatures.py`·`diff.py`·`cluster.py`·`labels.py`·
`compare_dxf.py`와 라우터 `api/routers/compare_clusters.py`.

## 흐름도

```
POST /compare/sets/{id}/run  {pair_ids?}
  ├─ 번들 없거나 없는 id → 404 / 모르는 pair_id → 404
  ├─ compare_set.status ∉ {matched, compared} → 409
  └─ job = jobs.create(compare_set_id=.., kind="compare.run") → 202 {job_id}

compare.run  # api/jobs.py::run_job이 감싼다
  ├─ 대상 고르기: 짝 정렬 순(sort_key), 아래는 건너뛰고 stats에 사유를 남긴다
  │    added · removed · unrecognized · converter_mismatch · 한쪽만 있는 짝 · 작업용 DXF 없음
  ├─ compare_set.status = comparing
  ├─ 짝 하나씩(취소는 짝 사이에서 확인):
  │   run_in_executor(ProcessPoolExecutor, compare_dxf.compare_pair(task, config))
  │     ├─ ezdxf.readfile(전) / (후)
  │     ├─ diff_pair()      → changes, offset, warnings
  │     ├─ build_clusters() → clusters (번호·라벨·클라우드·배지)
  │     ├─ write_compare_dxf()  → .halo/compare/<pair_id>/compare.dxf
  │     └─ write_clusters_json() → 같은 폴더 clusters.json (무결성 검사 통과해야 씀)
  │   실패는 예외 대신 ComparePairOutput.error (그 짝만 건너뛴다)
  │   ├─ repos.replace_changes(pair_id, changes)
  │   ├─ repos.replace_clusters(pair_id, clusters, keep_decisions=True)
  │   │     → 서명이 같은 옛 클러스터의 decision·user_label·note를 물려받는다
  │   ├─ 물려받은 판정이 있으면 clusters.json의 그 세 필드만 다시 쓴다
  │   └─ repos.update_pair(status=changed|same, 경로, warnings)
  └─ compare_set.status = compared,
     stats.compare = {compared, changed, same, failed, skipped}
     stats.compare_skipped=[{pair_id, reason}], stats.compare_failed=[{pair_id, error}]
     stats.last_job_id
```

## 좌표: 도곽 로컬

비교는 처음부터 끝까지 **도곽 로컬 좌표**에서 한다.

```
local  = world - frame.bbox.min
offset = after.bbox.min - before.bbox.min      # 사이드카 frame.offset_before
```

후 파일을 통째로 50m 옮겨 그린 세트(`fixtures/compare/S15_frame_shift`)가 "변경 없음"으로 나오는
이유가 이것이다. 파일이 아니라 시트를 비교한다는 결정(계약 §1)이 코드에서 실제로 뜻하는 바다.
변경 레코드의 `bbox`는 다시 **후 도면 세계 좌표**(`local + after.bbox.min`)로 돌려서 쓴다 —
뷰어와 마크업이 후 도면 좌표계에서 그리기 때문이다.

## 엔티티 서명 (`signatures.py`)

엔티티 하나는 `EntitySignature`(frozen dataclass, 피클 가능)로 요약한다. 매칭·접기·라벨은 전부
이 요약만 본다.

| 필드 | 뜻 |
|---|---|
| `points` | 기하 좌표(로컬, 소수 3자리). 형상 키를 만들 때 앵커만큼 평행이동한다 |
| `scalars` | 위치와 무관한 나머지(반지름·각도·블록 이름·척도·측정값…) |
| `anchor` | 기준점. 보통 `points[0]`, HATCH와 형식 미상은 자기 bbox의 왼쪽 아래 |
| `text` / `raw_text` | 서식 벗긴 문자열 / 원문. 둘의 차이가 `mtext_format_only`다 |
| `hatch_key` | `(패턴, solid, 축척, 각, hatch_style, 정렬된 정점 집합)` |
| `dim_key` | `(dimtype, 측정값, 재정의 문구, 정렬된 정의점)` |
| `box` | 로컬 bbox(변경 레코드·클러스터가 쓴다) |

### etype별 기하

| etype | points | scalars |
|---|---|---|
| LINE | 시작·끝 | — |
| LWPOLYLINE / POLYLINE | 정점 | 닫힘, bulge, 폭 |
| CIRCLE / ARC | 중심 | 반지름 (+ 시작·끝 각) |
| ELLIPSE | 중심 | 장축 벡터, 비율, 시작·끝 파라미터 |
| SPLINE | 제어점 | 차수, knots, weights, 닫힘 |
| TEXT / ATTRIB / ATTDEF | 삽입점, 정렬점 | 높이·회전·정렬·폭·기울기·스타일 |
| MTEXT | 삽입점 | 글자 높이·회전·폭·부착점·스타일 |
| INSERT | 삽입점 | 블록 이름, x/y/z 축척, 회전, **정렬된 ATTRIB (태그→값)** |
| DIMENSION | 있는 정의점만 | dimtype, `get_measurement()`, 재정의 문구, dimstyle, **정의점 이름 목록** |
| HATCH | 경계 정점(경로 순서) | 패턴 이름, solid, 축척, 각, hatch_style |
| LEADER / POINT / SOLID / TRACE / 3DFACE | 정점 | — |
| 그 외 | bbox 두 모서리 | etype |

DIMENSION의 "있는 정의점만"은 실제로 물린 적 있는 함정이다. 없는 `defpoint4`를 `(0,0)`으로
채우면 그 가짜 점이 도곽과 함께 움직여서, 평행이동한 시트의 치수가 전부 `modified`로 나온다.

## 매칭: 다섯 단계

각 단계는 앞 단계가 남긴 것만 본다. 강한 증거가 먼저 짝을 가져가고, 약한 증거는 실수할 기회를
얻지 못한다.

| # | 단계 | 키 | 무엇을 잡나 |
|---|---|---|---|
| 1 | identity | `(etype, layer, text, 기하)` 완전 일치 | 안 바뀐 엔티티. 사전 한 번 훑기(O(n)) |
| 2 | fingerprint | 같은 키를 `match.fingerprint_tolerance`(1mm) 격자로 양자화 + **이웃 셀 ±1**, 실제 거리 ≤ 1mm, 가까운 것부터 | 1mm 미만으로 흔들린 엔티티 |
| 3 | handle | 같은 핸들·같은 etype (bbox가 겹치거나 형상이 같을 때만) | 제자리에서 고쳐진 엔티티: 치수값·문구·레이어 이관 |
| 4 | shape | 앵커 기준으로 옮긴 기하(레이어 제외) | **이동**. 핸들이 전부 새로 매겨져도 살아남는다 |
| 5 | proximity | `(etype, layer)` + 앵커 거리 ≤ 1mm | 제자리에서 다시 그려진 엔티티: 시작 정점만 바뀐 해치, 재작도된 문자 |
| — | 나머지 | | 전에만 → `removed`, 후에만 → `added` |

### 왜 핸들이 1단계가 아닌가

브리프는 핸들 매칭을 ①로 적었다. 구현은 3단계로 내렸다. 통째 재작도
(`fixtures/compare/S12_whole_redraw`)에서는 핸들이 **재사용**된다 — 전 도면의 `F8`과 후 도면의
`F8`이 서로 남남이다. 핸들을 먼저 믿으면 그 시트의 거의 모든 엔티티가 가짜 `modified`로
나온다. 위치가 완전히 같은 엔티티를 먼저 정리하고 나면 핸들 단계에 남는 후보가 실제로
"고쳐진 엔티티"뿐이라서, 순서를 바꾸는 것만으로 오탐이 0이 된다. 위치가 같은 짝을 1단계에서
가져가도 결과는 달라지지 않는다(어차피 변경 레코드가 안 생긴다).

거리 동률은 `(거리, 후 문서 순서, 전 문서 순서)`로 끊는다. 형상이 같은 후보가 지나치게 많은
그룹(`MAX_GROUP_PAIRS` 초과)은 거리 순위를 매기지 않고 문서 순서로 짝짓는다.

## 접기 규칙

짝지어진 엔티티의 차이를 사실(fact) 단위로 모은 뒤, **전부** 접을 수 있으면 `minor=true`다.
하나라도 못 접으면 실제 변경이고, 접기 사유는 기록하지 않는다.

| 사실 | 사유(`minor_reason`) | 조건 |
|---|---|---|
| 평행이동 | `move_le_0_01` | 거리 ≤ `minor.move_tolerance`(0.01mm) |
| 레이어만 | `layer_only` | `minor.fold`에 있을 때 |
| 색만 | `color_only` | 〃 |
| 선종류만 | `linetype_only` | 〃 |
| 선굵기만 | `lineweight_only` | 〃 |
| 해치 재생성 | `hatch_regen` | 기하는 다르지만 `hatch_key`(패턴·축척·각·정렬된 정점) 같음 |
| 치수 재생성 | `dim_regen` | 기하는 다르지만 `dim_key`(측정값·문구·정렬된 정의점) 같음 |
| MTEXT 서식만 | `mtext_format_only` | 평문은 같고 원문만 다름 |

여러 사유는 스키마가 나열한 순서대로 `+`로 잇는다(`layer_only+color_only`). 접힌 변경도
`change` 레코드로 남고 사이드카 `changes[]`에 들어가지만 `cluster_id`는 `null`이고, 클라우드
마크·리비전 표에는 오르지 않는다. 도곽 짝의 상태는 **접히지 않은 변경이 하나라도 있어야**
`changed`, 없으면 `same`이다.

`kind` 우선순위는 `moved > dimension > text > modified`다. 측정값이 바뀐 치수는 정의점도 함께
움직이는데, 그것을 `modified`로 부르면 사용자가 볼 유일한 사실이 사라진다.

## `blockdef`

같은 이름의 블록 정의를 전·후에서 **재귀적으로** 서명해 비교한다(`block_signature`, 중첩은 부모
서명에 펼치고 자기 참조는 cycle guard로 끊는다). 다르면 그 블록의 INSERT마다 `modified`를
내는 대신 `blockdef` 변경 **한 건**을 낸다.

- 대표는 후 핸들이 가장 작은 인스턴스 짝(`before_handle`/`after_handle`), `etype`은 `INSERT`.
- `delta = {block: <이름>, instances: n}`, `bbox`는 인스턴스 bbox 합집합.
- 클러스터: 합집합의 긴 변이 도곽 긴 변의 **30%**(`BLOCKDEF_SPLIT_RATIO`)를 넘으면 인스턴스마다
  클러스터를 하나씩 만들고 모두 같은 변경을 가리킨다. 넘지 않으면 하나로 묶는다.
- 비교 DXF에서는 인스턴스마다 `__CMP_REMOVED`(전 정의, `__B_` 블록) + `__CMP_ADDED`(후 정의)
  한 쌍으로 그린다.

## 클러스터와 번호

- 묶는 거리 = `max(도곽 긴 변 × cluster.grow_ratio, cluster.grow_min × scale_factor)`.
  A1 1:100이면 `max(84,100 × 0.02, 300) = 1,682mm`.
- 각 bbox를 그 거리의 **절반**만큼 사방으로 키워 겹치면 union-find로 합친다. 그래야 두 변경
  사이 간격이 정확히 `grow` 이하일 때 묶인다(`compare.yaml` 주석의 약속).
- 전수 비교가 아니라 공간 격자(셀 = 묶는 거리) 위에서 돌린다. 재작도된 시트는 변경이 수천 개다.
- 번호는 읽는 순서: 아직 배치 안 된 것 중 가장 위 클러스터와 **세로로 겹치는** 것들이 한 행,
  행 안에서는 왼쪽부터. 나란한 두 구름이 몇 mm 어긋나도 번호가 이어진다.
- `signature` = 정렬된 `(kind, before_handle, after_handle)` 튜플의 sha256 앞 16자.
  번호도 bbox도 아니다 — 다시 비교하면 그 둘은 바뀌고, 사용자의 승인은 바뀌면 안 된다.

### 클라우드와 배지 (계약 §5)

`cloud_polyline()`·`badge_geometry()`가 좌표의 유일한 출처다. R1-06이 비교 DXF에 쓰고 R1-09가
마크업 DWG에 같은 좌표를 쓴다. 모든 길이는 1:100 기준 mm × `scale_factor`
(`scale_factor = scale_denominator / 100`, 못 읽으면 1.0).

- 사각형 = 클러스터 bbox ± `cloud.margin`. 왼쪽 아래에서 시작해 **반시계** 방향, 닫힘.
- 변마다 `ceil(변 길이 / (cloud.arc × f))`개로 균등 분할, 정점마다 bulge `cloud.arc_bulge`.
  반시계 + 양수 bulge = 바깥으로 볼록(양수 bulge의 호는 반시계로 도는데, 반시계 사각형에서는
  그 중심이 안쪽에 놓이므로 호가 바깥으로 나온다).
- 배지 = 정삼각형(한 변 `cloud.badge_side × f`, 꼭짓점 위). 밑변 왼쪽 끝을 사각형 오른쪽 위
  모서리에 붙인다. 숫자는 무게중심에 `MIDDLE_CENTER`, 높이 `cloud.badge_text_height × f`.

## 자동 문구 (`labels.py`)

`{종류} {행위}[ {수치}]`. 종류는 엔티티 타입의 한국어 이름(사전은 2주차), INSERT는
`블록 <이름>`, 여러 종류가 섞이면 `최다 종류 외 n건`.

| 행위 | 예 |
|---|---|
| 신설 / 삭제 | `폴리라인 신설`, `해치 삭제` |
| 이동 | `블록 DOOR_900 이동 1,250mm 동` (8방위) |
| 치수 | `치수 12,000→12,500` |
| 문구 | `문자 문구 거실→리빙룸` |
| 블록 정의 | `블록 DOOR_900 정의 변경 6곳` |
| 그 외 | `선 수정` |

종류와 행위의 첫 낱말이 같으면 한 번만 쓴다 — `치수 치수 12,000→12,500`은 도면에 쓰지 않는다.

## 비교 DXF 조립 순서 (`compare_dxf.py`)

빈 R2018 문서에서 시작해 엔티티 단위로 옮긴다. 후 파일을 고쳐 쓰지 않는 이유는 두 가지다:
파일에는 **그 도곽 하나**만 들어가야 하고(계약 §1), 전 도면 블록은 `__B_` 접두를 달고 와야
한다(계약 §3 — 같은 이름의 정의가 양쪽에서 다를 수 있고, 그게 바로 `blockdef` 변경이다).

1. 전 도면 블록 이름을 전부 `__B_<이름>`으로 바꾼다(`*` → `_`, 그래서 `*D1` → `__B__D1`).
   INSERT의 `name`과 DIMENSION의 `geometry` 참조도 같이 고친다. 레이아웃 블록은 건드리지 않는다.
2. 테이블을 **통째로, 원본 순서대로** 옮긴다: 후 도면의 linetypes·layers·styles·dimstyles →
   전 도면에만 있는 것들. (그다음 화살표 블록 → 후 도면 블록 전부 → `__CMP_ADDED`·
   `__CMP_REMOVED`·`REV-<날짜>`·`__CMP_LABEL`.)
3. 후 도곽 엔티티를 문서 순서대로 임포트. 변경에 관여했으면 XDATA를 달고, 접히지 않은 변경이면
   `__CMP_ADDED`로 옮긴다(색·선종류·선굵기는 `BYLAYER`로 강제, 원래 레이어는 XDATA에).
4. 변경에 필요한 전 도곽 엔티티를 임포트해 `offset`만큼 평행이동하고 `__CMP_REMOVED`로.
   접힌 변경의 전 상태는 그리지 않는다(계약 §2: 사소한 변경은 후 엔티티 하나로 나타낸다).
   DIMENSION은 임포트한 뒤 원본의 `geometry` 블록을 따로 가져와 다시 연결한다 —
   안 하면 `audit()`이 "geometry 블록 없음"으로 그 치수를 지운다.
5. 클러스터 번호 순으로 클라우드 폴리라인 → 배지 삼각형 → 배지 숫자 → `__CMP_LABEL` 히트 사각형.
6. 헤더·CLASSES 고정 → `audit()` → 직렬화 → 텍스트 정규화 → 바이트로 저장.

`handle_to_cluster`는 이 과정에서 **새 문서의 핸들**로 채운다(클라우드·배지 도형·배지 숫자·
히트 사각형 + 그 클러스터의 변경이 `__CMP_*`에 쓴 엔티티). 뷰어는 히트 테스트로 얻은 핸들을
이 표에 넣어 클러스터를 찾는다.

## 결정론 (계약 §8)

같은 전·후 작업용 DXF + 같은 설정 + 같은 `run_date`면 `compare.dxf`·`clusters.json`이
**바이트 동일**하다. 네 가지가 이것을 깨뜨렸고 넷 다 막았다.

| 원인 | 조치 |
|---|---|
| ezdxf `Importer`가 필요한 layer·linetype·style·dimstyle을 `set`으로 모은다 → LAYER 테이블 순서가 해시 시드에 좌우 | 엔티티 임포트 **전에** 테이블을 통째로 원본 순서대로 옮긴다. 임포터는 이미 다 있는 것을 보고 아무것도 추가하지 않는다 |
| CLASSES 절을 `entitydb.dxf_types_in_use()`(역시 `set`)로 채운다 | `pin_classes_for_determinism()` — 미리 등록하고 정렬한다 |
| 저장할 때 `$FINGERPRINTGUID`·`$VERSIONGUID`를 새로 만들고 `$TDUPDATE`를 현재 시각으로 덮는다 | 직렬화한 텍스트를 태그 쌍 단위로 훑어 GUID는 0으로, `$TD*`는 `$TDCREATE`가 이미 쓴 문자열로 통일 |
| 저장할 때 자기 버전·현재 시각을 `DICTIONARYVAR` 두 개에 남긴다 | 같은 순회에서 `<버전> @ <run_date>T00:00:00+00:00`으로 교체 |

그 밖에: 좌표는 소수 3자리, 각도·거리는 6자리, `-0.0`은 `0.0`, 모든 `set`/`dict` 순회는 정렬,
JSON은 `ensure_ascii=False, indent=2`에 LF·끝 개행. `run_date`는 명시 입력이고 엔진은 시계를
읽지 않는다(계약 §11).

앞의 두 개는 **한 프로세스 안에서는 보이지 않는다** — 해시 시드가 고정이기 때문이다. 실제
비교는 잡 러너의 프로세스 풀 워커(=새 인터프리터)에서 돌기 때문에,
`tests/compare/test_determinism.py`는 `PYTHONHASHSEED`를 둘로 바꿔 자식 프로세스에서 비교를
두 번 돌린다.

`PATCH .../clusters/{number}`는 사이드카의 `decision`·`user_label`·`note`(와 `counts`의 두 값)
**만** 다시 쓴다. 다시 비교해도 재현되어야 하는 것은 비교 결과이지 사용자의 판정이 아니다.

## 사이드카 무결성

`clusters.json`은 쓰기 전에 두 번 검사한다. JSON Schema
(`packages/schema/src/compare/clusters-sidecar.schema.json`)가 모양을, `sidecar_integrity_failures()`
가 스키마로 표현할 수 없는 것을 본다.

- `handle_to_cluster`의 값이 전부 실제 클러스터 id인가, 키가 정렬돼 있는가
- 클러스터 번호가 1부터 빠짐없이, `id == "c<number>"`인가
- 변경 `seq`가 1부터 빠짐없이, `id == "ch<seq>"`인가
- `changes[].cluster_id`가 실재하는 클러스터인가, 접힌 변경이 클러스터에 들어가 있지 않은가
- `counts`의 다섯 값이 배열과 맞는가

하나라도 어긋나면 `ValueError`를 내고 **파일을 쓰지 않는다**. 검토 화면이 도면과 어긋난 상태는
사용자가 알아챌 방법이 없다.

## API

| 엔드포인트 | 설명 |
|---|---|
| `POST /compare/sets/{id}/run` `{pair_ids?}` | 202 `{job_id}`. `matched`·`compared`에서만, 아니면 409 |
| `GET /compare/pairs/{pair_id}/clusters` | 사이드카 + DB 판정 병합. 비교 전이면 409 |
| `PATCH /compare/pairs/{pair_id}/clusters/{number}` | `{decision?, user_label?, note?}` → `Cluster`. 키가 없으면 그대로, `null`이면 지운다 |
| `GET /compare/pairs/{pair_id}/compare-dxf` | `application/dxf` 바이트, `ETag`는 파일 sha256(따옴표 포함). `If-None-Match`가 맞으면 304 |

## 성능

`diff_pair`는 35만 엔티티 도곽에서 **21초**(예산 120초). 합성 도곽(선·폴리라인·원·문자·INSERT
각 20%, 레이어 9개, 블록 1개)을 전·후로 만들어 잰 값이다. 변경이 17,500건(5%)이어도 21.7초,
클러스터링이 5.2초 더 붙는다. 측정: `mac / Python 3.12 / ezdxf 1.4.4`.

받쳐 주는 것은 두 가지다. 1단계가 사전 한 번 훑기로 시트의 대부분을 정리하기 때문에 뒤 단계는
남은 것만 보고, bbox는 블록 정의마다 한 번만 재서 인스턴스는 네 점 변환으로 끝낸다
(`signatures.BoxCache`, `frames.py`의 `_CentreFinder`와 같은 수법).

## 실패 모드

| 증상 | 어디를 보나 |
|---|---|
| 평행이동한 시트가 전부 `modified` | 도곽 bbox(로컬 좌표의 원점). `warnings`에 `frame_size_differs`가 있으면 도곽 크기가 1% 넘게 다르다 |
| 재작도한 시트에 오탐이 쏟아짐 | 매칭 단계 순서(핸들이 앞으로 갔는지), `_stage_handle`의 겹침 가드 |
| 사소한 변경이 클라우드로 나옴 | `compare.yaml`의 `minor.fold`·`minor.move_tolerance` |
| 클라우드가 통째로 하나 | `cluster.grow_ratio`·`grow_min`, 그리고 `blockdef` 분할 30% 규칙 |
| 클라우드 크기가 이상함 | 표제란 `SCALE` 파싱 → `scale_denominator` → `scale_factor` |
| 두 번 돌렸는데 바이트가 다름 | 위 결정론 표. 새 `set` 순회가 들어왔는지 의심한다 |
| 치수가 사라짐 | `_import_one`의 `geometry` 블록 재연결. `audit()`이 지운다 |
| 비교 DXF에 옆 도곽이 섞임 | `sheet_frame.entity_handles`(R1-04 `assign_entities`) |
