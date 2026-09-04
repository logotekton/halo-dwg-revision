# 세트 인입 잡 (R1-03)

`POST /api/v1/compare/sets`가 여는 `compare.ingest` 잡. 전·후 두 폴더를 받아 번들을 열고,
`drawing_set`(role=`before`/`after`) 두 행과 `drawing_file` 행을 만든 뒤, 파일마다 사본 →
(필요하면) 변환 → 작업용 DXF 정본을 만들어 `compare_set`을 `ingested`로 둔다. 계약은
`docs/contracts/r1.md` §1·§2·§3·§6·§6.1·§6.2·§7, 구현은
`engine/src/halo_engine/compare/ingest_set.py`(오케스트레이션)와
`engine/src/halo_engine/api/routers/compare_sets.py`(라우터), 잡 공용 부품은
`engine/src/halo_engine/api/jobs.py`(`run_job`·`ProgressReporter`·`JobCancelled`).

## 흐름도

```
POST /compare/sets {before_dir, after_dir, project_dir?, run_date, options?}
  │
  ├─ before_dir·after_dir 존재 확인(아니면 422), project_dir 기본값 = 공통 부모
  │  (형제가 아니면 after_dir의 부모, docs/contracts/r1.md §1)
  ├─ <project_dir>/.halo 열기(project.json 있으면) 또는 만들기 → app.state.bundle
  ├─ compare.yaml 로드(없으면 기본값 복사) → ingest.ignore_patterns·converter·
  │  zwcad_timeout_s·zwcad_dxf_version·crosscheck_sample
  ├─ 세트마다: drawing_set(role, label=폴더 이름, source_dir) 생성
  │  └─ plan_set_files(dir, ignore_patterns): 1단계만, .dwg/.dxf만, 이름 대소문자 무시 정렬
  │     └─ drawing_file 행(정렬 순). 제외 패턴 걸리면 import_status=EXCLUDED,
  │        excluded_reason="ignore_pattern" (사본·변환 없음)
  ├─ compare_set(status=ingesting, options) 생성
  └─ job = jobs.create(compare_set_id=.., kind="compare.ingest") → 202 {compare_set_id,
     project_id, job_id}, asyncio.Task로 compare.ingest_set.run_compare_set_ingest 시작

run_compare_set_ingest(app, job=.., bundle=.., compare_set_id=..)  # api/jobs.py::run_job이 감싼다
  │
  ├─ 전 세트 파일 순서대로 (_ingest_side role="before"):
  │  │  # 세트당 숨은 ZWCAD 인스턴스 하나, 전용 단일 스레드 executor에서만 연다
  │  └─ 파일마다 _process_file:
  │     ├─ copy_original_step(sha256, originals/) — 원본은 절대 쓰지 않는다
  │     ├─ sha 캐시 적중(아래)이면 변환·정본 생성 건너뛰고 DONE + converter_meta.cache_hit=true
  │     ├─ 아니면 DXF 입력은 변환 없음. DWG 입력은 pick_converter(zwcad.detect(), option):
  │     │  ├─ zwcad-com → ZwcadConverter.convert_dwg_to_dxf(originals 사본,
  │     │  │  cache/dxf/<sha>.zwcad.dxf). ZwcadError면 builtin으로 재시도
  │     │  │  (converter_meta.fallback_reason 기록)
  │     │  └─ builtin → WS convert.request(데스크톱) 또는 acad-ts 폴백
  │     ├─ build_working_dxf_step(변환된 DXF 또는 원본 DXF) → 정본 + stats
  │     ├─ DWG 입력이면 정본·stats를 원본 sha256 이름으로도 복사(아래 "캐시 규칙" 참고)
  │     └─ STYLE 테이블에서 font_names 읽어 행에 저장. 진행률
  │        ProgressReporter(progress, "convert i/N before 파일이름", stage="convert",
  │        extra={role, index, total, file, converter})
  ├─ 후 세트도 같은 방식(_ingest_side role="after")
  ├─ 같은 변환기 규칙: enforce_same_converter(...) — 한 파일이 builtin이면 상대 세트의 같은
  │  이름(정규화) 파일도 builtin으로 재변환(_reconvert_as_builtin)
  ├─ 표본 교차검증(아래) → compare_set.stats.crosscheck
  └─ compare_set.status = ingested (전부 실패면 failed), stats = {files, converted, failed,
     excluded, converter_counts, converter, fonts_missing, crosscheck, last_job_id}

GET /compare/sets/{id} → CompareSetSummary(계약 §7). before/after 집계는 매번 drawing_file
행에서 다시 세고(진행 중에도 폴링 가능), converter·fonts_missing·crosscheck는 compare_set.stats
에서, frames·pairs는 R1-04 전이라 항상 null.
```

