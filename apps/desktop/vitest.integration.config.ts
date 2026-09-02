import { defineConfig } from 'vitest/config'

// Separate from vitest.config.ts (unit-only, run by `pnpm -r test`/verify.sh)
// per brief W2-01's constraint: "pnpm -r test에는 단위만, 통합은 별도
// 스크립트로 두고 verify.sh 패치 제안에 포함". Run via `pnpm test:integration`
// (apps/desktop/package.json). Spawns a real `uv run halo-engine serve`
// subprocess, so it needs `uv` on PATH and is slower than the unit suite.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['tests/integration/**/*.test.ts'],
    testTimeout: 60_000,
    hookTimeout: 30_000,
  },
})
