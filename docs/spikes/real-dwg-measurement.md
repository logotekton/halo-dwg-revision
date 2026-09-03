# W3-09 실제 실시도서 세트 실측과 재보정

작성 2026-09-03 · 브랜치 `task/W3-09` · 대상 `samples/2026-09-02-실시도서/`(gitignore, 읽기 전용)
표·원자료 `docs/samples/inventory-2026-09-03.md`, `tools/bench/results-real-2026-09-03.json`
재현
```bash
node tools/bench-open.mjs --dir "samples/2026-09-02-실시도서" \
     --paths acad,acadconv,dxfout,engine --run-browser --timeout 300 --summary
node spikes/mlightcad/scripts/render-real.mjs --manifest samples/_reports/manifest.json --all \
     --out-dir samples/_reports/render --settle 6000 --no-screenshot     # (spikes/mlightcad에서)
node tools/bench/report-real.mjs && node tools/bench/make-labels.mjs
```

> 이 문서에는 도면 내용이 없다. 집계 수치, 파일명, 폰트명, 레이어명 통계, 해시만 적는다(브리프).

## 0. 요약 — 실측이 P0 결정을 바꾸는가

| P0 결정 | 판정 | 근거 한 줄 |
|---|---|---|
| **기본 변환기 = mlightcad `dxfOut()`** | **조건부 유지** (후처리 5건을 선행 조건으로 승격) | 파싱은 acad-ts와 동률(68/68, 엔티티 59/68 완전 일치)이지만, 산출 DXF를 엔진이 읽는 비율이 **26/68**이고 XREF 경로·TTF 폰트명을 **전량 잃는다**. 후처리 없이는 실서비스 불가 |
| **티어 A ≤ 25만 / B ≤ 80만 (엔티티 수)** | **변경** | 실제 68장 중 25만을 넘는 것은 1장뿐인데 **뷰어는 8장에서 죽는다.** 죽는 기준은 최상위 엔티티가 아니라 **블록 전개 포함 렌더 부하**이고 상한은 약 **5만**이다(25만의 1/5) |
| **교차검증 화이트리스트(W01~W09)** | **유지 + 4건 추가 제안** | 실세트 26장 교차검증에서 RED 73건 중 44건이 `dxfOut()`의 알려진 그룹코드 2건에서 나온다. 남는 것은 IMAGE bbox·`_recover` 중복 등 새 유형 |
| **폰트 정책(SHX 실패 시 Noto 매핑을 P0 승격)** | **변경 — 즉시 발동** | 스타일 838개가 쓰는 TTF typeface **33종 전부**와 SHX/폰트 파일 **19종**이 mlightcad 기본 폰트 세트에 **누락**이다. 실제 표지 도면 렌더에서 한글은 ⟨ST⟩ 자리표시자나 흰 사각형으로만 나온다 |

추가로 P0에 없던 사실 세 가지:

1. **68장 전부 모델공간 단독이다.** 레이아웃(페이퍼공간)을 쓰는 도면이 0장이고, 한 DWG 안에 도곽(표제란 INSERT)이 여러 개 놓인다. 표제란 INSERT 수 합계가 공종별 PDF 페이지 수와 **정확히 일치**한다(전기 104=104, 기계 51=51, 통신 28=28, 소방기계 45=45, 소방전기 28=28, 건축 101−2(`_recover` 중복)=99). → 시트 단위는 레이아웃이 아니라 **도곽**이다.
2. **XREF 경로는 전부 `..\XR\...` 형식의 윈도 상대경로**이고, 엔진 `resolve_xref_path`는 POSIX에서 백슬래시를 구분자로 보지 않아 **133건 중 0건**을 해석한다.
3. **macOS 파일명은 NFD, DXF 안의 경로 문자열은 NFC**다. 정규화 없이는 한글 XREF 대상 3종이 "없는 파일"로 보인다.

## 1. 측정 대상과 방법

| 항목 | 값 |
|---|---|
| 도면 | 68장 (`.dwg`/`.DWG`, `.bak` 제외), 합계 101.71 MB, 최대 19.83 MB |
| 버전 | AC1024 66 · AC1027 1 · AC1032 1 |
| `$DWGCODEPAGE` | `kcs5601` 68/68 (AC1024는 UTF-8 세대지만 헤더 코드페이지는 전부 cp949로 남아 있다) |
| 최상위 엔티티 합 | 895,995 · 블록 정의 안 엔티티 합 842,150 · 텍스트(`text_count`) 56,000 |
| 공간 | `MODEL` 68/68, `PAPER:*` 0 |
| 표제란 INSERT(`TITLE BLOCK-V`) | 375개 |

경로 세 가지(브리프 (a)(b)(c)):

