import { onBeforeUnmount, onMounted, ref } from 'vue'

export function useEditorFullscreen() {
  const isFullscreen = ref(false)
  const isFocusMode = ref(false)

  function toggleFullscreen() {
    isFullscreen.value = !isFullscreen.value
  }

  function toggleFocusMode() {
    isFocusMode.value = !isFocusMode.value
  }

  function handleEscape(e: KeyboardEvent) {
    if (e.key === 'Escape' && isFullscreen.value) {
      isFullscreen.value = false
    }
  }

  onMounted(() => {
    window.addEventListener('keydown', handleEscape)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('keydown', handleEscape)
  })

  return { isFullscreen, isFocusMode, toggleFullscreen, toggleFocusMode }
}
