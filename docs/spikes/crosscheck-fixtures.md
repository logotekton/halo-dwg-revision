# 파서 교차검증 픽스처 결과표 (W2-04)

`tools/crosscheck.sh`가 생성한다 — **손으로 고치지 않는다.**
세 파서가 같은 R2018 DXF 바이트를 읽어 낸 `LayerStatsDocument`를 쌍별로 비교한 결과다
(ADR-0002 6, `docs/contracts/stats-definition.md` "비교 임계").

- 판정: 🟢 GREEN = 차이 없음, 🟡 AMBER = `halo_engine/validate/whitelist.yaml`이 사유와 함께
  설명하는 알려진 격차, 🔴 RED = 설명되지 않은 계약 위반.
- **카운트 격차(`count_by_type`, `text_count`, 한쪽에만 있는 버킷, INSERT 총개수 변화)는
  화이트리스트로 낮출 수 없다** — 아래 표의 AMBER에는 그런 항목이 없다.
- 재실행: `tools/crosscheck.sh` (`--no-build`로 빌드 생략, `--only F06`으로 한 픽스처만).

## 상태 표

| 픽스처 | ezdxf vs mlightcad | ezdxf vs acad-ts | mlightcad vs acad-ts | 레이어 수 |
|---|---|---|---|---|
| F01 | 🟡 AMBER (1황) | 🟡 AMBER (2황) | 🟡 AMBER (2황) | 5 |
| F02 | 🟡 AMBER (3황) | 🟡 AMBER (3황) | 🟡 AMBER (1황) | 5 |
| F03 | 🟡 AMBER (1황) | 🟡 AMBER (1황) | 🟡 AMBER (1황) | 1 |
| F04 | 🟢 GREEN | 🟢 GREEN | 🟢 GREEN | 1 |
| F05 | 🟡 AMBER (2황) | 🟡 AMBER (2황) | 🟡 AMBER (1황) | 3 |
| F06 | 🟡 AMBER (3황) | 🟡 AMBER (2황) | 🟡 AMBER (3황) | 5 |
| F07 | 🟡 AMBER (1황) | 🟡 AMBER (1황) | 🟡 AMBER (1황) | 2 |
| F08 | 🟡 AMBER (1황) | 🟡 AMBER (1황) | 🟡 AMBER (1황) | 3 |
| F09 | 🟡 AMBER (1황) | 🟡 AMBER (1황) | 🟡 AMBER (1황) | 4 |
| F10_grid | 🟡 AMBER (2황) | 🟡 AMBER (1황) | 🟡 AMBER (2황) | 2 |
| F10_host | 🟡 AMBER (1황) | 🟡 AMBER (1황) | 🟡 AMBER (1황) | 3 |

총 33 비교 — GREEN 3 / AMBER 30 / RED 0.

## 차이 상세 (GREEN인 비교는 생략)

### F01 — ezdxf vs mlightcad → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| GEOM-PHTM | MODEL | 🟡 AMBER | `length_sum_mm 8123.733824→9041.266317 (10.148% > 0.100% 허용)` | W01-mlightcad-spline-length |
| GEOM-PHTM | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 198.502mm > 1mm` | W04-mlightcad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `length_sum_mm 50714.822632→51632.366434 (1.777% > 0.100% 허용)` | W01-mlightcad-spline-length |

### F01 — ezdxf vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| GEOM-CTR | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 2124.123mm > 1mm` | W07-acad-polyline-bbox |
| GEOM-PHTM | MODEL | 🟡 AMBER | `length_sum_mm 8123.733824→7858.767103 (3.262% > 0.100% 허용)` | W03-acad-curve-length |
| GEOM-PHTM | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 4.503mm > 1mm` | W05-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `length_sum_mm 50714.822632→50449.687945 (0.523% > 0.100% 허용)` | W03-acad-curve-length |

### F01 — mlightcad vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| GEOM-CTR | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 2124.123mm > 1mm` | W07-acad-polyline-bbox |
| GEOM-PHTM | MODEL | 🟡 AMBER | `length_sum_mm 9041.266317→7858.767103 (13.079% > 0.100% 허용)` | W02-mlightcad-acad-curve-length |
| GEOM-PHTM | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 203.005mm > 1mm` | W06-mlightcad-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `length_sum_mm 51632.366434→50449.687945 (2.291% > 0.100% 허용)` | W02-mlightcad-acad-curve-length |

### F02 — ezdxf vs mlightcad → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| 0 | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 27.831mm > 1mm` | W04-mlightcad-derived-bbox |
| A-DOOR | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 361.291mm > 1mm` | W04-mlightcad-derived-bbox |
| A-TEXT | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 148.840mm > 1mm` | W04-mlightcad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 361.291mm > 1mm` | W04-mlightcad-derived-bbox |

### F02 — ezdxf vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| 0 | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 27.831mm > 1mm` | W05-acad-derived-bbox |
| A-DOOR | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 361.291mm > 1mm` | W05-acad-derived-bbox |
| A-TEXT | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W05-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 361.291mm > 1mm` | W05-acad-derived-bbox |

