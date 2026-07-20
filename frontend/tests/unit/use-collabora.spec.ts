import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'

const openInCollaboraMock = vi.fn()
const windowOpenSpy = vi.fn()
const messageErrorMock = vi.fn()

vi.mock('../../src/api/files', () => ({
  openInCollabora: (...args: unknown[]) => openInCollaboraMock(...args),
}))

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('naive-ui', () => ({ useMessage: () => ({ error: messageErrorMock }) }))

import { useCollabora } from '../../src/composables/useCollabora'

describe('useCollabora (src/composables)', () => {
  beforeEach(() => {
    openInCollaboraMock.mockClear()
    windowOpenSpy.mockClear()
    messageErrorMock.mockClear()
    openInCollaboraMock.mockResolvedValue({ url: 'https://collabora.example/wopi' })
    vi.stubGlobal('open', windowOpenSpy)
  })

  it('openCollabora early-returns when folderId is null', async () => {
    const { openingCollaboraFile, openCollabora } = useCollabora(ref(null))

    await openCollabora({ name: 'doc.docx' } as any)
    expect(openingCollaboraFile.value).toBe(null)
    expect(openInCollaboraMock).not.toHaveBeenCalled()
  })

  it('openCollabora early-returns when already opening the same file', async () => {
    const folderId = ref('folder-1')
    const { openingCollaboraFile, openCollabora } = useCollabora(folderId)

    openingCollaboraFile.value = 'doc.docx'
    await openCollabora({ name: 'doc.docx' } as any)

    expect(openInCollaboraMock).not.toHaveBeenCalled()
  })

  it('opens the file in a new window with the returned URL on success', async () => {
    const { openingCollaboraFile, openCollabora } = useCollabora(ref('folder-1'))

    await openCollabora({ name: 'doc.docx' } as any)

    expect(openInCollaboraMock).toHaveBeenCalledWith('folder-1', 'doc.docx')
    expect(windowOpenSpy).toHaveBeenCalledWith(
      'https://collabora.example/wopi',
      '_blank',
      'noopener,noreferrer',
    )
    expect(openingCollaboraFile.value).toBe(null)
  })

  it('shows error toast and clears loading flag when API rejects', async () => {
    openInCollaboraMock.mockRejectedValueOnce(new Error('boom'))
    const { openingCollaboraFile, openCollabora } = useCollabora(ref('folder-1'))

    await openCollabora({ name: 'doc.docx' } as any)

    expect(messageErrorMock).toHaveBeenCalledWith('files.error.collabora')
    expect(windowOpenSpy).not.toHaveBeenCalled()
    expect(openingCollaboraFile.value).toBe(null)
  })

  it('sets openingCollaboraFile to the item name during the request', async () => {
    let observedDuringRequest: string | null = 'untouched'
    openInCollaboraMock.mockImplementationOnce(async () => {
      // The composable sets the ref before awaiting openInCollabora.
      return new Promise((resolve) => setTimeout(() => resolve({ url: 'u' }), 0))
    })
    const { openingCollaboraFile, openCollabora } = useCollabora(ref('folder-1'))

    const promise = openCollabora({ name: 'doc2.docx' } as any)
    observedDuringRequest = openingCollaboraFile.value
    await promise

    expect(observedDuringRequest).toBe('doc2.docx')
    expect(openingCollaboraFile.value).toBe(null)
  })
})
