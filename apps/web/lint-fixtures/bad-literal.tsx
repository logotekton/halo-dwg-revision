// Intentionally violates CLAUDE.md rule 8 (no hardcoded UI strings):
// a bare Korean literal in JSX text, not routed through i18next t(...).
// Exercised by apps/web/scripts/check-lint-fixtures.mjs, never imported by
// app code, and excluded from the TypeScript project (tsconfig.json).
export function BadLiteral() {
  return <div>한글이 그대로 노출됩니다</div>
}
