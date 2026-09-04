import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '../../i18n/i18n'
import { ImportSettingsPanel } from './ImportSettingsPanel'
import * as api from './api'

vi.mock('./api', () => ({
  getImportSettings: vi.fn(),
  updateImportSettings: vi.fn(),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ImportSettingsPanel', () => {
  it('loads and renders the current search paths and ignore patterns', async () => {
    vi.mocked(api.getImportSettings).mockResolvedValue({
      searchPaths: ['/xr'],
      ignorePatterns: ['*_recover.dwg', '*.bak'],
    })

    render(<ImportSettingsPanel projectId="proj-1" />)

    expect(await screen.findByText('/xr')).toBeInTheDocument()
    expect(screen.getByText('*_recover.dwg')).toBeInTheDocument()
    expect(screen.getByText('*.bak')).toBeInTheDocument()
  })

  it('shows the empty-state message for search paths when there are none', async () => {
    vi.mocked(api.getImportSettings).mockResolvedValue({ searchPaths: [], ignorePatterns: [] })
    render(<ImportSettingsPanel projectId="proj-1" />)
    expect(await screen.findByText('검색 경로 없음')).toBeInTheDocument()
  })

  it('adding a search path saves the merged list', async () => {
    vi.mocked(api.getImportSettings).mockResolvedValue({ searchPaths: [], ignorePatterns: ['*.bak'] })
    vi.mocked(api.updateImportSettings).mockResolvedValue({
      searchPaths: ['/new'],
      ignorePatterns: ['*.bak'],
    })

    render(<ImportSettingsPanel projectId="proj-1" />)
    await screen.findByText('검색 경로 없음')

    fireEvent.change(screen.getByPlaceholderText('폴더 경로 붙여넣기'), { target: { value: '/new' } })
    fireEvent.click(screen.getByText('경로 추가'))

    await waitFor(() => {
      expect(api.updateImportSettings).toHaveBeenCalledWith('proj-1', {
        searchPaths: ['/new'],
        ignorePatterns: ['*.bak'],
      })
    })
    expect(await screen.findByText('저장됨')).toBeInTheDocument()
  })

  it('removing an ignore pattern saves the list without it', async () => {
    vi.mocked(api.getImportSettings).mockResolvedValue({
      searchPaths: [],
      ignorePatterns: ['*_recover.dwg', '*.bak'],
    })
    vi.mocked(api.updateImportSettings).mockResolvedValue({
      searchPaths: [],
      ignorePatterns: ['*.bak'],
    })

    render(<ImportSettingsPanel projectId="proj-1" />)
    await screen.findByText('*_recover.dwg')

    fireEvent.click(screen.getByLabelText('제거: *_recover.dwg'))

    await waitFor(() => {
      expect(api.updateImportSettings).toHaveBeenCalledWith('proj-1', {
        searchPaths: [],
        ignorePatterns: ['*.bak'],
      })
    })
  })
})
