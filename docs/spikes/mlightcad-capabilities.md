# mlightcad 1.6.3 편집 capability 매트릭스 (W1-04)

작성: 2026-09-02 · 근거: `spikes/mlightcad/results/browser-facts.json` (`cmd-inventory` 프로브, 실행 시점 등록 명령 **135개**) + `node_modules/@mlightcad/*/lib/**/*.d.ts`
행 목록의 출처: `docs/PLAN.md` §7 (W4-01 · W4-03 · W4-04)
미확정 행은 없다. 모든 행이 **제공 / 부분 / 미제공** 중 하나로 판정됐다.

판정 기준
- **제공** — 등록된 명령 또는 공개 API가 있고 스파이크에서 동작을 확인했다.
- **부분** — 하위 API·프리미티브는 있으나 명령/UX가 없거나 범위가 좁다.
- **미제공** — 명령도 API도 없다(타입 선언 전수 검색으로 확인).

"우리가 만들 것" 열의 태스크 ID는 `docs/PLAN.md` §7 기준.

---

## 1. 선택 · 측정 · 표시

| 편집 항목 | 1.6.3 제공 여부 | 명령명 또는 API | 품질 메모 | 우리가 만들 것 |
|---|---|---|---|---|
| 선택(클릭) | 제공 | `SELECT`(별칭 `SE`) · `AcTrView2d.select(point)` · `pick(point, hitRadiusPx, pickOneOnly)` | `point`는 월드 좌표, `hitRadius`는 픽셀. 실측 원 둘레+해치 2건 정확히 반환 | 래핑만 (W3-02 `CadHost.pick`) |
| 선택(박스) | 제공 | `AcTrView2d.selectByBox(box)` · `AcEdBaseView.selectByBoxWithMode(box, mode, action)` | `AcEdSelectionMode = 'window' \| 'crossing'`, `AcEdSelectionAction = 'replace' \| 'add' \| 'remove'`. `selectByBox`는 crossing+add 고정 | 래핑 (W4-01) |
| 선택 필터 | 제공 | `AcEdSelectionFilter(values: AcDbTypedValue[])` · `.matches(entity)` · `AcEditor.selectAll(filter?)` | ssget 식 필터. 레이어/타입 필터에 충분 | 래핑 (W4-01) |
| 선택 집합 관리 | 제공 | `AcTrView2d.selectionSet` → `AcEdSelectionSet { ids, count, add, delete, has, clear }` + `events.selectionAdded/selectionRemoved` | 이벤트 실측 확인 | 래핑 (W3-02 `onSelectionChanged`) |
| 하이라이트 | 제공 | `AcTrView2d.highlight(ids)` / `unhighlight(ids)` · `AcTrLayout`의 hover/선택 하이라이트 | 레이어별 벌크 호출로 묶여 처리 | 래핑 (W3-02) |
| 줌·팬 | 제공 | `ZOOM`(`Z`), `PAN`(`P`) · `zoomTo(box, margin)`, `zoomToFitDrawing(timeout?, layoutBtrId?)`, `zoomToFitLayer(name)`, `flyTo(point, scale)` | 실측 전부 동작 | 래핑 (W3-02 `zoomTo`) |
| 객체 숨기기/격리 | 제공 | `HIDEOBJECTS`, `UNISOLATEOBJECTS` · `AcApDocument.isObjectHidden/addHiddenObject/takeHiddenObjects` | — | 그대로 사용 (W3-04) |
| 측정: 거리 | 제공 | `MEASUREDISTANCE`(`DI`, `DIST`) | 모드 `Read` — 읽기 전용 문서에서도 측정 가능 | 그대로 사용 (W4-01) |
| 측정: 면적 | 제공 | `MEASUREAREA`(`AA`, `AREA`) | 동일 | 그대로 사용 |
| 측정: 각도 | 제공 | `MEASUREANGLE`(`ANG`) | 동일 | 그대로 사용 |
| 측정: 호 | 제공 | `MEASUREARC` | 동일 | 그대로 사용 |
| 측정: 점(좌표) | 제공 | `MEASUREPOINT` | 동일 | 그대로 사용 |
| 측정 관리 | 제공 | `CLEARMEASUREMENTS`, `MEASUREMENTVIS`, `MEASUREMENTEXPORT`, `MEASUREMENTIMPORT`, `MEASUREMENT`, `MEASUREMENTCOLOR` · `AcApMeasurementStore` / `AcApMeasurementHistory` · 사이드카 `parseMeasurementSidecar`/`stringifyMeasurementSidecar`/`measurementSidecarFileName` | 측정값은 사이드카 JSON에 남고 DWG 엔티티가 아니다 → CLAUDE.md 5(측정값은 적산에 넣지 않음)와 정합 | 한국어 UI만 (W4-01) |
| 객체 스냅 | 제공 | `AcEdOsnapResolver`, `AcEdOSnapMarkerManager`, `AcDbOsnapMode`(EndPoint/MidPoint/Center/Node/Quadrant/…), 엔티티 `subGetOsnapPoints(...)`, 시스템 변수 `OSMODE` | — | 한국어 UI만 |
| 직교/극좌표 추적 | 제공 | `AcEdOrthoMode`, `AcEdPolarTracking` · `ORTHOMODE`, `POLARMODE`, `POLARANG`, `POLARADDANG` | — | 한국어 UI만 |
| 속성(특성) 보기·편집 | 제공 | `AcDbEntity.properties: AcDbEntityProperties` — 그룹별 `AcDbEntityRuntimeProperty { name, type, editable?, options?, accessor: { get, set? } }` | 폴리라인 실측: `general`(handle/color/layer/linetype/linetypeScale/lineWeight/transparency) · `geometry`(vertices/elevation/**length**) · `others`(closed). 패널 UI는 없음 | 패널 UI 신규 (W4-01) |

## 2. 기하 편집

| 편집 항목 | 1.6.3 제공 여부 | 명령명 또는 API | 품질 메모 | 우리가 만들 것 |
|---|---|---|---|---|
| 이동 | 제공 | `MOVE`(`M`) — `AcApMoveCmd` + `AcApMovePreviewJig` · `AcApEntityService.translateEntities(entities, displacement)` / `transformEntities(entities, matrix)` | 드래그 미리보기 있음. 실측 1건 이동 성공 | 그대로 사용 |
| 복사 | 제공 | `COPY`(`CO`) — `AcApCopyCmd` + `AcApCopyPreviewJig` · `AcApEntityService.cloneAndTransform(entities, matrix, { append })` | 다중 복사 지원. 실측 성공 | 그대로 사용 |
| 회전 | 제공 | `ROTATE`(`RO`) — `AcApRotateCmd` + `AcApRotatePreviewJig` · `AcApEntityService.rotateEntities(entities, basePoint, angleRad)` | 실측 성공 | 그대로 사용 |
| 삭제 | 제공 | `ERASE`(`E`) · `AcApEntityService.eraseEntities(objectIds)` | 실측 성공 | 그대로 사용 |
| 간격띄우기(offset) | 제공 | `OFFSET`(`O`) — `AcApOffsetCmd` · `AcDbCurve.getOffsetCurves(dist)`, `getOffsetSideAtPoint(point)`, `acgeOffsetVertexPath` | 커브 단위 오프셋. 폴리라인은 `AcDbPolyline.getOffsetCurves` 구현 있음 | 그대로 사용 |
| 축척(scale) | 미제공 | 없음 — `SCALE` 명령 없음, `AcApScaleCmd` 없음 | 프리미티브는 있다: `AcDbEntity.transformBy(AcGeMatrix3d)` + `AcApEntityService.transformEntities` + `AcGeMatrix3d.makeScale` | **신규 (W4-03)** |
| 대칭(mirror) | 미제공 | 없음 — 타입 선언 전수 검색에서 mirror 명령/메서드 없음(문자열 일치는 아이콘·프롬프트 텍스트뿐) | 프리미티브: `transformBy(AcGeMatrix3d)` 반사 행렬. 문자 엔티티의 미러 텍스트(MIRRTEXT) 처리는 직접 구현 | **신규 (W4-03)** |
| 늘리기(stretch) | 미제공 | 없음 — `stretch` 식별자 전무 | 그립 이동(`subMoveGripPointsAt`)을 crossing 선택과 조합해 구현 | **신규 (W4-03)** |
| 자르기(trim) | 미제공 | 없음 | 프리미티브: `acgeIntersectCurves(a, b, extendA?, extendB?, projPlane?)` + `AcDbEntity.subGetIntersectCurves()`(→ `AcGeIntersectPrimitive` union) + `AcDbIntersect` | **신규 (W4-03)** |
| 연장(extend) | 미제공 | 없음 | 동일 프리미티브. `acgeIntersectCurves`의 `extendA`/`extendB` 플래그가 정확히 이 용도 | **신규 (W4-03)** |
| 결합(join) | 미제공 | 없음 | 프리미티브: `AcDbPolyline.addVertexAt` / `AcDbPolyline.from2dPoints(points, closed)` / `fromGePolyline(AcGePolyline2d)` | **신규 (W4-03)** |
| 끊기(break) | 미제공 | 없음 | 프리미티브: `acgeIntersectCurves` + `AcDbPolyline.reset(reuse, numVerts?)` / `removeVertexAt` | **신규 (W4-03)** |
| 분해(explode) | 미제공 | 없음 — `explode` 식별자 전무 | 프리미티브: `AcDbBlockReference.blockTransform`(4×4) + `blockTableRecord.newIterator()` + `entity.clone()` + `transformBy`. `AcDbBlockTableRecord.explodability` 플래그로 허용 여부 판단 | **신규 (W4-03)** |
| 모깎기/모따기(fillet/chamfer) | 미제공 | 없음 — `RECTANG` 잼의 코너 옵션과 i18n 문자열에만 등장 | PLAN §7이 명시적으로 **범위 밖**이라 함 | 만들지 않음 |
| 그립 편집 | 제공 | `AcTrView2d.gripManager: AcEdGripManager { isDragging, refresh(), dispose() }` · `AcEdGripEditSession`, `AcEdGripHandle`, `AcEdGripAppearance`, `AcEdGripPreviewJig`, `acedShouldShowGrips(openMode, editorActive, mtextEditorActive, selectionCount, gripObjLimit)` · 엔티티 `subGetGripPoints()` / `subMoveGripPointsAt(indices, offset)` · 시스템 변수 `GRIPS`, `GRIPSIZE`, `GRIPCOLOR`, `GRIPHOT`, `GRIPOBJLIMIT` | 마우스 드래그 그립 편집이 뷰에 내장. 그립 정책은 `Write` 모드에서만 표시 | 한국어 UI·설정만 (W4-03) |
| 정점 편집 | 부분 | `AcDbPolyline.addVertexAt(i, pt, bulge?, startWidth?, endWidth?)`, `removeVertexAt(i)`, `reset(reuse, numVerts?)`, `numberOfVertices`, `closed` · 그립으로 정점 이동 · `properties.geometry.vertices`(읽기 전용 배열, `{x,y,bulge,startWidth,endWidth}`) | 이동은 그립으로 되지만 **정점 추가/삭제 명령(PEDIT 상당)이 없다**. API는 전부 있다 | **명령 신규 (W4-03)** |
| undo / redo | 제공 | `UNDO`(`U`), `REDO` · `acapRunDatabaseEdit(db, label, fn)` · `AcDbDatabase.runDatabaseEdit(label, fn)` · `db.transactionManager.{startUndoMark,endUndoMark,cancelUndoMark,undo,redo,canUndo,canRedo,clearUndoStack}` · 이벤트 `undo-stack-changed`, `session-db-edit-committed` | 실측: append→undo→redo 카운트 9/10/9/10 정확. 마크업·측정은 별도 히스토리(`AcApMarkupHistory`/`AcApMeasurementHistory`)라 **DB undo와 세션 undo를 우리가 통합해야 한다** | 통합 러너 (W3-02) |
| 특성 일치(match properties) | 미제공 | 명령 없음 | 프리미티브: 정적 `AcApEntityService.copyDisplayTraits(source, target)` — 색·레이어·선종류·선가중치·투명도를 복사. 명령/UX만 만들면 된다 | **신규 (W4-03)** |
| 현재 레이어로 이동 | 제공 | `LAYCUR` · `AcApEntityService.moveEntitiesToCurrentLayer(objectIds)` → `{ changedCount, alreadyCurrent, missing, currentLayerMissing }` | — | 그대로 사용 |

## 3. 생성 명령

| 편집 항목 | 1.6.3 제공 여부 | 명령명 또는 API | 품질 메모 | 우리가 만들 것 |
|---|---|---|---|---|
| 선 | 제공 | `LINE`(`L`) — `AcApLineCmd` | 연속 입력·잼 미리보기 | 그대로 사용 |
| 폴리라인 | 제공 | `PLINE`(`PL`) — `AcApPolylineCmd` | 벌지(호 세그먼트) 입력 지원 | 그대로 사용 |
| 사각형 | 제공 | `RECTANG`(`REC`) — `AcApRectCmd` | 코너 fillet/chamfer 옵션 포함 | 그대로 사용 |
| 다각형 | 제공 | `POLYGON`(`POL`) — `AcApPolygonCmd` | PLAN 목록 밖이지만 보너스 | 그대로 사용 |
| 원 | 제공 | `CIRCLE`(`C`) — `AcApCircleCmd` | — | 그대로 사용 |
| 호 | 제공 | `ARC`(`A`) — `AcApArcCmd` | — | 그대로 사용 |
| 타원 | 제공 | `ELLIPSE`(`EL`) — `AcApEllipseCmd` | — | 그대로 사용 |
| 스플라인 | 제공 | `SPLINE`(`SPL`) — `AcApSplineCmd` | — | 그대로 사용 |
| 점 | 제공 | `POINT`(`PO`) — `AcApPointCmd` · `PDMODE` | — | 그대로 사용 |
| 구성선/광선 | 제공 | `XLINE`(`XL`), `RAY`(`RA`) | — | 그대로 사용 |
| 다중선 | 제공 | `MLINE`(`ML`) — `AcApMLineCmd` · `CMLSTYLE`, `CMLSCALE` | — | 그대로 사용 |
| 자유 곡선 | 제공 | `SKETCH` — `AcApSketchCmd` | — | 그대로 사용 |
| 해치 | 부분 | `-HATCH`(`-H`) — `AcApHatchCmd`. 시스템 변수 `HPNAME`, `HPSCALE`, `HPANG`, `HPCOLOR`, `HPBACKGROUNDCOLOR`, `HPTRANSPARENCY`, `HPLAYER`, `HPASSOC`, `HPDOUBLE`, `HPISLANDDETECTION`, `HPSEPARATE`. 패턴 파서 `AcDbPatParser`, 미리보기 `AcDbPatSvgRenderer`, 프리셋 `AcDbPredefinedAcadPat` / `AcDbPredefinedAcadIsoPat` | **명령줄 버전만 있고 대화상자가 없다**(이름이 `-HATCH`인 이유). 패턴 선택 UI는 우리가 만든다. 읽기 쪽 `AcDbHatch.area`는 실측 정확(3600) | 대화상자 UI (W4-04) |
| 문자(MTEXT) | 제공 | `MTEXT`(`T`) — `AcApMTextCmd` · 인라인 편집기 `AcEdMTextEditor` (옵션 `AcEdMTextEditorOptions { view, location, width, textHeight, initialText?, initialAttachmentPoint?, toolbarFontFamilies?, toolbarColorPicker?, toolbarEnabled? }`, 결과 `AcEdMTextEditorResult { contents, location, width, height, lineSpacingFactor, attachmentPoint }`). MTEXT 더블클릭 시 `AcTrView2d`가 자동으로 연다 | 편집기는 `@mlightcad/mtext-input-box`(dist에 인라인) 기반이고 IME 처리는 **공개 타입 표면에 없다**(번들 내부에만 존재) → **한글 IME 입력은 W3-05에서 실기기 검증 필요** | 그대로 사용 + 한글 IME 검증 |
| 문자(단일행 TEXT) | 미제공 | `TEXT`/`DTEXT` 명령 없음 | 엔티티 `AcDbText`는 읽기·렌더 모두 지원. 생성은 `new AcDbText()` + `appendEntity` | **신규 (W4-04)** — 또는 MTEXT로 통일 |
| 치수: 선형 | 제공 | `DIMLINEAR`(`DLI`) — `AcApDimLinearCmd` | **모드가 `Review`(4)** 라 읽기 전용에 가까운 문서에서도 실행된다 — 우리 쪽 쓰기 가드로 막아야 한다 | 래핑 + 가드 (W4-04) |
| 치수: 정렬·각도·반지름·지름·좌표 | 미제공 | 명령 없음 | 엔티티는 전부 있다: `AcDbAlignedDimension`, `AcDb3PointAngularDimension`, `AcDbArcDimension`, `AcDbRadialDimension`, `AcDbDiametricDimension`, `AcDbOrdinateDimension`, `AcDbRotatedDimension` (읽기·렌더 지원) | **신규 (W4-04)** |
| 지시선(leader/multileader) | 미제공 | 명령 없음 | 엔티티 `AcDbLeader`, `AcDbMLeader`(+ `AcDbMLeaderStyle`, `CMLEADERSTYLE`)는 읽기·렌더 지원. 마크업 `MARKUPCALLOUT`이 유사 UX이지만 **DWG 엔티티가 아니라 사이드카**다 | **신규 (W4-04)** |
| 구름형 리비전 | 제공 | `REVCLOUD` — `AcApRevCloudCmd` + `AcApRevCloudGeom` | DWG 엔티티로 생성 | 그대로 사용 |
| 이미지 첨부 | 제공 | `IMAGEATTACH`(`IAT`) — `AcApImageAttachCmd` · `AcDbRasterImage`, `AcDbRasterImageDef` | 원본 불변 규칙상 파생본에서만 | 정책 가드 |
| 블록 삽입 | 제공 | `-INSERT`(`I`) — `AcApInsertCmd` + `AcApBlockInsertSession` + `isInsertableBlockName` · 미리보기 `AcApBlockPreviewConvertor` | **명령줄 버전만**. 블록 라이브러리/미리보기 팔레트는 없다 | 팔레트 UI (W4-04) |
| 블록 속성 편집 | 미제공 | 뷰어가 더블클릭 시 `sendStringToExecute("attedit")`를 호출하지만 **`ATTEDIT` 명령은 등록돼 있지 않다**(등록 명령 135개에 없음). 호스트가 플러그인으로 제공하는 것을 전제한 훅이다 | 읽기·쓰기 API는 있다: `AcDbBlockReference.attributeIterator()`, `appendAttributes(attrib)`, `syncAttributeDatabases()`, `AcDbAttribute.tag/textString`. 실측 ATTRIB 값 `대명건설 신축공사` 정상 | **`ATTEDIT` 플러그인 신규 (W4-04)** |
| 레이어 CRUD | 제공 | `-LAYER`(`-LA`), `LAYCUR`, `LAYDEL`, `LAYERP`, `LAYFRZ`, `LAYTHW`, `LAYLCK`, `LAYULK`, `LAYON`, `LAYOFF`, `LAYISO`, `LAYUNISO`, `LAYERCLOSE` · `AcApLayerService`(생성/삭제/복원/색·선종류·선가중치·투명도·플롯 여부/격리/스냅샷) · `AcApLayerStore`, `AcLyLayerFilterTree`(레이어 필터) | 13개 명령 + 서비스 API 완비. `deleteLayer`는 엔티티 스냅샷을 반환해 `restoreDeletedLayer`로 되돌릴 수 있다. **대화형 `LAYER` 팔레트 명령은 등록되지 않는다** — 별칭 표에는 `LAYER: ['LA']`가 있지만 라이브러리가 등록하는 명령은 `-LAYER`뿐이다(팔레트는 상류 Vue 셸이 제공). 이벤트 `close-layer-manager`가 팔레트 연동 훅 | 한국어 패널 + `LAYER` 명령 신규 (W3-04) |
| XREF 부착 | 부분 | `XATTACH`(`XA`) · `AcApXrefManager.attachOverlay({...})` | 오버레이 지오메트리가 **INSERT 전개·뷰포트·치수를 건너뛴다**(상류 JSDoc). 자동 해석 없음 | 정본 DXF 임베드로 대체 (W3-06 / ADR-0002) |

## 4. 파일 · 뷰 · 시스템

| 항목 | 1.6.3 제공 여부 | 명령명 또는 API | 품질 메모 | 우리가 만들 것 |
|---|---|---|---|---|
| 열기 | 제공 | `OPEN`(`OP`) · `AcApDocManager.openDocument(name, ArrayBuffer, options, view?)` / `openUrl(url, options)` | `builtinOpenFileDialog: false`로 내장 다이얼로그를 끄고 우리 IPC를 붙인다. **DWG 경로는 입력 ArrayBuffer를 워커로 transfer해 detach시킨다** | 래핑 (W3-02) |
| 새 도면 | 제공 | `QNEW` · `newDocument(options?)` | 템플릿을 `${baseUrl}/templates/acadiso.dxf`에서 받는다 → 로컬 호스팅 필수 | 로컬 템플릿 배치 |
| 닫기 | 제공 | `CLOSE` · `closeDocument(doc?)` | 마지막 문서를 닫으면 새 Untitled로 대체된다 | 래핑 |
| DXF 내보내기 | 제공 | `CDXF` — `AcApConvertToDxfCmd` / `AcApDxfConvertor` · `AcDbDatabase.dxfOut(fileName?, precision?, version?, options?)` | 왕복 실측 결과는 `mlightcad-api.md` §C.7. 핸들·레이어·블록·한글 보존 | 래핑 (W4-05) |
| PNG 내보내기 | 제공 | `PNGOUT` — `AcApConvertToPngCmd` / `AcApPngConvertor` | 썸네일 생성에 사용 가능 | 그대로 사용 |
| PDF/SVG 내보내기 | 미제공 | 없음 | `AcDbPatSvgRenderer`는 해치 패턴 미리보기 전용이라 도면 SVG 출력이 아니다 | **신규 (W4-06)** |
| DWG 저장 | 미제공 | 없음 — data-model에 DWG writer가 없다 | libredwg-web도 읽기 전용 경로만 쓴다 | `@node-projects/acad-ts` (W2-05 / W4-05) |
| 레이아웃 전환 | 제공 | `AcTrView2d.activeLayoutBtrId` · `AcApDocManager.setActiveLayout(view?, db?)` · `AcTrLayoutViewManager` · `AcDbLayoutManager.events.layoutSwitched` | 레이아웃 탭 UI는 없다 | 탭 UI (W3-01) |
| 뷰포트 드릴다운 | 제공 | `AcTrView2d.pick()` 내장(`pickThroughViewports`) | 뷰포트 내부 클릭 → 모델 엔티티, 테두리 클릭 → `AcDbViewport`. MSPACE/PSPACE·CVPORT는 **의도적으로 미구현** | 그대로 사용 |
| MDI | 제공 | `documents`, `documentCount`, `document(i)`, `activateDocument`, `closeDocument`, `ensureSplitView(container)` | 실측 2문서 동시 오픈·전환 성공 | 탭 UI (W3-01) |
| 비교 표시(diff) | 제공 | `setCompareDisplay(AcApCompareDisplayOptions, view?)`, `setOverlayCompareDisplay(overlayId, options, view?)` · 시스템 변수 `COMPAREPROPS`, `COMPARETOLERANCE`, `COMPARETEXT`, `COMPAREHATCH`, `COMPARERCMARGIN` · 상수 `ACDB_COMPAREPROPS_*` | **W5-03 / W7-01의 시각 diff에 바로 쓸 수 있다.** 오버레이 제약(INSERT/치수/뷰포트 생략)은 그대로 적용된다 | 활용 (W5-03) |
| 마크업 | 제공 | 14개 명령 + `AcApMarkupStore` / `AcApMarkupHistory` / 사이드카 JSON(v1) | 기하가 뷰 로컬이라 DWG를 더럽히지 않는다 → 원본 불변 규칙과 정합 | 한국어 UI + DMS 연동 (W5-02) |
| 플러그인 | 제공 | `AcApPluginManager.loadPlugin/registerLazyPlugin/loadByTrigger/unloadPlugin/loadPluginsFromConfig/loadPluginsFromFolder` | 자체 명령은 별도 그룹(`DMCAD`)으로 등록해 상류 명령과 충돌을 피한다 | W4-03 / W4-04 배선 |
| 시스템 변수 | 제공 | `AcDbSysVarManager`, `AC_DB_SYSTEM_VARIABLE_NAMES`, `AcDbSystemVariables` · 이벤트 `AcEditor.events.sysVarChanged` · 명령 형태로도 노출(아래 부록) | 등록 명령 135개 중 **57개가 시스템 변수 명령**이다 | 필요한 것만 UI 노출 |
| 스크립트 실행 | 제공 | `runScript(scriptText)`, `executeCommandString(cmdStr)` · `AcApScriptParser` | e2e 테스트 훅으로 유용(W2-07) | 테스트에 활용 |

---

## 5. 요약 — W4-03/W4-04가 만들어야 할 것

**W4-03 (기하 편집 보충, Opus 2일):** 축척 · 대칭 · 늘리기 · 자르기 · 연장 · 결합 · 끊기 · 분해 · 정점 추가/삭제 · 특성 일치 — **10개 명령**.
전부 하위 프리미티브(`transformBy`, `acgeIntersectCurves`, `subGetGripPoints`/`subMoveGripPointsAt`, `AcDbPolyline.*VertexAt`, `blockTransform`, `copyDisplayTraits`)가 이미 있으므로 **명령 계층만 새로 쓰면 된다.** 모두 `AcEdCommand` 서브클래스 + `acapRunDatabaseEdit` 래핑 + `DMCAD` 명령 그룹.

**W4-04 (생성 명령 + 레이어 CRUD):** 단일행 TEXT · 치수 5종(정렬/각도/반지름/지름/좌표) · 지시선(MLEADER) · `ATTEDIT`(블록 속성 편집) · 해치 대화상자 · 블록 삽입 팔레트 — **명령 8개 + UI 3개**. 레이어 CRUD는 명령·서비스가 완비되어 **한국어 패널만** 만든다.

**PLAN §7의 편집 목록 대비 커버리지:** 25개 항목 중 제공 13 · 부분 3 · 미제공 9.

---

## 부록 A. 등록된 명령 135개 (실행 시점 열거)

`docManager.commandManager.iterator()` 결과. 모두 그룹 `ACAD`.
모드는 `AcEdOpenMode`(Read 0 / Review 4 / Write 8)이며 **높은 값이 낮은 값과 호환**된다. 즉 `Write` 문서에서는 세 그룹 모두 실행된다.
집계: **Write 36 · Read 29 · Review 70 = 135**.

### A.1 Write (36) — 도면을 변경하는 명령

`-HATCH`(`-H`), `-INSERT`(`I`), `-LAYER`(`-LA`), `ARC`(`A`), `CIRCLE`(`C`), `COPY`(`CO`), `ELLIPSE`(`EL`), `ERASE`(`E`), `IMAGEATTACH`(`IAT`), `LAYCUR`, `LAYDEL`, `LAYERP`, `LAYFRZ`, `LAYISO`, `LAYLCK`, `LAYOFF`, `LAYON`, `LAYTHW`, `LAYULK`, `LAYUNISO`, `LINE`(`L`), `MLINE`(`ML`), `MOVE`(`M`), `MTEXT`(`T`), `OFFSET`(`O`), `PLINE`(`PL`), `POINT`(`PO`), `POLYGON`(`POL`), `RAY`(`RA`), `RECTANG`(`REC`), `REVCLOUD`, `ROTATE`(`RO`), `SKETCH`, `SPLINE`(`SPL`), `XATTACH`(`XA`), `XLINE`(`XL`)

### A.2 Read (29) — 파일·뷰·측정

`ABOUT`, `CACHEFONT`, `CDXF`, `CLEARMEASUREMENTS`, `CLOSE`, `ENTOUT`, `HIDEOBJECTS`, `LAYERCLOSE`, `LOG`, `MARKUPEXPORT`, `MEASUREANGLE`(`ANG`), `MEASUREARC`, `MEASUREAREA`(`AA`,`AREA`), `MEASUREDISTANCE`(`DI`,`DIST`), `MEASUREMENTEXPORT`, `MEASUREMENTIMPORT`, `MEASUREMENTVIS`, `MEASUREPOINT`, `OPEN`(`OP`), `PAN`(`P`), `PNGOUT`, `QNEW`, `REDO`, `REGEN`(`RE`), `SELECT`(`SE`), `SWITCHBG`, `UNDO`(`U`), `UNISOLATEOBJECTS`, `ZOOM`(`Z`)

### A.3 Review (70) — 마크업 + 시스템 변수 + 선형 치수

마크업(12): `MARKUPTEXT`, `MARKUPLINE`, `MARKUPARROW`, `MARKUPCLOUD`, `MARKUPRECT`, `MARKUPCIRCLE`, `MARKUPHIGHLIGHT`, `MARKUPCALLOUT`, `MARKUPSTAMP`, `MARKUPVIS`, `MARKUPIMPORT`, `CLEARMARKUPS`
측정 설정(2): `MEASUREMENT`, `MEASUREMENTCOLOR`
치수(1): `DIMLINEAR`(`DLI`) — **생성 명령인데 모드가 `Review`다. 우리 쪽 쓰기 가드가 필요하다.**
시스템 변수(55): `ANGBASE`, `ANGDIR`, `AUNITS`, `AUPREC`, `CECOLOR`, `CELTSCALE`, `CELTYPE`, `CELWEIGHT`, `CETRANSPARENCY`, `CLAYER`, `CMLEADERSTYLE`, `CMLSCALE`, `CMLSTYLE`, `COLORTHEME`, `COMPAREHATCH`, `COMPAREPROPS`, `COMPARERCMARGIN`, `COMPARETEXT`, `COMPARETOLERANCE`, `DWGNAME`, `DYNMODE`, `DYNPROMPT`, `GRIPCOLOR`, `GRIPHOT`, `GRIPOBJLIMIT`, `GRIPS`, `GRIPSIZE`, `HPANG`, `HPASSOC`, `HPBACKGROUNDCOLOR`, `HPCOLOR`, `HPDOUBLE`, `HPISLANDDETECTION`, `HPLAYER`, `HPNAME`, `HPSCALE`, `HPSEPARATE`, `HPTRANSPARENCY`, `INSUNITS`, `LOGINNAME`, `LUNITS`, `LUPREC`, `LWDISPLAY`, `MODELBKCOLOR`, `OPENPROF`, `ORTHOMODE`, `OSMODE`, `PAPERBKCOLOR`, `PICKBOX`, `POLARADDANG`, `POLARANG`, `POLARMODE`, `SHORTCUTMENU`, `TEXTSTYLE`, `UNITMODE`

### A.4 별칭 표에는 있으나 등록되지 않는 이름

`AcApDocManagerOptions.commandAliases`의 기본값 표(`dist/cad-simple-viewer.js`)에는 `LAYER: ['LA']`가 있지만 `LAYER` 명령 자체는 라이브러리가 등록하지 않는다(레이어 관리자 팔레트는 상류 Vue 셸 제공). `ATTEDIT`도 같은 경우로, `AcTrView2d`가 더블클릭 시 `sendStringToExecute('attedit')`를 호출하지만 명령은 호스트가 제공해야 한다.

## 부록 B. 명시적으로 존재하지 않는 식별자

전 `.d.ts` 전수 검색(`spikes/mlightcad/node_modules/@mlightcad/{cad-simple-viewer,data-model}/lib`)에서 **일치 없음**:
`explode` / `Explode` / `stretch` / `Stretch` / `join(` / `matchProp` / `AcApScaleCmd` / `AcApMirrorCmd` / `AcApTrimCmd` / `AcApExtendCmd` / `AcApExplodeCmd` / `statsByLayer` / `ATTEDIT`(등록 명령).
`fillet` / `chamfer`는 `AcApRectCmd`(사각형 코너 옵션)와 i18n 문자열에서만 나온다.
