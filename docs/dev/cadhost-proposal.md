# CadHost 파사드 설계 제안 (W1-04 스파이크 결론, W3-02 입력)

원칙: `packages/cad-core`가 `@mlightcad/*`를 임포트하는 유일한 장소이며(`src/mlightcad-surface.ts`), 파사드 밖으로는 mlightcad 타입이 새지 않는다. 반환값은 `@halo-cad/schema` 생성 타입과 `surface-types.ts`의 자체 DTO(핸들은 문자열, 좌표는 `{x,y}`)만 쓴다. W2-02가 헤드리스 절반(`openDxf`, `statsByLayer`, `exportNdj`, `curveLength`, `entityRef`)을 이미 구현했다.

## 노출할 표면

```ts
export interface CadHost {
  // lifecycle
  static create(opts: CadHostOptions): Promise<CadHost>   // container, 워커 URL, 폰트 baseUrl, 모드
  open(fileId: string, name: string, bytes: ArrayBuffer, mode: 'read'|'review'|'write'): Promise<OpenResult>
  activate(fileId: string): Promise<void>                 // MDI
  close(fileId: string): Promise<void>
  dispose(): Promise<void>                                 // 싱글턴 5종 전부 정리
  // read
  getEntityByHandle(h: Handle): EntityDto | undefined
  entities(opts?: { space?: 'MODEL'|'PAPER'; layer?: string }): Iterable<EntityDto>
  statsByLayer(): LayerStatsDocument
  layers(): LayerDto[]; layouts(): LayoutDto[]; setActiveLayout(id: string): void
  // view
  pick(worldPt: Pt, hitRadiusPx?: number): Handle[]
  search(box: Box): Handle[]
  selectByBox(box: Box, mode: 'window'|'crossing', action: 'replace'|'add'|'remove'): void
  setSelection(hs: Handle[]): void; highlight(hs: Handle[]): void; unhighlight(hs: Handle[]): void
  zoomTo(box: Box, margin?: number): void; zoomToFit(): void; zoomToLayer(name: string): boolean
  screenToWorld(p: Pt): Pt; worldToScreen(p: Pt): Pt
  // overlay (근거·diff·교차검증)
  addOverlay(spec: OverlayJson): Promise<OverlayId>        // transient 엔티티, 완료까지 await
  setOverlayVisible(id: OverlayId, v: boolean): boolean
  removeOverlay(id: OverlayId): void; clearOverlays(): void
  // edit
  runCommand(name: string, script?: string[]): Promise<void>
  edit<T>(label: string, fn: (tx: CadEditTx) => T): T      // acapRunDatabaseEdit 래핑
  undo(): boolean; redo(): boolean; canUndo(): boolean; canRedo(): boolean
  // events (자체 emitter가 mlightcad 이벤트를 흡수)
  on(event: 'selectionChanged'|'documentOpened'|'documentActivated'|'documentClosed'|'renderIdle'
          |'undoStackChanged'|'entityChanged'|'fontMissing'|'xrefUnresolved'|'openProgress'|'openFailed',
     cb: (...args: unknown[]) => void): () => void
}
```

## 버전 변동에 취약한 지점과 완화 (실측 기준)

| 취약점 | 완화 |
|---|---|
| `AcTrView2d` 공개 메서드 30여 개에 의존 | 파사드가 쓰는 메서드를 12개로 제한하고 `mlightcad-surface.ts` 한 파일에만 둔다 |
| `type` vs `dxfTypeName` | 통계·NDJ 키는 `dxfTypeName`만(DIMENSION 서브클래스 문제) |
| `AcDbCurve`에 `length` 없음 | `curveLength()` 헬퍼, `properties.geometry.length`와 양방향 대조 테스트. 스플라인은 **자체 NURBS 평탄화**로 교체(계약: ezdxf 정본, 현재 +11%) |
| `addTransientEntity()`가 fire-and-forget | `addOverlay()`는 Promise 반환, `setTransientEntityVisible()` 폴링으로 완료 확인 |
| MTEXT 폰트 상태가 워커에 별도 존재 | 폰트 설정은 `AcTrMTextRenderer.getInstance().setDefaultFonts()`와 `FontManager.instance` 양쪽을 통과하는 `setFontChain()` 하나로만 |
| 싱글턴 5종(`AcApDocManager`, `AcDbDatabaseConverterManager`, `AcApXrefManager`, `FontManager`, `AcTrMTextRenderer`) | `dispose()`가 5개 모두 정리. 힙 증가 <10% 기준은 이 경로 테스트 |
| `documentCreated`가 `documentActivated` 뒤에 오는 경우 | 파사드 상태 머신으로 정규화 |
| DWG 경로에서 입력 `ArrayBuffer` detach | `open()`이 바이트를 복사해 넘김(W2-02 구현됨) |
| GPL 경계 | `AcDbLibreDwgConverter` 등록은 `packages/dwg-io-gpl`의 `registerLibreDwgConverter()` 주입만 |
| 타입 선언 결함 | `skipLibCheck: true` + ADR-0006 |

## P0 실측에서 추가된 요구(W2-06, ADR-0002 개정)
- DWG→DXF 변환은 **숨김 BrowserWindow**에서 `dxfOut()`으로. Node utilityProcess에서는 `Worker`가 없어 DWG 파싱 불가.
- `dxfOut()` 산출물 후처리 2건: ATTRIB이 뒤따르는 INSERT에 그룹 `66 1`, HATCH 경계 그룹 `92`의 External 비트 복원.
- 변환 성공 판정 = 엔진 교차검증 통과(차단).
- 엔티티 수 25만 초과 시 라이트 DXF, 80만 초과 시 엔진 전용. 뷰어 렌더 비용 포함 A 경계 재확인.
- libredwg-web 미리보기 결과는 교차검증 전 "확인됨"으로 표시하지 않는다.
