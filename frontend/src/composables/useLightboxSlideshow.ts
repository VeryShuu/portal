import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useInterval } from './useInterval'

export function useLightboxSlideshow(onTick: () => void) {
  const { t } = useI18n()

  const slideshowDelay = ref(5000)
  const slideshowActive = ref(false)
  const slideshow = useInterval(onTick, 5000)

  const slideshowOptions = computed(() => {
    const opts: { label: string; key: string }[] = [
      { label: t('photos.lightbox.slideshow5s'), key: '5000' },
      { label: t('photos.lightbox.slideshow10s'), key: '10000' },
      { label: t('photos.lightbox.slideshow30s'), key: '30000' },
    ]
    if (slideshowActive.value) opts.unshift({ label: t('photos.lightbox.slideshowStop'), key: 'stop' })
    return opts
  })

  function startSlideshow(delay: number) {
    slideshowDelay.value = delay
    slideshowActive.value = true
    slideshow.start(delay)
  }

  function stopSlideshow() {
    slideshowActive.value = false
    slideshow.stop()
  }

  function onSlideshowSelect(key: string) {
    if (key === 'stop') stopSlideshow(); else startSlideshow(Number(key))
  }

  function onVisibilityChange() {
    if (!slideshowActive.value) return
    if (document.hidden) slideshow.stop()
    else slideshow.start(slideshowDelay.value)
  }

  return { slideshowDelay, slideshowActive, slideshowOptions, startSlideshow, stopSlideshow, onSlideshowSelect, onVisibilityChange }
}