| 키 | 내용 | 구현 |
|---|---|---|
| `acad` | (a) acad-ts가 **DWG를 직접** 읽어 `info` + `stats` | `packages/acad-bridge` |
| `dxfout` | (b) 헤드리스 Chromium에서 libredwg-web WASM 파싱 → `AcDbDatabase.dxfOut()` | `spikes/mlightcad/scripts/bench-real.mjs` |
| `engine` | (c) 그 산출 DXF를 `halo-engine stats`(ezdxf)로 읽기 + 그룹코드 스캔 | `tools/bench-open.mjs --dir`, `tools/bench/scan-dxf.mjs` |
| `acadconv` | (추가) acad-ts `dwg2dxf` 산출 DXF에 대해 같은 두 가지. **폰트·XREF의 기준값**이 여기서 나온다 | 같음 |

`--dir` 모드는 파일 하나마다 결과를 `samples/_reports/cells.json`에 적재하므로 중단 후 재개된다(3분 명령 제한 대응). 도면은 **id**(`S001`…)로만 URL·싱크 파일명에 등장한다 — 실제 이름에 공백·`#`·한글이 있고 원본 폴더는 읽기 전용이기 때문이다.

## 2. 파서 판별 — P0의 "85 vs 200,005"에 대한 답

**libredwg-web은 조용히 잘라 읽지 않았다.** 실제 AutoCAD가 쓴 DWG 68장에서 libredwg-web은 68장 전부를 열었고, acad-ts와 `entity_count`가 **59/68에서 완전히 일치**했다. 남은 9장의 격차도 전부 특정 타입 몇 개다.

| 타입 | 합계 격차(libredwg − acad-ts) | 성격 |
|---|---:|---|
| `SPLINE` | −396 | libredwg가 일부 스플라인을 내지 않는다(9장 중 5장) |
| `REGION` | −78 | ACIS 솔리드. libredwg-web 빌드에 ACIS 디코더가 없다 |
| `ARCALIGNEDTEXT` | −8 | Express Tools 커스텀 객체(프록시) |
| `INSERT` | −1 | 1장에서 1건 |

→ **W2-06 §4.4의 "20만 중 85개"는 libredwg의 결함이 아니라 acad-ts가 쓴 DWG의 결함이었다.** P0의 픽스처 DWG가 전부 acad-ts 산출물이었다는 §4.3의 유보가 옳았고, 제3자 DWG에서는 두 리더가 사실상 같은 것을 본다. 다만 결론 하나는 그대로 유지된다: **`lastOpenError === null`은 성공의 증거가 아니다** — 이번 세트에서도 `.DWG`를 확장자 없이 열었더니 libredwg가 DXF 리더로 넘어가 **엔티티 0개 + 오류 null**을 돌려줬다(하네스 버그로 발견, `bench-real.mjs`의 URL 확장자 주석 참조).

교차검증 게이트(ADR-0002 개정 §4)는 그대로 필요하다. 근거가 "조용한 절단"에서 "조용한 타입 누락"으로 바뀔 뿐이다.

## 3. 변환기 충실도 — 두 산출 DXF 모두 지금은 엔진에 못 먹인다

| 항목 | acad-ts `dwg2dxf` | libredwg + `dxfOut()` |
|---|---:|---:|
| 68장 변환 성공 | 68 | 68 |
| **엔진(ezdxf `stats`)이 산출 DXF를 읽음** | **23 / 68** | **26 / 68** |
| 실패 사유 | `AttributeError: 'Attrib' object has no attribute 'dxf'` 31건, `… 'doc'` 14건 | `DXFTableEntryError: 0` 41건, `ZeroDivisionError: Not a line.` 1건 |
| INSERT 그룹 `66` 보존 | 2,181 / 110,673 | **0 / 110,675** |
| HATCH 경계 External 비트 | 20,591 / 21,674 | **5,505 / 21,680** |
| STYLE 빅폰트를 `0`으로 기록 | 0 | **811 / 838** |
| STYLE XDATA typeface(실제 TTF 이름) 보존 | 705 | **0** |
| XREF 경로 문자열 보존 | 133 / 133 | **0 / 133** |
| 산출 DXF 크기(>2 MB 도면 중앙값) | 693 B/엔티티 | 522 B/엔티티 |

### 3.1 `dxfOut()`의 새 결함 — "풀지 못한 이름 참조를 `0`으로 쓴다"

W2-06이 찾은 두 가지(INSERT `66`, HATCH `92` External) 외에 **같은 뿌리의 결함 세 가지**를 실제 도면에서 처음 봤다.

