# 엔진 사이드카 수명주기

`apps/desktop`의 main 프로세스가 Python 엔진(`engine/`)을 자식 프로세스로 띄우고 상태를 관리하며,
렌더러(`apps/web`)가 IPC를 통해 그 상태를 구독하고 엔진 API를 호출하는 방식을 설명한다. 계약은
`docs/contracts/wave-2.md`, 프로토콜 개요는 `docs/PLAN.md` §3, 구현은
`apps/desktop/src/main/engine/**`.

## 상태 머신

```
        (spawn 성공, /health 200)
  starting ─────────────────────────► ready
     │                                  │
     │ uv/바이너리를 찾지 못함           │ 프로세스 exit 이벤트
     │ 또는 READY 30초 타임아웃          │ (또는 READY/health 실패)
     ▼                                  ▼
   failed ◄───────── (3회 초과) ── restarting
     ▲                                  │
     │ 3회 재시도 후에도 실패            │ 재연결 성공
     └──────────────────────────────────┘
                (attempt 1/3 → 2/3 → 3/3, 백오프 1s/3s/9s)
```

- **starting**: 초기 상태. dev 모드는 `uv run halo-engine serve --data-dir <dataDir>`를
  `engine/` cwd에서, 패키지 모드는 `<resourcesPath>/engine/halo-engine serve --data-dir <dataDir>`를
  직접 실행한다(`apps/desktop/src/main/engine/spawn.ts`). `uv`를 PATH와 `$HOME/.local/bin/uv`
  어디에서도 찾지 못하거나(dev) 바이너리 파일이 없으면(패키지) 재시도 없이 바로 `failed`로 간다 —
  스폰 자체가 안 됐으므로 "재시작"할 대상이 없다.
- 스폰에 성공하면 stdout 첫 줄의 READY JSON(`{"event":"ready","port":N,"pid":P,"version":"x.y.z"}`)을
  기다린다(최대 30초, `apps/desktop/src/main/engine/ready.ts`). READY 이전의 stdout 잡음과 모든
  stderr는 로그로 흘려보낸다. READY를 받으면 `GET /api/v1/system/health`를 500ms 간격·30초
  타임아웃으로 폴링해(`health.ts`) 실제로 응답하는지 확인한 뒤 **ready**로 전이한다.
- **ready**: `halocad:engine:get-connection` IPC가 `{baseUrl, token}`을 반환하고, 상태바가
  "엔진: 연결됨 v{version}"을 보여준다. 이후 자식 프로세스가 예기치 않게 종료되면(`exit` 이벤트,
  의도된 종료가 아닐 때) 크래시로 간주해 **restarting**으로 전이한다. READY 타임아웃이나 READY 직후
  health가 끝내 실패해도 동일하게 크래시로 취급한다.
- **restarting**: 크래시 이후 1s → 3s → 9s 백오프(`backoff.ts`)로 재시도한다. 재시도 시에는
  **처음 성공했던 포트를 그대로 재요청**한다(`--port <port>`) — 렌더러가 `getConnection()` 결과를
  세션당 한 번만 받아 메모이즈하므로, 재연결 후에도 `baseUrl`이 바뀌면 안 되기 때문이다. 재연결에
  성공하면 다시 **ready**로 돌아가고 재시도 카운터는 0으로 리셋된다(연속 실패만 센다).
- **failed**: 연속 3회 재시도 후에도 실패하면 도달하는 종단 상태. 상태바가 "엔진 시작 실패:
  <메시지>"를 보여준다. 메시지에는 로그 파일 경로가 포함된다.

`apps/desktop/src/main/engine/state-machine.ts`가 이 전이를 순수 함수(`reduceEngineStatus`)로
구현하고, `supervisor.ts`가 spawn/타이머/HTTP 같은 실제 부수효과를 담당한다. IPC 페이로드
(`halocad:engine:status`)는 `state-machine.ts`의 `EngineStatus`를 그대로 직렬화한 것이다.