## sha256 캐시 규칙

계약 Goal 2: "같은 sha256의 `cache/dxf/<sha>.working.dxf`와 `stats`가 이미 있으면 변환·정본
생성을 건너뛰고 행에 `converter_meta.cache_hit=true`." 여기서 `<sha>`는 **원본 파일**의
sha256(`copy_original_step`이 계산하는 값)이다.

DXF 입력은 `ingest/working_dxf.py::build_working_dxf`가 입력 파일 자체의 sha256으로 정본을
쓰기 때문에 이 규칙이 그대로 맞아떨어진다. **DWG 입력은 다르다** — `build_working_dxf_step`에
넘기는 `input_dxf_path`는 원본 DWG가 아니라 방금 변환기가 만든 DXF이므로, `ingest/working_dxf.py`
자신은 그 변환된 DXF의 sha256으로 `cache/dxf/<변환된-DXF-sha>.working.dxf`를 쓴다(이 파일은
`ingest/**` 소유라 R1-03이 그 이름 규칙을 바꿀 수 없다). 그래서 `ingest_set.py`는 DWG 변환이
끝날 때마다 방금 만든 정본·stats를 **원본 sha256 이름으로도** 한 벌 더 복사해 둔다
(`_mirror_working_dxf_to_original_sha`, DXF 입력이면 두 이름이 이미 같아서 아무 일도 하지
않는다). 다음에 같은 원본 파일(같은 sha256)을 다시 인입하면 — 전·후 폴더가 같은 경우(도곽 수
확인 용도, Defaults for ambiguity), 또는 같은 프로젝트를 두 번째로 인입하는 경우 — 이 사본을
찾아 변환을 건너뛴다. `drawing_file.working_dxf_path`/`stats_json_path`에는 항상 이
원본-sha256 경로가 저장된다.

같은 변환기 규칙으로 파일을 다시 변환할 때(`_reconvert_as_builtin`)도 같은 원본-sha256 이름
자리에 다시 쓴다 — "이미 ZWCAD로 끝났으면 다시 변환한다"는 계약 문장대로, 그 파일의 캐시 자리는
가장 최근에 실제로 돌린 변환기의 결과로 덮인다.

## 변환기 선택 (`pick_converter`)

`compare.yaml`의 `ingest.converter`(또는 `options.converter` 재정의)와 이 프로세스의
`zwcad.detect()` 결과로 파일마다 목표 변환기를 정한다.

| `option` | ZWCAD 가능 | 목표 | 불가능하면 |
|---|---|---|---|
| `auto` | 예 | `zwcad-com` | 세트 자체가 `builtin`으로 시작(재시도 아님) |
| `auto` | 아니오 | `builtin` | — |
| `zwcad` | 예 | `zwcad-com` | — |
| `zwcad` | 아니오 | `zwcad-com`(시도) | **그 파일은 FAILED** — "없으면 실패" (기계에 ZWCAD가
  아예 없는 경우; 실제 변환 중 오류는 아래처럼 builtin으로 재시도한다) |
| `builtin` | 상관없음 | `builtin` | — |

