# 실제 도서 세트 인벤토리 (2026-09-03)

자동 생성 문서 — 수정하지 말고 `node tools/bench/report-real.mjs`로 다시 만든다. 원자료는 `samples/_reports/`(gitignore)이고 재현 명령은 다음 두 줄이다.

```bash
node tools/bench-open.mjs --dir "samples/2026-09-02-실시도서" \
     --paths acad,acadconv,dxfout,engine --run-browser --timeout 300 --summary
node tools/bench/report-real.mjs
```

**도면 내용은 이 문서에 없다.** 집계 수치·파일명·폰트명·레이어명 통계·해시만 담는다(W3-09 브리프).

## 1. 세트 개요

| 항목 | 값 |
|---|---|
| 도면 파일(.dwg/.dxf, `.bak` 제외) | 68 |
| 합계 크기 | 101.71 MB (최대 19.83 MB) |
| DWG 버전 | AC1024 66, AC1032 1, AC1027 1 |
| `$DWGCODEPAGE`(acad-ts `info`) | kcs5601 68 |
| 공간 | 전 파일 `MODEL` 단독 — 레이아웃(페이퍼공간) 사용 0건 |
| 폴더 | ##실시도서(시공도면 수정) (1), ##실시도서(시공도면 수정)/00_표지 (1), ##실시도서(시공도면 수정)/01_건축 (38), ##실시도서(시공도면 수정)/02_기계 (1), ##실시도서(시공도면 수정)/03_전기 (1), ##실시도서(시공도면 수정)/04_통신 (1), ##실시도서(시공도면 수정)/05_소방_기계 (2), ##실시도서(시공도면 수정)/06_소방_전기 (1), ##실시도서(시공도면 수정)/XR (7), #골조샵 (5), #골조샵/XR (10) |

## 2. 파일별 표

`acad-ts`는 DWG를 직접 읽은 값, `libredwg`는 브라우저 WASM 파서가 돌려준 값, `ezdxf`는 그 파서가 `dxfOut()`으로 쓴 DXF를 엔진이 읽은 값이다. `텍스트`는 `text_count`(TEXT+MTEXT+ATTRIB), `한글`은 그 중 한글 문자를 포함한 문자열 수다.

