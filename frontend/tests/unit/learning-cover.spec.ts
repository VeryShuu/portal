import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'
import { defineComponent, ref } from 'vue'
import ru from '../../src/i18n/ru.json'

/**
 * Характеризующий тест обложки курса (этап 2, ТЗ §6.2) в drawer редактора.
 *
 * Контракты:
 * - без обложки: кнопка «Загрузить обложку», файл ограничен image/*,
 *   выбор файла уходит в upload-мутацию, input сбрасывается
 * - с обложкой: превью (img по cover_url) + «Заменить» + «Убрать»
 * - подтверждение «Убрать» вызывает delete-мутацию
 * - ошибка мутации показывается через message.error
 */

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  messages: { ru },
  missingWarn: false,
  fallbackWarn: false,
  silentFallbackWarn: true,
  silentTranslationWarn: true,
})

const mockMessage = { success: vi.fn(), error: vi.fn(), warning: vi.fn() }

vi.mock('naive-ui', () => {
  const NButton = defineComponent({
    emits: ['click'],
    template: '<button class="n-button" @click="$emit(\'click\')"><slot /></button>',
  })
  const NDrawer = defineComponent({ template: '<div class="n-drawer"><slot /></div>' })
  const NDrawerContent = defineComponent({
    props: ['title', 'closable'],
    template: '<div class="n-drawer-content"><slot /></div>',
  })
  const NModal = defineComponent({
    props: ['show'],
    template: '<div v-if="show" class="n-modal"><slot /></div>',
  })
  const NPopconfirm = defineComponent({
    emits: ['positive-click'],
    // клик по триггеру сразу подтверждает — проверяем сам вызов мутации
    template: `<span class="n-popconfirm" @click="$emit('positive-click')"><slot name="trigger" /><slot /></span>`,
  })
  const NSpin = defineComponent({
    props: ['show'],
    template: '<div class="n-spin"><slot /></div>',
  })
  const NTabs = defineComponent({ template: '<div class="n-tabs"><slot /></div>' })
  const NTabPane = defineComponent({
    props: ['name', 'tab'],
    template: '<div class="n-tab-pane"><slot /></div>',
  })
  const NTag = defineComponent({ template: '<span class="n-tag"><slot /></span>' })
  const NForm = defineComponent({ template: '<form class="n-form"><slot /></form>' })
  const NFormItem = defineComponent({
    props: ['label'],
    template: '<label class="n-form-item"><slot /></label>',
  })
  const NInput = defineComponent({
    props: ['value', 'maxlength', 'type', 'rows'],
    emits: ['update:value'],
    template: `<textarea v-if="type === 'textarea'" class="n-input" :value="value ?? ''" @input="$emit('update:value', $event.target.value)" />
      <input v-else class="n-input" :value="value ?? ''" @input="$emit('update:value', $event.target.value)" />`,
  })
  return {
    NButton,
    NDrawer,
    NDrawerContent,
    NModal,
    NPopconfirm,
    NSpin,
    NTabs,
    NTabPane,
    NTag,
    NForm,
    NFormItem,
    NInput,
    useMessage: () => mockMessage,
  }
})

const course = ref<Record<string, unknown> | null>(null)
const uploadError = ref<unknown>(null)
const deleteError = ref<unknown>(null)
let uploadShouldFail = false
let deleteShouldFail = false
const uploadMock = vi.fn(async (_v: { courseId: string; file: File }) => {
  // честная имитация useMutation: ошибка кладётся в error-ref и бросается
  if (uploadShouldFail) {
    const err = new Error('422')
    uploadError.value = err
    throw err
  }
  return {}
})
const deleteMock = vi.fn(async (_v: { courseId: string }) => {
  if (deleteShouldFail) {
    const err = new Error('500')
    deleteError.value = err
    throw err
  }
  return {}
})

vi.mock('../../src/queries/learning', () => ({
  useAdminCourseQuery: () => ({ data: course, isLoading: ref(false), error: ref(null), isError: ref(false), isFetching: ref(false), refetch: vi.fn().mockResolvedValue(undefined) }),
  useCategoriesQuery: () => ({ data: ref([]), error: ref(null), isLoading: ref(false) }),
  useUpdateCourseMutation: () => ({ isPending: ref(false), error: ref(null), mutateAsync: vi.fn() }),
  useSetCoursePublishedMutation: () => ({
    isPending: ref(false),
    error: ref(null),
    mutateAsync: vi.fn(),
  }),
  useUploadCoverMutation: () => ({
    isPending: ref(false),
    error: uploadError,
    mutateAsync: uploadMock,
  }),
  useDeleteCoverMutation: () => ({
    isPending: ref(false),
    error: deleteError,
    mutateAsync: deleteMock,
  }),
}))

