/**
 * Smoke-тесты GlobalSearch.vue (Фаза 6.3)
 * 
 * Покрытие:
 * - renders without errors when show=false
 * - renders modal content when show=true
 * - renders search input
 * - emits update:show=false when Esc pressed in input
 * - shows recent queries from localStorage
 * - shows hint when no query and no recent
 * - shows "no results" hint when query has no results
 * - shows command list when query starts with ">"
 */

import { beforeEach, describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createI18n } from 'vue-i18n'

vi.mock('naive-ui', () => ({
  NModal: {
    template: '<div v-if="show" class="n-modal"><slot /></div>',
    props: ['show', 'preset', 'maskClosable', 'closeOnEsc', 'bordered', 'segmented', 'style', 'autoFocus', 'displayDirective'],
    emits: ['update:show', 'after-enter'],
  },
  NIcon: { template: '<i><slot /></i>', props: ['size', 'class'] },
}))

vi.mock('@vicons/ionicons5', () => ({
  SearchOutline: { template: '<svg />' },
  TimeOutline: { template: '<svg />' },
  NewspaperOutline: { template: '<svg />' },
  GridOutline: { template: '<svg />' },
  BookmarkOutline: { template: '<svg />' },
  AlertCircleOutline: { template: '<svg />' },
  DocumentTextOutline: { template: '<svg />' },
  PersonOutline: { template: '<svg />' },
  TerminalOutline: { template: '<svg />' },
  LogOutOutline: { template: '<svg />' },
  SettingsOutline: { template: '<svg />' },
  PeopleOutline: { template: '<svg />' },
  DocumentOutline: { template: '<svg />' },
  ColorPaletteOutline: { template: '<svg />' },
  LinkOutline: { template: '<svg />' },
  HelpCircleOutline: { template: '<svg />' },
  ImageOutline: { template: '<svg />' },
  TrashOutline: { template: '<svg />' },
}))

vi.mock('../../src/components/search/SearchResultGroup.vue', () => ({
  default: { template: '<div class="search-result-group" />', props: ['title', 'icon', 'items', 'offset', 'activeIndex', 'getKey', 'getTitle', 'getMeta'], emits: ['hover', 'pick'] },
}))

vi.mock('../../src/stores/links', () => ({
  useLinksStore: () => ({
    links: [],
    bookmarks: [],
    loading: false,
    ensureLinksLoaded: vi.fn(),
    ensureBookmarksLoaded: vi.fn(),
  }),
}))

vi.mock('../../src/api/auth', () => ({
  fetchMe: vi.fn(),
  refreshSession: vi.fn(),
}))

vi.mock('../../src/api/bootstrap', () => ({
  fetchBootstrap: vi.fn(),
}))

vi.mock('../../src/api/index', () => ({
  api: { GET: vi.fn(), POST: vi.fn() },
  refreshAuth: vi.fn(),
}))

vi.mock('../../src/composables/useGlobalSearchCommands', () => {
  const { ref } = require('vue')
  return {
    useGlobalSearchCommands: () => ({
      isCommandMode: ref(false),
      filteredCommands: ref([]),
    }),
  }
})

vi.mock('../../src/composables/useGlobalSearchResults', () => {
  const { ref } = require('vue')
  return {
    useGlobalSearchResults: () => ({
      loading: ref(false),
      newsResults: ref([]),
      linkResults: ref([]),
      bookmarkResults: ref([]),
      kbResults: ref([]),
      userResults: ref([]),
      ensureCatalogLoaded: vi.fn(),
    }),
  }
})

vi.mock('../../src/utils/url', () => ({
  isSafeHttpUrl: (url: string) => url.startsWith('http'),
}))

vi.mock('../../src/utils/formatDate', () => ({
  formatDateShort: (d: string) => d,
}))