1. **LEADER의 `dimstyle`(그룹 3)을 `0`으로 쓴다.** `halo-engine stats`가 LEADER의 bbox를 구하며
   `doc.dimstyles.get("0")`을 호출해 `DXFTableEntryError: 0`으로 죽는다. **41/68의 단일 원인이다.**
   (S023 실측: DIMENSION 57건은 `KUMKANG-1B`로 정상, LEADER 60건 전부 `0`.)
2. **STYLE의 빅폰트(그룹 4)를 빈 문자열이 아니라 `0`으로 쓴다**(838개 중 811개).
3. **STYLE의 폰트 파일(그룹 3)이 비어 있으면 스타일 이름을 대신 써 넣고**, XDATA `ACAD` 1000(TrueType typeface)은 아예 쓰지 않는다.
   예: acad-ts `{name:"HY견고딕", font:"", typeface:"HY각헤드라인M"}` → dxfOut `{name:"HY견고딕", font:"HY견고딕", typeface:""}`.
   `.TTF`/`.ttf` 확장자도 떨어진다(`H2GTRE.TTF` → `H2GTRE`).

여기에 **핸들 중복**이 더해진다. `S023.dxf`를 ezdxf로 열면 `Found non-unique entity handle #A, #1E, #22, #26`이 나온다 — P0에서 acad-ts의 결함으로 기록했던 것과 같은 종류이고, ADR-0002 §2의 `(file_id, handle)` 공통 키를 깨뜨린다.

### 3.2 acad-ts의 결함은 P0와 동일하고, 실세트에서 더 자주 걸린다

`AttributeError: 'Attrib' object has no attribute 'dxf'/'doc'` 45/68 — W2-06 §4.1의 ATTRIB 서브클래스 마커·태그 누락 그대로다. 실세트에서는 표제란 ATTRIB이 거의 모든 도면에 있으므로 P0(픽스처 4/10)보다 **적중률이 높다**.

### 3.3 그래서 어느 쪽인가

| 기준 | acad-ts | `dxfOut()` |
|---|---|---|
| 고쳐야 하는 결함 수 | 1종(ATTRIB 직렬화) | 5종(66, 92, LEADER dimstyle, STYLE 폰트/빅폰트, 핸들) |
| 그 결함이 **우리 코드로** 고쳐지는가 | 아니오 — 상류 acad-ts 라이터 내부 | **예** — 산출 DXF 후처리로 전부 가능 |
| 잃은 데이터가 파일 안에 남아 있는가 | 아니오(ATTRIB 태그가 애초에 없음) | 66·92·dimstyle은 **복원 가능**, **XREF 경로와 TTF typeface는 남아 있지 않다** |
| 폰트·XREF 원본 정보 | **보존** | **소실** |
| Node(utilityProcess)에서 DWG 읽기 | 가능 | 불가(`Worker` 필요 → 숨김 BrowserWindow) |

**결정: 기본 변환기는 `dxfOut()`으로 유지하되, 아래 두 가지를 P1 착수 조건으로 승격한다.**

- **(A) 후처리 3건 추가**(W3-02 착수 항목에 66·92와 함께): LEADER `dimstyle` 복원, STYLE 빅폰트 `0` → 빈 문자열, 핸들 유일성 재부여(또는 검증 실패 처리).
- **(B) 폰트·XREF 메타데이터는 `dxfOut()` 경로에서 얻지 않는다.** 두 값은 `dxfOut()`이 구조적으로 잃으므로, 임포트 시 **acad-ts `info`(같은 DWG를 두 번째 파서로 한 번 더 읽는 값싼 패스)에서 STYLE 테이블과 XREF 경로를 따로 뽑아** 정본 DXF에 주입하거나 사이드카에 기록한다. 이미 ADR-0002 §6이 acad-ts를 제3파서로 돌리고 있으므로 새 의존성은 없다.

(B)를 하지 않으면 ADR-0002의 "XREF 임베드"와 W3-05의 폰트 매핑이 **원리적으로 불가능**하다 — 참조 경로도, 실제 폰트 이름도 정본 안에 없기 때문이다.

## 4. 폰트 — 누락 목록 (W3-05 입력)

acad-ts 산출 DXF의 STYLE 테이블 838개 레코드 전수 집계다(그룹 3 = 폰트 파일, 그룹 4 = 빅폰트, XDATA `ACAD` 1000 = TrueType typeface). 전체 표는 `docs/samples/inventory-2026-09-03.md` §4.

### 4.1 mlightcad 기본 폰트 세트에 **누락**된 SHX·폰트 파일 (19종)

