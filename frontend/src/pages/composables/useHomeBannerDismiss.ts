import { computed, ref } from 'vue'
import { useBrandingStore } from '../../stores/branding'

const BANNER_DISMISS_KEY = 'home_banner_dismissed'

export function useHomeBannerDismiss() {
  const branding = useBrandingStore()

  const bannerKey = computed(
    () => `${branding.settings.banner_text}|${branding.settings.banner_expires_at ?? ''}`,
  )
  const dismissedBannerKey = ref<string | null>(
    typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(BANNER_DISMISS_KEY) : null,
  )

  const showBanner = computed(
    () => branding.isBannerActive && dismissedBannerKey.value !== bannerKey.value,
  )

  function dismissBanner() {
    dismissedBannerKey.value = bannerKey.value
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.setItem(BANNER_DISMISS_KEY, bannerKey.value)
    }
  }

  return { branding, showBanner, dismissBanner }
}
