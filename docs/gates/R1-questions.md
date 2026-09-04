# R1 게이트 질문 (사용자 답변 필요)

Fable이 실행 중 멈추지 않고 기본값으로 진행한 항목이다. 답이 오면 해당 태스크의 설정값·문서를 바꾼다.

| # | 질문 | 기본값(현재 진행) | 영향 |
|---|---|---|---|
| Q1 | **GitHub 저장소.** `logotekton/halo-dwg-revision`(비공개)를 만들어 `origin`으로 잡아도 되는가? 아니면 사용자가 만들고 알려줄 것인가. 이 저장소는 아직 `halo-cad-local` 원격뿐이라 Windows 설치본 CI(R1-00b)가 돌 수 없다 | Fable은 만들지 않고 워크플로 파일만 준비. 저장소가 생기면 `git remote add origin ... && git push -u origin main task/*` | R1-00b 아티팩트, R1-11 게이트 |
| Q2 | **ClickUp 태스크.** 이 세션 셸에는 `CLICKUP_API_TOKEN`이 없어 `[Halo][halo-dwg-revision]` 태스크를 만들거나 `/team-harness:task-start`로 지정할 수 없다. 사용자가 태스크를 만들고 ID를 알려주면 지정한다 | 미지정 상태로 진행 | 팀 규칙(스프린트 기록) |
| Q3 | **클라우드 마크·리비전 표 수치의 단위.** 장부의 "호 100mm, 여백 50mm, 삼각 200mm"를 **1:100 도곽 기준 모델 mm**로 해석하고 축척 배율(축척 분모/100)을 곱한다. 1:100 도면에서 삼각형 한 변이 종이 위 2mm가 되는 셈이라 작을 수 있다. Windows 확인 때 마크업 DWG를 열어 보고 값을 정해 달라(`.halo/compare.yaml`의 `cloud`·`revtable` 값만 바꾸면 된다) | `compare.yaml` 기본값 그대로 | R1-06, R1-09 출력 모양 |
| Q4 | **앱 이름.** 설치본·창 제목이 아직 `Halo CAD`다. `Halo DWG Revision`(또는 한글 이름)으로 바꿀지. 바꾸면 productName·appId·창 제목·e2e 문자열이 함께 바뀐다 | `Halo CAD` 유지 | R1-05/R1-10/R1-11 |
| Q5 | **사용자 리비전 쌍.** `samples/revision-pairs/<이름>/{before,after}/` + `planted.md`(심은 변경 목록) 형식으로 D4 전에 넣어 달라. 없으면 합성 쌍으로만 개발·검증한다 | 합성 쌍만 | R1-11 `owner-pair` 게이트 |
| Q6 | **ZWCAD SaveAs 버전 상수.** ZWCAD COM의 `ZcSaveAsType` 값이 AutoCAD와 같다는 전제(2013 DXF = 61)로 코딩했다. Windows에서 `halo-engine.exe zwcad-convert` 5장 결과로 확인해 달라 | 61/60 | R1-02, R1-03, R1-09 |
