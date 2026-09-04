# Halo DWG Revision (halo-dwg-revision)

대명건설 사내 전용 **리비전 도면 관리 앱**: 변경 전·후 DWG 세트를 도곽 단위로 비교하고, 승인한 변경만 클라우드 마크와 리비전 표를 얹은 마크업 DWG로 내보내는 Windows 로컬 앱.

- 보고용 계획서: [docs/plans/dms-local/01-보고용-계획서.html](docs/plans/dms-local/01-보고용-계획서.html)
- 개발용 계획서: [docs/plans/dms-local/02-개발용-계획서.html](docs/plans/dms-local/02-개발용-계획서.html)
- 인터뷰 결정 장부(계획서보다 우선): [docs/plans/dms-local/interview-mvp-2026-09-04.md](docs/plans/dms-local/interview-mvp-2026-09-04.md)
- 1주차 MVP Seed: [docs/seeds/R1-mvp-2026-09-04.yaml](docs/seeds/R1-mvp-2026-09-04.yaml)
- 에이전트 규약: [CLAUDE.md](CLAUDE.md)

이 저장소는 `halo-cad`(Mac/Windows 무료 CAD 프로젝트)에서 분기했다. Electron 셸, React UI, 파이썬 엔진(인입·정본화·통계·교차검증), 스키마, DWG 브리지를 그대로 이어받았고 3D 뷰어·적산 관련 자산은 뺐다. 이력과 미병합 브랜치(`task/W3-02` 뷰어, `task/W3-06` XREF)는 보존되어 있다.

## 시작

```bash
pnpm install --frozen-lockfile
cd engine && uv sync --frozen && uv run pytest
tools/verify.sh
```