| id | 폴더 | 파일 | MB | 버전 | 코드페이지 | acad-ts | libredwg | ezdxf | 텍스트 a/e | 한글 | 레이어 | XREF | 티어 | acad s | 브라우저 s | ezdxf s | ezdxf 결과 |
|---|---|---|---:|---|---|---:|---:|---:|---|---:|---:|---:|---|---:|---:|---:|---|
| S001 | ##실시도서(시공도면 수정) | #기초 오시공 구조검토.dwg | 1.36 | AC1024 | kcs5601 | 4,205 | 4,205 | — | 525/— | 122 | 66 | 0 | A | 0.6 | 1.5 | 2.7 | FAIL(DXFTableEntryError) |
| S002 | ##실시도서(시공도면 수정)/00_표지 | #표지.dwg | 0.05 | AC1024 | kcs5601 | 60 | 60 | 60 | 36/36 | 24 | 4 | 1 | A | 0.2 | 0.3 | 6.2 | ok |
| S003 | ##실시도서(시공도면 수정)/01_건축 | #강판제작도_251028.dwg | 0.26 | AC1024 | kcs5601 | 444 | 444 | 448 | 38/34 | 17 | 18 | 2 | A | 0.3 | 0.7 | 3.2 | ok |
| S004 | ##실시도서(시공도면 수정)/01_건축 | A-000 표지.dwg | 0.58 | AC1024 | kcs5601 | 10 | 10 | 10 | 6/6 | 4 | 4 | 1 | A | 0.2 | 0.2 | 0.6 | ok |
| S005 | ##실시도서(시공도면 수정)/01_건축 | A-001 투시도.dwg | 0.50 | AC1024 | kcs5601 | 16 | 16 | 16 | 10/10 | 6 | 5 | 1 | A | 0.2 | 0.2 | 0.6 | ok |
| S006 | ##실시도서(시공도면 수정)/01_건축 | A-003 도면목록표.dwg | 0.61 | AC1024 | kcs5601 | 812 | 812 | 812 | 449/449 | 132 | 6 | 1 | A | 0.2 | 0.8 | 0.5 | ok |
| S007 | ##실시도서(시공도면 수정)/01_건축 | A-004 건축개요.dwg | 0.51 | AC1024 | kcs5601 | 420 | 420 | 420 | 290/290 | 174 | 9 | 1 | A | 0.2 | 0.5 | 0.7 | ok |
| S008 | ##실시도서(시공도면 수정)/01_건축 | A-011 배치도.dwg | 0.54 | AC1024 | kcs5601 | 160 | 160 | — | 82/— | 110 | 24 | 4 | A | 0.3 | 0.3 | 0.9 | FAIL(DXFTableEntryError) |
| S009 | ##실시도서(시공도면 수정)/01_건축 | A-012 대지종횡단면도.dwg | 0.51 | AC1024 | kcs5601 | 169 | 169 | — | 51/— | 27 | 20 | 3 | A | 0.2 | 0.3 | 0.7 | FAIL(DXFTableEntryError) |
| S010 | ##실시도서(시공도면 수정)/01_건축 | A-020 면적산출표.dwg | 0.70 | AC1024 | kcs5601 | 1,623 | 1,623 | — | 780/— | 174 | 20 | 3 | A | 0.3 | 0.8 | 0.8 | FAIL(DXFTableEntryError) |
| S011 | ##실시도서(시공도면 수정)/01_건축 | A-031 보행 및 차량동선 계획도.dwg | 0.54 | AC1024 | kcs5601 | 124 | 124 | — | 76/— | 93 | 18 | 4 | A | 0.3 | 0.3 | 0.7 | FAIL(DXFTableEntryError) |
| S012 | ##실시도서(시공도면 수정)/01_건축 | A-032 조경계획도.dwg | 0.54 | AC1024 | kcs5601 | 148 | 148 | 148 | 80/80 | 72 | 14 | 4 | A | 0.2 | 0.3 | 0.7 | ok |
| S013 | ##실시도서(시공도면 수정)/01_건축 | A-033 단열 계획도.dwg | 0.64 | AC1024 | kcs5601 | 544 | 544 | — | 167/— | 105 | 18 | 3 | A | 0.3 | 0.7 | 0.7 | FAIL(DXFTableEntryError) |
| S014 | ##실시도서(시공도면 수정)/01_건축 | A-035 흡음 계획도.dwg | 0.54 | AC1024 | kcs5601 | 387 | 387 | 387 | 165/165 | 95 | 14 | 3 | A | 0.2 | 0.5 | 0.8 | ok |
| S015 | ##실시도서(시공도면 수정)/01_건축 | A-037 방수 계획도.DWG | 0.55 | AC1024 | kcs5601 | 516 | 516 | — | 308/— | 153 | 17 | 3 | A | 0.3 | 0.7 | 0.8 | FAIL(DXFTableEntryError) |
| S016 | ##실시도서(시공도면 수정)/01_건축 | A-039 방화 계획도.dwg | 0.54 | AC1024 | kcs5601 | 311 | 311 | — | 171/— | 84 | 18 | 3 | A | 0.3 | 0.4 | 0.8 | FAIL(DXFTableEntryError) |
| S017 | ##실시도서(시공도면 수정)/01_건축 | A-041 우배수계획도.dwg | 0.53 | AC1024 | kcs5601 | 292 | 292 | — | 196/— | 84 | 18 | 3 | A | 0.3 | 0.4 | 0.7 | FAIL(DXFTableEntryError) |
| S018 | ##실시도서(시공도면 수정)/01_건축 | A-043 장애인 편의시설 계획도.dwg | 1.73 | AC1024 | kcs5601 | 9,436 | 9,436 | — | 911/— | 716 | 137 | 4 | A | 0.5 | 1.2 | 1.2 | FAIL(DXFTableEntryError) |
| S019 | ##실시도서(시공도면 수정)/01_건축 | A-049 안전난간 계획도.dwg | 0.07 | AC1032 | kcs5601 | 219 | 219 | 219 | 120/120 | 59 | 13 | 3 | A | 0.2 | 0.4 | 0.7 | ok |
| S020 | ##실시도서(시공도면 수정)/01_건축 | A-049 출입문 유효폭 검토.dwg | 0.80 | AC1024 | kcs5601 | 513 | 513 | 513 | 264/264 | 128 | 13 | 3 | A | 0.3 | 0.7 | 1.6 | ok |
| S021 | ##실시도서(시공도면 수정)/01_건축 | A-060 실내외재료마감표, 상세도.dwg | 0.79 | AC1024 | kcs5601 | 2,477 | 2,477 | — | 830/— | 529 | 49 | 1 | A | 0.3 | 0.9 | 0.6 | FAIL(DXFTableEntryError) |
| S022 | ##실시도서(시공도면 수정)/01_건축 | A-100 평면도.dwg | 0.17 | AC1024 | kcs5601 | 1,488 | 1,488 | — | 575/— | 201 | 44 | 3 | A | 0.3 | 0.9 | 1.1 | FAIL(DXFTableEntryError) |
| S023 | ##실시도서(시공도면 수정)/01_건축 | A-200 입면도.dwg | 0.09 | AC1024 | kcs5601 | 151 | 151 | — | 68/— | 44 | 14 | 2 | A | 0.3 | 0.3 | 1.0 | FAIL(DXFTableEntryError) |
| S024 | ##실시도서(시공도면 수정)/01_건축 | A-300 단면도.dwg | 0.11 | AC1024 | kcs5601 | 271 | 271 | — | 103/— | 86 | 16 | 3 | A | 0.3 | 0.4 | 0.7 | FAIL(DXFTableEntryError) |
| S025 | ##실시도서(시공도면 수정)/01_건축 | A-400 수직동선 상세도.dwg | 0.81 | AC1024 | kcs5601 | 1,307 | 1,307 | — | 408/— | 188 | 44 | 4 | A | 0.3 | 0.9 | 1.1 | FAIL(DXFTableEntryError) |
| S026 | ##실시도서(시공도면 수정)/01_건축 | A-500 외벽확대 상세도.dwg | 0.80 | AC1024 | kcs5601 | 1,659 | 1,659 | — | 485/— | 364 | 27 | 4 | A | 0.3 | 0.9 | 1.0 | FAIL(DXFTableEntryError) |
| S027 | ##실시도서(시공도면 수정)/01_건축 | A-520 부분확대 상세도.dwg | 0.87 | AC1024 | kcs5601 | 718 | 718 | — | 122/— | 79 | 48 | 7 | A | 0.3 | 0.8 | 1.1 | FAIL(DXFTableEntryError) |
| S028 | ##실시도서(시공도면 수정)/01_건축 | A-520 부분확대 상세도_recover.dwg | 0.87 | AC1024 | kcs5601 | 726 | 726 | — | 126/— | 83 | 48 | 7 | A | 0.3 | 0.8 | 1.1 | FAIL(DXFTableEntryError) |
| S029 | ##실시도서(시공도면 수정)/01_건축 | A-530 접합 상세도.dwg | 0.53 | AC1024 | kcs5601 | 84 | 84 | — | 23/— | 16 | 18 | 4 | A | 0.2 | 0.2 | 0.7 | FAIL(DXFTableEntryError) |
| S030 | ##실시도서(시공도면 수정)/01_건축 | A-601 기숙사 상세도-1(일반생활관 평면도).dwg | 0.55 | AC1024 | kcs5601 | 344 | 344 | — | 100/— | 54 | 19 | 3 | A | 0.3 | 0.5 | 0.7 | FAIL(DXFTableEntryError) |
| S031 | ##실시도서(시공도면 수정)/01_건축 | A-602 기숙사 상세도-2(일반생활관 천장,입단면도).dwg | 0.25 | AC1024 | kcs5601 | 628 | 628 | — | 142/— | 135 | 32 | 5 | A | 0.3 | 0.8 | 1.3 | FAIL(DXFTableEntryError) |
| S032 | ##실시도서(시공도면 수정)/01_건축 | A-605 기숙사 상세도-5(장애인생활관 평면도).dwg | 0.55 | AC1024 | kcs5601 | 310 | 310 | — | 80/— | 44 | 17 | 3 | A | 0.3 | 0.4 | 0.7 | FAIL(DXFTableEntryError) |
| S033 | ##실시도서(시공도면 수정)/01_건축 | A-606 기숙사 상세도-6(장애인생활관 천장,입단면도).dwg | 0.76 | AC1024 | kcs5601 | 853 | 851 | — | 109/— | 111 | 58 | 5 | A | 0.3 | 0.9 | 1.1 | FAIL(DXFTableEntryError) |
| S034 | ##실시도서(시공도면 수정)/01_건축 | A-620 화장실 전개도.dwg | 2.09 | AC1024 | kcs5601 | 2,295 | 2,295 | — | 183/— | 67 | 37 | 3 | A | 0.5 | 1.1 | 2.6 | FAIL(DXFTableEntryError) |
| S035 | ##실시도서(시공도면 수정)/01_건축 | A-700 창호위치안내도.DWG | 0.19 | AC1024 | kcs5601 | 805 | 805 | 1,386 | 1,335/173 | 79 | 11 | 3 | A | 0.3 | 0.9 | 0.9 | ok |
| S036 | ##실시도서(시공도면 수정)/01_건축 | A-710 창호도.dwg | 1.09 | AC1024 | kcs5601 | 4,632 | 4,579 | — | 766/— | 498 | 57 | 3 | A | 0.4 | 1.2 | 1.6 | FAIL(DXFTableEntryError) |
| S037 | ##실시도서(시공도면 수정)/01_건축 | A-800 바닥 평면도.dwg | 0.16 | AC1024 | kcs5601 | 813 | 813 | — | 160/— | 80 | 23 | 3 | A | 0.3 | 0.8 | 1.0 | FAIL(DXFTableEntryError) |
| S038 | ##실시도서(시공도면 수정)/01_건축 | A-810 천장 평면도.dwg | 1.65 | AC1024 | kcs5601 | 1,028 | 1,028 | — | 129/— | 246 | 36 | 3 | A | 1.2 | 1.5 | 10.9 | FAIL(DXFTableEntryError) |
| S039 | ##실시도서(시공도면 수정)/01_건축 | A-820 건식벽체 안내도.dwg | 1.17 | AC1024 | kcs5601 | 4,457 | 4,457 | — | 812/— | 549 | 66 | 3 | A | 0.4 | 1.0 | 1.3 | FAIL(DXFTableEntryError) |
| S040 | ##실시도서(시공도면 수정)/01_건축 | A-900 기타상세도.dwg | 0.74 | AC1024 | kcs5601 | 2,315 | 2,296 | — | 147/— | 117 | 100 | 2 | A | 0.3 | 0.9 | 0.7 | FAIL(DXFTableEntryError) |
| S041 | ##실시도서(시공도면 수정)/02_기계 | 01_기계도면(김화공고 모듈러 생활관 증축공사)_수정.DWG | 7.68 | AC1024 | kcs5601 | 127,974 | 127,886 | — | 8,839/— | 2,462 | 88 | 0 | A | 21.2 | 4.4 | 14.6 | FAIL(DXFTableEntryError) |
| S042 | ##실시도서(시공도면 수정)/03_전기 | 김화공업고등학교 모듈러 생활관 제작·설치 구매_전기도서 (1).dwg | 19.83 | AC1024 | kcs5601 | 348,076 | 347,892 | — | 14,525/— | 4,798 | 102 | 0 | B | 10.1 | 8.8 | 39.5 | FAIL(ZeroDivisionError) |
| S043 | ##실시도서(시공도면 수정)/04_통신 | 김화공업고등학교 모듈러 생활관 제작·설치 구매_통신도서.dwg | 8.86 | AC1024 | kcs5601 | 70,550 | 70,550 | — | 3,722/— | 672 | 49 | 0 | A | 4.5 | 4.3 | 37.9 | FAIL(DXFTableEntryError) |
| S044 | ##실시도서(시공도면 수정)/05_소방_기계 | 01_기계소방도면(김화공고 모듈러 생활관 증축공사).dwg | 3.44 | AC1024 | kcs5601 | 48,473 | 48,429 | 48,429 | 2,946/2,946 | 803 | 30 | 0 | A | 7.8 | 2.4 | 159.0 | ok |
| S045 | ##실시도서(시공도면 수정)/05_소방_기계 | 02_기계소방내진도면(김화공고 모듈러 생활관 증축공사).dwg | 9.80 | AC1024 | kcs5601 | 89,621 | 89,533 | — | 4,188/— | 1,400 | 39 | 0 | A | 18.7 | 4.4 | 127.7 | FAIL(DXFTableEntryError) |
| S046 | ##실시도서(시공도면 수정)/06_소방_전기 | 김화공업고등학교 모듈러 생활관 제작·설치 구매_전기소방도서 (3).dwg | 6.86 | AC1024 | kcs5601 | 124,487 | 124,487 | — | 3,478/— | 1,309 | 28 | 0 | A | 4.1 | 4.1 | 14.9 | FAIL(DXFTableEntryError) |
| S047 | ##실시도서(시공도면 수정)/XR | PLAN.dwg | 1.96 | AC1024 | kcs5601 | 1,656 | 1,656 | — | 99/— | 84 | 74 | 1 | A | 3.4 | 1.7 | 9.4 | FAIL(DXFTableEntryError) |
| S048 | ##실시도서(시공도면 수정)/XR | TITLE BLOCK-V.dwg | 0.54 | AC1024 | kcs5601 | 17 | 17 | 17 | 12/12 | 20 | 3 | 0 | A | 0.3 | 0.2 | 0.8 | ok |
| S049 | ##실시도서(시공도면 수정)/XR | xr_elevation.dwg | 0.33 | AC1024 | kcs5601 | 533 | 533 | 561 | 44/16 | 13 | 27 | 0 | A | 0.8 | 0.7 | 2.6 | ok |
| S050 | ##실시도서(시공도면 수정)/XR | xr_keymap.dwg | 0.03 | AC1024 | kcs5601 | 11 | 11 | 11 | 0/0 | 0 | 6 | 0 | A | 1.4 | 0.2 | 0.6 | ok |
| S051 | ##실시도서(시공도면 수정)/XR | xr_section.dwg | 0.89 | AC1024 | kcs5601 | 1,133 | 1,133 | — | 117/— | 99 | 50 | 0 | A | 2.4 | 1.2 | 5.6 | FAIL(DXFTableEntryError) |
| S052 | ##실시도서(시공도면 수정)/XR | 단위세대_평면.dwg | 0.74 | AC1024 | kcs5601 | 251 | 251 | 251 | 11/11 | 0 | 18 | 0 | A | 0.3 | 0.5 | 1.1 | ok |
| S053 | ##실시도서(시공도면 수정)/XR | 현황도_김화중공업고등학교.dwg | 1.29 | AC1024 | kcs5601 | 9,866 | 9,866 | 9,866 | 1,297/1,297 | 716 | 107 | 0 | A | 0.5 | 1.1 | 3.5 | ok |
| S054 | #골조샵 | 250711-목업골조제작도.dwg | 1.84 | AC1024 | kcs5601 | 7,390 | 7,389 | — | 2,679/— | 750 | 185 | 1 | A | 0.8 | 1.8 | 2.8 | FAIL(DXFTableEntryError) |
| S055 | #골조샵 | 250813-모듈안내도.dwg | 2.90 | AC1024 | kcs5601 | 456 | 456 | — | 181/— | 125 | 20 | 0 | A | 3.9 | 2.1 | 19.8 | FAIL(DXFTableEntryError) |
| S056 | #골조샵 | A-000 표지.dwg | 0.05 | AC1024 | kcs5601 | 36 | 36 | 36 | 20/20 | 12 | 4 | 1 | A | 0.2 | 0.2 | 0.6 | ok |
| S057 | #골조샵 | A-100 평면도.dwg | 0.17 | AC1024 | kcs5601 | 814 | 814 | — | 331/— | 172 | 25 | 4 | A | 0.3 | 0.8 | 0.9 | FAIL(DXFTableEntryError) |
| S058 | #골조샵/XR | PLAN(250618).dwg | 1.54 | AC1024 | kcs5601 | 1,339 | 1,339 | — | 41/— | 17 | 39 | 1 | A | 2.8 | 1.5 | 4.8 | FAIL(DXFTableEntryError) |
| S059 | #골조샵/XR | PLAN.dwg | 2.99 | AC1024 | kcs5601 | 1,733 | 1,733 | 1,733 | 69/69 | 63 | 58 | 1 | A | 3.4 | 2.4 | 21.1 | ok |
| S060 | #골조샵/XR | TITLE BLOCK-V.dwg | 0.08 | AC1027 | kcs5601 | 17 | 17 | 17 | 12/12 | 20 | 3 | 0 | A | 0.3 | 0.2 | 0.7 | ok |
| S061 | #골조샵/XR | xr_elevation.dwg | 0.13 | AC1024 | kcs5601 | 600 | 600 | 628 | 80/52 | 34 | 20 | 0 | A | 0.3 | 0.8 | 2.4 | ok |
| S062 | #골조샵/XR | xr_keymap.dwg | 0.03 | AC1024 | kcs5601 | 11 | 11 | 11 | 0/0 | 0 | 6 | 0 | A | 0.5 | 0.2 | 0.6 | ok |
| S063 | #골조샵/XR | xr_section.dwg | 2.13 | AC1024 | kcs5601 | 1,302 | 1,298 | — | 93/— | 95 | 51 | 1 | A | 2.5 | 2.0 | 6.3 | FAIL(DXFTableEntryError) |
| S064 | #골조샵/XR | xr_section_YH.dwg | 0.17 | AC1024 | kcs5601 | 606 | 606 | — | 92/— | 82 | 37 | 2 | A | 0.3 | 0.8 | 1.1 | FAIL(DXFTableEntryError) |
| S065 | #골조샵/XR | 단위세대_평면.dwg | 0.14 | AC1024 | kcs5601 | 30 | 30 | 30 | 0/0 | 0 | 13 | 0 | A | 0.3 | 0.3 | 0.5 | ok |
| S066 | #골조샵/XR | 모듈 코드번호.dwg | 0.11 | AC1024 | kcs5601 | 624 | 624 | 624 | 364/364 | 2 | 3 | 0 | A | 0.3 | 0.8 | 0.5 | ok |
| S067 | #골조샵/XR | 현황도_김화중공업고등학교.dwg | 0.72 | AC1024 | kcs5601 | 10,452 | 10,452 | 10,452 | 1,297/1,297 | 708 | 105 | 0 | A | 0.5 | 1.1 | 3.6 | ok |
| S068 | #골조샵 | 목업데크슬라브.dwg | 0.10 | AC1024 | kcs5601 | 167 | 167 | 167 | 35/35 | 30 | 10 | 0 | A | 0.3 | 0.4 | 0.5 | ok |

