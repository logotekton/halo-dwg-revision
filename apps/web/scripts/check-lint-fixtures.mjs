#!/usr/bin/env node
// Guard test for the two ESLint rules apps/web depends on for CLAUDE.md
// compliance (rule 8: no hardcoded UI strings; rule 3: GPL import boundary).
// Runs ESLint against apps/web/lint-fixtures/ and asserts it FAILS, and
// fails for the expected reasons. Exits 0 when the guard rules are working
// (i.e. ESLint correctly rejected the fixtures), exits 1 otherwise.
// Invoked by `pnpm --filter @halo-cad/web test` (see package.json).
//
// Run from the repo root: eslint.config.js `files` globs (e.g.
// "apps/web/lint-fixtures/**") are resolved against ESLint's basePath,
// which defaults to the CURRENT WORKING DIRECTORY (not the --config file's
// directory) -- so eslint must be invoked with cwd = repo root.
import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { dirname, join, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const repoRoot = join(__dirname, '..', '..', '..')

// Resolve the ESLint CLI from the repo root and run it with the current Node
// binary: spawning `pnpm`/`eslint` by name breaks on Windows (they are .cmd
// shims that need a shell), while spawning node directly is portable.
// eslint's package "exports" map does not expose bin/eslint.js, so resolve the
// package entry (lib/api.js) and walk up to the package directory instead.
const requireFromRoot = createRequire(join(repoRoot, 'package.json'))
const eslintEntry = requireFromRoot.resolve('eslint')
const eslintPkgDir = eslintEntry.slice(0, eslintEntry.lastIndexOf(`${sep}lib${sep}`))
const eslintBin = join(eslintPkgDir, 'bin', 'eslint.js')

const result = spawnSync(
  process.execPath,
  [eslintBin, 'apps/web/lint-fixtures', '--config', 'eslint.config.js'],
  { cwd: repoRoot, encoding: 'utf8' },
)

// ESLint prints OS-native separators; normalise so the expectations below
// match on Windows as well as POSIX.
const output = `${result.stdout ?? ''}${result.stderr ?? ''}`.replace(/\\/g, '/')

if (result.error) {
  console.error('[check-lint-fixtures] failed to run eslint:', result.error)
  process.exit(1)
}

if (result.status === 0) {
  console.error('[check-lint-fixtures] expected `eslint apps/web/lint-fixtures` to fail, but it exited 0')
  console.error(output)
  process.exit(1)
}

const expectations = [
  ['lint-fixtures/bad-literal.tsx', 'reported for bad-literal.tsx'],
  ['i18next/no-literal-string', 'i18next/no-literal-string rule fired'],
  ['lint-fixtures/bad-gpl-import.ts', 'reported for bad-gpl-import.ts'],
  ['no-restricted-imports', 'no-restricted-imports rule fired'],
]

const missing = expectations.filter(([needle]) => !output.includes(needle))

if (missing.length > 0) {
  console.error('[check-lint-fixtures] eslint failed as expected, but not for all expected reasons:')
  for (const [, description] of missing) {
    console.error(`  - missing: ${description}`)
  }
  console.error('--- eslint output ---')
  console.error(output)
  process.exit(1)
}

console.log('[check-lint-fixtures] OK: lint-fixtures/ correctly fails lint (literal-string + GPL import guards both fired)')
process.exit(0)
