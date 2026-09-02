# G0 질문 목록 (사용자 판정 필요)

에이전트가 작업 중 사용자 판정이 필요하다고 판단한 항목을 여기에 추가한다. 게이트 미팅에서 일괄 답변.

| # | 질문 | 제기 태스크 | 기본값(답변 전 적용) | 답변 |
|---|---|---|---|---|
| 1 | 앱 이름 | W0-01 | Halo CAD | halo-cad(가칭), 2026-09-02 사용자 확정 |
| 2 | Apple Developer ID(연 99달러) 가입 vs MDM 화이트리스트 | W0-01 | P1까지 ad-hoc 서명 + "확인 없이 열기" 안내 | 기본값: P1까지 ad-hoc 서명 |
| 3 | 한글 SHX 폰트(whgtxt.shx 등)를 사내 배포본에 동봉할 수 있는가(회사가 AutoCAD 라이선스 보유?) | W1-04 | 동봉하지 않음. Noto Sans KR(OFL) 기본 + 사용자가 자기 SHX 등록 | **사용자가 폰트를 직접 추가하는 기능**을 넣는다(2026-09-03). SHX 동봉은 하지 않고 Noto Sans KR 기본 + 폰트 추가 UI(W3-05) |
| 4 | DWG 변환기(GPL)를 포함한 빌드를 사외(협력업체·발주처)에 배포할 계획이 있는가 | W1-04 | 사내 전용. 사외 배포본은 acad-ts(MIT) 경로만 포함 | 기본값: 사내 전용 |
| 5 | `@mlightcad/libredwg-converter`의 라이선스 표기 불일치(package.json GPL-3.0 vs LICENSE 파일 MIT)를 상류에 이슈로 올릴지 | W1-04 | 엄격한 쪽(GPL)으로 취급, 격리 유지 | 기본값: GPL로 취급 |
| 6 | 천장고(CH)끼리의 등호 검사(층고표 CH vs 천장평면도 CH)를 허용할지 | W1-05 | 허용(같은 기준). 스키마 height_rules에 CH↔CH EQ 분기 추가 예정 | **천장평면도에 CH가 표기된 경우에만** CH끼리 등호 검사(2026-09-03). 스키마: CH↔CH EQ는 한쪽 source가 CEILING_PLAN일 때만 허용, 관측이 없으면 검사 생략 |
| 7 | DMS 스키마(리비전·체크아웃·승인·감사)를 `packages/schema/dms`에 둘지, 엔진 pydantic+OpenAPI에만 둘지 | W1-05 | `packages/schema/dms`(P2 W6-01에서 추가), 엔진은 코드젠 소비 | 기본값: packages/schema/dms |
| 8 | acad-ts 변환기 순위 | W2-05/W2-06 | — | **결정: mlightcad `dxfOut()` 1차, acad-ts 보조.** 한글은 W2-05가 우회했으나 acad-ts가 쓴 DXF를 ezdxf가 읽지 못하고 100만 엔티티에서 스택 오버플로. ADR-0002 개정 절 참조 |
| 9 | 실제 DWG 도면 3~5개 조기 제공 가능한지 — 현재 DWG 픽스처는 전부 acad-ts가 쓴 것이라 "DWG 읽기 품질"의 기준이 없다(같은 DWG를 acad-ts 200,005개, libredwg-web 85개로 읽음) | W2-06 | 합성 기준 결정 유지, 실제 파일 확보 시 `tools/bench-open.mjs`로 재보정 | **제공됨(2026-09-03)**: `samples/2026-09-02-실시도서/`(68 DWG, 실시도서 세트 + 골조샵, XREF 폴더 포함). W3-09에서 실측·재보정 |
| 10 | 네이티브 LibreDWG(`brew install libredwg`)를 워크스테이션에 설치할지(관리자 암호 필요) | W2-06 | 설치하지 않음. 3차 경로는 "사용자가 설치한 경우" | 기본값: 설치하지 않음 |
| 11 | `dxfOut()`의 그룹코드 누락 2건(INSERT 66, HATCH 92)을 상류 mlightcad에 이슈로 올릴지 | W2-06 | 우리 쪽 후처리로 먼저 고치고 재현 케이스를 상류에도 보고 | 기본값: 후처리 먼저, 상류 보고 |
