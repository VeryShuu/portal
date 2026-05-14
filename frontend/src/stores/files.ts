import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useFilesStore = defineStore('files', () => {
  const selectedFolderId = ref<string | null>(null)

  function selectFolder(id: string | null): void {
    selectedFolderId.value = id
  }

  return {
    selectedFolderId,
    selectFolder,
  }
})
