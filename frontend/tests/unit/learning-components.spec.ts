import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { setActivePinia, createPinia } from 'pinia'
import { computed, h, defineComponent, nextTick, ref, type Plugin } from 'vue'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import ru from '../../src/i18n/ru.json'

const { mockDownloadTemplate, mockExportBlob, mockFetchAccounts, mockCertBlob, progressData, detailItemsData, drawerError, drawerRefetch } = vi.hoisted(() => ({
  mockDownloadTemplate: vi.fn(),
  mockExportBlob: vi.fn(),
  mockFetchAccounts: vi.fn(),
  mockCertBlob: vi.fn(),
  // переключаемые данные для панели участников/детализации (ref-подобные)
  progressData: {
    value: {
      course_id: 'c1',
      total_items: 2,
      participants: [
        { id: 'p1', participant_kind: 'staff', display_name: 'Сотрудник Один', email: 's@x', enrolled_at: '2026-01-01T00:00:00Z', progress_completed: 1, progress_total: 2, has_certificate: false },
      ],
    },
  },
  detailItemsData: {
    value: {
      participant_id: 'p1',
      items: [] as Array<Record<string, unknown>>,
    },
  },
  drawerError: { test: { value: false }, editor: { value: false } },
  drawerRefetch: { test: vi.fn(), editor: vi.fn() },
}))

vi.mock('../../src/api/learning', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../src/api/learning')>()),
  downloadLearningAccountsTemplate: mockDownloadTemplate,
  exportProgressBlob: mockExportBlob,
  fetchLearningAccounts: mockFetchAccounts,
  fetchParticipantCertificateBlob: mockCertBlob,
}))

