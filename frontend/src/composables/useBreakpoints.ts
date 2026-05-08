import { onBeforeUnmount, onMounted, ref } from 'vue'

const MOBILE_MAX = 768
const TABLET_MAX = 1024

export function useBreakpoints() {
  const isMobile = ref(false)
  const isTablet = ref(false)

  function update() {
    if (typeof window === 'undefined') return
    const w = window.innerWidth
    isMobile.value = w < MOBILE_MAX
    isTablet.value = w >= MOBILE_MAX && w < TABLET_MAX
  }

  onMounted(() => {
    if (typeof window === 'undefined') return
    update()
    window.addEventListener('resize', update)
  })

  onBeforeUnmount(() => {
    if (typeof window === 'undefined') return
    window.removeEventListener('resize', update)
  })

  return { isMobile, isTablet, update }
}