| 폰트 파일 | 스타일 수 | 성격 |
|---|---:|---|
| `malgun.ttf` / `malgunbd.ttf` / `malgunsl.ttf` | 165 / 2 / 1 | 맑은 고딕(Windows 번들) |
| `H2GTRE.TTF` / `H2GTRM.TTF` / `H2HDRM.TTF` / `HYWULM.TTF` | 50 / 10 / 2 / 1 | 한양 폰트 |
| `gulim.ttc` | 19 | 굴림 |
| `arialbd.ttf` / `ariblk.ttf` / `isocpeur.ttf` / `Yu Gothic.ttf` / `MoeumT R.ttf` | 1 / 1 / 2 / 1 / 1 | 라틴·일문 TTF (`arial.ttf` 11건은 cad-data에 mesh로 있어 제외) |
| `kscals.shx` | 2 | 한국 SHX |
| `ghs.shx` / `GHS.shx` / `ghs` | 4 | 한국 SHX(빅폰트) |
| `C:\xicad\arcbig03.shx` | 5 | **절대경로가 그대로 박힌** 사내 빅폰트 |
| `ENGINEERING.shx` | 2 | 사내 SHX |

`romans.shx`는 5건이 `C:\program files\autodesk\autocad 2013\fonts\romans.shx` 같은 **절대경로**로 적혀 있다 — 폰트 이름 정규화는 경로를 떼고 확장자·대소문자를 무시해야 한다.

cad-data가 가진 한글 SHX는 `whgtxt` / `whgdtxt` **둘뿐**이고, 이 세트에서 실제로 쓰이는 빅폰트는 `whgtxt.shx`(16) 외에 `arcbig03`(5)·`ghs`(4)다.

### 4.2 **누락**된 TrueType typeface (33종, 스타일 705개 중 대부분)

`Dotum`(206) · `Malgun Gothic`(141) · `HY각헤드라인M`(45) · `HYGothic-Extra`(42) · `DotumChe`(38) · `Rix모던고딕 M`(32) · `맑은 고딕`(24) · `Rix모던고딕 L`(23) · `돋움`(23) · `Gulim`(22) · `HYGothic-Medium`(12) · `GulimChe`(12) · `HY울릉도M`(12) · `08서울남산체 M`(11) · `HY울릉도L`(10) · `HY견고딕`(8) · `나눔스퀘어_ac`(6) · `Expo M`(4) · `HCR Dotum`(3) · `HYHeadLine-Medium`(3) · `08SeoulNamsan M`(3) · 그 밖 12종.
cad-data의 mesh 폰트 11종에는 이 중 **하나도 없다**(`Arial`만 이름이 겹친다).

같은 서체가 **한글 이름과 로마자 이름 양쪽**으로 등장한다(`돋움`/`Dotum`, `맑은 고딕`/`Malgun Gothic`, `견고딕`/`HY견고딕`, `08서울남산체 M`/`08SeoulNamsan M`). 매핑 테이블은 **양쪽 표기와 대소문자·공백을 정규화**해서 받아야 한다.

### 4.3 렌더에서 실제로 어떻게 보이는가

`A-000 표지`(TEXT 6개 중 한글 4개)를 뷰어에서 열어 확인했다(`samples/_reports/render/S004.*.png`, 커밋하지 않음).

| 폰트 세트 | 결과 |
|---|---|
| 폰트 없음(기본 상태) | 한글·영문 모두 **흰 사각형** 덩어리로만 그려진다 |
| cad-data 기본 8종 + AppleGothic 매핑 | 영문·숫자(`2025.08.`)는 **정상**, 한글은 **⟨ST⟩ 자리표시자 글리프** 또는 흰 사각형 |

**콘솔 경고는 0건이었다.** 즉 폰트가 없어도 뷰어는 조용히 잘못 그린다 — 폰트 해석 실패를 **UI로 올리는 것**이 W3-05의 필수 요건이다.

## 5. XREF

- XREF 블록 **133건**, 대상 파일 **8종**(`TITLE BLOCK-V.dwg`, `PLAN.dwg`, `xr_section.dwg`, `xr_elevation.dwg`, `xr_keymap.dwg`, `단위세대_평면.dwg`, `현황도_김화중공업고등학교.dwg`, `모듈 코드번호.dwg`). NFC 정규화 후 **8종 전부 세트 안에서 해석 가능**하다.
- 저장 경로 형태는 **133건 전부 `..\XR\<이름>.dwg`**(윈도 상대경로). 절대경로·파일명 단독은 0건이다.
- **엔진은 이 중 0건을 해석한다.** `halo_engine/ingest/xref.py::resolve_xref_path`가 `Path("..\\XR\\TITLE BLOCK-V.dwg")`를 만드는데, POSIX의 `Path`는 백슬래시를 구분자로 보지 않아 `.name`이 문자열 전체가 되고 5단계 탐색이 모두 빗나간다. 실측:
  ```
  FileNotFoundError: xref '..\XR\TITLE BLOCK-V.dwg' (block 'TITLE BLOCK-V') not found
  ```
