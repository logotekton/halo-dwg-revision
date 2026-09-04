# 도곽 추출과 짝짓기 (R1-04)

`POST /api/v1/compare/sets/{id}/frames`가 여는 `compare.frames` 잡. 인입이 끝난 작업용 DXF를
파일마다 열어 **도곽**(표제란 INSERT 하나 = 시트 하나)으로 자르고, 전·후 도곽을 짝지어
`compare_set.status`를 `matched`로 둔다. 계약은 `docs/contracts/r1.md` §1·§3·§5·§6·§7·§12,
구현은 `engine/src/halo_engine/compare/frames.py`(추출)·`match.py`(짝짓기)와
`engine/src/halo_engine/api/routers/compare_pairs.py`(라우터·잡 본체).

비교 단위가 파일이 아니라 도곽인 이유는 실측이다. 실도면 68장은 전부 모델공간 단독이고 한
파일에 도곽이 최대 100개 넘게 들어 있으며, 표제란 INSERT 수가 공종별 PDF 페이지 수와 정확히
일치한다(`docs/spikes/real-dwg-measurement.md` §0-1, §12 항목 14).

## 흐름도

```
POST /compare/sets/{id}/frames
  ├─ 번들 없거나 없는 id → 404
  ├─ compare_set.status ∉ {ingested, matched, compared} → 409
  └─ job = jobs.create(compare_set_id=.., kind="compare.frames") → 202 {job_id}
     stats.last_job_id 갱신(병합: 인입 잡이 쓴 값은 그대로 둔다)

compare.frames  # api/jobs.py::run_job이 감싼다
  ├─ 수동 짝 스냅숏: match_method="manual"인 짝을 (file_id, sort_index) 쌍으로 기억
  ├─ compare_set.status = extracting
  ├─ 전 세트 → 후 세트, 파일 하나씩(취소는 파일 사이에서 확인):
  │   run_in_executor(ProcessPoolExecutor, frames.extract_file_frames(path, file_id, config))
  │     ├─ ezdxf.readfile → extract_frames() → assign_entities()
  │     └─ 실패하면 예외 대신 FileFramesResult.error (그 파일만 건너뛴다)
  │   결과 FrameRecord에 role·file_name·file_sha256·converter를 붙이고,
  │   미인식 프레임은 norm_key = "file:<정규화 파일명>"
  ├─ repos.replace_frames(before) / (after)   # 이때 그 세트의 짝·변경·클러스터가 함께 지워진다
  ├─ match.match_frames_with_stats(before, after, compare.yaml, frames.yaml)
  ├─ 스냅숏한 수동 짝 복원(그 프레임을 물고 있던 자동 짝은 버린다)
  ├─ repos.replace_pairs
  └─ compare_set.status = matched,
     stats.frames = {before, after, unrecognized_files}
     stats.pairs  = {changed, same, added, removed, unpaired, unrecognized,
                     converter_mismatch, pending}
     stats.duplicate_sheet_no, stats.frames_skipped=[{file, role, error}]
```

`stats`는 **병합**한다. 인입 잡(R1-03)이 쓴 `files`·`converter`·`crosscheck`·`fonts_missing`은
그대로 두고 위 키만 더한다.

## 표제란 찾기 (`frames.yaml`의 값만 쓴다)

1. **후보 모으기** — 모델공간 INSERT를 문서 순서대로 훑는다. 블록 정의 안의 INSERT도
   **깊이 2까지** 따라가며 바깥 INSERT의 변환 행렬을 누적한다(W3-06이 XREF를 임베드하면
   표제란이 블록 안으로 들어오기 때문이다). 3단계 이상 깊으면 무시하고
   `titleblock_search_depth_exceeded:<n>` 경고를 남긴다.
   - ATTRIB이 `titleblock.min_attribs`(기본 3) 이상이면 후보. INSERT에 ATTRIB이 없으면 블록
     정의의 **고정(const) ATTDEF**를 대신 읽는다.
   - `titleblock.block_name_patterns`가 비어 있지 않으면 **그 이름에 맞는 INSERT만** 후보이고,
     이때는 `min_attribs`를 요구하지 않는다. 이름을 적었다는 것 자체가 "이게 표제란이다"라는
     선언이고, 변환기가 ATTRIB을 잃은 파일에서는 이 경로가 유일한 구제책이다(아래 실측 표).
2. **확정** — 태그가 `number_tags`나 `title_tags` 중 하나에 맞으면 표제란. 파일 안 어느 후보도
   태그가 안 맞으면 `fallback_most_common_block`(기본 true)이 **가장 많이 반복된 블록 이름**의
   인스턴스를 전부 표제란으로 삼는다(동수면 이름 오름차순).
   - 태그 비교는 `normalize_key` + 하이픈 제거다. `DWG_NO`·`DWG-NO`·`DWG NO`·`DWGNO`가 한 태그다.
