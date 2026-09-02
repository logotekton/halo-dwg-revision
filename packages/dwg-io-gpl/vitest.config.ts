import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { createLogger } from 'vite';
import { defineConfig } from 'vitest/config';

// Identical to packages/cad-core: the published sourcemaps point at TypeScript
// sources that are not in the tarballs, and the warning buries the report.
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
  test: {
    environment: 'node',
    include: ['test/**/*.test.ts'],
    root: fileURLToPath(new URL('.', import.meta.url)),
    server: {
      // @mlightcad ESM entries use extensionless directory imports that Node's
      // resolver rejects (spike C.11); Vite's resolver handles them.
      deps: { inline: [/@mlightcad\//] },
    },
  },
});