- 경로를 POSIX로 바꿔 넣으면 해석 단계는 통과하고, 다음 단계에서 **XREF 대상이 `.dwg`라서** 또 막힌다(엔진은 DXF만 읽는다). 즉 정본 생성은 **호스트 1개가 아니라 XREF 그래프 전체를 변환**해야 한다. 이 세트에서는 호스트 55장 + XREF 대상 13장이 사실상 한 덩어리다.
- `dxfOut()` 산출 DXF는 경로가 **빈 문자열**이라 더 나쁘게 실패한다: 빈 경로가 `host_dir / ""` = 호스트 디렉터리로 "존재"해서 리졸버가 **디렉터리를 반환**하고 `IsADirectoryError`가 난다.

**제안(엔진 소관, 패치 문안은 §11):** (a) 경로 문자열의 `\`를 `/`로 정규화한 뒤 `PurePosixPath`로 다루기, (b) 비교 시 양쪽을 NFC로 정규화, (c) 빈 경로는 즉시 "해석 불가"로 처리, (d) 대상이 DWG면 변환 파이프라인으로 되돌리기.

## 6. 한글·코드페이지

| 항목 | 값 |
|---|---|
| `$DWGCODEPAGE` | 68장 전부 `kcs5601` (AC1024/AC1027/AC1032 구분 없이) |
| 한글 포함 문자열 | acad-ts 경로 20,435 · `dxfOut()` 경로 20,422 |
| 모지바케 의심 문자열 | **양쪽 0건** |
| `text_count` 일치 | 양쪽 stats가 모두 성공한 26장 중 **22장** |
| `text_hash` 일치 | 같은 26장 중 **22장** |

**한글 디코딩 자체는 두 경로 모두 정확하다.** 어긋난 4장은 전부 `dxfOut()`의 INSERT `66` 누락 때문이다 — ATTRIB이 INSERT에 붙지 않아 `text_count`에서 빠지고 고아 SEQEND가 최상위로 올라온다.

| id | 파일 | acad-ts text | ezdxf text | 여분 SEQEND |
|---|---|---:|---:|---:|
| S035 | A-700 창호위치안내도.DWG | 1,335 | 173 | 581 |
| S049 | XR/xr_elevation.dwg | 44 | 16 | 28 |
| S061 | 골조샵 XR/xr_elevation.dwg | 80 | 52 | 28 |
| S003 | #강판제작도_251028.dwg | 38 | 34 | 4 |

S035 한 장에서만 **창호 기호 1,162개**가 사라진다. 창호 물량의 근거가 되는 값이므로 `66` 후처리는 미관 문제가 아니라 **물량 정확도 문제**다.

## 7. 티어 재보정

### 7.1 크기 → 엔티티 수 추정 계수 (1단 게이트)

| 형식 | 중앙값 B/엔티티(전체 68장) | 중앙값(>2 MB, 10장) | 최소 |
|---|---:|---:|---:|
| 원본 DWG (AutoCAD 작성) | 827 | **115** | 58 |
| `dxfOut()` 산출 DXF | 950 | 522 | 257 |
| acad-ts `dwg2dxf` 산출 DXF | 1,470 | 693 | 409 |

W2-06의 **DWG 26 B/엔티티는 실제 DWG에서 성립하지 않는다.** 그 값은 acad-ts가 쓴 DWG(테이블·썸네일·프록시 없음)의 것이고, AutoCAD가 쓴 실제 DWG는 **58~115 B/엔티티**다. 작은 도면은 로고 JPEG·표제란·테이블 같은 고정비가 크기를 지배해서 중앙값이 827까지 올라간다.

→ **1단 추정 계수를 DWG 60 B/엔티티로 바꾼다**(보수적으로 엔티티 수를 과대 추정하는 쪽). DXF는 실측 522~693이 W2-06의 207~242보다 크므로 **500 B/엔티티**로 올린다. 1단은 "경고를 띄울지" 결정하는 값일 뿐이고 정확한 판정은 2단(`entity_count`)이므로 과대 추정이 안전한 방향이다.

### 7.2 진짜 상한은 엔티티 수가 아니라 **렌더 부하**다

뷰어 렌더를 68장 전부에 대해 돌렸다(`AcApDocManager.openDocument`, 헤드리스 Chromium + SwiftShader, 1600×1100, 6초 대기).

| 결과 | 수 |
|---|---:|
| 정상 렌더 | **60 / 68** |
| 렌더러 프로세스 crash | **8 / 68** |

crash한 8장의 **최상위 엔티티 수는 456 ~ 348,076**으로 전혀 예측력이 없다. 예측하는 값은 **최상위 엔티티 + 블록 정의 안 엔티티**(= 렌더 시 전개되는 지오메트리 양)다.

| | 최소 | 최대 |
|---|---:|---:|
| 정상 렌더한 60장의 부하 | 19 | **61,561** (S059 `PLAN.dwg`) |
| crash한 8장의 부하 | **45,064** (S054, 최상위 7,390) | 473,156 |

- `S055 250813-모듈안내도.dwg`는 **최상위 456개**인데 블록 정의 안에 63,980개가 있어 crash한다. 25만 티어 경계로는 절대 잡히지 않는다.
- 반대로 `S059`는 부하 61,561로 통과한다. 경계는 대략 **4.5만~6만 사이**다.

**제안 — ADR-0002 개정 §5의 티어 게이트를 다음으로 바꾼다.**

| 티어 | 게이트 | 비고 |
|---|---|---|
| **A. 전체 편집** | `render_load` ≤ **50,000** | `render_load = 최상위 엔티티 + Σ(INSERT가 참조하는 블록 정의 엔티티)`. 정본 생성 시 한 번 계산해 `<sha>.stats.json`에 넣는다 |
| **B. 라이트 DXF** | 50,000 < `render_load` ≤ **250,000** | 뷰어에는 도곽 1장 단위 서브셋. 이 세트에서는 설비 도서 6장이 여기 |
| **C. 엔진 전용** | `render_load` > 250,000 또는 `entity_count` > 800,000 | S042(부하 473,156)가 유일 |

**중요한 단서:** 이 수치는 **SwiftShader 소프트웨어 GL의 헤드리스 Chromium**에서 나왔다. 실제 Electron 앱은 GPU를 쓰므로 상한이 더 높을 수 있다. **W3-02가 패키징된 앱에서 같은 68장을 다시 돌려 경계를 확정해야 한다.** 다만 방향은 바뀌지 않는다 — 게이트 변수는 `entity_count`가 아니라 블록 전개를 포함한 부하다.

### 7.3 지금 티어 분포

`entity_count` 기준으로는 A 67 / B 1 / C 0, `render_load` 기준으로는 A 60 / B 7 / C 1이다. **실무 세트의 8분의 1이 뷰어 전체 편집 대상이 아니다.**

## 8. 렌더 충실도 소견 (대표 4장)

PDF 페이지 번호는 표제란 INSERT 수의 누적합으로 계산했고(§0-1), `A-810`의 첫 장이 `00_건축.pdf` 86쪽 `A-811 천장 평면도-1(지하1층, 지상1층)`임을 렌더로 확인했다. 산출물은 `samples/_reports/render/`(gitignore).

| 도면 | 뷰어 | PDF 대조 | 소견 |
|---|---|---|---|
| `A-810 천장 평면도`(S038, 부하 31,997) | ok, 8.9 s | `00_건축.pdf` 86–88쪽 | 도곽·그리드·벽체·천장 해치·색상·선종류 모두 재현. **텍스트만 없다**(전체보기 축척에서 글리프가 서브픽셀). 해치 패턴 밀도가 PDF보다 촘촘해 보이는데 축척 차이인지 패턴 스케일 오차인지 이 축척에서는 판정 불가 |
| `A-620 화장실 전개도`(S034, 부하 11,335) | ok, 10.2 s | `00_건축.pdf` 66–70쪽 | 전개면 윤곽·치수선 재현. 치수 **문자**는 위와 같은 이유로 미판정 |
| `03_전기 전기도서`(S042, 348,076 엔티티) | **crash** | `03_전기.pdf` 1–104쪽 | 뷰어가 열지 못한다. `dxfOut()`은 116.7 MB DXF를 15초에 만들지만 엔진이 `ZeroDivisionError`로 못 읽는다 → 현재 이 도면은 **어떤 경로로도 물량에 들어오지 못한다** |
| `#골조샵/250711-목업골조제작도`(S054, 최상위 7,390) | **crash** | 대응 PDF 없음(`01_구조_PDF.pdf` 31쪽은 골조샵 12도곽과 매칭되지 않음) → **미대조** | 최상위 7,390개짜리 작은 도면이 죽는다. 원인은 블록 정의 37,674개(무명 치수 블록 1,246개 포함)로 보인다 |

