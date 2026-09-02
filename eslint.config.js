// Halo CAD workspace ESLint flat config (CLAUDE.md rule 8, ADR-0001).
// CommonJS on purpose: root package.json has no "type": "module", so
// eslint.config.js is loaded as CJS by Node/ESLint without extra config.
'use strict'

const { defineConfig, globalIgnores } = require('eslint/config')
const js = require('@eslint/js')
const tseslint = require('typescript-eslint')
const reactHooks = require('eslint-plugin-react-hooks')
const i18next = require('eslint-plugin-i18next')
const prettierConfig = require('eslint-config-prettier')
const globals = require('globals')

// CLAUDE.md rule 3 / ADR-0001: @mlightcad/libredwg-* is GPL and may only be
// imported from packages/dwg-io-gpl/** or apps/desktop/src/main/ipc/convert.ts.
const GPL_IMPORT_MESSAGE =
  '@mlightcad/libredwg-* is GPL-licensed and may only be imported from packages/dwg-io-gpl/** or apps/desktop/src/main/ipc/convert.ts (CLAUDE.md rule 3, ADR-0001).'

const gplImportRestriction = {
  'no-restricted-imports': [
    'error',
    {
      patterns: [
        {
          group: ['@mlightcad/libredwg-*', '@mlightcad/libredwg-*/**'],
          message: GPL_IMPORT_MESSAGE,
        },
      ],
    },
  ],
}

// CLAUDE.md rule 8: UI strings live in apps/web/src/i18n/ko.json only.
const literalStringRule = {
  'i18next/no-literal-string': [
    'error',
    {
      // 'jsx-only' checks both JSX text children AND JSX attribute values
      // (title/aria-label/placeholder/alt/value stay checked by the plugin's
      // default jsx-attributes exclude list; className/style/id/etc. do not).
      mode: 'jsx-only',
      'should-validate-template': false,
    },
  ],
}

module.exports = defineConfig(
  globalIgnores([
    '**/node_modules/**',
    '**/dist/**',
    '**/out/**',
    '**/release/**',
    '**/.turbo/**',
    '**/coverage/**',
    '**/*.tsbuildinfo',
    // Ambient declaration files aren't part of any tsconfig "program" the
    // typescript-eslint project service builds for type-aware rules, and
    // there's little lint value in a pure `declare global {}` file anyway.
    '**/*.d.ts',
    'pnpm-lock.yaml',
  ]),

  // ---- Base JS + type-checked TS rules for the whole TS workspace ----
  {
    files: ['apps/**/*.{ts,tsx}', 'packages/**/*.{ts,tsx}'],
    extends: [js.configs.recommended, tseslint.configs.strictTypeChecked, tseslint.configs.stylisticTypeChecked],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: __dirname,
      },
      globals: {
        ...globals.es2023,
      },
    },
  },

  // ---- GPL import boundary: forbidden by default across apps/packages ----
  {
    files: ['apps/**/*.{ts,tsx}', 'packages/**/*.{ts,tsx}'],
    rules: gplImportRestriction,
  },
  {
    files: ['packages/dwg-io-gpl/**/*.{ts,tsx}', 'apps/desktop/src/main/ipc/convert.ts'],
    rules: {
      'no-restricted-imports': 'off',
    },
  },

  // ---- Node-context sources: main/preload process + config files ----
  {
    files: [
      'apps/desktop/src/main/**/*.ts',
      'apps/desktop/src/preload/**/*.ts',
      'apps/desktop/*.config.{ts,js,mjs,cjs}',
      'apps/web/*.config.{ts,js,mjs,cjs}',
      'vitest.workspace.ts',
    ],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },

  // ---- Renderer (apps/web): browser globals + react-hooks ----
  {
    files: ['apps/web/**/*.{ts,tsx}'],
    plugins: {
      'react-hooks': reactHooks,
    },
    languageOptions: {
      globals: {
        ...globals.browser,
      },
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
    },
  },

  // ---- i18n literal-string guard: renderer source only, tests excluded ----
  {
    files: ['apps/web/src/**/*.{ts,tsx}'],
    ignores: ['**/*.test.{ts,tsx}', '**/*.spec.{ts,tsx}', '**/__tests__/**'],
    plugins: { i18next },
    rules: literalStringRule,
  },

  // ---- lint-fixtures: intentionally violate the guarded rules above.
  // Not part of any tsconfig project, so type-aware rules are disabled here
  // and only the two guard rules (i18n literal string + GPL import) apply.
  {
    files: ['apps/web/lint-fixtures/**/*.{ts,tsx}'],
    extends: [tseslint.configs.disableTypeChecked],
    plugins: { i18next },
    languageOptions: {
      globals: {
        ...globals.browser,
      },
    },
    rules: {
      ...literalStringRule,
      ...gplImportRestriction,
    },
  },

  // ---- Test files: relax a few rules that fight normal test patterns ----
  {
    files: ['**/*.test.{ts,tsx}', '**/*.spec.{ts,tsx}'],
    rules: {
      '@typescript-eslint/no-unsafe-assignment': 'off',
    },
  },

  // Always last: turn off stylistic rules that fight Prettier formatting.
  prettierConfig,
)