목표가 `zwcad-com`이고 실제로 열었는데 `ZwcadError`(타임아웃 포함)가 나면 — `option` 값과
무관하게 — 그 파일은 `builtin`으로 재시도하고 `converter_meta.fallback_reason`을 남긴다. 이
재시도는 "기계에 ZWCAD가 있다고 판단해서 열어봤는데 이 파일 하나가 실패한" 런타임 오류에만
적용되고, 위 표의 "ZWCAD 자체가 없음" 경우와는 다르다.

`builtin`은 WS로 연결된 데스크톱(`convert.request`)이 있으면 그쪽을, 없고
`converter_fallback == "acad-ts"`(서버 기본값 또는 `options.converter_fallback`)면 acad-ts
CLI 서브프로세스를 쓴다. 둘 다 없으면 그 파일은 `NEEDS_MANUAL_CONVERSION`.

## 같은 변환기 규칙 (1차)

`enforce_same_converter`: 두 세트를 다 변환한 뒤, 파일 이름을 정규화(소문자, 확장자 제거,
`norm_key`)해 짝지어 본다. 한쪽이 `builtin`으로 끝났는데 같은 이름의 반대쪽이 `zwcad-com`으로
끝났으면, 그 `zwcad-com` 쪽을 `builtin`으로 다시 변환한다(`converter_meta.same_converter_forced
= true`). 재변환이 실패하면 원래 `zwcad-com` 결과를 그대로 두고 로그에 남긴다(그 파일 하나를
성공에서 실패로 되돌리지 않는다). 도곽 단위의 최종 판정은 R1-04가 한다 — 이건 이름 기준의
1차 규칙일 뿐이다.

## 표본 교차검증

두 변환기가 다 가능한 PC(ZWCAD 가능 **그리고** 데스크톱 연결 또는 acad-ts 브리지 존재)에서만,
`zwcad-com`으로 끝난 파일 중 세트당 앞에서부터 `ingest.crosscheck_sample`개를 builtin으로도
변환해 `validate/crosscheck.compare()`로 비교한다. 상태가 `GREEN`이 아니면 그 파일을
"불일치"로 세고, 각 차이를 로그에 한 줄씩 남긴다. 불가능하면(ZWCAD 없음/builtin 없음/표본 0개
설정/`zwcad-com`으로 변환된 파일이 아예 없음) `compare_set.stats.crosscheck`에
`skipped` 사유를 남긴다 — 다만 `GET /compare/sets/{id}`의 공개 `crosscheck` 필드는 스키마가
`{sampled, mismatched}`만 허용해 `skipped`는 내부 `stats`에만 남고 API에는 나가지 않는다
(Shared-file patch 참고).

## 로그 형식

`.halo/log/<compare_set_id>.log`, UTF-8, 한 줄 = `<ISO 시각>\t<level>\t<file>\t<message>`.
레벨은 `INFO`/`WARN`/`ERROR`. 예:

```
2026-09-04T09:12:03.512000	WARN	A-101.dwg	zwcad failed, falling back to builtin: ZWCAD conversion failed: ...
2026-09-04T09:12:07.118000	INFO	A-101.dwg	re-converted with builtin to match the other side
2026-09-04T09:15:40.221000	WARN	A-050.dwg	bbox 최대 코너 편차 3.200mm > 1mm 허용
```

## 취소

`POST /jobs/{id}/cancel` → 파일 사이(세트 안에서, 그리고 같은-변환기 재변환 목록을 도는
사이)에 `job.cancel_requested`를 확인하고 `JobCancelled`를 던진다. 열려 있던 ZWCAD 인스턴스는
그 세트의 `_ingest_side`가 `finally`에서 닫는다.

## 결정론

파일 순서는 항상 이름 대소문자 무시 정렬 순, 세트 순서는 항상 전 → 후. 시각은 DB
`created_at`/`updated_at`과 로그 줄에만 쓴다. 같은 입력·같은 `compare.yaml`이면 같은 파일
목록·같은 변환기 선택·같은 `stats`가 나온다(단, 실제 ZWCAD/acad-ts 변환 자체의 바이트 동일성은
이 모듈의 책임이 아니다 — R1-06의 결정론 테스트가 다루는 비교 DXF·클러스터 단계와는 다른 층이다).