추가로 두 가지가 눈에 띈다.

1. **`zoomToFitDrawing`이 도면을 담지 못한다.** `xr_keymap`(S050, 최상위 11개·부하 235)에서 도곽이 화면 오른쪽으로 잘려 나간다. 실제 도면에서 재현되는 UX 결함이므로 W3-02 착수 항목.
2. **폰트 실패가 조용하다.** §4.3.

## 9. 교차검증 — 화이트리스트 제안

양쪽 stats가 성공한 26장에 대해 `halo-engine crosscheck --allow-sha-mismatch`를 돌렸다(기준: acad-ts가 DWG를 직접 읽은 stats, 상대: ezdxf가 `dxfOut()` DXF를 읽은 stats). 버킷 525개.

| 판정 | 수 |
|---|---:|
| GREEN | 301 |
| AMBER | 151 (**전부** 기존 `W05-acad-derived-bbox`) |
| RED | 73 |

RED 73건의 필드별 내역: `hatch_area_sum_mm2` 40 · `bbox` 23 · `bucket`(한쪽에만 있는 레이어) 5 · `count_by_type` 4 · `length_sum_mm` 2.

**44건(60%)이 `dxfOut()`의 알려진 그룹코드 2건에서 직접 나온다**(해치 부호 40 + SEQEND/ATTRIB 카운트 4). §3.3(A)의 후처리를 넣으면 RED는 73 → 29로 떨어진다. 남는 29건에 대해 아래 4건을 제안한다.

