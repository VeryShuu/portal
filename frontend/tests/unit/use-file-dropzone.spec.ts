import { describe, it, expect, vi } from 'vitest'
import { useFileDropzone } from '../../src/composables/useFileDropzone'

function dragOverEvent(types: string[]) {
  const dataTransfer = { types, dropEffect: 'none' as string }
  return { dataTransfer } as unknown as DragEvent & { dataTransfer: { dropEffect: string } }
}

function dropEvent(files: File[]) {
  return { dataTransfer: { files } } as unknown as DragEvent
}

const f = (name: string) => new File(['x'], name, { type: 'text/plain' })

describe('useFileDropzone', () => {
  it('activates drag state and sets copy effect only when dragging files', () => {
    const dz = useFileDropzone({ onFiles: vi.fn() })
    const e = dragOverEvent(['Files'])
    dz.onDragOver(e)
    expect(dz.isDragOver.value).toBe(true)
    expect(e.dataTransfer.dropEffect).toBe('copy')
  })

  it('ignores dragover that carries no files (text/element drags)', () => {
    const dz = useFileDropzone({ onFiles: vi.fn() })
    dz.onDragOver(dragOverEvent(['text/plain']))
    expect(dz.isDragOver.value).toBe(false)
  })

  it('does not activate when disabled', () => {
    const dz = useFileDropzone({ onFiles: vi.fn(), enabled: () => false })
    dz.onDragOver(dragOverEvent(['Files']))
    expect(dz.isDragOver.value).toBe(false)
  })

  it('clears drag state on dragleave when leaving the dropzone', () => {
    const dz = useFileDropzone({ onFiles: vi.fn() })
    dz.onDragOver(dragOverEvent(['Files']))
    const current = { contains: () => false } as unknown as HTMLElement
    dz.onDragLeave({ currentTarget: current, relatedTarget: {} } as unknown as DragEvent)
    expect(dz.isDragOver.value).toBe(false)
  })

  it('keeps drag state when moving onto a child element', () => {
    const dz = useFileDropzone({ onFiles: vi.fn() })
    dz.onDragOver(dragOverEvent(['Files']))
    const current = { contains: () => true } as unknown as HTMLElement
    dz.onDragLeave({ currentTarget: current, relatedTarget: {} } as unknown as DragEvent)
    expect(dz.isDragOver.value).toBe(true)
  })

  it('passes all dropped files to onFiles and resets drag state', async () => {
    const onFiles = vi.fn()
    const dz = useFileDropzone({ onFiles })
    dz.onDragOver(dragOverEvent(['Files']))
    await dz.onDrop(dropEvent([f('a.txt'), f('b.txt')]))
    expect(dz.isDragOver.value).toBe(false)
    expect(onFiles).toHaveBeenCalledTimes(1)
    expect(onFiles.mock.calls[0][0]).toHaveLength(2)
  })

  it('does not call onFiles on an empty drop', async () => {
    const onFiles = vi.fn()
    const dz = useFileDropzone({ onFiles })
    await dz.onDrop(dropEvent([]))
    expect(onFiles).not.toHaveBeenCalled()
  })

  it('does not call onFiles on drop when disabled', async () => {
    const onFiles = vi.fn()
    const dz = useFileDropzone({ onFiles, enabled: () => false })
    await dz.onDrop(dropEvent([f('a.txt')]))
    expect(onFiles).not.toHaveBeenCalled()
  })
})
