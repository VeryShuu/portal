import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { Ref } from 'vue'
import Sortable from 'sortablejs'
import type { ClockCity } from './useWorldClockCities'

export function useWorldClockSortable(
  cities: Ref<ClockCity[]>,
  reorder: (next: ClockCity[]) => void,
) {
  const listRef = ref<HTMLElement | null>(null)
  let sortable: Sortable | null = null

  function initSortable() {
    sortable?.destroy()
    sortable = null
    if (!listRef.value) return
    sortable = Sortable.create(listRef.value, {
      handle: '.drag-handle',
      animation: 150,
      ghostClass: 'sortable-ghost',
      chosenClass: 'sortable-chosen',
      onEnd(evt) {
        const oldIdx = evt.oldIndex
        const newIdx = evt.newIndex
        if (oldIdx == null || newIdx == null || oldIdx === newIdx) return
        const next = [...cities.value]
        const [moved] = next.splice(oldIdx, 1)
        next.splice(newIdx, 0, moved)
        reorder(next)
        nextTick(() => initSortable())
      },
    })
  }

  watch(listRef, () => initSortable())

  function destroySortable() {
    sortable?.destroy()
    sortable = null
  }

  onBeforeUnmount(destroySortable)

  return { listRef, initSortable, destroySortable }
}
