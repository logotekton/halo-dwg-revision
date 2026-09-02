# ADR-0001 기술 스택과 기반 선정

상태: 승인 (2026-09-02)

## 맥락
Mac/Windows에서 동작하는 무료 CAD를 확보하고 여기에 도면관리와 적산을 붙여야 한다. 사내 전용이라 GPL 사용은 가능하지만 상용 라이선스 비용은 쓸 수 없다. 개발은 AI 에이전트가 수행하므로 "실제로 동작하고 검증 가능한가"가 언어 선호보다 우선한다.

## 검토한 대안
- **OpenCADStudio 포크(Rust, GPL-3)**: 2D는 AutoCAD식이고 DWG 자체 파서·3D 커널이 있으나, 플러그인이 Rust 전용이며 커스텀 패널·오버레이·3D 접근이 불가해 적산 UI를 얹으려면 본체 포크가 필요. 커밋 91%가 1인, 주 1회 릴리스로 상류 추적 부담이 크고 한글 폰트 이슈가 미해결. → 본체 후보 탈락, 보조 변환기 후보로만.
- **FreeCAD 플랫폼(LGPL)**: 3D·IFC·Python 확장은 우수하나 2D 도면은 엔티티=문서 객체 구조라 대용량 건축 도면에서 사용 불가 수준. 기본 DXF 임포터가 HATCH·ATTRIB를 버리고 SHX 미지원, macOS 26 크래시 미해결. → 기반 탈락, 선택적 정밀 B-rep 백엔드로만.
- **웹 스택 조립(채택)**: mlightcad cad-simple-viewer(MIT)가 브라우저에서 DWG/DXF를 렌더하며 한글 SHX 빅폰트와 CP949를 지원하고 선택·오버레이·트랜잭션 API를 제공. 3D는 Three.js + ThatOpen + web-ifc. 엔진은 Python(ezdxf, shapely, manifold3d, ifcopenshell). 데스크톱은 Electron + PyInstaller 사이드카.

## 결정
웹 스택 조립을 채택한다. 세부 버전은 `CLAUDE.md`의 핀 목록을 따른다. DWG 파싱은 브라우저에서 libredwg-web(GPL, `packages/dwg-io-gpl`에 격리), Node에서 acad-ts(MIT). ODA File Converter는 비회원 상업 사용이 금지되어 사용하지 않는다.

## 결과
- 처음부터 만드는 부분은 적산 엔진과 UI 셸에 한정된다.
- mlightcad는 3일마다 릴리스되므로 정확 버전을 고정하고 `packages/cad-core`의 CadHost 파사드 뒤에 숨긴다. 업그레이드는 단계 경계에서만.
- 두 Three 버전 문제는 ADR-0004로 해결한다.
