# <ID> <제목>

- Owner model: Sonnet | Opus
- Size: <0.5–2 d>
- Branch: `task/<ID>`
- Wave: <n>  Phase: <P0..P6>

## Context (3~8줄)
무엇이 이미 있고, 왜 이 태스크가 필요한지. 먼저 읽을 문서: `CLAUDE.md`, `docs/PLAN.md` §<n>, `docs/adr/<...>.md`, `docs/spikes/<...>.md`.

## Goal
결과 중심 한 문단.

## Inputs
읽어야 할 정확한 파일/디렉터리, 스키마 버전, 픽스처 경로.

## Files you own
```
<glob>
<glob>
```

## Forbidden
루트 `package.json`, `pnpm-lock.yaml`, `packages/schema/**`, 다른 패키지, `fixtures/truth/**` 쓰기. 필요한 변경은 보고서 "Shared-file patch"에 diff로 제안.

## Constraints
- 버전 핀은 `CLAUDE.md`를 따른다. 신규 의존성은 이름·버전·라이선스를 보고서에 나열.
- GPL 경계, ODA 금지, i18n 키만, provenance/evidence 필수, 시드 결정론, 외부 네트워크 금지(127.0.0.1과 설정된 DMS 서버 제외).
- 높이 4필드 규칙(ADR-0003).
- 성능 예산: <예: F11 열기 < 15초>.

## Definition of done
- 테스트: `<test file>::<name>` ...
- `tools/verify.sh` 녹색 (worktree에서 직접 실행).
- 문서: <갱신할 문서>.
- 커밋 `<ID>: ...` on `task/<ID>`.

## Acceptance checks (Fable이 실행)
```bash
<command>   # expected: ...
```

## Defaults for ambiguity
멈추지 말고 아래 기본값을 택하고 보고서 "Decisions"에 기록한다.
- <상황> → <기본 선택>

## Design notes required (Opus 브리프만)
코드 판정 전에 보고서 앞부분에 설계 요약(데이터 흐름, 핵심 자료구조, 실패 모드)을 쓴다.

## Reference implementation (Sonnet 브리프만)
따라갈 패턴 파일: `<path>`.

## Report format
Summary / Files changed / Verification(명령 + 요약 출력) / Decisions / Deviations from brief / Shared-file patch / Questions for gate / Follow-ups
