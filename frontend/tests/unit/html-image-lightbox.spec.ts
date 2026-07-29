import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { defineComponent } from 'vue'

/**
 * NModal от Naive UI использует Teleport (монтируется в document.body), что
 * в jsdom мешает проверять видимость через wrapper.find. Мокаем naive-ui целиком,
 * подставляя NModal-стаб, который рендерит slot inline только при show=true.
 */
vi.mock('naive-ui', () => ({
  NModal: defineComponent({
    name: 'NModal',
    props: { show: { type: Boolean, default: false }, autoFocus: { type: Boolean, default: false } },
    emits: ['update:show'],
    template: '<div v-if="show" class="n-modal-stub"><slot /></div>',
  }),
}))

// Импорт ПОСЛЕ vi.mock, чтобы naive-ui разрешился в mock.
const HtmlImageLightbox = (await import('../../src/components/HtmlImageLightbox.vue')).default

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    ru: { common: { imageClose: 'Кликните в любом месте, чтобы закрыть' } },
    en: { common: { imageClose: 'Click anywhere to close' } },
  },
})

function mountLightbox(slottedHtml: string) {
  return mount(HtmlImageLightbox, {
    slots: { default: slottedHtml },
    global: { plugins: [i18n] },
  })
}

describe('HtmlImageLightbox — общий лайтбокс для inline-картинок', () => {
  beforeEach(() => {
    process.env.NODE_ENV = 'test'
  })

  it('рендерит slot-контент и не показывает лайтбокс', () => {
    const wrapper = mountLightbox('<p class="content">текст</p>')
    expect(wrapper.find('.content').exists()).toBe(true)
    expect(wrapper.find('.lightbox').exists()).toBe(false)
  })

  it('клик по <img> открывает лайтбокс с src/alt картинки', async () => {
    const wrapper = mountLightbox(
      '<p><img class="pic" src="/img/a.png" alt="диаграмма"></p>',
    )
    await wrapper.find('img.pic').trigger('click')

    expect(wrapper.find('.lightbox').exists()).toBe(true)
    const img = wrapper.find('.lightbox__img')
    expect(img.attributes('src')).toBe('/img/a.png')
    expect(img.attributes('alt')).toBe('диаграмма')
    expect(wrapper.find('.lightbox__close').text()).toContain('закрыть')
  })

  it('клик по элементу, отличному от img, не открывает лайтбокс', async () => {
    const wrapper = mountLightbox(
      '<div><p class="text">текст</p><img class="pic" src="/img/a.png"></div>',
    )
    await wrapper.find('.text').trigger('click')
    expect(wrapper.find('.lightbox').exists()).toBe(false)
  })

  it('img без src игнорируется (лайтбокс не открывается)', async () => {
    const wrapper = mountLightbox('<img class="pic" alt="без src">')
    await wrapper.find('img.pic').trigger('click')
    expect(wrapper.find('.lightbox').exists()).toBe(false)
  })

  it('клик по overlay закрывает лайтбокс', async () => {
    const wrapper = mountLightbox('<img class="pic" src="/img/a.png" alt="x">')
    await wrapper.find('img.pic').trigger('click')
    expect(wrapper.find('.lightbox').exists()).toBe(true)

    await wrapper.find('.lightbox').trigger('click')
    expect(wrapper.find('.lightbox').exists()).toBe(false)
  })

  it('preventDefault вызывается для клика по картинке', async () => {
    const wrapper = mountLightbox('<img class="pic" src="/img/a.png">')
    const evt = new MouseEvent('click', { bubbles: true, cancelable: true })
    const imgEl = wrapper.find('img.pic').element
    Object.defineProperty(evt, 'target', { value: imgEl })
    ;(wrapper.element as HTMLElement).dispatchEvent(evt)
    expect(evt.defaultPrevented).toBe(true)
  })
})
