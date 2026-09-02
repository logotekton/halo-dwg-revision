# G0 질문 목록 (사용자 판정 필요)

에이전트가 작업 중 사용자 판정이 필요하다고 판단한 항목을 여기에 추가한다. 게이트 미팅에서 일괄 답변.

| # | 질문 | 제기 태스크 | 기본값(답변 전 적용) | 답변 |
|---|---|---|---|---|
| 1 | 앱 이름 | W0-01 | Halo CAD | halo-cad(가칭), 2026-09-02 사용자 확정 |
| 2 | Apple Developer ID(연 99달러) 가입 vs MDM 화이트리스트 | W0-01 | P1까지 ad-hoc 서명 + "확인 없이 열기" 안내 | |
| 3 | 한글 SHX 폰트(whgtxt.shx 등)를 사내 배포본에 동봉할 수 있는가(회사가 AutoCAD 라이선스 보유?) | W1-04 | 동봉하지 않음. Noto Sans KR(OFL) 기본 + 사용자가 자기 SHX 등록 | |
| 4 | DWG 변환기(GPL)를 포함한 빌드를 사외(협력업체·발주처)에 배포할 계획이 있는가 | W1-04 | 사내 전용. 사외 배포본은 acad-ts(MIT) 경로만 포함 | |
| 5 | `@mlightcad/libredwg-converter`의 라이선스 표기 불일치(package.json GPL-3.0 vs LICENSE 파일 MIT)를 상류에 이슈로 올릴지 | W1-04 | 엄격한 쪽(GPL)으로 취급, 격리 유지 | |
| 6 | 천장고(CH)끼리의 등호 검사(층고표 CH vs 천장평면도 CH)를 허용할지 | W1-05 | 허용(같은 기준). 스키마 height_rules에 CH↔CH EQ 분기 추가 예정 | |
| 7 | DMS 스키마(리비전·체크아웃·승인·감사)를 `packages/schema/dms`에 둘지, 엔진 pydantic+OpenAPI에만 둘지 | W1-05 | `packages/schema/dms`(P2 W6-01에서 추가), 엔진은 코드젠 소비 | |
