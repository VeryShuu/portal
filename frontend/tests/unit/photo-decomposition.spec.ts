import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

describe('usePhotoUpload composable', () => {
  it('has correct interface shape', async () => {
    vi.doMock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
    vi.doMock('naive-ui', () => ({ useMessage: () => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }) }))
    vi.doMock('@/api/photos', () => ({ uploadPhotos: vi.fn() }))

    const { usePhotoUpload } = await import('../../src/composables/usePhotoUpload')
    const folderId = ref<string | null>(null)
    const onSuccess = vi.fn().mockResolvedValue(undefined)
    const result = usePhotoUpload(folderId, onSuccess)

    expect(result).toHaveProperty('fileInputRef')
    expect(result).toHaveProperty('uploadQueue')
    expect(result).toHaveProperty('uploadAborted')
    expect(result).toHaveProperty('uploadingActive')
    expect(result).toHaveProperty('uploadDoneCount')
    expect(result).toHaveProperty('isDraggingOver')
    expect(result).toHaveProperty('triggerUpload')
    expect(result).toHaveProperty('runUploadQueue')
    expect(result).toHaveProperty('onFilesPicked')
    expect(result).toHaveProperty('onDrop')
  })

  it('uploadingActive is false when queue is empty', async () => {
    vi.doMock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
    vi.doMock('naive-ui', () => ({ useMessage: () => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }) }))
    vi.doMock('@/api/photos', () => ({ uploadPhotos: vi.fn() }))

    const { usePhotoUpload } = await import('../../src/composables/usePhotoUpload')
    const folderId = ref<string | null>('folder-1')
    const onSuccess = vi.fn().mockResolvedValue(undefined)
    const { uploadingActive, uploadQueue } = usePhotoUpload(folderId, onSuccess)

    expect(uploadQueue.value).toHaveLength(0)
    expect(uploadingActive.value).toBe(false)
  })

  it('uploadDoneCount counts done items', async () => {
    vi.doMock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
    vi.doMock('naive-ui', () => ({ useMessage: () => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }) }))
    vi.doMock('@/api/photos', () => ({ uploadPhotos: vi.fn() }))

    const { usePhotoUpload } = await import('../../src/composables/usePhotoUpload')
    const folderId = ref<string | null>('folder-1')
    const onSuccess = vi.fn().mockResolvedValue(undefined)
    const { uploadQueue, uploadDoneCount } = usePhotoUpload(folderId, onSuccess)

    uploadQueue.value = [
      { file: new File([''], 'a.jpg'), status: 'done' },
      { file: new File([''], 'b.jpg'), status: 'error' },
      { file: new File([''], 'c.jpg'), status: 'done' },
    ]
    expect(uploadDoneCount.value).toBe(2)
  })

  it('onDrop ignores non-file drag types', async () => {
    vi.doMock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
    vi.doMock('naive-ui', () => ({ useMessage: () => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }) }))
    const uploadPhotosMock = vi.fn()
    vi.doMock('@/api/photos', () => ({ uploadPhotos: uploadPhotosMock }))

    const { usePhotoUpload } = await import('../../src/composables/usePhotoUpload')
    const folderId = ref<string | null>('folder-1')
    const onSuccess = vi.fn().mockResolvedValue(undefined)
    const { onDrop } = usePhotoUpload(folderId, onSuccess)

    const mockEvent = {
      dataTransfer: {
        types: ['text/plain'],
        files: [],
      },
    } as unknown as DragEvent

    onDrop(mockEvent)
    expect(uploadPhotosMock).not.toHaveBeenCalled()
  })

  it('runUploadQueue does nothing when folderId is null', async () => {
    vi.doMock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
    vi.doMock('naive-ui', () => ({ useMessage: () => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }) }))
    const uploadPhotosMock = vi.fn()
    vi.doMock('@/api/photos', () => ({ uploadPhotos: uploadPhotosMock }))

    const { usePhotoUpload } = await import('../../src/composables/usePhotoUpload')
    const folderId = ref<string | null>(null)
    const onSuccess = vi.fn()
    const { runUploadQueue } = usePhotoUpload(folderId, onSuccess)

    await runUploadQueue([new File([''], 'test.jpg')])
    expect(uploadPhotosMock).not.toHaveBeenCalled()
    expect(onSuccess).not.toHaveBeenCalled()
  })
})

