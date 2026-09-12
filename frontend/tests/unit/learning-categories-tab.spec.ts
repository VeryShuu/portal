import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { defineComponent, nextTick, ref } from 'vue'
import ru from '../../src/i18n/ru.json'

/**
 * Спек вкладки «Категории» (справочник курсов, миграция 109):
 * список с количеством курсов, добавление/переименование/удаление/reorder.
 * naive-ui стабится точечно (см. precedent learning-learner.spec).
 */

const { categoriesData, mutateSpies, mockMessage } = vi.hoisted(() => ({
  categoriesData: { value: undefined as unknown[] | undefined },
  mutateSpies: {} as Record<string, ReturnType<typeof vi.fn>>,
  mockMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  messages: { ru },
  missingWarn: false,
  fallbackWarn: false,
  silentTranslationWarn: true,
})

vi.mock('naive-ui', () => {
  const NButton = defineComponent({
    emits: ['click'],
    template: '<button class="n-button" @click="$emit(\'click\')"><slot name="icon" /><slot /></button>',
  })
  const NIcon = defineComponent({ template: '<span class="n-icon"><slot /></span>' })
  const NInput = defineComponent({
    props: ['value', 'placeholder', 'maxlength'],
    emits: ['update:value'],
    template: `<input class="n-input" :value="value ?? ''" @input="$emit('update:value', $event.target.value)" />`,
  })
  const NTag = defineComponent({ props: ['type', 'size', 'bordered'], template: '<span class="n-tag"><slot /></span>' })
  const NEmpty = defineComponent({ props: ['description'], template: '<div class="n-empty">{{ description }}</div>' })
  const NPopconfirm = defineComponent({
    emits: ['positive-click'],
    template: '<div class="n-popconfirm" @click="$emit(\'positive-click\')"><slot name="trigger" /></div>',
  })
  const NModal = defineComponent({
    props: ['show', 'title', 'preset', 'style'],
    template: '<div v-if="show" class="n-modal"><h3>{{ title }}</h3><slot /><slot name="footer" /></div>',
  })
  return {
    NButton,
    NIcon,
    NInput,
    NTag,
    NEmpty,
    NPopconfirm,
    NModal,
    useMessage: () => mockMessage,
  }
})

function fakeMutation(name: string) {
  mutateSpies[name] ??= vi.fn().mockResolvedValue({ ok: true })
  return { mutateAsync: mutateSpies[name], isPending: ref(false), error: ref(null) }
}

vi.mock('../../src/queries/learning', () => ({
  useCategoriesQuery: () => ({
    data: categoriesData,
    error: ref(null),
    isLoading: ref(false),
  }),
  useCreateCategoryMutation: () => fakeMutation('createCategory'),
  useUpdateCategoryMutation: () => fakeMutation('updateCategory'),
  useDeleteCategoryMutation: () => fakeMutation('deleteCategory'),
  useReorderCategoriesMutation: () => fakeMutation('reorderCategories'),
}))

import CategoriesTab from '../../src/components/learning/CategoriesTab.vue'

const mountOpts = { global: { plugins: [i18n] } }

describe('CategoriesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    categoriesData.value = [
      { id: 'k1', title: 'Инструктажи', sort_order: 0, course_count: 3 },
      { id: 'k2', title: 'ГО и ЧС', sort_order: 1, course_count: 0 },
    ]
  })

  it('рисует категории с количеством курсов', async () => {
    const w = mount(CategoriesTab, mountOpts)
    await flushPromises()
    const rows = w.findAll('.cat-row')
    expect(rows.length).toBe(2)
    expect(w.text()).toContain('Инструктажи')
    expect(w.text()).toContain('ГО и ЧС')
    // счётчик: ru-множественная форма «3 курса»
    expect(rows[0].find('.cat-count').text()).toContain('3')
  })

  it('пустой справочник — empty state', async () => {
    categoriesData.value = []
    const w = mount(CategoriesTab, mountOpts)
    await flushPromises()
    expect(w.find('.n-empty').exists()).toBe(true)
  })

  it('добавление: пустое название отклоняется, валидное уходит в мутацию', async () => {
    const w = mount(CategoriesTab, mountOpts)
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('Добавить категорию'))!.trigger('click')
    await nextTick()
    const modal = w.find('.n-modal')
    await modal.findAll('button').find((b) => b.text().trim() === 'Создать')!.trigger('click')
    await flushPromises()
    expect(mutateSpies.createCategory).not.toHaveBeenCalled()
    expect(mockMessage.error).toHaveBeenCalledWith('Укажите название категории')

    await modal.find('input.n-input').setValue('  Электробезопасность  ')
    await modal.findAll('button').find((b) => b.text().trim() === 'Создать')!.trigger('click')
    await flushPromises()
    expect(mutateSpies.createCategory).toHaveBeenCalledWith({ title: 'Электробезопасность' })
    expect(mockMessage.success).toHaveBeenCalled()
  })

  it('переименование шлёт title по id категории', async () => {
    const w = mount(CategoriesTab, mountOpts)
    await flushPromises()
    const row = w.findAll('.cat-row')[0]
    await row.findAll('button').find((b) => b.text().trim() === 'Редактировать')!.trigger('click')
    await nextTick()
    const modal = w.find('.n-modal')
    await modal.find('input.n-input').setValue('Промышленная безопасность')
    await modal.findAll('button').find((b) => b.text().trim() === 'Сохранить')!.trigger('click')
    await flushPromises()
    expect(mutateSpies.updateCategory).toHaveBeenCalledWith({
      id: 'k1',
      body: { title: 'Промышленная безопасность' },
    })
  })

  it('reorder: кнопка вниз меняет порядок id', async () => {
    const w = mount(CategoriesTab, mountOpts)
    await flushPromises()
    await w.findAll('.cat-row')[0].findAll('.cat-order button')[1].trigger('click')
    await flushPromises()
    expect(mutateSpies.reorderCategories).toHaveBeenCalledWith({
      ordered_ids: ['k2', 'k1'],
    })
  })

  it('удаление по подтверждению', async () => {
    const w = mount(CategoriesTab, mountOpts)
    await flushPromises()
    const row = w.findAll('.cat-row')[0]
    await row.findAll('button').find((b) => b.text().trim() === 'Удалить')!.trigger('click')
    await flushPromises()
    expect(mutateSpies.deleteCategory).toHaveBeenCalledWith('k1')
    expect(mockMessage.success).toHaveBeenCalled()
  })
})