3. **값 읽기** — `sheet_no`·`sheet_title`·`scale_text`·`date_text`는 `frames.yaml`의 태그 목록 순
   (먼저 적힌 것이 우선), `attributes`에는 태그→값을 전부 남긴다. `\M+c….`·`\U+…` 이스케이프는
   `ingest/encoding.py::decode_escapes`가 푼다.

## 도곽 경계 — 세 경로

| 순서 | `boundary_source` | 규칙 |
|---|---|---|
| (a) | `smallest_enclosing_rect` | 표제란 bbox를 완전히 포함하는 **가장 작은** 축 정렬 닫힌 사각형 LWPOLYLINE(정점 4~5, 각 변 수평·수직 ±1°, bulge 0). 모델공간 최상위만 본다 |
| (b) | `modal_size_titleblock_bottom_right` | (a)가 없으면 **그 파일에서** (a)로 구한 도곽 크기의 최빈값을 표제란 오른쪽 아래 기준으로 |
| (c) | `a1_titleblock_bottom_right` | 그것도 없으면 A1(841×594) × `scale_denominator`(못 읽으면 100)를 표제란 오른쪽 아래 기준으로 |
| — | `model_extents` | 표제란이 하나도 없는 파일의 `unrecognized_file` 프레임(도면 extents) |

- (a)에서 **표제란 자신의 테두리**(bbox가 표제란과 1mm 이내로 같은 사각형)는 제외한다. 안 그러면
  도곽이 표제란 크기로 줄어든다.
- 블록 정의 안의 사각형은 (a) 후보가 아니다. 실도면처럼 도곽선이 XREF 표제란 블록 안에 있으면
  자연히 (b)·(c)로 내려간다.
- 어느 경로든 결과가 표제란을 담지 못하면 표제란 bbox와 합집합을 취하고
  `frame_widened_for_titleblock` 경고를 붙인다.

## 엔티티 배정과 읽는 순서

- `frames.yaml` `frame.assign = bbox_center`: 모델공간 **최상위** 엔티티의 bbox 중심이 들어가는
  도곽에 배정한다. 두 도곽에 걸치면 중심이 든 쪽, 어느 도곽에도 없으면 미배정(비교 대상 아님).
- `entity_handles`는 정렬된 핸들 목록이다(같은 입력 → 같은 순서).
- 성능: INSERT는 블록 정의 extents를 **블록 이름마다 한 번** 재서 중심만 INSERT 행렬로 옮긴다.
  아핀 변환은 상자의 중심을 옮긴 상자의 중심으로 보내므로 근사가 아니라 정확하다
  (`test_insert_centres_match_the_full_bounding_box`). 도곽 검색은 가장 큰 도곽 크기를 한 칸으로
  하는 균일 격자 해시(`_FrameGrid`)라 엔티티당 dict 조회 한 번 + 사각형 비교 몇 번이다.
- `sort_index`는 읽는 순서다. 도곽 중심의 y를 도곽 높이 절반 단위로 묶어 행을 만들고(위→아래),
  행 안에서 x 오름차순(왼→오른쪽).
- `provenance = {file: <file_id>, handle: <표제란 handle>, path: [바깥 INSERT 핸들…], space: "MODEL"}`.

## 짝짓기 — 4단계

| 단계 | `match_method` | 조건 | `score` |
|---|---|---|---|
| 0 | (없음) | `unrecognized_file` 프레임끼리 정규화 파일명이 같으면 짝, 남으면 한쪽만. `status=unrecognized` | `null` |
| 1 | `number` | 정규화 도면번호가 같고 **양쪽에서 유일** | 1.0 |
| 2 | `title` | 제목 토큰(공백·하이픈·괄호·`/`로 분리) 자카드 ≥ `match.title_jaccard_min`이고 **양쪽에서 서로가 유일한 최고** | 유사도 |
| 3 | `position` | 정규화 파일명이 같고 `sort_index`가 같고 도곽 크기 ±1% | 0.5 |
| 4 | (없음) | 전에만 `removed`, 후에만 `added`, 후보가 여럿이었으면 `unpaired` | `null` |

**번호가 서로 다르면 2·3단계로 짝짓지 않는다.** `match.title_jaccard_min`은 설정 파일에
"도면번호가 없을 때 받아들이는 최소 제목 유사도"로 적혀 있고(`compare/config.py`), 한 세트의
도면명은 대부분 `1층 평면도`처럼 겹쳐서 자카드 1.0이 아무 증거가 못 된다. R1-07의 S14(A-101이
빠지고 A-103이 들어온다, 둘 다 `1층 평면도`)가 정확히 이 경우다 — 이 규칙이 없으면 서로 무관한
두 도면을 R1-06에 넘긴다. 번호가 바뀐 시트는 `removed` + `added`가 되고 화면 B에서 손으로
짝지으면 된다.