## 3. 파서 대조

| 항목 | 값 |
|---|---|
| acad-ts가 읽은 파일 | 68/68 |
| libredwg-web이 읽은 파일 | 68/68 |
| `entity_count` 완전 일치(acad-ts = libredwg) | 59/68 |
| 세 파서 모두 일치 | 21/68 |
| ezdxf가 `dxfOut()` DXF를 읽음 | 26/68 |
| ezdxf가 acad-ts DXF를 읽음 | 23/68 |

격차가 있는 파일(음수 = libredwg가 덜 읽음):

| id | 파일 | acad-ts | libredwg | 차 | 타입별 |
|---|---|---:|---:|---:|---|
| S033 | A-606 기숙사 상세도-6(장애인생활관 천장,입단면도).dwg | 853 | 851 | -2 | REGION -2 |
| S036 | A-710 창호도.dwg | 4,632 | 4,579 | -53 | REGION -53 |
| S040 | A-900 기타상세도.dwg | 2,315 | 2,296 | -19 | REGION -19 |
| S041 | 01_기계도면(김화공고 모듈러 생활관 증축공사)_수정.DWG | 127,974 | 127,886 | -88 | SPLINE -88 |
| S042 | 김화공업고등학교 모듈러 생활관 제작·설치 구매_전기도서 (1).dwg | 348,076 | 347,892 | -184 | ARCALIGNEDTEXT -8, SPLINE -176 |
| S044 | 01_기계소방도면(김화공고 모듈러 생활관 증축공사).dwg | 48,473 | 48,429 | -44 | SPLINE -44 |
| S045 | 02_기계소방내진도면(김화공고 모듈러 생활관 증축공사).dwg | 89,621 | 89,533 | -88 | SPLINE -88 |
| S054 | 250711-목업골조제작도.dwg | 7,390 | 7,389 | -1 | INSERT -1 |
| S063 | xr_section.dwg | 1,302 | 1,298 | -4 | REGION -4 |

