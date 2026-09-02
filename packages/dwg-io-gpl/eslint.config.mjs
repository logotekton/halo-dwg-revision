// Local flat config for @halo-cad/dwg-io-gpl.
//
// This is the one package where importing @mlightcad/libredwg-* is allowed
// (CLAUDE.md rule 3, ADR-0001), so the workspace-wide GPL restriction is
// deliberately absent here. `tools/verify.sh` still checks that no other
// directory imports those packages.
import js from '@eslint/js';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist/**', 'node_modules/**', 'coverage/**', '*.config.mjs'] },
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
        { prefer: 'type-imports', fixStyle: 'inline-type-imports' },
      ],
      eqeqeq: ['error', 'always', { null: 'ignore' }],
      'no-console': 'error',
    },
  },
  {
    files: ['scripts/**/*.mjs', 'test/**/*.ts', '*.config.ts', '*.config.mjs'],
    extends: [tseslint.configs.disableTypeChecked],
    languageOptions: {
      globals: { process: 'readonly', console: 'readonly' },
    },
    rules: {
      'no-console': 'off',
      '@typescript-eslint/no-non-null-assertion': 'off',
    },
  }
);