## 로그 위치

- `<userData>/logs/engine.log` — 엔진 자식 프로세스의 stdout 잡음(READY 줄 자체는 제외)과 stderr,
  그리고 supervisor 자신의 수명주기 로그(spawn/크래시/재시작/종료)가 모두 여기로 모인다.
  `apps/desktop/src/main/engine/logger.ts`가 5MB마다 회전하며 최대 5개 파일
  (`engine.log`, `engine.log.1` … `engine.log.4`)을 보관한다. macOS 기본 위치는
  `~/Library/Application Support/Halo CAD/logs/engine.log`.
- 엔진 프로세스 자신도 `--log-dir`를 받으면 별도로 회전 로그를 남길 수 있지만(`engine/README.md`),
  현재 supervisor는 `--log-dir`를 넘기지 않는다 — 엔진의 stderr를 그대로 받아 위 파일에 함께
  적재하는 쪽을 택했다(엔진과 supervisor 로그를 시간순으로 한 파일에서 보기 위함).
- 토큰은 로그에 남기지 않는다(`HALO_ENGINE_TOKEN`은 env로만 전달되고, spawn 로그 줄에는 명령/인자만
  기록한다 — 인자에는애초에 토큰이 없다).

> **Defaults for ambiguity 참고:** 브리프는 로깅 라이브러리로 `electron-log`(MIT) 채택을 기본값으로
> 제시하지만, 이를 추가하려면 `apps/desktop/package.json`(의존성 추가)을 수정해야 하고 이는 이
> 태스크의 "Files you own" 글롭 밖이다(`test:integration` 스크립트 추가만 예외로 허용됨). 그래서
> `logger.ts`는 동일한 외부 동작(회전 파일 트랜스포트 + 콘솔 에코)을 내는 의존성 없는 대체
> 구현이다. `electron-log` 도입은 보고서의 "Shared-file patch"에 diff로 제안했다 — 그 패치가
> 적용되면 `logger.ts` 내부만 교체하면 된다(외부 `EngineLogger` 인터페이스는 그대로).

## 부착 모드(HALO_ENGINE_URL)

브라우저에서 UI만 개발할 때, 또는 이미 떠 있는 엔진에 붙을 때 쓴다. Electron이 엔진을 spawn하지
않고 재시작도 하지 않는다 — 지정된 URL에 대해 health 폴링만 한다(500ms 간격, 30초 타임아웃).

```bash
# 터미널 1: 엔진을 직접 띄운다
cd engine && uv run halo-engine serve --dev --port 8765 --token dev

# 터미널 2: Electron이 spawn 대신 그 엔진에 붙는다
HALO_ENGINE_URL=http://127.0.0.1:8765 HALO_ENGINE_TOKEN=dev pnpm dev
```

`HALO_ENGINE_URL`만 있고 `HALO_ENGINE_TOKEN`이 없으면 즉시 `failed` 상태가 된다(안내 메시지 포함).
부착 모드에서는 health가 최초 1회 성공하면 바로 **ready**로 전이하고, 이후 프로세스 크래시 감지는
하지 않는다(Electron이 그 프로세스를 소유하지 않으므로 `exit` 이벤트를 볼 수 없다) — 이는
`docs/contracts/wave-2.md`의 "부착 모드: spawn과 재시작을 하지 않고 health 폴링만" 요구사항 그대로다.

## 스폰 pid ≠ 서버 pid

dev 모드의 `uv run halo-engine serve`는 자기 프로세스를 halo_engine으로 exec 치환하지 않고,
halo_engine을 **진짜 자식 프로세스**로 띄운다(macOS에서 직접 확인함: `child_process.spawn('uv', ...)`가
돌려주는 pid와 READY 줄의 `pid`가 서로 다르다). 코디네이터가 Windows CI에서 보고한 것과 같은 패턴
이다 — 패키지 모드의 `halo-engine.exe` 런처도 python을 자식으로 띄우므로 스폰 pid와 서버 pid가
다를 수 있다(`docs/dev/ci.md`, main). 즉 "스폰 pid만 죽이면 서버가 죽는다"는 가정은 두 모드 모두에서
성립하지 않는다 — 그 pid 하나만 죽이면 서버 프로세스가 고아로 남아 포트를 계속 쥐고 있고, 다음 재시작
시도가 같은 포트에 bind하려다 `Address already in use`로 실패한다(직접 재현해 확인함).