합계 타입별 격차: `REGION` -78, `SPLINE` -396, `ARCALIGNEDTEXT` -8, `INSERT` -1

## 4. 폰트 (STYLE 테이블 전수)

acad-ts `dwg2dxf` 산출 DXF에서 집계했다 — 이 경로만 그룹 3(폰트 파일)·4(빅폰트)·XDATA `ACAD` 1000(TTF typeface)을 모두 보존한다(§6). 스타일 레코드 832개, 고유 스타일명 140개.

### 4.1 SHX / 폰트 파일명 (그룹 3)

| 폰트 파일 | 스타일 수 | mlightcad cad-data 보유 |
|---|---:|---|
| `malgun.ttf` | 165 | **누락** |
| `txt` | 85 | 있음 |
| `H2GTRE.TTF` | 50 | **누락** |
| `gulim.ttc` | 19 | **누락** |
| `romans.shx` | 15 | 있음 |
| `arial.ttf` | 11 | 있음 |
| `H2GTRM.TTF` | 10 | **누락** |
| `ltypeshp.shx` | 5 | 있음 |
| `C:\program files\autodesk\autocad 2013\fonts\romans.shx` | 4 | 있음 |
| `ROMANS.shx` | 3 | 있음 |
| `txt.shx` | 3 | 있음 |
| `malgunbd.ttf` | 2 | **누락** |
| `isocpeur.ttf` | 2 | **누락** |
| `kscals.shx` | 2 | **누락** |
| `H2HDRM.TTF` | 2 | **누락** |
| `romant` | 2 | 있음 |
| `ENGINEERING.shx` | 2 | **누락** |
| `HYWULM.TTF` | 1 | **누락** |
| `SIMPLEX.SHX` | 1 | 있음 |
| `ariblk.ttf` | 1 | **누락** |
| `Yu Gothic.ttf` | 1 | **누락** |
| `simplex` | 1 | 있음 |
| `romans` | 1 | 있음 |
| `TXT` | 1 | 있음 |
| `isocp.shx` | 1 | 있음 |
| `malgunsl.ttf` | 1 | **누락** |
| `arialbd.ttf` | 1 | **누락** |
| `MoeumT R.ttf` | 1 | **누락** |
| `C:\Program Files\Autodesk\AutoCAD 2022\fonts\romans.shx` | 1 | 있음 |

