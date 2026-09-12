/**
 * Настройка размера превью картинок в опросах:
 * composable usePollPreviewSize (localStorage-персистентность) и тулбар PollQuestion
 * (подсказка «нажмите, чтобы увеличить» + переключатель S/M/L).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

vi.mock('naive-ui', () => ({
  NButton: {
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'quaternary', 'disabled'],
    emits: ['click'],
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>', props: ['size'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['size', 'type', 'round'] },
  NInput: { template: '<input />', props: ['value', 'placeholder'] },
}))

vi.mock('@vicons/ionicons5', () => ({
  ExpandOutline: { template: '<span class="zoom-icon" />' },
}))

vi.mock('../../src/components/news/poll/PollOption.vue', () => ({
  default: { name: 'PollOption', props: ['opt', 'question', 'hasImages', 'selected', 'hasVoted', 'submitting', 'isInteractive', 'canSeeResults', 'optionIndex'], template: '<div class="poll-option-stub" />' },
}))

const imageQuestion = {
  id: 'q1',
  text: 'Question with images?',
  is_required: true,
  is_multiple: false,
  max_choices: null,
  allow_custom_answer: false,
  sort_order: 0,
  options: [
    { id: 'o1', text: '', image_url: '/a.png', votes_count: 0, sort_order: 0 },
    { id: 'o2', text: '', image_url: '/b.png', votes_count: 0, sort_order: 1 },
    { id: 'o3', text: '', image_url: '/c.png', votes_count: 0, sort_order: 2 },
  ],
}

function baseProps(overrides: Record<string, unknown> = {}) {
  return {
    question: imageQuestion,
    questionIndex: 0,
    sortedOpts: imageQuestion.options,
    hasImages: true,
    selectedIds: [],
    customText: '',
    customChecked: false,
    hasVoted: false,
    submitting: false,
    isInteractive: true,
    canSeeResults: false,
    ...overrides,
  }
}

type QuestionProps = ReturnType<typeof baseProps>

async function mountQuestion(props: QuestionProps) {
  const Cmp = (await import('../../src/components/news/poll/PollQuestion.vue')).default
  return mount(Cmp, { props, global: { plugins: [i18n] } })
}

describe('usePollPreviewSize', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.resetModules()
  })

  it('defaults to medium when localStorage is empty', async () => {
    const { usePollPreviewSize } = await import('../../src/components/news/poll/composables/usePollPreviewSize')
    const { previewSize } = usePollPreviewSize()
    expect(previewSize.value).toBe('m')
  })

  it('reads a valid stored size and falls back on garbage', async () => {
    localStorage.setItem('news:poll-preview-size', 'l')
    const { usePollPreviewSize } = await import('../../src/components/news/poll/composables/usePollPreviewSize')
    expect(usePollPreviewSize().previewSize.value).toBe('l')

    vi.resetModules()
    localStorage.setItem('news:poll-preview-size', 'xl')
    const reloaded = await import('../../src/components/news/poll/composables/usePollPreviewSize')
    expect(reloaded.usePollPreviewSize().previewSize.value).toBe('m')
  })

  it('persists the chosen size and shares it across invocations', async () => {
    const { usePollPreviewSize } = await import('../../src/components/news/poll/composables/usePollPreviewSize')
    const first = usePollPreviewSize()
    const second = usePollPreviewSize()
    first.setPreviewSize('s')
    expect(second.previewSize.value).toBe('s')
    expect(localStorage.getItem('news:poll-preview-size')).toBe('s')
  })
})

describe('PollQuestion preview toolbar', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.resetModules()
  })

  it('shows hint and size switcher for image options, default medium grid', async () => {
    const w = await mountQuestion(baseProps())
    expect(w.find('.news-poll__image-hint').exists()).toBe(true)
    expect(w.find('.news-poll__image-hint').text()).toContain('news.poll.imageHint')
    expect(w.find('.news-poll__preview-size').exists()).toBe(true)
    expect(w.find('.news-poll__options').classes()).toContain('news-poll__options--preview-m')
  })

  it('hides toolbar for text-only options', async () => {
    const w = await mountQuestion(baseProps({ hasImages: false }))
    expect(w.find('.news-poll__options-toolbar').exists()).toBe(false)
    expect(w.find('.news-poll__options').classes()).not.toContain('news-poll__options--grid')
  })

  it('switches grid class and persists on size click', async () => {
    const w = await mountQuestion(baseProps())
    const buttons = w.findAll('.news-poll__preview-size .n-button')
    expect(buttons.map(b => b.text())).toEqual(['S', 'M', 'L'])
    expect(buttons[2].attributes('title')).toBe('news.poll.previewSizeLarge')

    await buttons[2].trigger('click')
    expect(w.find('.news-poll__options').classes()).toContain('news-poll__options--preview-l')
    expect(localStorage.getItem('news:poll-preview-size')).toBe('l')

    await buttons[0].trigger('click')
    expect(w.find('.news-poll__options').classes()).toContain('news-poll__options--preview-s')
    expect(localStorage.getItem('news:poll-preview-size')).toBe('s')
  })
})
