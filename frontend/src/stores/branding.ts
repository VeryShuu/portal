import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { GlobalThemeOverrides } from 'naive-ui'
import { lightThemeOverrides, darkThemeOverrides } from '../styles/naive-theme'
import { api } from '../api'

export interface BrandingSettings {
  portal_name: string
  portal_tagline: string
  accent_color: string
  welcome_subtitle: string
  banner_enabled: boolean
  banner_text: string
  banner_type: 'info' | 'warning' | 'error' | 'success'
  banner_expires_at: string | null
  has_favicon?: boolean
  has_login_bg?: boolean
  has_logo?: boolean
  allowed_iframe_origins?: string[]
}

const DEFAULTS: BrandingSettings = {
  portal_name: 'Корпоративный портал',
  portal_tagline: '',
  accent_color: '#d8262c',
  welcome_subtitle: '',
  banner_enabled: false,
  banner_text: '',
  banner_type: 'info',
  banner_expires_at: null,
}

function hexToRgb(hex: string): [number, number, number] | null {
  const m = /^#([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : null
}

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255; g /= 255; b /= 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  let h = 0, s = 0
  const l = (max + min) / 2
  if (max !== min) {
    const d = max - min
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6
    else if (max === g) h = ((b - r) / d + 2) / 6
    else h = ((r - g) / d + 4) / 6
  }
  return [h, s, l]
}

function hslToHex(h: number, s: number, l: number): string {
  let r: number, g: number, b: number
  if (s === 0) {
    r = g = b = l
  } else {
    const hue2rgb = (p: number, q: number, t: number) => {
      if (t < 0) t += 1
      if (t > 1) t -= 1
      if (t < 1 / 6) return p + (q - p) * 6 * t
      if (t < 1 / 2) return q
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6
      return p
    }
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s
    const p = 2 * l - q
    r = hue2rgb(p, q, h + 1 / 3)
    g = hue2rgb(p, q, h)
    b = hue2rgb(p, q, h - 1 / 3)
  }
  const toHex = (x: number) => Math.round(x * 255).toString(16).padStart(2, '0')
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`
}

function deriveAccent(hex: string) {
  const rgb = hexToRgb(hex)
  if (!rgb) return { base: hex, hover: hex, pressed: hex }
  const [h, s, l] = rgbToHsl(...rgb)
  return {
    base: hex,
    hover: hslToHex(h, s, Math.max(0, l - 0.08)),
    pressed: hslToHex(h, s, Math.max(0, l - 0.16)),
  }
}

function applyCssVars(hex: string) {
  const { base, hover, pressed } = deriveAccent(hex)
  const root = document.documentElement
  root.style.setProperty('--color-brand-red', base)
  root.style.setProperty('--color-brand-red-hover', hover)
  root.style.setProperty('--color-brand-red-pressed', pressed)
  root.style.setProperty('--color-brand-red-soft', `${base}20`)
  root.style.setProperty('--color-danger', base)
}

let _faviconVersion = 1

function applyFavicon(hasFavicon?: boolean) {
  if (!hasFavicon) return
  let link = document.querySelector<HTMLLinkElement>('link[rel~="icon"]')
  if (!link) {
    link = document.createElement('link')
    link.rel = 'icon'
    document.head.appendChild(link)
  }
  const href = `/api/v1/branding/favicon?v=${_faviconVersion}`
  if (link.href !== href) {
    link.href = href
  }
}

export const useBrandingStore = defineStore('branding', () => {
  const settings = ref<BrandingSettings>({ ...DEFAULTS })
  const loaded = ref(false)

  const isBannerActive = computed(() => {
    if (!settings.value.banner_enabled || !settings.value.banner_text) return false
    if (settings.value.banner_expires_at) {
      return new Date(settings.value.banner_expires_at) > new Date()
    }
    return true
  })

  const accent = computed(() => deriveAccent(settings.value.accent_color))

  const lightOverrides = computed<GlobalThemeOverrides>(() => ({
    ...lightThemeOverrides,
    common: {
      ...lightThemeOverrides.common,
      primaryColor: accent.value.base,
      primaryColorHover: accent.value.hover,
      primaryColorPressed: accent.value.pressed,
      primaryColorSuppl: accent.value.hover,
      errorColor: accent.value.base,
      errorColorHover: accent.value.hover,
    },
    Menu: {
      ...lightThemeOverrides.Menu,
      itemTextColorActive: accent.value.base,
      itemIconColorActive: accent.value.base,
      itemTextColorActiveHover: accent.value.hover,
      itemIconColorActiveHover: accent.value.hover,
      itemColorActive: `${accent.value.base}14`,
      itemColorActiveHover: `${accent.value.base}1f`,
    },
  }))

  const darkOverrides = computed<GlobalThemeOverrides>(() => ({
    ...darkThemeOverrides,
    common: {
      ...darkThemeOverrides.common,
      primaryColor: accent.value.base,
      primaryColorHover: accent.value.hover,
      primaryColorPressed: accent.value.pressed,
      primaryColorSuppl: accent.value.hover,
      errorColor: accent.value.base,
      errorColorHover: accent.value.hover,
    },
    Menu: {
      ...darkThemeOverrides.Menu,
      itemTextColorActive: accent.value.base,
      itemIconColorActive: accent.value.base,
      itemColorActive: `${accent.value.base}29`,
      itemColorActiveHover: `${accent.value.base}3d`,
    },
  }))

  async function load() {
    try {
      const data = await api<Partial<BrandingSettings>>('/branding/settings')
      settings.value = { ...DEFAULTS, ...data }
    } catch (err) {
      console.error('[branding] Failed to load branding settings:', err)
    }
    _apply()
    loaded.value = true
  }

  function setSettings(data: Partial<BrandingSettings>): void {
    settings.value = { ...DEFAULTS, ...data }
    _apply()
    loaded.value = true
  }

  function _apply() {
    applyCssVars(settings.value.accent_color)
    if (settings.value.portal_name) {
      document.title = settings.value.portal_name
    }
    applyFavicon(settings.value.has_favicon)
  }

  async function save(updates: Partial<BrandingSettings>) {
    const previous = { ...settings.value }
    const next = { ...settings.value, ...updates }
    try {
      const saved = await api<BrandingSettings>('/admin/branding/settings', {
        method: 'PUT',
        body: next,
      })
      settings.value = { ...DEFAULTS, ...saved }
      _faviconVersion++
      _apply()
    } catch (err) {
      // Rollback optimistic update so the UI reflects server state
      settings.value = previous
      throw err
    }
  }

  return {
    settings,
    loaded,
    isBannerActive,
    accent,
    lightOverrides,
    darkOverrides,
    load,
    setSettings,
    save,
  }
})