// CourseItemsPanel/ParticipantsPanel в этом спеке не интересны
vi.mock('../../src/components/learning/CourseItemsPanel.vue', () => ({
  default: defineComponent({ template: '<div class="items-stub" />' }),
}))
vi.mock('../../src/components/learning/ParticipantsPanel.vue', () => ({
  default: defineComponent({ template: '<div class="participants-stub" />' }),
}))
// rich-редактор (TipTap) здесь не тестируется — стаб вместо реального
vi.mock('../../src/components/RichEditor.vue', () => ({
  default: defineComponent({
    props: ['modelValue', 'placeholder'],
    emits: ['update:modelValue'],
    template: '<div class="rich-editor-stub" />',
  }),
}))

import CourseEditorDrawer from '../../src/components/learning/CourseEditorDrawer.vue'

function mountDrawer() {
  return mount(CourseEditorDrawer, {
    props: { show: true, courseId: 'c1' },
    global: { plugins: [i18n, setActivePinia(createPinia())] },
  })
}

function pickFile(wrapper: ReturnType<typeof mountDrawer>, file: File) {
  const input = wrapper.find('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  return input.trigger('change')
}

describe('CourseEditorDrawer — обложка курса', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    uploadShouldFail = false
    deleteShouldFail = false
    uploadError.value = null
    deleteError.value = null
    course.value = {
      id: 'c1',
      slug: 'kurs-1',
      title: 'Курс',
      description: null,
      status: 'draft',
      cover_url: null,
    }
  })

  it('без обложки предлагает загрузку и валидный accept', () => {
    const w = mountDrawer()
    expect(w.text()).toContain('Загрузить обложку')
    const input = w.find('input[type="file"]')
    expect(input.attributes('accept')).toBe('image/jpeg,image/png,image/webp,image/gif')
  })

  it('выбор файла уходит в upload-мутацию, input сбрасывается', async () => {
    const w = mountDrawer()
    const file = new File(['x'], 'cover.png', { type: 'image/png' })
    await pickFile(w, file)
    await flushPromises()
    expect(uploadMock).toHaveBeenCalledTimes(1)
    expect(uploadMock).toHaveBeenCalledWith({ courseId: 'c1', file })
    expect(mockMessage.success).toHaveBeenCalled()
    const input = w.find('input[type="file"]')
    expect((input.element as HTMLInputElement).value).toBe('')
  })

  it('с обложкой: превью, «Заменить», «Убрать» с подтверждением', async () => {
    course.value = { ...course.value, cover_url: '/api/v1/learning/admin/courses/c1/cover?v=1' }
    const w = mountDrawer()
    await flushPromises()
    expect(w.text()).toContain('Заменить обложку')
    const img = w.find('img.cover-preview')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toBe('/api/v1/learning/admin/courses/c1/cover?v=1')
    expect(w.text()).toContain('Убрать')

    // popconfirm-стаб эмитит positive-click на клик по триггеру
    const removeBtn = w.findAll('button.n-button').find((b) => b.text() === 'Убрать')
    expect(removeBtn).toBeTruthy()
    await removeBtn!.trigger('click')
    await flushPromises()
    expect(deleteMock).toHaveBeenCalledWith({ courseId: 'c1' })
  })

  it('ошибка загрузки показывается через message.error', async () => {
    uploadShouldFail = true
    const w = mountDrawer()
    await pickFile(w, new File(['x'], 'cover.png', { type: 'image/png' }))
    await flushPromises()
    expect(mockMessage.error).toHaveBeenCalled()
  })

  it('ошибка удаления показывается через message.error', async () => {
    deleteShouldFail = true
    course.value = { ...course.value, cover_url: '/api/v1/learning/admin/courses/c1/cover?v=1' }
    const w = mountDrawer()
    await flushPromises()
    const removeBtn = w.findAll('button.n-button').find((b) => b.text() === 'Убрать')!
    await removeBtn.trigger('click')
    await flushPromises()
    expect(mockMessage.error).toHaveBeenCalled()
  })
})
