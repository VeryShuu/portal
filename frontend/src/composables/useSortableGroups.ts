import { watch, onUnmounted } from 'vue'
import type { ComputedRef } from 'vue'
import Sortable from 'sortablejs'

type SortableEntry = { el: HTMLElement; instance: Sortable }

export function useSortableGroups(
  canDrag: ComputedRef<boolean>,
  onReorder: (group: string, fromIdx: number, toIdx: number) => void,
) {
  const sortableInstances = new Map<string, SortableEntry>()

  function bindSortable(el: Element | null, group: string) {
    const existing = sortableInstances.get(group)
    if (!el) {
      if (existing) {
        existing.instance.destroy()
        sortableInstances.delete(group)
      }
      return
    }
    const htmlEl = el as HTMLElement
    if (existing && existing.el === htmlEl) return
    if (existing) existing.instance.destroy()

    const instance = Sortable.create(htmlEl, {
      handle: '.drag-handle',
      animation: 150,
      ghostClass: 'sortable-ghost',
      chosenClass: 'sortable-chosen',
      dragClass: 'sortable-drag',
      disabled: !canDrag.value,
      onEnd(evt) {
        const oldIdx = evt.oldIndex
        const newIdx = evt.newIndex
        if (oldIdx == null || newIdx == null || oldIdx === newIdx) return

        const item = evt.item
        const parent = evt.from
        parent.removeChild(item)
        const refNode = parent.children[oldIdx] ?? null
        parent.insertBefore(item, refNode)

        onReorder(group, oldIdx, newIdx)
      },
    })
    sortableInstances.set(group, { el: htmlEl, instance })
  }

  watch(canDrag, (val) => {
    for (const { instance } of sortableInstances.values()) {
      instance.option('disabled', !val)
    }
  })

  onUnmounted(() => {
    for (const { instance } of sortableInstances.values()) instance.destroy()
    sortableInstances.clear()
  })

  return { bindSortable }
}
