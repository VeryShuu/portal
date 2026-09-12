import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useLayoutStore = defineStore('layout', () => {
  const headerText = ref('')

  function setHeader(text: string) {
    headerText.value = text
  }

  function clearHeader() {
    headerText.value = ''
  }

  return { headerText, setHeader, clearHeader }
})