### 4.2 빅폰트 (그룹 4)

| 빅폰트 | 스타일 수 | cad-data 보유 |
|---|---:|---|
| `whgtxt.shx` | 16 | 있음 |
| `C:\xicad\arcbig03.shx` | 5 | **누락** |
| `ghs.shx` | 2 | **누락** |
| `WHGTXT.SHX` | 1 | 있음 |
| `ghs` | 1 | **누락** |
| `GHS.shx` | 1 | **누락** |
| `WHGTXT.shx` | 1 | 있음 |

### 4.3 TTF typeface (STYLE XDATA `ACAD` 1000)

| typeface | 스타일 수 | cad-data 보유 |
|---|---:|---|
| Dotum | 206 | **누락** |
| Malgun Gothic | 141 | **누락** |
| HY각헤드라인M | 45 | **누락** |
| HYGothic-Extra | 42 | **누락** |
| DotumChe | 38 | **누락** |
| Rix모던고딕 M | 32 | **누락** |
| 맑은 고딕 | 24 | **누락** |
| Rix모던고딕 L | 23 | **누락** |
| 돋움 | 23 | **누락** |
| Gulim | 22 | **누락** |
| HYGothic-Medium | 12 | **누락** |
| GulimChe | 12 | **누락** |
| HY울릉도M | 12 | **누락** |
| 08서울남산체 M | 11 | **누락** |
| Arial | 11 | 있음 |
| HY울릉도L | 10 | **누락** |
| HY견고딕 | 8 | **누락** |
| 나눔스퀘어_ac | 6 | **누락** |
| Expo M | 4 | **누락** |
| HYHeadLine-Medium | 3 | **누락** |
| HCR Dotum | 3 | **누락** |
| 08SeoulNamsan M | 3 | **누락** |
| malgunbd | 2 | **누락** |
| ISOCPEUR | 2 | **누락** |
| ariblk | 1 | **누락** |
| Yu Gothic | 1 | **누락** |
| HYwulM | 1 | **누락** |
| VNI-Helve-Condense | 1 | **누락** |
| 굴림 | 1 | **누락** |
| 나눔스퀘어라운드 Regular | 1 | **누락** |
| Malgun Gothic Semilight | 1 | **누락** |
| arialbd | 1 | **누락** |
| MoeumT R | 1 | **누락** |
| 견고딕 | 1 | **누락** |

**누락 요약** — SHX/폰트 파일 19종, TTF typeface 33종이 mlightcad 기본 폰트 세트(cad-data 97종)에 없다.

## 5. XREF

XREF 블록 133건, 대상 파일 8종.

| 경로 형태 | 건수 |
|---|---:|
| relative | 132 |
| absolute | 1 |

| 대상 파일 | 참조 횟수 | 세트 안에 있음 |
|---|---:|---|
| TITLE BLOCK-V.dwg | 42 | 예 |
| 단위세대_평면.dwg | 32 | 예 |
| PLAN.dwg | 30 | 예 |
| xr_section.dwg | 9 | 예 |
| xr_elevation.dwg | 7 | 예 |
| xr_keymap.dwg | 7 | 예 |
| 현황도_김화중공업고등학교.dwg | 5 | 예 |
| 모듈 코드번호.dwg | 1 | 예 |

해석 가능 8종 / 미해석 0종.