같은 도면번호가 **양쪽에** 여러 개면 그 프레임들은 1단계를 건너뛰고(2·3단계로 내려간다) 끝까지
안 맞으면 `unpaired`가 된다. 한쪽에만 중복이면 후보 자체가 없으므로 그냥 `removed`/`added`다.
중복 건수는 `stats.duplicate_sheet_no`에 남는다.

### 비교 전 상태

| `status` | 언제 |
|---|---|
| `converter_mismatch` | 전·후 파일의 `drawing_file.converter`가 둘 다 있고 다르다 |
| `same` | 전·후 파일의 sha256이 같다(내용이 같으니 비교할 것이 없다) |
| `pending` | 그 밖의 짝. R1-06이 `changed`/`same`으로 바꾼다 |

경고(`sheet_pair.warnings`): `frame_size_differs`(도곽 크기 1% 초과 차이),
`converter:<전>!=<후>`.

`sort_key`는 도면번호의 자연 정렬 키(숫자 8자리 0패딩, `A-101` → `A-00000101`)다. 번호가 없으면
제목, 그것도 없으면 `파일명:sort_index`. 후 프레임 기준이고 없으면 전 프레임 기준이다.

## API

| 메서드 | 경로 | 비고 |
|---|---|---|
| POST | `/compare/sets/{id}/frames` | 202 `{job_id}`. 상태가 `ingested`·`matched`·`compared`가 아니면 409 |
| GET | `/compare/sets/{id}/pairs?status=&q=&sort=` | `SheetPair` 목록. `before_frame`/`after_frame` 요약 포함(`entity_handles`는 뺀다) |
| POST | `/compare/sets/{id}/pairs/manual` | `{before_frame_id, after_frame_id}`. 두 프레임의 현재 짝이 `removed`·`added`·`unpaired`가 아니면 409, 역할이 어긋나면 422 |
| DELETE | `/compare/pairs/{pair_id}` | `manual` 짝만(아니면 409). 지우고 원래의 `removed`/`added` 짝을 되살린다 |

- `q`는 도면번호·도면명·파일명 부분 일치다. 양쪽을 `normalize_key` + 하이픈 제거로 접으므로
  `a103`으로 `A-103`이 찾아진다.
- `sort`는 `sheet_no`(기본, `sort_key`)·`status`·`changes`(변경 수 내림차순).
- 응답 모델은 `halo_engine.model.compare.SheetFrameView`·`SheetPairView`다. 계약 §4가 허용하는
  "같은 필드의 자체 모델"이며, 생성 모델(`halo_schema`)이 엔진 의존성에 없어서 그렇게 했다.
  `engine/tests/api/test_compare_pairs.py`가 `packages/schema/src/compare/*.schema.json`을 직접
  읽어 필드 집합이 어긋나면 실패한다.

## 수동 짝과 재추출

`repos.replace_frames`는 그 compare_set의 짝을 전부 지운다(짝은 프레임 id 두 개라서 그래야 한다).
그래서 잡은 시작 전에 수동 짝을 `(file_id, sort_index)` 쌍으로 스냅숏하고, 새 프레임에 다시
매핑해 되살린다. `drawing_file` 행은 도곽 잡이 건드리지 않고, 안 바뀐 파일의 읽는 순서는 그대로라
이 키가 재추출을 넘어 유효하다.

## 결정론

- 후보는 문서 순서, 그 밖의 모든 반복은 정렬된 키를 돈다. 좌표는 소수점 3자리 반올림.
- 파일 순서는 `plan_set_files`(이름 대소문자 무시 정렬)가 정하고, 전 세트 → 후 세트 순으로 돈다.
- 같은 입력이면 프레임·짝의 순서와 값이 같다(`test_assignment_is_stable_across_two_runs`,
  `test_frames_can_be_re_extracted_after_matching`).

## 실도면 실측 (mac, acad-ts 변환)

`HALO_REAL_SET=1 uv run pytest tests/compare/test_real_set_frames.py -q -s`
(`HALO_REAL_SET_FOLDERS=03_전기`처럼 공종을 골라 돌릴 수 있다.)

표는 두 설정을 나란히 잰다. **기본**은 ATTRIB 태그로 찾는 경로,
**블록명**은 `block_name_patterns: ["*TITLE BLOCK*"]`(실도면의 표제란 블록 이름)이다.
mac에서는 acad-ts가 ATTRIB을 잃어서(스파이크 §3.2, 68장 중 45장) 기본 경로가 0을 내지만,
블록명 경로는 장부 수와 맞는다. **합격 판정은 Windows 설치본(ZWCAD 변환)에서 한다** —
`docs/gates/R1.md`.

측정값은 R1-04 보고서에 있다.