**대응(둘 다 구현):**

1. `spawnChild()`는 `detached: true`로 띄운다 — POSIX에서 스폰한 프로세스가 자기 프로세스 그룹의
   리더가 되고, 그 자식(halo_engine)도 같은 그룹에 남는다. `killTree()`는 **음수 pid로 그룹 전체**에
   신호를 보낸다(`process.kill(-spawnPid, signal)`) — 대상 pid 하나가 아니라. 그룹은 구성원이 하나라도
   살아 있는 한 그 번호로 계속 신호를 받을 수 있으므로, 스폰 프로세스가 이미 죽은 뒤에도 orphan이 된
   서버 프로세스까지 정리된다(확인함). Windows는 `taskkill /pid <spawnPid> /T /F`의 `/T`가 OS의 실제
   프로세스 트리를 따라가므로 동일하게 자식까지 정리된다.
2. `spawned.on('exit', ...)`(예기치 않은 종료 = 크래시) 핸들러가 재시작을 예약하기 **전에** 방어적으로
   `killTree(spawned, logger, 'SIGKILL')`을 한 번 더 호출한다 — 스폰 프로세스만 먼저 죽고 서버가 아직
   살아 있는 경우를 대비한 것이다. 스폰·서버가 함께 죽은 보통의 경우엔 `ESRCH`만 나고 조용히 무시된다
   (경고 로그를 남기지 않음).

`EngineSupervisor.getPid()`(ops/테스트 전용, IPC 계약 밖)는 `{spawnPid, serverPid}`를 둘 다 반환한다.
통합 테스트(`apps/desktop/tests/integration/engine-supervisor.test.ts`)가 두 시나리오를 모두 검증한다:
서버 pid를 직접 죽이는 "현실적인" 경로(사용자가 `pgrep -f halo-engine`으로 찾아 죽이는 것과 동일)와,
스폰 pid만 죽이는 회귀 가드.

## 종료 시퀀스

`before-quit`에서(`apps/desktop/src/main/index.ts`):

1. 연결된 적이 있으면 `POST /api/v1/system/shutdown`을 Bearer 토큰과 함께 보낸다(최대 4초 대기,
   실패해도 무시하고 다음 단계로 — 엔진이 이미 죽었거나 응답 못 하는 상황일 수 있음).
2. 자식 프로세스가 5초 안에 스스로 종료하는지 기다린다.
3. 5초가 지나도 살아 있으면 트리 전체를 강제 종료한다 — POSIX는 프로세스 그룹에
   `SIGTERM`(`process.kill(-pid, 'SIGTERM')`, 자식을 `detached: true`로 스폰해 자신이 그룹 리더가
   되게 했다), Windows는 `taskkill /pid <pid> /T /F`.
4. 엔진 프로세스 자신도 `HALO_ENGINE_PARENT_PID`로 Electron main의 생존을 5초 간격으로 감시하다가
   부모가 사라지면 스스로 종료한다(`engine/src/halo_engine/cli.py`, W1-02 산출) — 위 1~3단계가 모두
   실패해도 좀비 프로세스가 남지 않는 마지막 방어선이다.

> **Windows 미검증**: `taskkill /T /F` 경로는 코드로는 넣었지만 이 브랜치는 macOS에서만 검증했다
> (`docs/contracts/wave-2.md`의 CI가 `windows-latest`를 매트릭스에 포함하므로 W2-09에서 실제로
> 실행되어 검증될 것이다).
