import path from 'node:path'

// node:path's plain join()/delimiter follow the *host* OS, not a `platform`
// parameter. Since this module is built to be pure/testable from any host
// (and CI runs both macOS and Windows runners, docs/contracts/wave-2.md
// "CI"), path construction below always goes through the win32/posix
// variant matching the injected `platform`, never the ambient one.
function pathFor(platform: NodeJS.Platform): path.PlatformPath {
  return platform === 'win32' ? path.win32 : path.posix
}

/**
 * Resolves the `uv` binary to run in dev mode (constraint: "uv가 PATH에 없으면
 * $HOME/.local/bin/uv를 시도, 그래도 없으면 failed"). Pure given its inputs —
 * `fileExists` is injected so this is testable without touching the real
 * filesystem or `process.env`.
 */
export interface FindUvBinaryOptions {
  pathEnv: string
  homeDir: string
  platform: NodeJS.Platform
  fileExists: (path: string) => boolean
}

export function findUvBinary(options: FindUvBinaryOptions): string | null {
  const p = pathFor(options.platform)
  const binName = options.platform === 'win32' ? 'uv.exe' : 'uv'

  const pathDirs = options.pathEnv.split(p.delimiter).filter((dir) => dir.length > 0)
  for (const dir of pathDirs) {
    const candidate = p.join(dir, binName)
    if (options.fileExists(candidate)) return candidate
  }

  const fallback = p.join(options.homeDir, '.local', 'bin', binName)
  if (options.fileExists(fallback)) return fallback

  return null
}

export interface EngineCommand {
  command: string
  args: string[]
  cwd: string
}

export type EngineCommandResult = ({ ok: true } & EngineCommand) | { ok: false; message: string }

export interface ResolveEngineCommandOptions {
  isPackaged: boolean
  /** Dev mode only: the `engine/` directory to run `uv run` from. */
  engineDir: string
  /** Packaged mode only: `process.resourcesPath`. */
  resourcesPath: string
  /** `--data-dir` value, both modes. */
  dataDir: string
  /** `--port` value once known (stable across restarts); omitted on first spawn (OS-assigned). */
  port?: number
  homeDir: string
  platform: NodeJS.Platform
  pathEnv: string
  fileExists: (path: string) => boolean
}

/**
 * Builds the spawn descriptor for either mode (constraints: dev spawns
 * `uv run halo-engine serve ...` with cwd `engine/`; packaged spawns
 * `<resourcesPath>/engine/halo-engine serve ...` directly). Neither argv list
 * ever contains the bearer token — it travels only via `HALO_ENGINE_TOKEN`.
 */
export function resolveEngineCommand(options: ResolveEngineCommandOptions): EngineCommandResult {
  const p = pathFor(options.platform)
  const portArgs = options.port === undefined ? [] : ['--port', String(options.port)]

  if (options.isPackaged) {
    const binaryName = options.platform === 'win32' ? 'halo-engine.exe' : 'halo-engine'
    const engineResourceDir = p.join(options.resourcesPath, 'engine')
    const binary = p.join(engineResourceDir, binaryName)
    if (!options.fileExists(binary)) {
      return { ok: false, message: `엔진 실행 파일을 찾을 수 없습니다: ${binary}` }
    }
    return {
      ok: true,
      command: binary,
      args: ['serve', '--data-dir', options.dataDir, ...portArgs],
      cwd: engineResourceDir,
    }
  }

  const uv = findUvBinary({
    pathEnv: options.pathEnv,
    homeDir: options.homeDir,
    platform: options.platform,
    fileExists: options.fileExists,
  })
  if (!uv) {
    return { ok: false, message: 'uv가 설치되어 있지 않습니다.' }
  }
  return {
    ok: true,
    command: uv,
    args: ['run', 'halo-engine', 'serve', '--data-dir', options.dataDir, ...portArgs],
    cwd: options.engineDir,
  }
}
