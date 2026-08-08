import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'

/**
 * HeroBgFocalEditor — компактный focal-point редактор (drag-маркер + zoom).
 * Контракты: рендерится только при наличии imageUrl; показывает превью с
 * маркером и zoom-слайдер; v-model пробрасывает focal-значения.
 */
const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: { ru: { admin: { branding: { heroBgZoom: 'Zoom', heroBgFocalLabel: 'Фокус' } } } },
})

vi.mock('naive-ui', () => ({
  NSlider: {
    name: 'NSlider',
    template: '<input class="n-slider" type="range" :value="String(value)" @input="onChange" />',
    props: ['value', 'min', 'max', 'step'],
    emits: ['update:value'],
    methods: {
      onChange(e: Event) {
        this.$emit('update:value', Number((e.target as HTMLInputElement).value))
      },
    },
  },
}))

describe('HeroBgFocalEditor', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('не рендерится без imageUrl', async () => {
    const HeroBgFocalEditor = (await import('../../src/components/widgets/HeroBgFocalEditor.vue')).default
    const wrapper = mount(HeroBgFocalEditor, {
      props: { imageUrl: null, focalX: null, focalY: null, focalZoom: null },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.hero-focal').exists()).toBe(false)
  })

  it('рендерит превью с маркером и zoom-слайдер при наличии imageUrl', async () => {
    const HeroBgFocalEditor = (await import('../../src/components/widgets/HeroBgFocalEditor.vue')).default
    const wrapper = mount(HeroBgFocalEditor, {
      props: { imageUrl: '/hero-bg-day.jpg', focalX: 30, focalY: 60, focalZoom: 150 },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('.hero-focal__preview').exists()).toBe(true)
    expect(wrapper.find('.hero-focal__img').exists()).toBe(true)
    expect(wrapper.find('.hero-focal__marker').exists()).toBe(true)
    // Маркер позиционируется по focalX/focalY (30%/60%)
    const markerStyle = wrapper.find('.hero-focal__marker').attributes('style') || ''
    expect(markerStyle).toContain('left: 30%')
    expect(markerStyle).toContain('top: 60%')
    expect(wrapper.find('.n-slider').exists()).toBe(true)
  })

  it('zoom-слайдер меняет focalZoom через update:value', async () => {
    const HeroBgFocalEditor = (await import('../../src/components/widgets/HeroBgFocalEditor.vue')).default
    const wrapper = mount(HeroBgFocalEditor, {
      props: { imageUrl: '/x.jpg', focalX: null, focalY: null, focalZoom: null },
      global: { plugins: [i18n] },
    })
    // Триггерим emit update:value от NSlider напрямую (надёжнее input-event в jsdom)
    const slider = wrapper.findComponent({ name: 'NSlider' })
    if (slider.exists()) {
      slider.vm.$emit('update:value', 180)
    } else {
      // fallback: input event на mock
      await wrapper.find('.n-slider').trigger('input', { target: { value: '180' } })
    }
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('update:focalZoom')?.[0]?.[0]).toBe(180)
  })

  it('zoom=100 сохраняется как null (соглашение: «без zoom»)', async () => {
    const HeroBgFocalEditor = (await import('../../src/components/widgets/HeroBgFocalEditor.vue')).default
    // focalZoom=150 (не null) → при zoom=100 меняется на null (реальное изменение → emit)
    const wrapper = mount(HeroBgFocalEditor, {
      props: { imageUrl: '/x.jpg', focalX: null, focalY: null, focalZoom: 150 },
      global: { plugins: [i18n] },
    })
    const slider = wrapper.findComponent({ name: 'NSlider' })
    slider.vm.$emit('update:value', 100)
    await wrapper.vm.$nextTick()
    const emitted = wrapper.emitted('update:focalZoom')
    expect(emitted).toBeTruthy()
    expect(emitted?.[0]?.[0]).toBeNull()
  })

  it('дефолтный маркер по центру (50%/50%) когда focal null', async () => {
    const HeroBgFocalEditor = (await import('../../src/components/widgets/HeroBgFocalEditor.vue')).default
    const wrapper = mount(HeroBgFocalEditor, {
      props: { imageUrl: '/x.jpg', focalX: null, focalY: null, focalZoom: null },
      global: { plugins: [i18n] },
    })
    const markerStyle = wrapper.find('.hero-focal__marker').attributes('style') || ''
    expect(markerStyle).toContain('left: 50%')
    expect(markerStyle).toContain('top: 50%')
  })

  it('клавиатурные стрелки двигают фокус (nudging)', async () => {
    const HeroBgFocalEditor = (await import('../../src/components/widgets/HeroBgFocalEditor.vue')).default
    const wrapper = mount(HeroBgFocalEditor, {
      props: { imageUrl: '/x.jpg', focalX: 50, focalY: 50, focalZoom: null },
      global: { plugins: [i18n] },
    })
    const preview = wrapper.find('.hero-focal__preview')
    // ArrowRight → focalX 50→51
    await preview.trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.emitted('update:focalX')?.[0]?.[0]).toBe(51)
    // Shift+ArrowDown → focalY 50→60 (шаг 10)
    await preview.trigger('keydown', { key: 'ArrowDown', shiftKey: true })
    expect(wrapper.emitted('update:focalY')?.[0]?.[0]).toBe(60)
  })

  it('колесо мыши меняет zoom', async () => {
    const HeroBgFocalEditor = (await import('../../src/components/widgets/HeroBgFocalEditor.vue')).default
    const wrapper = mount(HeroBgFocalEditor, {
      props: { imageUrl: '/x.jpg', focalX: null, focalY: null, focalZoom: null },
      global: { plugins: [i18n] },
    })
    // deltaY < 0 (скролл вверх) → zoom +5 → 105
    await wrapper.find('.hero-focal__preview').trigger('wheel', { deltaY: -100 })
    expect(wrapper.emitted('update:focalZoom')?.[0]?.[0]).toBe(105)
  })
})
