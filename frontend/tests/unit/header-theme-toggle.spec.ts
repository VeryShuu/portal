import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: { ru: {}, en: {} },
})

vi.mock('naive-ui', () => ({
  NButton: {
    name: 'NButton',
    props: ['quaternary', 'circle', 'ariaLabel', 'aria-label'],
    emits: ['click'],
    template:
      '<button class="n-button" :aria-label="ariaLabel || ariaLabel" @click="$emit(\'click\', $event)"><slot name="icon" /><slot /></button>',
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
  NTooltip: {
    template: '<span class="n-tooltip"><slot name="trigger" /><slot /></span>',
  },
}))

vi.mock('@vicons/ionicons5', () => ({
  SunnyOutline: { template: '<span class="icon-sunny" />' },
  MoonOutline: { template: '<span class="icon-moon" />' },
}))

import HeaderThemeToggle from '../../src/components/layout/HeaderThemeToggle.vue'
import { useThemeStore } from '../../src/stores/theme'

function mountToggle() {
  return mount(HeaderThemeToggle, { global: { plugins: [i18n] } })
}

describe('HeaderThemeToggle.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('renders the Moon icon when theme is light and toggles to dark on click', async () => {
    const wrapper = mountToggle()
    const store = useThemeStore()

    // Default theme store initialises to light (no 'theme' key in localStorage).
    expect(store.isDark).toBe(false)
    expect(wrapper.find('.icon-moon').exists()).toBe(true)
    expect(wrapper.find('.icon-sunny').exists()).toBe(false)

    await wrapper.find('.n-button').trigger('click')

    expect(store.isDark).toBe(true)
    expect(localStorage.getItem('theme')).toBe('dark')
  })

  it('renders the Sun icon when theme is dark', async () => {
    localStorage.setItem('theme', 'dark')
    // Pinia store reads localStorage lazily at construction — recreate after seed.
    setActivePinia(createPinia())

    const wrapper = mountToggle()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.icon-sunny').exists()).toBe(true)
    expect(wrapper.find('.icon-moon').exists()).toBe(false)
  })

  it('exposes the aria-label from i18n', () => {
    const wrapper = mountToggle()
    expect(wrapper.find('.n-button').attributes('aria-label')).toContain('nav.toggleTheme')
  })
})
