import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'

const create = vi.fn()

vi.mock('sortablejs', () => ({
  default: { create },
}))

async function setupHost() {
  const canDrag = ref(true)
  const onReorder = vi.fn()
  const groups: Record<string, any> = {}
  const mod = await import('../../src/composables/useSortableGroups')

  const Host = defineComponent({
    setup() {
      const api = mod.useSortableGroups(canDrag as any, onReorder)
      groups.bindSortable = api.bindSortable
      return () => h('div')
    },
  })
  const wrapper = mount(Host)
  return { wrapper, canDrag, onReorder, groups }
}

describe('cov-feat useSortableGroups', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('bindSortable creates/destroys and handles rebind rules', async () => {
    const { groups } = await setupHost()
    const option = vi.fn()
    const destroy = vi.fn()
    create.mockReturnValue({ option, destroy })

    const el = document.createElement('div')
    groups.bindSortable(el, 'g1')
    expect(create).toHaveBeenCalledTimes(1)

    groups.bindSortable(el, 'g1')
    expect(create).toHaveBeenCalledTimes(1)

    const el2 = document.createElement('div')
    groups.bindSortable(el2, 'g1')
    expect(destroy).toHaveBeenCalledTimes(1)
    expect(create).toHaveBeenCalledTimes(2)

    groups.bindSortable(null, 'g1')
    expect(destroy).toHaveBeenCalledTimes(2)
  })

  it('onEnd no-ops for null/same indices and reorders for valid move', async () => {
    const { groups, onReorder } = await setupHost()
    let onEnd: any = null
    create.mockImplementation((_el: any, cfg: any) => {
      onEnd = cfg.onEnd
      return { option: vi.fn(), destroy: vi.fn() }
    })

    const parent = document.createElement('div')
    const a = document.createElement('div')
    a.textContent = 'A'
    const b = document.createElement('div')
    b.textContent = 'B'
    parent.appendChild(a)
    parent.appendChild(b)

    groups.bindSortable(parent, 'g2')

    onEnd({ oldIndex: null, newIndex: 1, item: a, from: parent })
    onEnd({ oldIndex: 0, newIndex: 0, item: a, from: parent })
    expect(onReorder).not.toHaveBeenCalled()

    parent.removeChild(a)
    parent.appendChild(a)
    onEnd({ oldIndex: 0, newIndex: 1, item: a, from: parent })
    expect(parent.children[0].textContent).toBe('A')
    expect(onReorder).toHaveBeenCalledWith('g2', 0, 1)
  })

  it('reacts to canDrag changes and destroys all on unmount', async () => {
    const { groups, canDrag, wrapper } = await setupHost()
    const option1 = vi.fn()
    const option2 = vi.fn()
    const destroy1 = vi.fn()
    const destroy2 = vi.fn()

    create
      .mockReturnValueOnce({ option: option1, destroy: destroy1 })
      .mockReturnValueOnce({ option: option2, destroy: destroy2 })

    groups.bindSortable(document.createElement('div'), 'a')
    groups.bindSortable(document.createElement('div'), 'b')

    canDrag.value = false
    await Promise.resolve()
    expect(option1).toHaveBeenCalledWith('disabled', true)
    expect(option2).toHaveBeenCalledWith('disabled', true)

    wrapper.unmount()
    expect(destroy1).toHaveBeenCalled()
    expect(destroy2).toHaveBeenCalled()
  })
})