| 제안 id | 필드 | 사유 | 판정 |
|---|---|---|---|
| `W10-image-bbox` | `bbox` | IMAGE/OLE2FRAME 엔티티의 extents를 acad-ts는 삽입점 기준, ezdxf는 픽셀 크기 기준으로 계산해 수백 mm 차이가 난다(표지·로고 레이어 4건). 지오메트리가 아니라 래스터 프레임이라 물량 근거가 아니다 | AMBER |
| `W11-region-acis` | `count_by_type` | `REGION`(ACIS)을 libredwg-web 빌드가 내지 않는다(78건). 뷰어에 없고 엔진에 있는 타입 | **RED 유지** — 카운트 격차는 낮추지 않는다는 계약(`stats-definition.md`)대로, 다만 사유를 등록해 원인 표시 |
| `W12-proxy-arcaligned` | `count_by_type` | `ARCALIGNEDTEXT` 등 Express Tools 프록시 8건. 위와 같음 | **RED 유지 + 사유 등록** |
| `W13-spline-libredwg` | `count_by_type`·`length_sum_mm` | libredwg-web이 일부 SPLINE을 내지 않는다(396건). 길이 합에도 직접 영향 | **RED 유지 + 사유 등록**. 상류 이슈 후보 |

즉 **화이트리스트로 낮출 수 있는 새 항목은 `W10`뿐**이고 나머지 셋은 "원인이 밝혀진 RED"로 기록만 한다. 계약의 "카운트 격차는 절대 낮출 수 없다"를 그대로 지킨다.

## 10. 골든셋 후보 (P4 입력)

브리프대로 **시트명과 헤더 행만** 기록한다. 수치는 커밋하지 않는다.

| 파일 | 시트명 | 헤더 행 |
|---|---|---|
| `#골조샵/250709-…(골조 수량산출서).xlsx` (76 KB) | `1. 수량산출서(모듈러 골조)` | `층 / 규격 / 타입 / Q'TY / <부재별 열 그룹>`, 부재 그룹마다 `길이 / 수량 / 도장면적 / 총 수량 / 총 중량`, 상단에 `단중`·`온둘레` 상수 행 |
| `#골조샵/250731-…(골조 수량산출서).xlsx` (76 KB) | 같음 | 같음(부재 구성만 `데크평철 PL 150*9` 등으로 개정) |
| `01_건축/#강판 수량표_251028.xlsx` (296 KB) | `김화공고 모듈러 생활관` | `구분 / 수량 / 강판 색상` (제품번호 주기 포함) |
| `#골조샵/251016-모듈 코드번호.xlsx` (36 KB) | `CHECK LIST` | `번호 / 모듈번호 / 타입 / 개구부 / 규격(W×L×H) / 실용도 / 슬리브 / 입면타입 / 내부창호 / 콘크리트높이 / 완료일자 / 도면번호 / 비고` |

**이 산출서는 모듈러 강구조(H형강 기둥·보, 퍼린, 조이스트, 데크) 물량이다.** 부재별 `길이 × 단중 → 총 중량`, `온둘레 × 길이 → 도장면적`이 산식이고, 콘크리트·거푸집·철근이 아니다. 따라서:

- P4의 **콘크리트 룰과 직접 대조되지 않는다.** 이 세트로 검증할 수 있는 것은 (a) 부재 식별(기둥/보/빔 타입 코드), (b) 길이 집계, (c) 표면적(도장) 집계, (d) 층·타입별 그룹핑이다.
- 반대로 **P3 3D 재구성에는 이상적이다** — `모듈 코드번호.xlsx`가 모듈 단위 `규격(W×L×H)`과 층·위치를 표로 갖고 있어 도면에서 복원한 배치와 1:1 대조가 된다.
- P4 진입 전에 **콘크리트 구조 프로젝트의 산출서**가 별도로 필요하다(`docs/samples/REQUEST.md`의 "준공 프로젝트 + 적산 엑셀" 항목 유지).

