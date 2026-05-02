import { ref } from 'vue'

const _headerText = ref<string>('')

export function useLayoutHeader() {
  function setHeader(text: string) {
    _headerText.value = text
  }

  function clearHeader() {
    _headerText.value = ''
  }

  return { headerText: _headerText, setHeader, clearHeader }
}
