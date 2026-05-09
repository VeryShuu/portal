import { computed, type ComputedRef } from 'vue'
import { useFilesStore } from '../stores/files'
import type { FileFolderTreeNode } from '../api/files'

export function useFilesTree(): {
  tree: ComputedRef<FileFolderTreeNode[]>
  loadingTree: ComputedRef<boolean>
  selectedFolderId: ComputedRef<string | null>
  selectFolder(id: string | null): void
  findNodeById(id: string): FileFolderTreeNode | null
  findNodeByNcPath(path: string): FileFolderTreeNode | null
  loadTree(): Promise<void>
} {
  const store = useFilesStore()

  return {
    tree: computed(() => store.tree),
    loadingTree: computed(() => store.loadingTree),
    selectedFolderId: computed(() => store.selectedFolderId),
    selectFolder: (id) => store.selectFolder(id),
    findNodeById: (id) => store.findNodeById(id),
    findNodeByNcPath: (path) => store.findNodeByNcPath(path),
    loadTree: () => store.loadTree(),
  }
}
