import { ref } from 'vue'

export type PollPreviewSize = 's' | 'm' | 'l'

const STORAGE_KEY = 'news:poll-preview-size'
const VALID_SIZES: PollPreviewSize[] = ['s', 'm', 'l']

function readStoredSize(): PollPreviewSize {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (VALID_SIZES.includes(v as PollPreviewSize)) return v as PollPreviewSize
  } catch { /* ignore */ }
  return 'm'
}

// Настройка общая для всех опросов (module-scope singleton), персистится per-user
const previewSize = ref<PollPreviewSize>(readStoredSize())

export function usePollPreviewSize() {
  function setPreviewSize(v: PollPreviewSize) {
    previewSize.value = v
    try {
      localStorage.setItem(STORAGE_KEY, v)
    } catch { /* ignore */ }
  }

  return { previewSize, setPreviewSize }
}