## 11. 제안 패치 (다른 태스크 소유 영역, 이 태스크에서는 수정하지 않음)

1. **`engine/src/halo_engine/ingest/xref.py`** — `resolve_xref_path`
   - `xref_path.replace("\\", "/")` 후 `PurePosixPath`로 basename/상대경로를 뽑는다(윈도 절대경로 `C:\…`는 드라이브 문자를 떼고 basename만 쓴다).
   - 빈 문자열이면 즉시 `None`(지금은 `host_dir / ""`가 디렉터리로 존재해 `IsADirectoryError`가 난다).
   - 5단계 basename 비교를 `unicodedata.normalize("NFC", …)` 양쪽에 적용한다(macOS NFD).
   - 해석 결과가 디렉터리면 `None`.
2. **`engine/src/halo_engine/ingest/stats.py`** — LEADER/DIMENSION의 bbox 계산에서 `DXFTableEntryError`·`ZeroDivisionError`를 잡아 그 엔티티만 bbox에서 빼고 진단으로 남긴다. 지금은 도면 하나가 통째로 실패한다(41/68). G0 후속 (2)와 같은 항목이며, 실세트에서 **차단 수준**임이 확인됐다.
3. **`packages/cad-core` 또는 변환 래퍼의 `dxfOut()` 후처리** — W3-02의 66·92에 더해 LEADER `dimstyle`, STYLE 빅폰트 `0`, 핸들 유일성.
4. **`packages/acad-bridge`** — `info`에 `styles[]`(name/font/bigfont/typeface)와 `xrefs[]`(block/path)를 추가한다. §3.3(B)의 메타데이터 주입 경로가 여기서 나온다. 그룹코드 스캐너 `tools/bench/scan-dxf.mjs`가 참조 구현이다.
5. **`.gitignore`** — 루트의 `samples/`가 앵커 없는 패턴이라 `docs/samples/`까지 무시한다. `/samples/`로 바꾼다(이 태스크는 `git add -f`로 우회했다).

## 12. G1 충실도 체크리스트 초안

실세트 68장으로 자동 판정 가능한 항목만 넣었다. 괄호는 현재 값이다.

| # | 항목 | 기준 | 현재 |
|---|---|---|---|
| 1 | 정본 DXF를 엔진이 읽는다 | 68/68 | **26/68** |
| 2 | ezdxf 감사기 삭제 건수 | 0 | 미측정(항목 1 통과 후) |
| 3 | `entity_count` 3파서 일치(±0.5%) | 68/68 | 59/68 완전 일치, 나머지도 0.5% 이내 |
| 4 | `text_count`·`text_hash` 일치 | 68/68 | 22/26(측정 가능분) |
| 5 | INSERT `66` 보존율 | 100% | 0% |
| 6 | HATCH External 비트 보존율 | 100% | 25.4% |
| 7 | XREF 경로 보존 + 해석 | 133/133 | 보존 0/133, 해석 0/133 |
| 8 | STYLE 폰트·빅폰트·typeface 보존 | 838/838 | typeface 0/838 |
| 9 | 폰트 해석 실패 시 UI 경고 | 있음 | 없음(조용히 사각형) |
| 10 | 뷰어가 도면을 연다 | 68/68 | 60/68 |
| 11 | `zoomToFitDrawing`이 도곽을 담는다 | 68/68 | 미달(최소 1장 확인) |
| 12 | 핸들 유일성 | 위반 0 | 위반 있음(최소 1장 4건) |
| 13 | 한글 모지바케 | 0 | **0 ✅** |
| 14 | 도곽(표제란 INSERT) 수 = PDF 페이지 수 | 공종별 일치 | **6/6 일치 ✅** |

## 13. 남은 것

1. **실제 GPU에서 렌더 상한 재측정**(W3-02). 이 문서의 5만은 SwiftShader 값이다.
2. **`REGION`·`ARCALIGNEDTEXT`·일부 `SPLINE`을 libredwg-web이 내지 않는 원인** 확인 후 상류 보고.
3. **XREF 그래프 단위 임포트.** 호스트 1장이 아니라 대상 13장을 함께 변환·임베드해야 정본이 완성된다.
4. **도곽 기반 시트 추출**(P2/P3). 레이아웃이 없으므로 `TITLE BLOCK-V` INSERT의 위치·회전이 시트 경계다. 표제란 ATTRIB에서 도면번호·축척·층이 나오므로 `docs/samples/labels.csv`의 `floor`·`sheet_type`을 자동 채울 수 있다.
5. **`A-520 부분확대 상세도_recover.dwg`** 같은 RECOVER 사본 처리 규칙(중복 도곽을 물량에 두 번 넣지 않도록). DMS(P2) 소관.
