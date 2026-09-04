# 뷰어 폰트 (자리표시자)

`docs/contracts/wave-3.md` "뷰어 자산 배치": W3-05 이전까지 이 매니페스트는
**Noto Sans KR 1종**만 선언한다. 폰트 파일 자체(`NotoSansKR-Regular.woff`)는
저장소에 없다 — OFL 배포물을 커밋하지 않고, 사용자가 폰트를 추가하는 UI가
W3-05의 범위이기 때문이다(G0 사용자 판정: "SHX 동봉 없음, 폰트 추가 UI").

파일이 없는 동안의 동작(실측):

- `FontManager`가 매니페스트는 읽고 파일 요청에서 실패한다 → 전역 이벤트
  `fonts-not-found`가 뜨고 `CadHost`가 `fontMissing` 이벤트와
  `viewer.warning.fontsMissing` 경고로 올린다.
- 렌더 자체는 계속된다. SHX 빅폰트가 지정된 TEXT/ATTRIB는 글리프가 없어
  비어 보이고, 도형·치수선·해치는 정상이다.

W3-05가 이 디렉터리에 실제 폰트와 SHX 매핑표를 채운다.
