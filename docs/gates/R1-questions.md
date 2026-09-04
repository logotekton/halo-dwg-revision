# R1 게이트 질문 (사용자 답변 필요)

Fable이 실행 중 멈추지 않고 기본값으로 진행한 항목이다. 답이 오면 해당 태스크의 설정값·문서를 바꾼다.

| # | 질문 | 기본값(현재 진행) | 영향 |
|---|---|---|---|
| Q1 | ~~**GitHub 저장소.**~~ **해결(2026-09-04, 사용자 지시):** Fable이 `logotekton/halo-dwg-revision`(비공개)을 만들고 `origin`으로 잡아 `main`을 푸시했다. https://github.com/logotekton/halo-dwg-revision | 완료 | R1-00b 아티팩트, R1-11 게이트 |
| Q2 | ~~**ClickUp 태스크.**~~ **해결(2026-09-04):** 사용자가 토큰을 주어 `[Halo][halo-dwg-revision]` 태스크 `z8nrz7d503`을 만들고 `task-start`로 지정했다(상태 in progress, 마감 09-06 자동). 현재 스프린트(2026-W36) 미편입 — 사용자 지시에 따른 긴급 투입으로 코멘트 남김 | 완료 | 팀 규칙(스프린트 기록) |
| Q3 | **클라우드 마크·리비전 표 수치의 단위.** 장부의 "호 100mm, 여백 50mm, 삼각 200mm"를 **1:100 도곽 기준 모델 mm**로 해석하고 축척 배율(축척 분모/100)을 곱한다. 1:100 도면에서 삼각형 한 변이 종이 위 2mm가 되는 셈이라 작을 수 있다. Windows 확인 때 마크업 DWG를 열어 보고 값을 정해 달라(`.halo/compare.yaml`의 `cloud`·`revtable` 값만 바꾸면 된다). 사용자 답 "ok"(2026-09-04) — 기본값으로 진행, Windows 확인 때 재검토 | `compare.yaml` 기본값 그대로 | R1-06, R1-09 출력 모양 |
| Q4 | **앱 이름.** 설치본·창 제목이 아직 `Halo CAD`다. `Halo DWG Revision`(또는 한글 이름)으로 바꿀지. 바꾸면 productName·appId·창 제목·e2e 문자열이 함께 바뀐다 | `Halo CAD` 유지 | R1-05/R1-10/R1-11 |
| Q5 | **사용자 리비전 쌍.** `samples/revision-pairs/<이름>/{before,after}/` + `planted.md`(심은 변경 목록) 형식으로 D4 전에 넣어 달라. 없으면 합성 쌍으로만 개발·검증한다 | 합성 쌍만 | R1-11 `owner-pair` 게이트 |
| Q7 | **GitHub Actions 결제 차단(사용자만 해결 가능).** `logotekton` 조직의 모든 워크플로 잡이 시작 전에 실패한다: "The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings". 옛 저장소 `halo-cad`의 오늘 CI 4건도 같은 이유로 실패했다. 비공개 저장소의 Actions 분(minutes)은 유료이므로 조직 **Settings → Billing & plans**에서 결제 수단 갱신 또는 지출 한도(Actions spending limit) 상향이 필요하다. 해결 전에는 Windows 설치본 아티팩트(R1-00b)와 `installer` 게이트를 만들 수 없다(macOS에서는 NSIS·PyInstaller x64 교차 빌드 불가) | 워크플로는 준비됨(`.github/workflows/windows-installer.yml`). 결제 해결 후 `main` 또는 `task/**` 푸시(또는 Actions 탭 Run workflow)로 즉시 생성 | R1-00b 아티팩트, R1-11 `installer`·`sheet-count`·`owner-pair`·`markup-dwg-opens` 게이트 전부 |
| Q6 | **ZWCAD SaveAs 버전 상수.** ZWCAD COM의 `ZcSaveAsType` 값이 AutoCAD와 같다는 전제(2013 DXF = 61)로 코딩했다. Windows에서 `halo-engine.exe zwcad-convert` 5장 결과로 확인해 달라 | 61/60 | R1-02, R1-03, R1-09 |
