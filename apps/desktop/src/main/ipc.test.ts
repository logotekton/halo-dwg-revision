import { describe, expect, it, vi } from 'vitest'
import { pickDrawingFiles } from './ipc'

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