| 호스트 | XREF 블록 | 저장된 경로 | 형태 |
|---|---|---|---|
| S002 ##실시도서(시공도면 수정)/00_표지/#표지.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S003 ##실시도서(시공도면 수정)/01_건축/#강판제작도_251028.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S003 ##실시도서(시공도면 수정)/01_건축/#강판제작도_251028.dwg | xr_elevation | `..\XR\xr_elevation.dwg` | relative |
| S004 ##실시도서(시공도면 수정)/01_건축/A-000 표지.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S005 ##실시도서(시공도면 수정)/01_건축/A-001 투시도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S006 ##실시도서(시공도면 수정)/01_건축/A-003 도면목록표.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S007 ##실시도서(시공도면 수정)/01_건축/A-004 건축개요.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S008 ##실시도서(시공도면 수정)/01_건축/A-011 배치도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S008 ##실시도서(시공도면 수정)/01_건축/A-011 배치도.dwg | 현황도_김화중공업고등학교 | `..\XR\현황도_김화중공업고등학교.dwg` | relative |
| S008 ##실시도서(시공도면 수정)/01_건축/A-011 배치도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S008 ##실시도서(시공도면 수정)/01_건축/A-011 배치도.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S009 ##실시도서(시공도면 수정)/01_건축/A-012 대지종횡단면도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S009 ##실시도서(시공도면 수정)/01_건축/A-012 대지종횡단면도.dwg | xr_section | `..\XR\xr_section.dwg` | relative |
| S009 ##실시도서(시공도면 수정)/01_건축/A-012 대지종횡단면도.dwg | xr_keymap | `..\XR\xr_keymap.dwg` | relative |
| S010 ##실시도서(시공도면 수정)/01_건축/A-020 면적산출표.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S010 ##실시도서(시공도면 수정)/01_건축/A-020 면적산출표.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S010 ##실시도서(시공도면 수정)/01_건축/A-020 면적산출표.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S011 ##실시도서(시공도면 수정)/01_건축/A-031 보행 및 차량동선 계획도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S011 ##실시도서(시공도면 수정)/01_건축/A-031 보행 및 차량동선 계획도.dwg | 현황도_김화중공업고등학교 | `..\XR\현황도_김화중공업고등학교.dwg` | relative |
| S011 ##실시도서(시공도면 수정)/01_건축/A-031 보행 및 차량동선 계획도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S011 ##실시도서(시공도면 수정)/01_건축/A-031 보행 및 차량동선 계획도.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S012 ##실시도서(시공도면 수정)/01_건축/A-032 조경계획도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S012 ##실시도서(시공도면 수정)/01_건축/A-032 조경계획도.dwg | 현황도_김화중공업고등학교 | `..\XR\현황도_김화중공업고등학교.dwg` | relative |
| S012 ##실시도서(시공도면 수정)/01_건축/A-032 조경계획도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S012 ##실시도서(시공도면 수정)/01_건축/A-032 조경계획도.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S013 ##실시도서(시공도면 수정)/01_건축/A-033 단열 계획도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S013 ##실시도서(시공도면 수정)/01_건축/A-033 단열 계획도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S013 ##실시도서(시공도면 수정)/01_건축/A-033 단열 계획도.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S014 ##실시도서(시공도면 수정)/01_건축/A-035 흡음 계획도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S014 ##실시도서(시공도면 수정)/01_건축/A-035 흡음 계획도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S014 ##실시도서(시공도면 수정)/01_건축/A-035 흡음 계획도.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S015 ##실시도서(시공도면 수정)/01_건축/A-037 방수 계획도.DWG | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S015 ##실시도서(시공도면 수정)/01_건축/A-037 방수 계획도.DWG | PLAN | `..\XR\PLAN.dwg` | relative |
| S015 ##실시도서(시공도면 수정)/01_건축/A-037 방수 계획도.DWG | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S016 ##실시도서(시공도면 수정)/01_건축/A-039 방화 계획도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S016 ##실시도서(시공도면 수정)/01_건축/A-039 방화 계획도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S016 ##실시도서(시공도면 수정)/01_건축/A-039 방화 계획도.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S017 ##실시도서(시공도면 수정)/01_건축/A-041 우배수계획도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S017 ##실시도서(시공도면 수정)/01_건축/A-041 우배수계획도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S017 ##실시도서(시공도면 수정)/01_건축/A-041 우배수계획도.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S018 ##실시도서(시공도면 수정)/01_건축/A-043 장애인 편의시설 계획도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S018 ##실시도서(시공도면 수정)/01_건축/A-043 장애인 편의시설 계획도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S018 ##실시도서(시공도면 수정)/01_건축/A-043 장애인 편의시설 계획도.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S018 ##실시도서(시공도면 수정)/01_건축/A-043 장애인 편의시설 계획도.dwg | xr_section | `..\XR\xr_section.dwg` | relative |
| S019 ##실시도서(시공도면 수정)/01_건축/A-049 안전난간 계획도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S019 ##실시도서(시공도면 수정)/01_건축/A-049 안전난간 계획도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S019 ##실시도서(시공도면 수정)/01_건축/A-049 안전난간 계획도.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S020 ##실시도서(시공도면 수정)/01_건축/A-049 출입문 유효폭 검토.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S020 ##실시도서(시공도면 수정)/01_건축/A-049 출입문 유효폭 검토.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S020 ##실시도서(시공도면 수정)/01_건축/A-049 출입문 유효폭 검토.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S021 ##실시도서(시공도면 수정)/01_건축/A-060 실내외재료마감표, 상세도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S022 ##실시도서(시공도면 수정)/01_건축/A-100 평면도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S022 ##실시도서(시공도면 수정)/01_건축/A-100 평면도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S022 ##실시도서(시공도면 수정)/01_건축/A-100 평면도.dwg | 단위세대_평면 | `.\단위세대_평면.dwg` | relative |
| S023 ##실시도서(시공도면 수정)/01_건축/A-200 입면도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S023 ##실시도서(시공도면 수정)/01_건축/A-200 입면도.dwg | xr_elevation | `..\XR\xr_elevation.dwg` | relative |
| S024 ##실시도서(시공도면 수정)/01_건축/A-300 단면도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S024 ##실시도서(시공도면 수정)/01_건축/A-300 단면도.dwg | xr_section | `..\XR\xr_section.dwg` | relative |
| S024 ##실시도서(시공도면 수정)/01_건축/A-300 단면도.dwg | xr_keymap | `..\XR\xr_keymap.dwg` | relative |
| S025 ##실시도서(시공도면 수정)/01_건축/A-400 수직동선 상세도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S025 ##실시도서(시공도면 수정)/01_건축/A-400 수직동선 상세도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S025 ##실시도서(시공도면 수정)/01_건축/A-400 수직동선 상세도.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S025 ##실시도서(시공도면 수정)/01_건축/A-400 수직동선 상세도.dwg | xr_section | `..\XR\xr_section.dwg` | relative |
| S026 ##실시도서(시공도면 수정)/01_건축/A-500 외벽확대 상세도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S026 ##실시도서(시공도면 수정)/01_건축/A-500 외벽확대 상세도.dwg | xr_keymap | `..\XR\xr_keymap.dwg` | relative |
| S026 ##실시도서(시공도면 수정)/01_건축/A-500 외벽확대 상세도.dwg | xr_elevation | `..\XR\xr_elevation.dwg` | relative |
| S026 ##실시도서(시공도면 수정)/01_건축/A-500 외벽확대 상세도.dwg | xr_section | `..\XR\xr_section.dwg` | relative |
| S027 ##실시도서(시공도면 수정)/01_건축/A-520 부분확대 상세도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S027 ##실시도서(시공도면 수정)/01_건축/A-520 부분확대 상세도.dwg | xr_section | `..\XR\xr_section.dwg` | relative |
| S027 ##실시도서(시공도면 수정)/01_건축/A-520 부분확대 상세도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S027 ##실시도서(시공도면 수정)/01_건축/A-520 부분확대 상세도.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S027 ##실시도서(시공도면 수정)/01_건축/A-520 부분확대 상세도.dwg | 현황도_김화중공업고등학교 | `..\XR\현황도_김화중공업고등학교.dwg` | relative |
| S027 ##실시도서(시공도면 수정)/01_건축/A-520 부분확대 상세도.dwg | xr_elevation | `..\XR\xr_elevation.dwg` | relative |
| S027 ##실시도서(시공도면 수정)/01_건축/A-520 부분확대 상세도.dwg | xr_keymap | `..\XR\xr_keymap.dwg` | relative |
| S028 ##실시도서(시공도면 수정)/01_건축/A-520 부분확대 상세도_recover.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S028 ##실시도서(시공도면 수정)/01_건축/A-520 부분확대 상세도_recover.dwg | xr_section | `..\XR\xr_section.dwg` | relative |
| S028 ##실시도서(시공도면 수정)/01_건축/A-520 부분확대 상세도_recover.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S028 ##실시도서(시공도면 수정)/01_건축/A-520 부분확대 상세도_recover.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S028 ##실시도서(시공도면 수정)/01_건축/A-520 부분확대 상세도_recover.dwg | 현황도_김화중공업고등학교 | `..\XR\현황도_김화중공업고등학교.dwg` | relative |
| S028 ##실시도서(시공도면 수정)/01_건축/A-520 부분확대 상세도_recover.dwg | xr_elevation | `..\XR\xr_elevation.dwg` | relative |
| S028 ##실시도서(시공도면 수정)/01_건축/A-520 부분확대 상세도_recover.dwg | xr_keymap | `..\XR\xr_keymap.dwg` | relative |
| S029 ##실시도서(시공도면 수정)/01_건축/A-530 접합 상세도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S029 ##실시도서(시공도면 수정)/01_건축/A-530 접합 상세도.dwg | xr_section | `..\XR\xr_section.dwg` | relative |
| S029 ##실시도서(시공도면 수정)/01_건축/A-530 접합 상세도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S029 ##실시도서(시공도면 수정)/01_건축/A-530 접합 상세도.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S030 ##실시도서(시공도면 수정)/01_건축/A-601 기숙사 상세도-1(일반생활관 평면도).dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S030 ##실시도서(시공도면 수정)/01_건축/A-601 기숙사 상세도-1(일반생활관 평면도).dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S030 ##실시도서(시공도면 수정)/01_건축/A-601 기숙사 상세도-1(일반생활관 평면도).dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S031 ##실시도서(시공도면 수정)/01_건축/A-602 기숙사 상세도-2(일반생활관 천장,입단면도).dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S031 ##실시도서(시공도면 수정)/01_건축/A-602 기숙사 상세도-2(일반생활관 천장,입단면도).dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S031 ##실시도서(시공도면 수정)/01_건축/A-602 기숙사 상세도-2(일반생활관 천장,입단면도).dwg | 단위세대_평면 | `.\단위세대_평면.dwg` | relative |
| S031 ##실시도서(시공도면 수정)/01_건축/A-602 기숙사 상세도-2(일반생활관 천장,입단면도).dwg | xr_elevation | `..\XR\xr_elevation.dwg` | relative |
| S031 ##실시도서(시공도면 수정)/01_건축/A-602 기숙사 상세도-2(일반생활관 천장,입단면도).dwg | xr_keymap | `..\XR\xr_keymap.dwg` | relative |
| S032 ##실시도서(시공도면 수정)/01_건축/A-605 기숙사 상세도-5(장애인생활관 평면도).dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S032 ##실시도서(시공도면 수정)/01_건축/A-605 기숙사 상세도-5(장애인생활관 평면도).dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S032 ##실시도서(시공도면 수정)/01_건축/A-605 기숙사 상세도-5(장애인생활관 평면도).dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S033 ##실시도서(시공도면 수정)/01_건축/A-606 기숙사 상세도-6(장애인생활관 천장,입단면도).dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S033 ##실시도서(시공도면 수정)/01_건축/A-606 기숙사 상세도-6(장애인생활관 천장,입단면도).dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S033 ##실시도서(시공도면 수정)/01_건축/A-606 기숙사 상세도-6(장애인생활관 천장,입단면도).dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S033 ##실시도서(시공도면 수정)/01_건축/A-606 기숙사 상세도-6(장애인생활관 천장,입단면도).dwg | xr_elevation | `..\XR\xr_elevation.dwg` | relative |
| S033 ##실시도서(시공도면 수정)/01_건축/A-606 기숙사 상세도-6(장애인생활관 천장,입단면도).dwg | xr_keymap | `..\XR\xr_keymap.dwg` | relative |
| S034 ##실시도서(시공도면 수정)/01_건축/A-620 화장실 전개도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S034 ##실시도서(시공도면 수정)/01_건축/A-620 화장실 전개도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S034 ##실시도서(시공도면 수정)/01_건축/A-620 화장실 전개도.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S035 ##실시도서(시공도면 수정)/01_건축/A-700 창호위치안내도.DWG | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S035 ##실시도서(시공도면 수정)/01_건축/A-700 창호위치안내도.DWG | PLAN | `..\XR\PLAN.dwg` | relative |
| S035 ##실시도서(시공도면 수정)/01_건축/A-700 창호위치안내도.DWG | 단위세대_평면 | `.\단위세대_평면.dwg` | relative |
| S036 ##실시도서(시공도면 수정)/01_건축/A-710 창호도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S036 ##실시도서(시공도면 수정)/01_건축/A-710 창호도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S036 ##실시도서(시공도면 수정)/01_건축/A-710 창호도.dwg | 단위세대_평면 | `.\단위세대_평면.dwg` | relative |
| S037 ##실시도서(시공도면 수정)/01_건축/A-800 바닥 평면도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S037 ##실시도서(시공도면 수정)/01_건축/A-800 바닥 평면도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S037 ##실시도서(시공도면 수정)/01_건축/A-800 바닥 평면도.dwg | 단위세대_평면 | `.\단위세대_평면.dwg` | relative |
| S038 ##실시도서(시공도면 수정)/01_건축/A-810 천장 평면도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S038 ##실시도서(시공도면 수정)/01_건축/A-810 천장 평면도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S038 ##실시도서(시공도면 수정)/01_건축/A-810 천장 평면도.dwg | 단위세대_평면 | `.\단위세대_평면.dwg` | relative |
| S039 ##실시도서(시공도면 수정)/01_건축/A-820 건식벽체 안내도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S039 ##실시도서(시공도면 수정)/01_건축/A-820 건식벽체 안내도.dwg | PLAN | `..\XR\PLAN.dwg` | relative |
| S039 ##실시도서(시공도면 수정)/01_건축/A-820 건식벽체 안내도.dwg | 단위세대_평면 | `..\XR\단위세대_평면.dwg` | relative |
| S040 ##실시도서(시공도면 수정)/01_건축/A-900 기타상세도.dwg | TITLE BLOCK-V | `..\XR\TITLE BLOCK-V.dwg` | relative |
| S040 ##실시도서(시공도면 수정)/01_건축/A-900 기타상세도.dwg | xr_section | `..\XR\xr_section.dwg` | relative |
| S047 ##실시도서(시공도면 수정)/XR/PLAN.dwg | 단위세대_평면 | `.\단위세대_평면.dwg` | relative |
| S054 #골조샵/250711-목업골조제작도.dwg | TITLE BLOCK-V | `.\XR\TITLE BLOCK-V.dwg` | relative |
| S056 #골조샵/A-000 표지.dwg | TITLE BLOCK-V | `..\..\14.납품\250630 허가접수\05_도면\01_건축\XR\TITLE BLOCK-V.dwg` | relative |
| S057 #골조샵/A-100 평면도.dwg | TITLE BLOCK-V | `.\XR\TITLE BLOCK-V.dwg` | relative |
| S057 #골조샵/A-100 평면도.dwg | PLAN | `.\XR\PLAN.dwg` | relative |
| S057 #골조샵/A-100 평면도.dwg | 단위세대_평면 | `.\단위세대_평면.dwg` | relative |
| S057 #골조샵/A-100 평면도.dwg | 모듈 코드번호 | `.\XR\모듈 코드번호.dwg` | relative |
| S058 #골조샵/XR/PLAN(250618).dwg | 단위세대_평면 | `U:\04_김화공고\02.도면\#실시설계\XR\단위세대_평면.dwg` | absolute |
| S059 #골조샵/XR/PLAN.dwg | 단위세대_평면 | `.\단위세대_평면.dwg` | relative |
| S063 #골조샵/XR/xr_section.dwg | PLAN | `.\PLAN.dwg` | relative |
| S064 #골조샵/XR/xr_section_YH.dwg | PLAN | `.\PLAN.dwg` | relative |
| S064 #골조샵/XR/xr_section_YH.dwg | 단위세대_평면 | `.\단위세대_평면.dwg` | relative |

