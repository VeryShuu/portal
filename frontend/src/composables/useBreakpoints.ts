import { onBeforeUnmount, onMounted, ref } from 'vue'

const BP_MD = 768
const BP_LG = 1024
const BP_XL = 1280
const BP_2XL = 1536

export function useBreakpoints() {
  const isMobile = ref(false)
  const isTablet = ref(false)
  const isWide = ref(false)
  const isDesktopXl = ref(false)

  function update() {
    if (typeof window === 'undefined') return
    const w = window.innerWidth
    isMobile.value = w < BP_MD
    isTablet.value = w >= BP_MD && w < BP_LG
    isWide.value = w >= BP_XL
    isDesktopXl.value = w >= BP_2XL
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

  return { isMobile, isTablet, isWide, isDesktopXl, update }
}