### F02 — mlightcad vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W06-mlightcad-acad-derived-bbox |

### F03 — ezdxf vs mlightcad → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 157.338mm > 1mm` | W04-mlightcad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 157.338mm > 1mm` | W04-mlightcad-derived-bbox |

### F03 — ezdxf vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 4967.565mm > 1mm` | W05-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 4967.565mm > 1mm` | W05-acad-derived-bbox |

### F03 — mlightcad vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 5124.904mm > 1mm` | W06-mlightcad-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 5124.904mm > 1mm` | W06-mlightcad-acad-derived-bbox |

### F05 — ezdxf vs mlightcad → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| 0 | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 2467.020mm > 1mm` | W04-mlightcad-derived-bbox |
| A-DIM | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 66.542mm > 1mm` | W04-mlightcad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 66.542mm > 1mm` | W04-mlightcad-derived-bbox |

### F05 — ezdxf vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| 0 | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 2467.020mm > 1mm` | W05-acad-derived-bbox |
| A-DIM | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 266.542mm > 1mm` | W05-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 266.542mm > 1mm` | W05-acad-derived-bbox |

### F05 — mlightcad vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-DIM | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 300.000mm > 1mm` | W06-mlightcad-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 300.000mm > 1mm` | W06-mlightcad-acad-derived-bbox |

### F06 — ezdxf vs mlightcad → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 43.690mm > 1mm` | W04-mlightcad-derived-bbox |
| X-GRID | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 320.000mm > 1mm` | W04-mlightcad-derived-bbox |
| X-TITLE | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 194.816mm > 1mm` | W04-mlightcad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 194.816mm > 1mm` | W04-mlightcad-derived-bbox |

### F06 — ezdxf vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W05-acad-derived-bbox |
| X-TITLE | MODEL | 🟡 AMBER | `insert_by_block.<unresolved> 0→1` | W09-acad-unresolved-block |
| X-TITLE | MODEL | 🟡 AMBER | `insert_by_block.X-TITLE 1→0` | W09-acad-unresolved-block |
| X-TITLE | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W05-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `insert_by_block.<unresolved> 0→1` | W09-acad-unresolved-block |
| (totals) | (all) | 🟡 AMBER | `insert_by_block.X-TITLE 1→0` | W09-acad-unresolved-block |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 50500.000mm > 1mm` | W05-acad-derived-bbox |

### F06 — mlightcad vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W06-mlightcad-acad-derived-bbox |
| X-GRID | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 320.000mm > 1mm` | W06-mlightcad-acad-derived-bbox |
| X-TITLE | MODEL | 🟡 AMBER | `insert_by_block.<unresolved> 0→1` | W09-acad-unresolved-block |
| X-TITLE | MODEL | 🟡 AMBER | `insert_by_block.X-TITLE 1→0` | W09-acad-unresolved-block |
| X-TITLE | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W06-mlightcad-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `insert_by_block.<unresolved> 0→1` | W09-acad-unresolved-block |
| (totals) | (all) | 🟡 AMBER | `insert_by_block.X-TITLE 1→0` | W09-acad-unresolved-block |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 50500.000mm > 1mm` | W06-mlightcad-acad-derived-bbox |

### F07 — ezdxf vs mlightcad → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 461.296mm > 1mm` | W04-mlightcad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 140.000mm > 1mm` | W04-mlightcad-derived-bbox |

### F07 — ezdxf vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W05-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 348.000mm > 1mm` | W05-acad-derived-bbox |

### F07 — mlightcad vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W06-mlightcad-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 348.000mm > 1mm` | W06-mlightcad-acad-derived-bbox |

### F08 — ezdxf vs mlightcad → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 396.330mm > 1mm` | W04-mlightcad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 396.330mm > 1mm` | W04-mlightcad-derived-bbox |