## 6. 변환기별 그룹코드 보존

| 항목 | acad-ts `dwg2dxf` | libredwg + `dxfOut()` |
|---|---:|---:|
| 스캔한 DXF 수 | 68 | 68 |
| INSERT 총수 | 110,673 | 110,675 |
| 그룹 66이 있는 INSERT | 2,181 | 0 |
| HATCH 경계 경로 | 21,674 | 21,680 |
| 그 중 External 비트 | 20,591 | 5,505 |
| STYLE 레코드 | 832 | 838 |
| 빅폰트가 `0`으로 기록된 STYLE | 0 | 811 |
| XDATA typeface를 가진 STYLE | 705 | 0 |
| XREF 블록 | 133 | 133 |
| 그 중 경로가 남은 것 | 133 | 0 |

## 7. 레이어명 통계

레이어 레코드 4168개, 고유 이름 1190개.

| 접두 | 레코드 수 |
|---|---:|
| `(other)` | 2971 |
| `A-` | 975 |
| `DVM_` | 73 |
| `S-` | 44 |
| `H-` | 12 |
| `L-` | 11 |
| `AA_` | 7 |
| `HAT_` | 7 |
| `SYP_` | 7 |
| `XA_` | 6 |
| `G-` | 5 |
| `JD_` | 5 |
| `E-` | 5 |
| `C-` | 4 |
| `F-` | 4 |
| `DIM_` | 4 |
| `M_` | 4 |
| `E_` | 4 |
| `C_` | 4 |
| `X-` | 3 |