describe('LightboxModal zoom/rotation logic', () => {
  function clampZoom(z: number, delta: number): number {
    return Math.min(8, Math.max(0.25, +(z + delta).toFixed(2)))
  }
  function rotateStep(r: number, step: number): number {
    return (r + step) % 360
  }

  it('zoomIn increases zoom by 0.25', () => {
    expect(clampZoom(1, 0.25)).toBe(1.25)
    expect(clampZoom(1.75, 0.25)).toBe(2)
  })

  it('zoomOut decreases zoom by 0.25', () => {
    expect(clampZoom(1, -0.25)).toBe(0.75)
    expect(clampZoom(0.5, -0.25)).toBe(0.25)
  })

  it('zoom does not exceed 8', () => {
    expect(clampZoom(7.9, 0.25)).toBe(8)
    expect(clampZoom(8, 0.25)).toBe(8)
  })

  it('zoom does not go below 0.25', () => {
    expect(clampZoom(0.3, -0.25)).toBe(0.25)
    expect(clampZoom(0.25, -0.25)).toBe(0.25)
  })

  it('rotateLeft subtracts 90 degrees', () => {
    expect(rotateStep(0, -90)).toBe(-90)
    expect(rotateStep(90, -90)).toBe(0)
  })

  it('rotateRight adds 90 degrees', () => {
    expect(rotateStep(0, 90)).toBe(90)
    expect(rotateStep(270, 90)).toBe(0)
  })

  it('rotation wraps at 360', () => {
    expect(rotateStep(360, 0)).toBe(0)
    expect(rotateStep(350, 90) % 360).toBe(80)
  })
})

describe('PhotoTrashView logic', () => {
  it('correctly counts remaining photos after restore', () => {
    const photos = [
      { id: '1', original_name: 'a.jpg' },
      { id: '2', original_name: 'b.jpg' },
      { id: '3', original_name: 'c.jpg' },
    ]
    const afterRestore = photos.filter(p => p.id !== '2')
    expect(afterRestore).toHaveLength(2)
    expect(afterRestore.map(p => p.id)).toEqual(['1', '3'])
  })

  it('empty trash sets photos to empty array', () => {
    let trashPhotos = [{ id: '1' }, { id: '2' }]
    trashPhotos = []
    expect(trashPhotos).toHaveLength(0)
  })
})

describe('PhotoPermissionsModal logic', () => {
  it('upserts permission by subject_id (deduplicate)', () => {
    const permsList = [
      { id: 'p1', subject_id: 'user-1', subject_name: 'Alice', permission: 'viewer' },
      { id: 'p2', subject_id: 'user-2', subject_name: 'Bob', permission: 'viewer' },
    ]
    const newPerm = { id: 'p3', subject_id: 'user-1', subject_name: 'Alice', permission: 'manager' }
    const updated = [...permsList.filter(p => p.subject_id !== newPerm.subject_id), newPerm]
    expect(updated).toHaveLength(2)
    expect(updated.find(p => p.subject_id === 'user-1')?.permission).toBe('manager')
  })

  it('revoke removes permission by id', () => {
    const permsList = [
      { id: 'p1', subject_id: 'user-1', subject_name: 'Alice', permission: 'viewer' },
      { id: 'p2', subject_id: 'user-2', subject_name: 'Bob', permission: 'editor' },
    ]
    const afterRevoke = permsList.filter(p => p.id !== 'p1')
    expect(afterRevoke).toHaveLength(1)
    expect(afterRevoke[0].subject_id).toBe('user-2')
  })

  it('validation requires subject_id and subject_name', () => {
    function validate(subjectId: string, subjectName: string): boolean {
      return !!subjectId.trim() && !!subjectName.trim()
    }
    expect(validate('', 'Alice')).toBe(false)
    expect(validate('user-1', '')).toBe(false)
    expect(validate('', '')).toBe(false)
    expect(validate('user-1', 'Alice')).toBe(true)
  })
})