### F08 — ezdxf vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `text_hash 2f126cef169b37ea→ce7b75cac197146d` | W08-acad-trailing-a0-text |
| A-TEXT | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W05-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `text_hash 2f126cef169b37ea→ce7b75cac197146d` | W08-acad-trailing-a0-text |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 1183.670mm > 1mm` | W05-acad-derived-bbox |

### F08 — mlightcad vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `text_hash 2f126cef169b37ea→ce7b75cac197146d` | W08-acad-trailing-a0-text |
| A-TEXT | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W06-mlightcad-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `text_hash 2f126cef169b37ea→ce7b75cac197146d` | W08-acad-trailing-a0-text |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 1580.000mm > 1mm` | W06-mlightcad-acad-derived-bbox |

### F09 — ezdxf vs mlightcad → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 317.599mm > 1mm` | W04-mlightcad-derived-bbox |

### F09 — ezdxf vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W05-acad-derived-bbox |

### F09 — mlightcad vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W06-mlightcad-acad-derived-bbox |

### F10_grid — ezdxf vs mlightcad → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| X-GRID | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 100.000mm > 1mm` | W04-mlightcad-derived-bbox |
| X-TITLE | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 194.816mm > 1mm` | W04-mlightcad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 194.816mm > 1mm` | W04-mlightcad-derived-bbox |

### F10_grid — ezdxf vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| X-TITLE | MODEL | 🟡 AMBER | `insert_by_block.<unresolved> 0→1` | W09-acad-unresolved-block |
| X-TITLE | MODEL | 🟡 AMBER | `insert_by_block.X-TITLE 1→0` | W09-acad-unresolved-block |
| X-TITLE | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W05-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `insert_by_block.<unresolved> 0→1` | W09-acad-unresolved-block |
| (totals) | (all) | 🟡 AMBER | `insert_by_block.X-TITLE 1→0` | W09-acad-unresolved-block |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 67600.000mm > 1mm` | W05-acad-derived-bbox |

### F10_grid — mlightcad vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| X-GRID | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 100.000mm > 1mm` | W06-mlightcad-acad-derived-bbox |
| X-TITLE | MODEL | 🟡 AMBER | `insert_by_block.<unresolved> 0→1` | W09-acad-unresolved-block |
| X-TITLE | MODEL | 🟡 AMBER | `insert_by_block.X-TITLE 1→0` | W09-acad-unresolved-block |
| X-TITLE | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W06-mlightcad-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `insert_by_block.<unresolved> 0→1` | W09-acad-unresolved-block |
| (totals) | (all) | 🟡 AMBER | `insert_by_block.X-TITLE 1→0` | W09-acad-unresolved-block |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 67600.000mm > 1mm` | W06-mlightcad-acad-derived-bbox |

### F10_host — ezdxf vs mlightcad → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 최대 코너 편차 55.662mm > 1mm` | W04-mlightcad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 42.838mm > 1mm` | W04-mlightcad-derived-bbox |

### F10_host — ezdxf vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W05-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 280.000mm > 1mm` | W05-acad-derived-bbox |

### F10_host — mlightcad vs acad-ts → 🟡 AMBER

| 레이어 | 공간 | 상태 | 원인 | 근거 |
|---|---|---|---|---|
| A-TEXT | MODEL | 🟡 AMBER | `bbox 누락 (other 문서에 없음)` | W06-mlightcad-acad-derived-bbox |
| (totals) | (all) | 🟡 AMBER | `bbox 최대 코너 편차 280.000mm > 1mm` | W06-mlightcad-acad-derived-bbox |

## 인용된 화이트리스트 항목

