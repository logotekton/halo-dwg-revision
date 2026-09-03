import { defineWorkspace } from 'vitest/config'

// Each project keeps its own vitest.config.ts (environment, setup files);
// this workspace file just lets `vitest` run every package from the repo
// root in one pass. Per-package `pnpm --filter <pkg> test` still works
// against each package's own config independently.
export default defineWorkspace([
  'apps/web/vitest.config.ts',
  'apps/desktop/vitest.config.ts',
  'packages/schema/vitest.config.ts',
  'packages/acad-bridge/vitest.config.ts',
  'packages/cad-core/vitest.config.ts',
  'packages/dwg-io-gpl/vitest.config.ts',
])
