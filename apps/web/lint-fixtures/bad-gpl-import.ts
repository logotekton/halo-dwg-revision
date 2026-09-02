// Intentionally violates CLAUDE.md rule 3 / ADR-0001 (GPL boundary):
// @mlightcad/libredwg-* may only be imported from packages/dwg-io-gpl/**
// or apps/desktop/src/main/ipc/convert.ts, never from apps/web.
// Exercised by apps/web/scripts/check-lint-fixtures.mjs; the package below
// is not installed, and this file is excluded from the TypeScript project
// (tsconfig.json), so it only ever runs through ESLint.
import '@mlightcad/libredwg-web'

export const marker = 'gpl-import-fixture'