/**
 * Характеризующие тесты UI методиста (learning).
 *
 * naive-ui стабится целиком (прецедент home-page.spec / files-table-smoke):
 * клики — обычные DOM-события по стаб-кнопкам, update:value — по инпутам.
 *
 * Контракты:
 * - CoursesTab: рендер списка, создание (тело + валидация), publish-toggle
 * - CourseItemsPanel: reorder меняет порядок идентификаторов, валидация названия
 * - TestDrawer: настройки теста уходят мутацией, удаление вопроса
 * - QuestionFormModal: валидации, нормализация тела вопроса
 * - ParticipantsPanel: зачисление требует выбора участника
 * - AccountsTab: валидация создания, сброс пароля по строке
 * - MyCoursesWidget: скелет при загрузке
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

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
    useRoute: () => ({ query: {} as Record<string, string> }),
  }
})

vi.mock('naive-ui', () => {
  const NButton = defineComponent({
    props: ['disabled'],
    emits: ['click'],
    template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot name="icon" /><slot /></button>',
  })
  const NIcon = defineComponent({ template: '<span class="n-icon"><slot /></span>' })
  const NInput = defineComponent({
    props: ['value', 'placeholder', 'maxlength', 'type', 'rows', 'clearable', 'size'],
    emits: ['update:value'],
    template: `<textarea v-if="type === 'textarea'" class="n-input" :value="value ?? ''" :placeholder="placeholder" @input="$emit('update:value', $event.target.value)" />
      <input v-else class="n-input" :value="value ?? ''" :placeholder="placeholder" @input="$emit('update:value', $event.target.value)" />`,
  })
  const NInputNumber = defineComponent({
    props: ['value', 'min', 'max', 'size'],
    emits: ['update:value'],
    template: `<input type="number" class="n-input-number" :value="value ?? 0" @input="$emit('update:value', Number($event.target.value))" />`,
  })
  const NDatePicker = defineComponent({
    props: ['value', 'type', 'clearable'],
    emits: ['update:value'],
    template: `<input type="datetime-local" class="n-date-picker" :value="value ?? ''" @change="$emit('update:value', $event.target.value ? Date.parse($event.target.value) : null)" />`,
  })
  const NSelect = defineComponent({
    props: ['value', 'options', 'filterable', 'clearable', 'remote', 'loading', 'placeholder', 'size', 'multiple'],
    emits: ['update:value', 'search'],
    template: `<select class="n-select" :multiple="!!multiple || multiple === ''" @change="$emit('update:value', (multiple === '' || multiple === true) ? Array.from($event.target.selectedOptions, (o) => o.value) : $event.target.value); $emit('search', $event.target.value)"><option v-for="o in options || []" :key="o.value" :value="o.value">{{ o.label }}</option></select>`,
  })
  const NSwitch = defineComponent({
    props: ['value'],
    emits: ['update:value'],
    template: `<input type="checkbox" class="n-switch" :checked="value" @change="$emit('update:value', $event.target.checked)" />`,
  })
  const NCheckbox = defineComponent({
    props: ['checked', 'title'],
    emits: ['update:checked'],
    template: `<label class="n-checkbox"><input type="checkbox" :checked="checked" @change="$emit('update:checked', $event.target.checked)" /><slot /></label>`,
  })
  const NDataTable = defineComponent({
    props: ['data', 'columns', 'rowKey', 'loading', 'bordered', 'striped'],
    setup(props: any) {
      return () =>
        h(
          'div',
          { class: 'n-data-table' },
          (props.data ?? []).map((row: any, ri: number) =>
            h(
              'div',
              { class: 'table-row', key: ri },
              (props.columns ?? []).map((col: any, ci: number) => {
                if (col.type === 'expand' && typeof col.renderExpand === 'function') {
                  // раскрываемая строка панели участников: рендерим контент сразу
                  return h('div', { key: ci, class: 'expand-cell' }, [col.renderExpand(row, ri)])
                }
                if (typeof col.render === 'function') {
                  return h('div', { key: ci }, [col.render(row, ri)])
                }
                return h('span', { key: ci }, String(row[col.key] ?? ''))
              }),
            ),
          ),
        )
    },
  })
  const NPagination = defineComponent({
    props: ['page', 'pageSize', 'itemCount'],
    template: '<div class="n-pagination" />',
  })
  return {
    NButton,
    NIcon,
    NInput,
    NInputNumber,
    NDatePicker,
    NSelect,
    NSwitch,
    NCheckbox,
    NDataTable,
    NPagination,
    NModal: defineComponent({
      props: ['show', 'title', 'preset', 'style'],
      template: `<div v-if="show" class="n-modal"><h3>{{ title }}</h3><slot /><slot name="footer" /></div>`,
    }),
    NDrawer: defineComponent({
      props: ['show', 'width', 'placement'],
      template: `<div v-if="show" class="n-drawer"><slot /></div>`,
    }),
    NDrawerContent: defineComponent({
      props: ['title', 'closable'],
      template: `<div class="n-drawer-content"><slot /></div>`,
    }),
    NTabs: defineComponent({ props: ['value', 'type'], template: '<div class="n-tabs"><slot /></div>' }),
    NTab: defineComponent({ props: ['name'], template: '<div class="n-tab"><slot /></div>' }),
    NTabPane: defineComponent({ props: ['name', 'tab'], template: `<div class="n-tab-pane" :data-name="name"><slot /></div>` }),
    NForm: defineComponent({ template: '<form class="n-form"><slot /></form>' }),
    NFormItem: defineComponent({ props: ['label'], template: `<label class="n-form-item">{{ label }}<slot /></label>` }),
    NTag: defineComponent({ props: ['type', 'size', 'bordered'], template: '<span class="n-tag"><slot /></span>' }),
    NPopconfirm: defineComponent({
      emits: ['positiveClick'],
      template:
        '<span class="n-popconfirm" @click="$emit(\'positiveClick\')"><slot name="trigger" /><slot name="default" /></span>',
    }),
    NAlert: defineComponent({ props: ['type', 'showIcon', 'title'], template: '<div class="n-alert">{{ title }}<slot /></div>' }),
    NEmpty: defineComponent({ props: ['description', 'size'], template: '<div class="n-empty">{{ description }}</div>' }),
    NSpin: defineComponent({ props: ['show'], template: '<div class="n-spin"><slot /></div>' }),
    NText: defineComponent({ template: '<span class="n-text"><slot /></span>' }),
    NDivider: defineComponent({ template: '<hr class="n-divider" />' }),
    NRadio: defineComponent({
      props: ['value', 'checked', 'name', 'title'],
      emits: ['update:checked'],
      template: `<label class="n-radio"><input v-if="checked !== undefined" type="radio" :name="name" :checked="checked" @change="$emit('update:checked', true)" /><slot /></label>`,
    }),
    NRadioGroup: defineComponent({ props: ['value'], template: '<div class="n-radio-group"><slot /></div>' }),
    NProgress: defineComponent({ props: ['type', 'percentage', 'showIndicator', 'height'], template: '<div class="n-progress" />' }),
    useMessage: () => mockMessage,
  }
})

// ── Моки queries/learning: общий шпион на имя действия ──────────────────────
// Несколько смонтированных компонентов (страница + drawer) заводят одну и ту же
// мутацию — записи в карте не должны перетирать друг друга.
const mutateSpies: Record<string, ReturnType<typeof vi.fn>> = {}
const pendingFlags: Record<string, ReturnType<typeof ref<boolean>>> = {}
const errorFlags: Record<string, ReturnType<typeof ref<unknown>>> = {}
function fakeQuery<T>(data: T) {
  // isError/isFetching — ревью 2026-08-30: drawers показывают error-state
  return { data: ref(data), error: ref(null), isLoading: ref(false), isError: ref(false), isFetching: ref(false), refetch: vi.fn().mockResolvedValue(undefined) }
}
function fakeMutation(name: string) {
  mutateSpies[name] ??= vi.fn().mockResolvedValue({ ok: true })
  pendingFlags[name] ??= ref(false)
  errorFlags[name] ??= ref(null)
  return { mutateAsync: mutateSpies[name], isPending: pendingFlags[name], error: errorFlags[name] }
}
const mutateSpy = (name: string) => mutateSpies[name]

vi.mock('../../src/queries/learning', () => ({
  useAdminCoursesQuery: () =>
    fakeQuery({
      items: [
        { id: 'c1', slug: 'ohrana', title: 'Охрана труда', status: 'draft', description: null, published_at: null, created_at: '2026-01-01T00:00:00Z', for_all_staff: true },
        { id: 'c9', slug: 'misc', title: 'Прочее', status: 'draft', description: null, published_at: null, created_at: '2026-01-01T00:00:00Z', for_all_staff: false },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    }),
  useCreateCourseMutation: () => fakeMutation('createCourse'),
  useUpdateCourseMutation: () => fakeMutation('updateCourse'),
  useSetCoursePublishedMutation: () => fakeMutation('publish'),
  useDeleteCourseMutation: () => fakeMutation('deleteCourse'),
  useUploadCoverMutation: () => fakeMutation('uploadCover'),
  useDeleteCoverMutation: () => fakeMutation('deleteCover'),
  useAdminCourseQuery: () => ({
    ...fakeQuery({
      id: 'c1', slug: 'ohrana', title: 'Охрана труда', status: 'draft', description: 'Desc', published_at: null, created_at: '2026-01-01T00:00:00Z',
      items: [{ id: 'i1', course_id: 'c1', type: 'test', title: 'Тест вводный', sort_order: 0, url: null, file_path: null }],
    }),
    isError: drawerError.editor,
    refetch: drawerRefetch.editor,
  }),
  useAddItemMutation: () => fakeMutation('addItem'),
  useUpdateItemMutation: () => fakeMutation('updateItem'),
  useDeleteItemMutation: () => fakeMutation('deleteItem'),
  useReorderItemsMutation: () => fakeMutation('reorder'),
  useUploadMaterialMutation: () => fakeMutation('upload'),
  useAdminTestQuery: () => ({
    ...fakeQuery({
      pass_score: 70, max_attempts: 3, time_limit_minutes: 30, shuffle_questions: false, shuffle_answers: false,
      questions: [{ id: 'q1', text: 'Вопрос 1', multi: false, sort_order: 0, options: [{ id: 'o1', text: 'Верный', is_correct: true, sort_order: 0 }] }],
    }),
    isError: drawerError.test,
    refetch: drawerRefetch.test,
  }),
  useUpdateTestSettingsMutation: () => fakeMutation('testSettings'),
  useAddQuestionMutation: () => fakeMutation('addQuestion'),
  useUpdateQuestionMutation: () => fakeMutation('updateQuestion'),
  useDeleteQuestionMutation: () => fakeMutation('deleteQuestion'),
  usePreviewQuestionsImportMutation: () => fakeMutation('previewImport'),
  useImportQuestionsMutation: () => fakeMutation('importQuestions'),
  useAdminProgressQuery: () => fakeQuery(progressData.value),
  useBulkEnrollMutation: () => fakeMutation('bulkEnroll'),
  useCategoriesQuery: () => fakeQuery([]),
  useCreateCategoryMutation: () => fakeMutation('createCategory'),
  useUpdateCategoryMutation: () => fakeMutation('updateCategory'),
  useDeleteCategoryMutation: () => fakeMutation('deleteCategory'),
  useReorderCategoriesMutation: () => fakeMutation('reorderCategories'),
  useEnrollParticipantMutation: () => fakeMutation('enroll'),
  useUnenrollParticipantMutation: () => fakeMutation('unenroll'),
  useParticipantItemsQuery: () => fakeQuery(detailItemsData.value),
  useResetParticipantAttemptsMutation: () => fakeMutation('resetAttempts'),
  useAdminAccountsQuery: () =>
    fakeQuery({
      items: [
        { id: 'a1', email: 'ext@x', full_name: 'Внешний Один', department: null, position: null, status: 'active', last_login_at: null, created_at: '2026-01-01T00:00:00Z' },
      ],
      total: 1, limit: 20, offset: 0,
    }),
  useCreateAccountMutation: () => fakeMutation('createAccount'),
  useImportAccountsMutation: () => fakeMutation('importAccounts'),
  useIssueAccountLoginCodeMutation: () => fakeMutation('issueLoginCode'),
  useBlockAccountMutation: () => fakeMutation('blockAccount'),
  useMyCoursesQuery: () => fakeQuery([]),
  useLearningAdminsQuery: () =>
    fakeQuery([
      { user_id: 'u1', full_name: 'Методист Один', email: 'm1@x', added_at: '2026-08-01T00:00:00Z' },
    ]),
  useAssignMethodistMutation: () => fakeMutation('assignMethodist'),
  useRevokeMethodistMutation: () => fakeMutation('revokeMethodist'),
  useVideoOriginsQuery: () => ({
    query: fakeQuery({ video_iframe_origins: ['https://rutube.ru'] }),
    origins: computed(() => ['https://rutube.ru']),
  }),
}))

vi.mock('../../src/api/users', () => ({
  fetchUsers: vi.fn().mockResolvedValue({
    items: [{ id: 'u9', full_name: 'Иванов Иван', email: 'ivanov@x' }],
    total: 1, limit: 20, offset: 0,
  }),
}))

// rich-редактор (TipTap) в этом спеке не тестируется — стаб вместо реального.
// Контракт: значение отображается, ввод эмитит текст, клик — фиксированный
// 'rich-описание' (используется старыми тестами создания курса).
vi.mock('../../src/components/RichEditor.vue', () => ({
  default: defineComponent({
    props: ['modelValue', 'placeholder'],
    emits: ['update:modelValue'],
    setup(props, { emit }) {
      return () =>
        h('input', {
          class: 'rich-editor-stub',
          value: props.modelValue ?? '',
          placeholder: props.placeholder,
          onInput: (e: Event) => emit('update:modelValue', (e.target as HTMLInputElement).value),
          onClick: () => emit('update:modelValue', 'rich-описание'),
        })
    },
  }),
}))

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const globalPlugins: Plugin[] = [
  i18n as unknown as Plugin,
  [VueQueryPlugin, { queryClient }] as unknown as Plugin,
]
const mountOpts = { global: { plugins: globalPlugins } }

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  mockDownloadTemplate.mockResolvedValue(new Blob(['template']))
  mockFetchAccounts.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })
  progressData.value = {
    course_id: 'c1',
    total_items: 2,
    participants: [
      { id: 'p1', participant_kind: 'staff', display_name: 'Сотрудник Один', email: 's@x', enrolled_at: '2026-01-01T00:00:00Z', progress_completed: 1, progress_total: 2, has_certificate: false },
    ],
  }
  detailItemsData.value = { participant_id: 'p1', items: [] }
})

describe('CoursesTab', () => {
  it('renders course row and create-mutation sends trimmed body', async () => {
    const { default: CoursesTab } = await import('../../src/components/learning/CoursesTab.vue')
    const w = mount(CoursesTab, mountOpts)
    await flushPromises()
    // тег «Всем» у обязательного курса + клик по ссылке (openEditor)
    expect(w.text()).toContain('Всем')
    await w.find('a.course-link').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Охрана труда')

    await w.findAll('button').find((b) => b.text().includes('Создать курс'))!.trigger('click')
    await nextTick()
    await w.findAll('.n-modal input')[0]!.setValue('  Новый курс  ')
    // rich-описание: стаб эмитит update:modelValue
    await w.find('.n-modal .rich-editor-stub').trigger('click')
    await w.findAll('.n-modal button').find((b) => b.text().trim() === 'Создать')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('createCourse')).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Новый курс', description: 'rich-описание' }),
    )
  })

  it('create: чекбокс «для всех сотрудников» уходит в мутацию (for_all_staff)', async () => {
    const { default: CoursesTab } = await import('../../src/components/learning/CoursesTab.vue')
    const w = mount(CoursesTab, mountOpts)
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('Создать курс'))!.trigger('click')
    await nextTick()
    const modal = w.find('.n-modal')
    await modal.find('input.n-input').setValue('Курс для всех')
    await modal.find('.n-checkbox input').setValue(true)
    expect(w.text()).toContain('включая новых')
    await modal.findAll('button').find((b) => b.text().trim() === 'Создать')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('createCourse')).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Курс для всех', for_all_staff: true }),
    )
  })

  it('blocks course creation without title', async () => {
    const { default: CoursesTab } = await import('../../src/components/learning/CoursesTab.vue')
    const w = mount(CoursesTab, mountOpts)
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('Создать курс'))!.trigger('click')
    await nextTick()
    await w.findAll('.n-modal button').find((b) => b.text().trim() === 'Создать')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('createCourse')).not.toHaveBeenCalled()
    expect(mockMessage.error).toHaveBeenCalledWith('Укажите название курса')
  })

  it('publish toggle sends published flag by current status', async () => {
    const { default: CoursesTab } = await import('../../src/components/learning/CoursesTab.vue')
    const w = mount(CoursesTab, mountOpts)
    await flushPromises()
    await w.findAll('.table-row button').find((b) => b.text().includes('Опубликовать'))!.trigger('click')
    await flushPromises()
    expect(mutateSpy('publish')).toHaveBeenCalledWith({ courseId: 'c1', published: true })
  })
})

describe('CourseItemsPanel', () => {
  const items = [
    { id: 'i1', course_id: 'c1', type: 'test', title: 'Тест', sort_order: 0, url: null, file_path: null },
    { id: 'i2', course_id: 'c1', type: 'material', title: 'Материал', sort_order: 1, url: 'https://e.e', file_path: null },
  ]

  it('reorder swaps neighbour ids', async () => {
    const { default: Panel } = await import('../../src/components/learning/CourseItemsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1', items }, ...mountOpts })
    await flushPromises()
    await w.findAll('.item-row')[0].findAll('.item-order button')[1].trigger('click')
    await flushPromises()
    expect(mutateSpy('reorder')).toHaveBeenCalledWith({ courseId: 'c1', orderedIds: ['i2', 'i1'] })
  })

  it('add-item requires title', async () => {
    const { default: Panel } = await import('../../src/components/learning/CourseItemsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1', items }, ...mountOpts })
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('Добавить элемент'))!.trigger('click')
    await nextTick()
    await w.findAll('.n-modal button').find((b) => b.text().trim() === 'Создать')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('addItem')).not.toHaveBeenCalled()
    expect(mockMessage.error).toHaveBeenCalledWith('Укажите название элемента')
  })

  it('формат-чипы: Видео / Ссылка / PDF у материалов, тесты — без чипа; сырых ссылок нет', async () => {
    const { default: Panel } = await import('../../src/components/learning/CourseItemsPanel.vue')
    const videoItems = [
      ...items,
      { id: 'i3', course_id: 'c1', type: 'material', title: 'Вебинар', sort_order: 2, url: 'https://rutube.ru/video/abc123def0/', file_path: null },
      { id: 'i4', course_id: 'c1', type: 'material', title: 'Методичка', sort_order: 3, url: null, file_path: '/data/m.pdf' },
    ]
    const w = mount(Panel, { props: { courseId: 'c1', items: videoItems }, ...mountOpts })
    await flushPromises()
    const rows = w.findAll('.item-row')
    const chipOf = (title: string) =>
      rows.find((r) => r.text().includes(title))?.find('.item-format')?.text().trim()
    // rutube-материал — Видео; обычная ссылка — Ссылка; файл — PDF; тест — без чипа
    expect(chipOf('Вебинар')).toBe('Видео')
    expect(chipOf('Материал')).toBe('Ссылка')
    expect(chipOf('Методичка')).toBe('PDF')
    expect(rows.find((r) => r.text().includes('Тест'))?.find('.item-format').exists()).toBe(false)
    // сырые URL в строках больше не показываются
    expect(w.text()).not.toContain('https://rutube.ru')
    expect(w.text()).not.toContain('https://e.e')
  })

  it('описание материала: edit-модалка префиллит и шлёт description', async () => {
    const { default: Panel } = await import('../../src/components/learning/CourseItemsPanel.vue')
    const descItems = [
      ...items,
      {
        id: 'i5', course_id: 'c1', type: 'material', title: 'С описанием', sort_order: 4,
        url: 'https://e.e', file_path: null, description: '<p>Комментарий</p>',
      },
    ]
    const w = mount(Panel, { props: { courseId: 'c1', items: descItems }, ...mountOpts })
    await flushPromises()
    const row = w.findAll('.item-row').find((r) => r.text().includes('С описанием'))!
    await row.findAll('button').find((b) => b.text().trim() === 'Редактировать')!.trigger('click')
    await nextTick()
    const modal = w.find('.n-modal')
    const stub = modal.find('input.rich-editor-stub')
    expect(stub.exists()).toBe(true)
    expect((stub.element as HTMLTextAreaElement).value).toBe('<p>Комментарий</p>')
    await stub.setValue('Новый **текст**')
    await modal.findAll('button').find((b) => b.text().trim() === 'Сохранить')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('updateItem')).toHaveBeenCalledWith({
      courseId: 'c1',
      itemId: 'i5',
      body: { title: 'С описанием', url: 'https://e.e', description: 'Новый **текст**' },
    })
  })

  it('add-модалка материала отправляет description вместе с телом', async () => {
    const { default: Panel } = await import('../../src/components/learning/CourseItemsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1', items }, ...mountOpts })
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('Добавить элемент'))!.trigger('click')
    await nextTick()
    const modal = w.find('.n-modal')
    await modal.find('input.n-input').setValue('Новый материал')
    await modal.find('input.rich-editor-stub').setValue('Комментарий к материалу')
    await modal.findAll('button').find((b) => b.text().trim() === 'Создать')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('addItem')).toHaveBeenCalledWith({
      courseId: 'c1',
      body: {
        type: 'material',
        title: 'Новый материал',
        url: null,
        description: 'Комментарий к материалу',
      },
    })
  })

  it('тест: edit-модалка не шлёт url и description (чужие поля → 422)', async () => {
    const { default: Panel } = await import('../../src/components/learning/CourseItemsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1', items }, ...mountOpts })
    await flushPromises()
    const row = w.findAll('.item-row')[0]
    await row.findAll('button').find((b) => b.text().trim() === 'Редактировать')!.trigger('click')
    await nextTick()
    const modal = w.find('.n-modal')
    expect(modal.find('.rich-editor-stub').exists()).toBe(false)
    await modal.find('input.n-input').setValue('Новое имя теста')
    await modal.findAll('button').find((b) => b.text().trim() === 'Сохранить')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('updateItem')).toHaveBeenCalledWith({
      courseId: 'c1',
      itemId: 'i1',
      body: { title: 'Новое имя теста' },
    })
  })
})

describe('QuestionFormModal', () => {
  it('validates empty question text and blank options', async () => {
    const { default: Modal } = await import('../../src/components/learning/QuestionFormModal.vue')
    const w = mount(Modal, { props: { show: true, itemId: 'i1', question: null }, ...mountOpts })
    await flushPromises()
    const save = w.findAll('button').find((b) => b.text().trim() === 'Сохранить')!
    await save.trigger('click')
    await flushPromises()
    expect(mockMessage.error).toHaveBeenCalledWith('Введите текст вопроса')

    await w.find('textarea').setValue('Вопрос?')
    await save.trigger('click')
    await flushPromises()
    expect(mockMessage.error).toHaveBeenCalledWith('Заполните все варианты')
    expect(mutateSpy('addQuestion')).not.toHaveBeenCalled()
  })

  it('submits normalized options for new question', async () => {
    const { default: Modal } = await import('../../src/components/learning/QuestionFormModal.vue')
    const w = mount(Modal, { props: { show: true, itemId: 'i1', question: null }, ...mountOpts })
    await flushPromises()
    await w.find('textarea').setValue('  Вопрос?  ')
    const inputs = w.findAll('.option-row .n-input')
    await inputs[0].setValue('да')
    await inputs[1].setValue('нет')
    await w.findAll('button').find((b) => b.text().trim() === 'Сохранить')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('addQuestion')).toHaveBeenCalledWith({
      itemId: 'i1',
      body: {
        text: 'Вопрос?',
        multi: false,
        options: [
          { text: 'да', is_correct: true },
          { text: 'нет', is_correct: false },
        ],
      },
    })
  })

  it('single-режим: радио вместо чекбоксов, выбор переносит верный ответ', async () => {
    const { default: Modal } = await import('../../src/components/learning/QuestionFormModal.vue')
    const w = mount(Modal, { props: { show: true, itemId: 'i1', question: null }, ...mountOpts })
    await flushPromises()
    // по умолчанию multi=false: в строках вариантов радио, чекбоксов нет
    expect(w.find('.option-row .n-radio').exists()).toBe(true)
    expect(w.find('.option-row .n-checkbox').exists()).toBe(false)

    await w.find('textarea').setValue('Вопрос?')
    const inputs = w.findAll('.option-row .n-input')
    await inputs[0].setValue('а')
    await inputs[1].setValue('б')
    // выбор второго варианта переносит «правильность» с первого
    await w.findAll('.option-row .n-radio input')[1].setValue(true)
    await w.findAll('button').find((b) => b.text().trim() === 'Сохранить')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('addQuestion')).toHaveBeenCalledWith({
      itemId: 'i1',
      body: {
        text: 'Вопрос?',
        multi: false,
        options: [
          { text: 'а', is_correct: false },
          { text: 'б', is_correct: true },
        ],
      },
    })
  })

  it('переключение multi→single оставляет первую отмеченную галочку', async () => {
    const { default: Modal } = await import('../../src/components/learning/QuestionFormModal.vue')
    const w = mount(Modal, { props: { show: true, itemId: 'i1', question: null }, ...mountOpts })
    await flushPromises()
    // включаем «несколько», отмечаем два варианта
    await w.find('.n-switch').setValue(true)
    const checks = w.findAll('.option-row .n-checkbox input')
    await checks[1].setValue(true)
    expect(w.findAll('.option-row .n-checkbox').length).toBeGreaterThan(0)
    // выключаем обратно — отмеченной остаётся только первая (иначе 422 бэкенда)
    await w.find('.n-switch').setValue(false)
    await w.find('textarea').setValue('Вопрос?')
    const inputs = w.findAll('.option-row .n-input')
    await inputs[0].setValue('а')
    await inputs[1].setValue('б')
    await w.findAll('button').find((b) => b.text().trim() === 'Сохранить')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('addQuestion')).toHaveBeenCalledWith({
      itemId: 'i1',
      body: {
        text: 'Вопрос?',
        multi: false,
        options: [
          { text: 'а', is_correct: true },
          { text: 'б', is_correct: false },
        ],
      },
    })
  })
})

describe('TestDrawer', () => {
  it('saves settings and deletes question', async () => {
    const { default: Drawer } = await import('../../src/components/learning/TestDrawer.vue')
    const w = mount(Drawer, { props: { show: true, itemId: 'i1' }, ...mountOpts })
    await flushPromises()
    expect(w.text()).toContain('Вопрос 1')

    await w.findAll('button').find((b) => b.text().trim() === 'Сохранить')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('testSettings')).toHaveBeenCalledWith({
      itemId: 'i1',
      body: { pass_score: 70, max_attempts: 3, time_limit_minutes: 30, shuffle_questions: false, shuffle_answers: false },
    })

    await w.findAll('.question-card button').find((b) => b.text().trim() === 'Удалить')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('deleteQuestion')).toHaveBeenCalledWith({ itemId: 'i1', questionId: 'q1' })
  })

  it('импорт вопросов: файл → предпросмотр → подтверждение', async () => {
    const { default: Drawer } = await import('../../src/components/learning/TestDrawer.vue')
    mutateSpy('previewImport').mockResolvedValueOnce({
      questions: [{ row: 2, text: 'Импортированный?', multi: false, options: [] }],
      errors: [{ row: 3, message: 'плохая строка' }],
    })
    const w = mount(Drawer, { props: { show: true, itemId: 'i1' }, ...mountOpts })
    await flushPromises()

    const input = w.find('input[type="file"]')
    expect(input.attributes('accept')).toBe('.xlsx')
    Object.defineProperty(input.element, 'files', {
      value: [new File(['x'], 'q.xlsx')],
      configurable: true,
    })
    await input.trigger('change')
    await flushPromises()
    expect(mutateSpy('previewImport')).toHaveBeenCalledWith({
      itemId: 'i1',
      file: expect.any(File),
    })

    // модал предпросмотра: вопрос, ошибка строки, подтверждение
    expect(w.text()).toContain('Импортированный?')
    expect(w.text()).toContain('плохая строка')
    const confirm = w
      .findAll('.n-modal button')
      .find((b) => b.text().trim() === 'Импортировать')!
    await confirm.trigger('click')
    await flushPromises()
    expect(mutateSpy('importQuestions')).toHaveBeenCalledWith({
      itemId: 'i1',
      file: expect.any(File),
    })
  })
})

describe('ParticipantsPanel', () => {
  it('renders progress rows and enroll requires picked participant', async () => {
    const { default: Panel } = await import('../../src/components/learning/ParticipantsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1' }, ...mountOpts })
    await flushPromises()
    expect(w.text()).toContain('Сотрудник Один')
    expect(w.text()).toContain('1 / 2')
    expect(w.text()).toContain('Экспорт в xlsx')

    await w.findAll('button').find((b) => b.text().includes('Зачислить'))!.trigger('click')
    await nextTick()
    await w.findAll('.n-modal button').find((b) => b.text().trim() === 'Зачислить')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('enroll')).not.toHaveBeenCalled()
    expect(mockMessage.error).toHaveBeenCalledWith('Выберите участника')
  })
})

describe('ParticipantsPanel draft guard', () => {
  it('черновик: «Зачислить» неактивна, показана подсказка о публикации', async () => {
    const { default: Panel } = await import('../../src/components/learning/ParticipantsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1', courseStatus: 'draft' }, ...mountOpts })
    await flushPromises()
    const enrollBtn = w.findAll('button').find((b) => b.text().includes('Зачислить'))!
    expect(enrollBtn.attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('зачисление доступно после публикации')
  })

  it('опубликованный курс: кнопка активна, подсказки нет', async () => {
    const { default: Panel } = await import('../../src/components/learning/ParticipantsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1', courseStatus: 'published' }, ...mountOpts })
    await flushPromises()
    const enrollBtn = w.findAll('button').find((b) => b.text().includes('Зачислить'))!
    expect(enrollBtn.attributes('disabled')).toBeUndefined()
    expect(w.text()).not.toContain('зачисление доступно после публикации')
  })
})

describe('ParticipantsPanel bulk enroll', () => {
  it('мультивыбор сотрудников → bulk-мутация со списком id', async () => {
    const { default: Panel } = await import('../../src/components/learning/ParticipantsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1' }, ...mountOpts })
    await flushPromises()

    await w.findAll('button').find((b) => b.text().includes('Зачислить'))!.trigger('click')
    await nextTick()

    const select = w.find('select.n-select')
    ;(select.element as HTMLSelectElement).innerHTML =
      '<option value="u1" selected></option><option value="u2"></option>'
    await select.trigger('change')
    await nextTick()

    await w.findAll('.n-modal button').find((b) => b.text().trim() === 'Зачислить')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('bulkEnroll')).toHaveBeenCalledWith({
      courseId: 'c1',
      userIds: ['u1'],
    })
  })
})

describe('ParticipantsPanel export', () => {
  it('кнопка экспорта скачивает blob', async () => {
    const blob = new Blob(['xlsx'], { type: 'application/octet-stream' })
    mockExportBlob.mockResolvedValueOnce(blob)
    const createObjectURL = vi.fn(() => 'blob:mock')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true })

    const { default: Panel } = await import('../../src/components/learning/ParticipantsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1' }, ...mountOpts })
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('Экспорт в xlsx'))!.trigger('click')
    await flushPromises()
    expect(mockExportBlob).toHaveBeenCalledWith('c1')
    expect(createObjectURL).toHaveBeenCalledWith(blob)
  })
})

describe('ParticipantsPanel bulk — отчёт об ошибках и тост мутации (ревью 2026-08-30)', () => {
  it('errors[] из ответа не теряются — warning с первой ошибкой', async () => {
    mutateSpy('bulkEnroll').mockResolvedValueOnce({
      enrolled: 1,
      skipped_duplicates: 0,
      errors: [{ user_id: 'u9', message: 'Сотрудник не найден' }],
    })
    const { default: Panel } = await import('../../src/components/learning/ParticipantsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1' }, ...mountOpts })
    await flushPromises()

    await w.findAll('button').find((b) => b.text().includes('Зачислить'))!.trigger('click')
    await nextTick()
    const select = w.find('select.n-select')
    ;(select.element as HTMLSelectElement).innerHTML = '<option value="u1" selected></option><option value="u2"></option>'
    await select.trigger('change')
    await nextTick()
    await w.findAll('.n-modal button').find((b) => b.text().trim() === 'Зачислить')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('bulkEnroll')).toHaveBeenCalled()
    expect(mockMessage.warning).toHaveBeenCalledWith(
      expect.stringContaining('Сотрудник не найден'),
    )
  })

  it('отказ bulk-мутации показывается тостом (был пропущен error-watch)', async () => {
    errorFlags['bulkEnroll'].value = new Error('network down')
    const { default: Panel } = await import('../../src/components/learning/ParticipantsPanel.vue')
    mount(Panel, { props: { courseId: 'c1' }, ...mountOpts })
    await flushPromises()
    // parseApiError нормализует текст — важен сам факт тоста
    expect(mockMessage.error).toHaveBeenCalled()
  })
})

describe('ParticipantsPanel external accounts search', () => {
  it('открывает серверный поиск учёток, а не фиксированные первые 100', async () => {
    // Ревью 2026-08-30 (P1): импорт допускает 1000 строк — селектор обязан
    // искать по q на сервере (паттерн поиска сотрудников), не показывать
    // только первый limit.
    mockFetchAccounts.mockResolvedValue({
      items: [
        { id: 'a1', email: 'ext101@x', full_name: 'Внешний Сто Первый', status: 'active' },
        { id: 'a2', email: 'blocked@x', full_name: 'Внешний Блокнутый', status: 'blocked' },
      ],
      total: 2,
      limit: 50,
      offset: 0,
    })
    const { default: Panel } = await import('../../src/components/learning/ParticipantsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1' }, ...mountOpts })
    await flushPromises()

    // до открытия модалки поиск не выполняется
    expect(mockFetchAccounts).not.toHaveBeenCalled()

    await w.findAll('button').find((b) => b.text().includes('Зачислить'))!.trigger('click')
    await flushPromises()
    expect(mockFetchAccounts).toHaveBeenCalledWith({ q: undefined, limit: 50 })
  })
})

describe('AccountsTab', () => {
  it('renders accounts, validates create and issues a login code', async () => {
    const { default: Tab } = await import('../../src/components/learning/AccountsTab.vue')
    const w = mount(Tab, mountOpts)
    await flushPromises()
    expect(w.text()).toContain('Внешний Один')

    await w.findAll('button').find((b) => b.text().includes('Создать учётку'))!.trigger('click')
    await nextTick()
    await w.findAll('.n-modal button').find((b) => b.text().trim() === 'Создать')!.trigger('click')
    await flushPromises()
    expect(mutateSpy('createAccount')).not.toHaveBeenCalled()
    expect(mockMessage.error).toHaveBeenCalledWith('Заполните email и ФИО')

    // «Выдать код» → mutation → модалка с plaintext-кодом
    mutateSpy('issueLoginCode').mockResolvedValueOnce({
      code: '654321',
      expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
    })
    await w.findAll('.table-row button').find((b) => b.text().includes('Выдать код'))!.trigger('click')
    await flushPromises()
    expect(mutateSpy('issueLoginCode')).toHaveBeenCalledWith('a1')
    expect(w.text()).toContain('654321')
  })

  it('uploads xlsx and renders the import report', async () => {
    mutateSpy('importAccounts').mockResolvedValueOnce({
      created: 2,
      skipped_duplicates: 1,
      error_count: 1,
      errors: [{ row: 4, message: 'email: Некорректный email' }],
    })
    const { default: Tab } = await import('../../src/components/learning/AccountsTab.vue')
    const w = mount(Tab, mountOpts)
    await flushPromises()
    const file = new File(['xlsx'], 'accounts.xlsx')
    const input = w.find('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    expect(mutateSpy('importAccounts')).toHaveBeenCalledWith(file)
    expect(w.text()).toContain('Создано: 2 / пропущено дублей: 1 / ошибок: 1')
    expect(w.text()).toContain('Строка 4')
    expect(w.text()).toContain('email: Некорректный email')
  })

  it('renders a successful report without row errors', async () => {
    mutateSpy('importAccounts').mockResolvedValueOnce({
      created: 2,
      skipped_duplicates: 0,
      error_count: 0,
      errors: [],
    })
    const { default: Tab } = await import('../../src/components/learning/AccountsTab.vue')
    const w = mount(Tab, mountOpts)
    const file = new File(['xlsx'], 'accounts.xlsx')
    const input = w.find('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()

    expect(w.text()).toContain('Создано: 2 / пропущено дублей: 0 / ошибок: 0')
    expect(w.find('.import-errors').exists()).toBe(false)
  })

  it('downloads the template and reports download errors', async () => {
    const createUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:template')
    const revokeUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    const { default: Tab } = await import('../../src/components/learning/AccountsTab.vue')
    const w = mount(Tab, mountOpts)
    const button = w.findAll('button').find((item) => item.text().includes('Скачать шаблон'))!

    await button.trigger('click')
    await flushPromises()
    expect(mockDownloadTemplate).toHaveBeenCalledOnce()
    expect(createUrl).toHaveBeenCalled()
    expect(click).toHaveBeenCalled()
    expect(revokeUrl).toHaveBeenCalledWith('blob:template')

    mockDownloadTemplate.mockRejectedValueOnce(new Error('download failed'))
    await button.trigger('click')
    await flushPromises()
    expect(mockMessage.error).toHaveBeenCalled()
  })
})

describe('LearningAdminPage', () => {
  it('renders both tabs', async () => {
    const { default: Page } = await import('../../src/pages/learning/LearningAdminPage.vue')
    const w = mount(Page, mountOpts)
    await flushPromises()
    expect(w.text()).toContain('Курсы')
    expect(w.text()).toContain('Внешние учётки')
  })
})

describe('CourseEditorDrawer', () => {
  it('renders course, saves edit and toggles publish', async () => {
    const { default: Drawer } = await import('../../src/components/learning/CourseEditorDrawer.vue')
    const w = mount(Drawer, { props: { show: true, courseId: 'c1' }, ...mountOpts })
    await flushPromises()
    expect(w.text()).toContain('Desc')
    expect(w.text()).toContain('Тест вводный')

    // правка карточки курса
    await w.findAll('button').find((b) => b.text().trim() === 'Редактировать')!.trigger('click')
    await nextTick()
    await w.findAll('.n-modal input')[0]!.setValue('Новое имя')
    await w.find('.n-modal .rich-editor-stub').trigger('click')
    // чекбокс «для всех сотрудников» (миграция 111) в форме правки курса
    await w.find('.n-modal .n-checkbox input').setValue(true)
    await w.findAll('.n-modal button').find((b) => b.text().trim() === 'Сохранить')!.trigger('click')
    await flushPromises()
    expect(mutateSpies.updateCourse).toHaveBeenCalledWith({
      courseId: 'c1',
      body: expect.objectContaining({
        title: 'Новое имя',
        description: 'rich-описание',
        for_all_staff: true,
      }),
    })

    // публикация из шапки редактора
    await w.findAll('button').find((b) => b.text().includes('Опубликовать'))!.trigger('click')
    await flushPromises()
    expect(mutateSpies.publish).toHaveBeenCalled()
  })
})

describe('CourseItemsPanel — правка и удаление', () => {
  const items = [
    { id: 'i1', course_id: 'c1', type: 'test', title: 'Тест', sort_order: 0, url: null, file_path: null },
    { id: 'i2', course_id: 'c1', type: 'material', title: 'Материал', sort_order: 1, url: 'https://e.e', file_path: null },
  ]

  it('edit flow sends title/url of material', async () => {
    const { default: Panel } = await import('../../src/components/learning/CourseItemsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1', items }, ...mountOpts })
    await flushPromises()
    // редактируем материал во второй строке (i2)
    await w.findAll('.item-row')[1].findAll('button').find((b) => b.text().trim() === 'Редактировать')!.trigger('click')
    await nextTick()
    const modalInputs = w.findAll('.n-modal .n-input')
    await modalInputs[0].setValue('  Материал 2  ')
    await w.findAll('.n-modal button').find((b) => b.text().trim() === 'Сохранить')!.trigger('click')
    await flushPromises()
    expect(mutateSpies.updateItem).toHaveBeenCalledWith({
      courseId: 'c1',
      itemId: 'i2',
      body: { title: 'Материал 2', url: 'https://e.e', description: null },
    })
  })

  it('delete item by row button', async () => {
    const { default: Panel } = await import('../../src/components/learning/CourseItemsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1', items }, ...mountOpts })
    await flushPromises()
    await w.findAll('.item-row button').find((b) => b.text().trim() === 'Удалить')!.trigger('click')
    await flushPromises()
    expect(mutateSpies.deleteItem).toHaveBeenCalledWith({ courseId: 'c1', itemId: 'i1' })
  })
})

describe('ParticipantsPanel — исключение', () => {
  it('removes participant by row button', async () => {
    const { default: Panel } = await import('../../src/components/learning/ParticipantsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1' }, ...mountOpts })
    await flushPromises()
    await w.findAll('.table-row button').find((b) => b.text().trim() === 'Исключить')!.trigger('click')
    await flushPromises()
    expect(mutateSpies.unenroll).toHaveBeenCalledWith({ courseId: 'c1', participantId: 'p1' })
  })
})

describe('QuestionFormModal — режим правки', () => {
  it('prefills question and calls update', async () => {
    const { default: Modal } = await import('../../src/components/learning/QuestionFormModal.vue')
    const question = {
      id: 'q1', text: 'Старый?', multi: false, sort_order: 0,
      options: [{ id: 'o1', text: 'Верный', is_correct: true, sort_order: 0 }, { id: 'o2', text: 'Неверный', is_correct: false, sort_order: 1 }],
    }
    const w = mount(Modal, { props: { show: false, itemId: 'i1', question }, ...mountOpts })
    await w.setProps({ show: true })
    await flushPromises()
    await w.find('textarea').setValue('Новый?')
    await w.findAll('button').find((b) => b.text().trim() === 'Сохранить')!.trigger('click')
    await flushPromises()
    expect(mutateSpies.updateQuestion).toHaveBeenCalledWith({
      itemId: 'i1',
      questionId: 'q1',
      body: expect.objectContaining({ text: 'Новый?' }),
    })
  })
})

describe('AccountsTab — блок/разблокировка и успешное создание', () => {
  it('toggles block status by row', async () => {
    const { default: Tab } = await import('../../src/components/learning/AccountsTab.vue')
    const w = mount(Tab, mountOpts)
    await flushPromises()
    await w.findAll('.table-row button').find((b) => b.text().includes('Заблокировать'))!.trigger('click')
    await flushPromises()
    expect(mutateSpies.blockAccount).toHaveBeenCalledWith({ accountId: 'a1', blocked: true })
  })

  it('creates account with trimmed fields', async () => {
    const { default: Tab } = await import('../../src/components/learning/AccountsTab.vue')
    const w = mount(Tab, mountOpts)
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('Создать учётку'))!.trigger('click')
    await nextTick()
    const inputs = w.findAll('.n-modal .n-input')
    await inputs[0].setValue('  a@b  ')
    await inputs[1].setValue('  Имя  ')
    await w.findAll('.n-modal button').find((b) => b.text().trim() === 'Создать')!.trigger('click')
    await flushPromises()
    expect(mutateSpies.createAccount).toHaveBeenCalledWith({
      email: 'a@b',
      full_name: 'Имя',
      department: null,
      position: null,
    })
  })
})

describe('CoursesTab delete + MethodistsTab (ревью 2026-08-28)', () => {
  it('delete course through popconfirm invalidates via mutation', async () => {
    const { default: CoursesTab } = await import('../../src/components/learning/CoursesTab.vue')
    const w = mount(CoursesTab, mountOpts)
    await flushPromises()
    const popconfirm = w.findAll('.n-popconfirm')[0]!
    await popconfirm.trigger('click')
    await flushPromises()
    expect(mutateSpy('deleteCourse')).toHaveBeenCalledWith('c1')
    expect(mockMessage.success).toHaveBeenCalledWith('Курс удалён')
  })

  it('MethodistsTab renders admins, assigns picked user, revokes via popconfirm', async () => {
    const { default: MethodistsTab } = await import('../../src/components/learning/MethodistsTab.vue')
    const w = mount(MethodistsTab, mountOpts)
    await flushPromises()
    expect(w.text()).toContain('Методист Один')

    // выбор кандидата через NSelect-мок: change → search (подгрузка опций) → update:value
    await w.find('select.n-select').setValue('')
    await flushPromises()
    await w.find('select.n-select').setValue('u9')
    const assignBtn = w.findAll('button').find((b) => b.text().includes('Назначить методистом'))!
    await assignBtn.trigger('click')
    await flushPromises()
    expect(mutateSpy('assignMethodist')).toHaveBeenCalledWith('u9')
    expect(mockMessage.success).toHaveBeenCalledWith('Методист назначен')

    const popconfirm = w.findAll('.n-popconfirm')[0]!
    await popconfirm.trigger('click')
    await flushPromises()
    expect(mutateSpy('revokeMethodist')).toHaveBeenCalledWith('u1')
    expect(mockMessage.success).toHaveBeenCalledWith('Методист снят')
  })

  it('MethodistsTab assign without pick is disabled', async () => {
    const { default: MethodistsTab } = await import('../../src/components/learning/MethodistsTab.vue')
    const w = mount(MethodistsTab, mountOpts)
    await flushPromises()
    const assignBtn = w.findAll('button').find((b) => b.text().includes('Назначить методистом'))!
    expect(assignBtn.attributes('disabled')).toBeDefined()
    expect(mutateSpy('assignMethodist')).not.toHaveBeenCalled()
  })
})

describe('Drawers — error-state вместо пустого тела (ревью 2026-08-30)', () => {
  it('TestDrawer: ошибка запроса → alert + retry', async () => {
    drawerError.test.value = true
    const { default: Drawer } = await import('../../src/components/learning/TestDrawer.vue')
    const w = mount(Drawer, { props: { show: true, itemId: 't1' }, ...mountOpts })
    await flushPromises()
    expect(w.find('.n-alert').exists()).toBe(true)
    await w.findAll('button').find((b) => b.text().includes('Повторить'))!.trigger('click')
    expect(drawerRefetch.test).toHaveBeenCalled()
    drawerError.test.value = false
  })

  it('CourseEditorDrawer: ошибка запроса → alert + retry', async () => {
    drawerError.editor.value = true
    const { default: Drawer } = await import('../../src/components/learning/CourseEditorDrawer.vue')
    const w = mount(Drawer, { props: { show: true, courseId: 'c1' }, ...mountOpts })
    await flushPromises()
    expect(w.find('.n-alert').exists()).toBe(true)
    await w.findAll('button').find((b) => b.text().includes('Повторить'))!.trigger('click')
    expect(drawerRefetch.editor).toHaveBeenCalled()
    drawerError.editor.value = false
  })
})

describe('Search debounce (ревью 2026-08-30)', () => {
  it('CoursesTab: ввод ищет с дебаунсом и сбрасывает страницу', async () => {
    const { default: Tab } = await import('../../src/components/learning/CoursesTab.vue')
    const w = mount(Tab, mountOpts)
    await flushPromises()
    const input = w.find('input.n-input')
    await input.setValue('пожарная')
    await new Promise((r) => setTimeout(r, 400))
    await flushPromises()
    expect((input.element as HTMLInputElement).value).toBe('пожарная')
  })

  it('AccountsTab: ввод ищет с дебаунсом и сбрасывает страницу', async () => {
    const { default: Tab } = await import('../../src/components/learning/AccountsTab.vue')
    const w = mount(Tab, mountOpts)
    await flushPromises()
    const input = w.find('input.n-input')
    await input.setValue('иванов')
    await new Promise((r) => setTimeout(r, 400))
    await flushPromises()
    expect((input.element as HTMLInputElement).value).toBe('иванов')
  })
})

// ── Панель участников 2.0 (2026-09-01): сертификат-кнопка, детализация, сброс ──

describe('ParticipantsPanel certificate button', () => {
  it('у завершившего курс кнопку видно, клик скачивает PDF', async () => {
    progressData.value = {
      course_id: 'c1',
      total_items: 2,
      participants: [
        { id: 'p1', participant_kind: 'staff', display_name: 'Сотрудник Один', email: 's@x', enrolled_at: '2026-01-01T00:00:00Z', progress_completed: 2, progress_total: 2, has_certificate: false },
      ],
    }
    mockCertBlob.mockResolvedValueOnce(new Blob(['pdf'], { type: 'application/pdf' }))
    const createObjectURL = vi.fn(() => 'blob:mock')
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true })

    const { default: Panel } = await import('../../src/components/learning/ParticipantsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1' }, ...mountOpts })
    await flushPromises()

    const certButton = w.findAll('button').find((b) => b.text().includes('Сертификат'))
    expect(certButton).toBeTruthy()
    await certButton!.trigger('click')
    await flushPromises()
    expect(mockCertBlob).toHaveBeenCalledWith('c1', 'p1')
    expect(mockMessage.success).toHaveBeenCalled()
  })

  it('у не завершившего и без сертификата кнопки нет', async () => {
    const { default: Panel } = await import('../../src/components/learning/ParticipantsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1' }, ...mountOpts })
    await flushPromises()
    expect(w.findAll('button').some((b) => b.text().includes('Сертификат'))).toBe(false)
  })

  it('ошибка скачивания — error-тост', async () => {
    progressData.value = {
      course_id: 'c1',
      total_items: 2,
      participants: [
        { id: 'p1', participant_kind: 'staff', display_name: 'Сотрудник Один', email: 's@x', enrolled_at: '2026-01-01T00:00:00Z', progress_completed: 2, progress_total: 2, has_certificate: true },
      ],
    }
    mockCertBlob.mockRejectedValueOnce(new Error('boom'))

    const { default: Panel } = await import('../../src/components/learning/ParticipantsPanel.vue')
    const w = mount(Panel, { props: { courseId: 'c1' }, ...mountOpts })
    await flushPromises()
    await w.findAll('button').find((b) => b.text().includes('Сертификат'))!.trigger('click')
    await flushPromises()
    expect(mockMessage.error).toHaveBeenCalled()
  })
})

describe('ParticipantItemsDetail', () => {
  it('показывает статус каждого элемента и попытки теста', async () => {
    detailItemsData.value = {
      participant_id: 'p1',
      items: [
        { item_id: 'm1', title: 'Инструкция', type: 'material', completed: true, test_passed: false, attempts_submitted: 0 },
        { item_id: 't1', title: 'Тест вводный', type: 'test', completed: true, test_passed: true, attempts_submitted: 1 },
        { item_id: 't2', title: 'Тест финальный', type: 'test', completed: false, test_passed: false, attempts_submitted: 3 },
      ],
    }
    const { default: Detail } = await import('../../src/components/learning/ParticipantItemsDetail.vue')
    const w = mount(Detail, { props: { courseId: 'c1', participantId: 'p1' }, ...mountOpts })
    await flushPromises()

    expect(w.text()).toContain('Инструкция')
    expect(w.text()).toContain('Ознакомлен')
    expect(w.text()).toContain('Тест вводный')
    expect(w.text()).toContain('Пройден')
    expect(w.text()).toContain('Тест финальный')
    expect(w.text()).toContain('Не пройден')
    expect(w.text()).toContain('Попытки: 3')
  })

  it('кнопка сброса вызывает мутацию с ids и показывает успех', async () => {
    detailItemsData.value = {
      participant_id: 'p1',
      items: [
        { item_id: 't1', title: 'Тест вводный', type: 'test', completed: false, test_passed: false, attempts_submitted: 2 },
      ],
    }
    mutateSpy('resetAttempts').mockResolvedValueOnce({ ok: true, deleted_attempts: 2 })
    const { default: Detail } = await import('../../src/components/learning/ParticipantItemsDetail.vue')
    const w = mount(Detail, { props: { courseId: 'c1', participantId: 'p1' }, ...mountOpts })
    await flushPromises()

    const popconfirm = w.find('.n-popconfirm')
    await popconfirm.trigger('click')
    await flushPromises()
    expect(mutateSpy('resetAttempts')).toHaveBeenCalledWith({
      courseId: 'c1',
      participantId: 'p1',
      itemId: 't1',
    })
    expect(mockMessage.success).toHaveBeenCalledWith('Попытки сброшены (2)')
  })

  it('ошибка сброса — error-тост, успех не показывается', async () => {
    detailItemsData.value = {
      participant_id: 'p1',
      items: [
        { item_id: 't1', title: 'Тест вводный', type: 'test', completed: false, test_passed: false, attempts_submitted: 2 },
      ],
    }
    mutateSpy('resetAttempts').mockRejectedValueOnce(new Error('boom'))
    const { default: Detail } = await import('../../src/components/learning/ParticipantItemsDetail.vue')
    const w = mount(Detail, { props: { courseId: 'c1', participantId: 'p1' }, ...mountOpts })
    await flushPromises()

    await w.find('.n-popconfirm').trigger('click')
    await flushPromises()
    expect(mockMessage.error).toHaveBeenCalled()
    expect(mockMessage.success).not.toHaveBeenCalled()
  })
})

describe('LearnerCourseItemCard', () => {
  const baseItem = {
    id: 'i9', course_id: 'c1', type: 'material', title: 'Инструктаж', sort_order: 0,
    url: 'https://example.org/doc', has_file: false, completed: false,
  }

  it('материал рендерит rich-описание (markdown → html)', async () => {
    const { default: Card } = await import('../../src/components/learning/LearnerCourseItemCard.vue')
    const w = mount(Card, {
      props: {
        item: { ...baseItem, description: 'Смотри **внимательно** на <script>alert(1)</script>условия' },
        index: 0,
        origins: [],
        completing: false,
      },
      ...mountOpts,
    })
    const desc = w.find('.item__description')
    expect(desc.exists()).toBe(true)
    // markdown отрендерен
    expect(desc.find('strong').exists()).toBe(true)
    expect(desc.text()).toContain('внимательно')
    // опасный html срезан sanitize-гейтом
    expect(desc.find('script').exists()).toBe(false)
    expect(w.html()).not.toContain('alert(1)')
  })

  it('без описания блока нет', async () => {
    const { default: Card } = await import('../../src/components/learning/LearnerCourseItemCard.vue')
    const w = mount(Card, {
      props: { item: { ...baseItem, description: null }, index: 0, origins: [], completing: false },
      ...mountOpts,
    })
    expect(w.find('.item__description').exists()).toBe(false)
  })
})
