import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { isPreviewableImage, isPreviewablePdf, type NCItem } from '../api/files'

export interface FilesSelectionCallbacks {
  onOpenDir?: (item: NCItem) => void
  onPreview?: (item: NCItem) => void
}

export function useFilesSelection(
  items: Ref<NCItem[]>,
  folderId: Ref<string | null>,
  callbacks?: FilesSelectionCallbacks,
): {
  selectedKeys: Ref<string[]>
  lastSelectedIndex: Ref<number | null>
  selectedFilenames: ComputedRef<string[]>
  onRowClick(row: NCItem, index: number, e: MouseEvent): void
  clearSelection(): void
} {
  const selectedKeys = ref<string[]>([])
  const lastSelectedIndex = ref<number | null>(null)

  watch(folderId, () => clearSelection())

  const selectedFilenames = computed(() => {
    const names: string[] = []
    for (const it of items.value) {
      if (selectedKeys.value.includes(it.nc_path) && !it.is_dir) {
        names.push(it.name)
      }
    }
    return names
  })

  function clearSelection() {
    selectedKeys.value = []
    lastSelectedIndex.value = null
  }

  function onRowClick(row: NCItem, index: number, e: MouseEvent) {
    if (row.is_dir) {
      if (!e.shiftKey && !e.ctrlKey && !e.metaKey) {
        callbacks?.onOpenDir?.(row)
      }
      return
    }

    if (e.shiftKey && lastSelectedIndex.value !== null) {
      e.preventDefault()
      const start = Math.min(lastSelectedIndex.value, index)
      const end = Math.max(lastSelectedIndex.value, index)
      const range = items.value
        .slice(start, end + 1)
        .filter((it) => !it.is_dir)
        .map((it) => it.nc_path)
      const set = new Set(selectedKeys.value)
      for (const k of range) set.add(k)
      selectedKeys.value = Array.from(set)
      return
    }

    if (e.ctrlKey || e.metaKey) {
      e.preventDefault()
      const set = new Set(selectedKeys.value)
      if (set.has(row.nc_path)) {
        set.delete(row.nc_path)
      } else {
        set.add(row.nc_path)
      }
      selectedKeys.value = Array.from(set)
      lastSelectedIndex.value = index
      return
    }

    lastSelectedIndex.value = index
    if (!selectedKeys.value.length) {
      if (isPreviewableImage(row) || isPreviewablePdf(row)) {
        callbacks?.onPreview?.(row)
      }
    }
  }

  return { selectedKeys, lastSelectedIndex, selectedFilenames, onRowClick, clearSelection }
}
