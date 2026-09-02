# ADR-0004 Three.js 두 버전의 iframe 격리

상태: 승인 (2026-09-02)

## 맥락
2D 코어(mlightcad cad-simple-viewer 1.6.3)는 `three@^0.172`를 peer로 요구하고, 3D 부품(@thatopen/components 3.4.8, web-ifc 0.0.77)은 `three>=0.182`를 요구한다. 한 모듈 그래프에 두 Three를 섞으면 instanceof 검사와 싱글턴이 깨진다.

## 결정
3D 패널을 **별도 Vite 엔트리(`apps/viewer3d`)** 로 빌드해 **iframe** 으로 띄우고 `postMessage` 브리지(`packages/schema/bridge`)로만 통신한다. 2D 쪽은 `three@0.172.0`, 3D 쪽은 `three>=0.182`를 각자 번들한다. Three 객체는 경계를 넘지 않는다. 브리지 메시지: `load(glb|ifc url)`, `select(ids)`, `colorize(map)`, `camera(...)`, 역방향 `selected(ids)`, `ready`, `error`.

## 결과
- `pnpm why three`가 앱별로 단일 버전을 보이는지 `tools/verify.sh`가 검사한다.
- 선택 동기화는 id 기반이며 약간의 지연이 있다. 허용한다.
- mlightcad가 peer를 ≥0.182로 올리면 단일 번들로 합치는 ADR을 새로 쓴다.
