import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { createLogger } from 'vite';
import { defineConfig } from 'vitest/config';

// @mlightcad/data-model ships sourcemaps that point at TypeScript sources it
// does not publish. Vite warns once per file, which buries the test output.
const logger = createLogger();
const noisy = (message: string): boolean => message.includes('points to missing source files');
const warn = logger.warn.bind(logger);
const warnOnce = logger.warnOnce.bind(logger);
logger.warn = (message, options) => {
  if (!noisy(message)) warn(message, options);
};
logger.warnOnce = (message, options) => {
  if (!noisy(message)) warnOnce(message, options);
};

/**
 * The published `.js.map` files reference TypeScript sources that are not in
 * the tarball, so Vite warns once per module and buries the test report. The
 * maps are useless either way; dropping the comment is the quiet fix.
 */
const dropMlightcadSourcemaps = {
  name: 'halo-cad:drop-mlightcad-sourcemaps',
  enforce: 'pre' as const,
  load(id: string) {
    const path = id.split('?')[0] ?? id;
    if (!path.includes('@mlightcad') || !path.endsWith('.js')) return null;
    const code = readFileSync(path, 'utf8');
    return { code: code.replace(/\/\/# sourceMappingURL=.*$/gm, ''), map: null };
  },
};

export default defineConfig({
  customLogger: logger,
  plugins: [dropMlightcadSourcemaps],
  resolve: {
    alias: {
      // Same reason as the tsconfig `paths` entry: the schema package's `dist/`
      // is generated, not committed, so tests read its sources directly.
      '@halo-cad/schema/gen/ts': fileURLToPath(new URL('../schema/gen/ts', import.meta.url)),
      '@halo-cad/schema': fileURLToPath(new URL('../schema/src/index.ts', import.meta.url)),
    },
  },
  test: {
    environment: 'node',
    include: ['test/**/*.test.ts'],
    root: fileURLToPath(new URL('.', import.meta.url)),
    // F11 (200k entities) is the slowest case; the stats budget itself is 15s.
    testTimeout: 120_000,
    hookTimeout: 120_000,
    server: {
      deps: {
        // @mlightcad/data-model's ESM entry uses extensionless directory
        // imports, which Node's own ESM resolver rejects with
        // ERR_UNSUPPORTED_DIR_IMPORT (spike C.11). Letting Vite process the
        // package applies its resolver instead, which handles them.
        inline: [/@mlightcad\//],
      },
    },
  },
});