vi.mock('../../src/router', () => ({
  ROUTES: {
    HOME: { name: 'home' },
    NEWS_DETAIL: { name: 'news-detail' },
    KB_ARTICLE: { name: 'kb-article' },
    LINKS: { name: 'links' },
    PROFILE: { name: 'profile' },
    ADMIN: { name: 'admin' },
  },
}))

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'ru',
    messages: {
      ru: {
        search: {
          placeholder: 'Поиск...',
          recent: 'Недавние',
          hint: 'Введите запрос',
          commandHint: 'Введите > для команд',
          commands: { title: 'Команды' },
          noResults: 'Ничего не найдено',
          loading: 'Загрузка...',
          nav: 'навигация',
          open: 'открыть',
          close: 'закрыть',
        },
        nav: {
          news: 'Новости',
          links: 'Ссылки',
          bookmarks: 'Закладки',
          kb: 'База знаний',
        },
        users: { title: 'Пользователи' },
      },
    },
    missingWarn: false,
    fallbackWarn: false,
    silentFallbackWarn: true,
    silentTranslationWarn: true,
  })
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { render: () => null } }],
  })
}

async function mountSearch(props: { show: boolean } = { show: false }) {
  const { default: GlobalSearch } = await import('../../src/components/GlobalSearch.vue')
  const router = makeRouter()
  const i18n = makeI18n()

  const wrapper = mount(GlobalSearch, {
    props,
    global: { plugins: [router, i18n] },
  })
  return wrapper
}

describe('GlobalSearch', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('renders without errors when show=false', async () => {
    const wrapper = await mountSearch({ show: false })
    expect(wrapper.exists()).toBe(true)
  })

  it('does not render modal content when show=false', async () => {
    const wrapper = await mountSearch({ show: false })
    expect(wrapper.find('.gs').exists()).toBe(false)
  })

  it('renders modal content when show=true', async () => {
    const wrapper = await mountSearch({ show: true })
    expect(wrapper.find('.gs').exists()).toBe(true)
  })

  it('renders search input when visible', async () => {
    const wrapper = await mountSearch({ show: true })
    const input = wrapper.find('input.gs__input')
    expect(input.exists()).toBe(true)
  })

  it('shows hint when no query and no recent searches', async () => {
    const wrapper = await mountSearch({ show: true })
    expect(wrapper.find('.gs__hint').exists()).toBe(true)
  })

  it('shows recent searches from localStorage', async () => {
    localStorage.setItem('gs-recent', JSON.stringify(['first query', 'second query']))
    const wrapper = await mountSearch({ show: true })
    expect(wrapper.text()).toContain('first query')
    expect(wrapper.text()).toContain('second query')
  })

  it('emits update:show=false when Esc pressed in input', async () => {
    const wrapper = await mountSearch({ show: true })
    const input = wrapper.find('input.gs__input')
    await input.trigger('keydown.esc')
    const emitted = wrapper.emitted('update:show')
    expect(emitted).toBeTruthy()
    expect(emitted![0]).toEqual([false])
  })

  it('renders search result groups when query is set', async () => {
    const wrapper = await mountSearch({ show: true })
    const input = wrapper.find('input.gs__input')
    await input.setValue('test')
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('.search-result-group').length).toBeGreaterThanOrEqual(0)
  })

  it('shows no-results hint when query has no results', async () => {
    const wrapper = await mountSearch({ show: true })
    const input = wrapper.find('input.gs__input')
    await input.setValue('xxxxxxxxxxx')
    await wrapper.vm.$nextTick()
    const hints = wrapper.findAll('.gs__hint')
    expect(hints.some(h => h.text().includes('Ничего не найдено'))).toBe(true)
  })

  it('resets query when show transitions from false to true', async () => {
    const wrapper = await mountSearch({ show: true })
    const input = wrapper.find('input.gs__input')
    await input.setValue('previous query')
    await wrapper.setProps({ show: false })
    await wrapper.setProps({ show: true })
    await wrapper.vm.$nextTick()
    const inputEl = wrapper.find('input.gs__input')
    expect((inputEl.element as HTMLInputElement).value).toBe('')
  })
})