- **W01-mlightcad-spline-length** — mlightcad 1.14.3의 SPLINE 길이는 계약이 요구하는 flattening(0.01) 급 근사가 아니라 더 성긴 근사여서 F01의 SPLINE 버킷에서 ezdxf 대비 약 10% 크다 (docs/contracts/stats-definition.md "통합에서 확정된 사항" 알려진 격차 (1)). 후속: cad-core가 NURBS를 직접 평탄화(W3-02 또는 별도 태스크).
- **W02-mlightcad-acad-curve-length** — 같은 SPLINE 근사 격차의 반대편 조합. mlightcad는 계약보다 성기게(F01에서 +10%), acad-ts는 계약보다 촘촘하지 않게(-3%) 평탄화해 둘 사이 편차가 가장 크다(약 13%). 두 구현 중 어느 쪽도 ezdxf flattening(0.01)을 재현하지 않는다.
- **W03-acad-curve-length** — acad-ts는 SPLINE/ELLIPSE를 자체 polygonalVertexes 정밀도로 평탄화한다 (packages/acad-bridge/src/acad/length.ts의 flatteningPrecision). F01의 SPLINE 버킷에서 ezdxf flattening(0.01) 대비 약 3.3% 짧다. packages/acad-bridge/README.md "stats: schema and contract notes" 마지막 항목이 이 값을 조일지 화이트리스트로 둘지 W2-04/G1에 넘겼고, 여기서 화이트리스트로 둔다(카운트 격차가 아니고, 정밀도 상향은 acad-bridge 소유 태스크의 패치 사항이다).
- **W04-mlightcad-derived-bbox** — 파생 extents 격차. mlightcad는 자체 폰트 메트릭과 블록 전개로 extents를 계산하고 ezdxf는 ezdxf.bbox로 계산해 텍스트·블록·치수·스플라인이 든 버킷에서 수십~수백 mm 차이가 난다(packages/cad-core/README.md "알려진 한계" 3, stats-definition.md 알려진 격차 (2)). 순수 기하만 든 버킷은 ±1mm 안에서 맞는다.
- **W05-acad-derived-bbox** — 같은 파생 extents 격차. acad-ts는 여기에 더해 getBoundingBox()가 던지는 엔티티를 합집합에서 빼고 *.drops.json에 기록하므로(packages/acad-bridge/README.md "Known acad-ts gaps" 2) 텍스트만 있는 버킷은 bbox 자체가 비기도 한다.
- **W06-mlightcad-acad-derived-bbox** — 위 두 항목과 같은 파생 extents 격차의 세 번째 조합. 두 파서 모두 ezdxf와 다르고 서로도 다르다.
- **W07-acad-polyline-bbox** — acad-ts의 SeqendCollection이 종결자(SEQEND/VERTEX)를 원소로 흘려 보내 Polyline2D.getBoundingBox()가 던진다(packages/acad-bridge/README.md "Known acad-ts gaps" 2). acad-bridge가 try/catch로 감싸 그 엔티티를 bbox 합집합에서 제외하고 드롭으로 기록하므로 구식 2D POLYLINE이 든 버킷(F01 GEOM-CTR)의 bbox가 좁게 나온다. 카운트·길이는 영향받지 않는다.
- **W08-acad-trailing-a0-text** — acad-ts 3.1.0 DXF 리더가 텍스트 값의 **후행 0xA0 바이트를 잘라낸다**(cp1252에서 NBSP라 공백으로 보고 트림하는 것으로 보인다). UTF-8 한글의 마지막 바이트가 0xA0인 글자(예: '고' = EA B3 A0)로 끝나는 문자열은 바이트열이 잘려 유효한 UTF-8이 아니게 되고, acad-bridge의 디코드 복구(src/acad/decode-fix.ts, main 1ca713a)는 치환문자가 나오면 복구를 포기하도록 설계돼 있어 모지바케가 남는다. F01~F10에서 남은 사례는 F08 A-TEXT의 '층고' 하나뿐이며(실측: 'ì¸µê³' = EC B8 B5 EA B3, 5바이트), 그 외 한글 픽스처(F03/F06/F07/F09/F10_grid)의 text_hash는 세 파서가 정확히 일치한다. text_count는 항상 일치하므로 카운트 격차가 아니다. 근본 해결은 acad-ts 상류 수정 (보고서 "Questions for gate"/"Follow-ups").
- **W09-acad-unresolved-block** — 블록과 레이어가 같은 이름을 쓰면(F06/F10_grid의 X-TITLE 도곽) acad-ts의 DxfReader가 INSERT의 블록 참조를 null로 남겨 acad-bridge가 블록명을 "<unresolved>"로 기록한다(packages/acad-bridge/README.md "Known acad-ts gaps" 1). INSERT **총개수는 양쪽이 같다** — 이름만 못 푼 것이라 비교기가 총개수 일치를 확인한 경우에만 이 항목이 적용된다(총개수가 다르면 카운트 격차로 RED 유지). 근본 해결은 acad-bridge 쪽 패치(보고서 "Shared-file patch") 또는 acad-ts 상류 수정.
