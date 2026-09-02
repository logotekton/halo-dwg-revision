# 프로브 결과 스냅샷 (W1-04)

문서(`docs/spikes/*.md`)가 인용하는 원본 측정값이다. 재생성:

```bash
npm run dev &          # http://localhost:5178
npm run shots          # → browser-facts.json (+ docs/spikes/img/*.png)
npm run probe:node     # → probe-node.json
npm run licenses       # → licenses.json
```

| 파일 | 내용 |
|---|---|
| `browser-facts.json` | 브라우저 프로브 17건(`window.__spike`). `facts[].id`가 `mlightcad-api.md`의 절 번호와 대응한다 |
| `probe-node.json` | Node 헤드리스 프로브(사실 11) + `dxfOut()` 왕복 + CP949 디코딩 |
| `licenses.json` | `npm ls --all --omit=dev` 기반 라이선스 트리 |
| `roundtrip-r2018.dxf` | 픽스처를 `AcDbDatabase.dxfOut('…', 6, 'AC1032')`로 다시 쓴 결과(비교용) |