상위 40개 레이어명:

| 레이어 | 파일 수 |
|---|---:|
| `0` | 68 |
| `Defpoints` | 68 |
| `AREA` | 58 |
| `AA-BORD-TEXT` | 53 |
| `DIM` | 49 |
| `TEXT` | 45 |
| `AA-SYMB-BUBL` | 44 |
| `AA-TEXT-7` | 44 |
| `AA-SYMB-NAME` | 37 |
| `AA-SYMB-NAMEBOX` | 37 |
| `AA-XXXX-CNTL` | 34 |
| `A-ELEV-8` | 26 |
| `A-TEXT-ROOM` | 26 |
| `AA-LEAD-7` | 26 |
| `253` | 26 |
| `A-ELEV-2` | 25 |
| `PATH` | 23 |
| `@금강_REV` | 22 |
| `A-DIM` | 22 |
| `CEN` | 22 |
| `SYM` | 22 |
| `A-HDRL-5` | 21 |
| `INS` | 21 |
| `A-FEN` | 20 |
| `A-DOOR-4` | 19 |
| `A-OPEN-1` | 19 |
| `A-FURN-8` | 19 |
| `A-DOOR-SWNG` | 18 |
| `A-STAIR-LE` | 18 |
| `A-WIND-4` | 18 |
| `STUD` | 18 |
| `A-DIM-2` | 18 |
| `A-CEN-1` | 17 |
| `3NCC-ELE-3` | 17 |
| `252` | 17 |
| `A-SYM` | 17 |
| `AA-DIM` | 17 |
| `AA-DIMS` | 17 |
| `4` | 16 |
| `A-CONC-2` | 16 |

## 8. 상위 5장 시간·메모리

| id | 파일 | DWG MB | 엔티티 | acad-ts stats s / RSS | acad-ts dwg2dxf s / 출력 MB | libredwg parse s | dxfOut s / 출력 MB | 브라우저 피크 RSS | ezdxf s / RSS | ezdxf 결과 |
|---|---|---:|---:|---|---|---:|---|---:|---|---|
| S042 | 김화공업고등학교 모듈러 생활관 제작·설치 구매_전기도서 (1).dwg | 19.83 | 348,076 | 10.1 / 2331.30 MB | 50.7 / 152.09 | 7.4 | 1.3 / 111.29 | 3288.55 MB | 39.5 / 2534.23 MB | FAIL(ZeroDivisionError) |
| S045 | 02_기계소방내진도면(김화공고 모듈러 생활관 증축공사).dwg | 9.80 | 89,621 | 18.7 / 1037.55 MB | 5.5 / 59.20 | 3.9 | 0.5 / 44.57 | 1564.80 MB | 127.7 / 1359.52 MB | FAIL(DXFTableEntryError) |
| S043 | 김화공업고등학교 모듈러 생활관 제작·설치 구매_통신도서.dwg | 8.86 | 70,550 | 4.5 / 1074.94 MB | 7.2 / 64.72 | 3.7 | 0.6 / 46.18 | 1822.55 MB | 37.9 / 1315.92 MB | FAIL(DXFTableEntryError) |
| S041 | 01_기계도면(김화공고 모듈러 생활관 증축공사)_수정.DWG | 7.68 | 127,974 | 21.2 / 946.89 MB | 8.3 / 55.13 | 4.0 | 0.4 / 40.01 | 1461.14 MB | 14.6 / 1138.25 MB | FAIL(DXFTableEntryError) |
| S046 | 김화공업고등학교 모듈러 생활관 제작·설치 구매_전기소방도서 (3).dwg | 6.86 | 124,487 | 4.1 / 953.20 MB | 8.1 / 48.53 | 3.5 | 0.6 / 39.16 | 1543.72 MB | 14.9 / 827.09 MB | FAIL(DXFTableEntryError) |

## 9. 크기 밀도 (티어 1차 추정 계수)

| 형식 | 중앙값 B/엔티티 | 최소 | 최대 | 표본 |
|---|---:|---:|---:|---:|
| 원본 DWG (AutoCAD 작성) | 827 | 58 | 61258 | 68 |
| `dxfOut()` 산출 DXF | 950 | 257 | 47733 | 68 |
| acad-ts `dwg2dxf` 산출 DXF | 1470 | 409 | 66314 | 68 |

| 원본 DWG (>2 MB만) | 115 | 58 | 6674 | 10 |
| `dxfOut()` DXF (>2 MB만) | 522 | 328 | 47733 | 10 |
| acad-ts DXF (>2 MB만) | 693 | 409 | 66314 | 10 |

작은 도면은 로고 이미지·표제란 XREF·테이블 같은 고정비가 크기를 지배해서 B/엔티티가 수천까지 치솟는다. 1차 추정 계수는 내용이 크기를 지배하는 >2 MB 표본에서 읽어야 한다.

## 10. 한글 텍스트와 인코딩

| 항목 | acad-ts DXF | `dxfOut()` DXF |
|---|---:|---:|
| 한글 포함 문자열 | 20,435 | 20,422 |
| 모지바케 의심 문자열 | 0 | 0 |

양쪽 stats가 모두 성공한 26개 파일에서 `text_count` 일치 22건, `text_hash` 일치 22건.

티어 분포(엔티티 수 기준, ADR-0002 개정 §5): A 67 · B 1 · C 0.
