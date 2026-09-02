// Local flat config for @halo-cad/cad-core.
//
// The one rule that matters here is the mlightcad import boundary: only
// `src/mlightcad-surface.ts` may import `@mlightcad/*`. `docs/briefs/W2-02.md`
// asks for it as a local `no-restricted-imports` setting, and the acceptance
// commands re-check it with grep. The GPL restriction of the workspace config
// (CLAUDE.md rule 3) is repeated so this package is guarded even when eslint is
// run from inside the package directory.
import js from '@eslint/js';
import tseslint from 'typescript-eslint';

const MLIGHTCAD_MESSAGE =
  '@mlightcad/* may only be imported from src/mlightcad-surface.ts. Everything else uses the plain interfaces of src/surface-types.ts (docs/briefs/W2-02.md, CLAUDE.md "packages/cad-core: mlightcad 유일 임포트").';

const GPL_MESSAGE =
  '@mlightcad/libredwg-* is GPL-licensed and may only be imported from packages/dwg-io-gpl/** (CLAUDE.md rule 3, ADR-0001).';

export default tseslint.config(
  { ignores: ['dist/**', 'node_modules/**', 'coverage/**'] },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
  {
    files: ['**/*.ts'],
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    rules: {
      '@typescript-eslint/consistent-type-imports': [
        'error',
        { prefer: 'type-imports', fixStyle: 'separate-type-imports' },
      ],
      eqeqeq: ['error', 'always', { null: 'ignore' }],
      'no-console': 'error',
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            { group: ['@mlightcad/*', '@mlightcad/*/**'], message: MLIGHTCAD_MESSAGE },
            { group: ['@mlightcad/libredwg-*', '@mlightcad/libredwg-*/**'], message: GPL_MESSAGE },
          ],
        },
      ],
    },
  },
  {
    // The single exception. GPL packages stay forbidden even here.
    files: ['src/mlightcad-surface.ts'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            { group: ['@mlightcad/libredwg-*', '@mlightcad/libredwg-*/**'], message: GPL_MESSAGE },
          ],
        },
      ],
    },
  },
  {
    files: ['test/**/*.ts', '*.config.ts', '*.config.mjs'],
    rules: {
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
      '@typescript-eslint/no-non-null-assertion': 'off',
      'no-console': 'off',
    },
  }
);
