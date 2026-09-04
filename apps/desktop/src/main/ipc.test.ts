import { describe, expect, it, vi } from 'vitest'
import { openPath, pickDrawingFiles, pickFolder, recordE2EOpenedPath, type PickFolderQueueState } from './ipc'

describe('pickDrawingFiles', () => {
  it('shows the real dialog and returns its file paths when not in e2e mode', async () => {
    const showOpenDialog = vi.fn().mockResolvedValue({ canceled: false, filePaths: ['/a.dwg', '/b.dxf'] })
    const result = await pickDrawingFiles({}, showOpenDialog)

    expect(result).toEqual(['/a.dwg', '/b.dxf'])
    expect(showOpenDialog).toHaveBeenCalledTimes(1)
  })

  it('returns an empty array when the real dialog is cancelled', async () => {
    const showOpenDialog = vi.fn().mockResolvedValue({ canceled: true, filePaths: [] })
    const result = await pickDrawingFiles({}, showOpenDialog)

    expect(result).toEqual([])
  })

  it('bypasses the dialog under HALO_E2E=1 and returns HALO_E2E_PICK_FILES instead', async () => {
    const showOpenDialog = vi.fn()
    const result = await pickDrawingFiles(
      { HALO_E2E: '1', HALO_E2E_PICK_FILES: '/tmp/a.dxf,/tmp/b.dxf' },
      showOpenDialog,
    )

    expect(result).toEqual(['/tmp/a.dxf', '/tmp/b.dxf'])
    expect(showOpenDialog).not.toHaveBeenCalled()
  })

  it('trims whitespace around each HALO_E2E_PICK_FILES path', async () => {
    const result = await pickDrawingFiles(
      { HALO_E2E: '1', HALO_E2E_PICK_FILES: ' /tmp/a.dxf , /tmp/b.dxf ' },
      vi.fn(),
    )

    expect(result).toEqual(['/tmp/a.dxf', '/tmp/b.dxf'])
  })

  it('returns an empty array under HALO_E2E=1 when HALO_E2E_PICK_FILES is unset', async () => {
    const showOpenDialog = vi.fn()
    const result = await pickDrawingFiles({ HALO_E2E: '1' }, showOpenDialog)

    expect(result).toEqual([])
    expect(showOpenDialog).not.toHaveBeenCalled()
  })

  it('ignores HALO_E2E_PICK_FILES when HALO_E2E is not "1"', async () => {
    const showOpenDialog = vi.fn().mockResolvedValue({ canceled: false, filePaths: ['/real-dialog-path.dwg'] })
    const result = await pickDrawingFiles(
      { HALO_E2E: '0', HALO_E2E_PICK_FILES: '/should-not-be-used.dwg' },
      showOpenDialog,
    )

    expect(result).toEqual(['/real-dialog-path.dwg'])
    expect(showOpenDialog).toHaveBeenCalledTimes(1)
  })
})

// R1-05 (docs/contracts/r1.md §8): screen A's two folder pickers (전/후).
describe('pickFolder', () => {
  it('shows the real dialog and returns its first path when not in e2e mode', async () => {
    const showOpenDialog = vi.fn().mockResolvedValue({ canceled: false, filePaths: ['/before'] })
    const state: PickFolderQueueState = { queue: null }

    const result = await pickFolder({}, state, showOpenDialog)

    expect(result).toBe('/before')
    expect(showOpenDialog).toHaveBeenCalledTimes(1)
  })

  it('returns null when the real dialog is cancelled', async () => {
    const showOpenDialog = vi.fn().mockResolvedValue({ canceled: true, filePaths: [] })
    const state: PickFolderQueueState = { queue: null }

    const result = await pickFolder({}, state, showOpenDialog)

    expect(result).toBeNull()
  })

  it('consumes HALO_E2E_PICK_FOLDERS one entry per call (FIFO), not the dialog', async () => {
    const showOpenDialog = vi.fn()
    const env = { HALO_E2E: '1', HALO_E2E_PICK_FOLDERS: '/before-dir, /after-dir' }
    const state: PickFolderQueueState = { queue: null }

    const first = await pickFolder(env, state, showOpenDialog)
    const second = await pickFolder(env, state, showOpenDialog)
    const third = await pickFolder(env, state, showOpenDialog)

    expect(first).toBe('/before-dir')
    expect(second).toBe('/after-dir')
    expect(third).toBeNull()
    expect(showOpenDialog).not.toHaveBeenCalled()
  })

  it('parses HALO_E2E_PICK_FOLDERS only once even if it is absent on a later call', async () => {
    // The queue is parsed lazily on the first call and then only ever
    // shifted -- a later call site that forgot to pass the env var again
    // must not reset an in-progress queue back to empty.
    const state: PickFolderQueueState = { queue: null }
    const first = await pickFolder({ HALO_E2E: '1', HALO_E2E_PICK_FOLDERS: '/a,/b' }, state, vi.fn())
    const second = await pickFolder({ HALO_E2E: '1' }, state, vi.fn())

    expect(first).toBe('/a')
    expect(second).toBe('/b')
  })

  it('returns null under HALO_E2E=1 when HALO_E2E_PICK_FOLDERS is unset', async () => {
    const state: PickFolderQueueState = { queue: null }
    const result = await pickFolder({ HALO_E2E: '1' }, state, vi.fn())

    expect(result).toBeNull()
  })
})

describe('recordE2EOpenedPath', () => {
  it('starts a fresh list when HALO_E2E_OPENED_PATHS is unset', () => {
    expect(recordE2EOpenedPath({}, '/out/A-101_markup.dwg')).toBe('/out/A-101_markup.dwg')
  })

  it('appends to an existing comma-separated list', () => {
    const env = { HALO_E2E_OPENED_PATHS: '/out/a.dwg' }
    expect(recordE2EOpenedPath(env, '/out/b.dwg')).toBe('/out/a.dwg,/out/b.dwg')
  })
})

describe('openPath', () => {
  it('calls the real shell.openPath when not in e2e mode', async () => {
    const shellOpenPath = vi.fn().mockResolvedValue('')

    await openPath({}, '/out/run.json', shellOpenPath)

    expect(shellOpenPath).toHaveBeenCalledWith('/out/run.json')
  })

  it('throws when the real shell.openPath reports an error', async () => {
    const shellOpenPath = vi.fn().mockResolvedValue('no application registered')

    await expect(openPath({}, '/out/run.json', shellOpenPath)).rejects.toThrow(
      'no application registered',
    )
  })

  it('records the path instead of opening it under HALO_E2E=1', async () => {
    const shellOpenPath = vi.fn()
    const env: Record<string, string | undefined> = { HALO_E2E: '1' }

    await openPath(env, '/out/run.json', shellOpenPath)

    expect(shellOpenPath).not.toHaveBeenCalled()
    expect(process.env.HALO_E2E_OPENED_PATHS).toBe('/out/run.json')
    delete process.env.HALO_E2E_OPENED_PATHS
  })
})
