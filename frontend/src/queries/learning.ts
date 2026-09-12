import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import type { MaybeRef } from 'vue'
import { computed, toValue, unref } from 'vue'
import { queryKeys } from './keys'
import {
  addCourseItem,
  bulkEnrollParticipants,
  addQuestion,
  assignLearningAdmin,
  blockLearningAccount,
  completeMaterial,
  createCourse,
  createLearningAccount,
  deleteCourse,
  deleteCourseCover,
  deleteCourseItem,
  deleteQuestion,
  enrollParticipant,
  fetchAdminCourse,
  fetchAdminCourses,
  fetchCourseProgress,
  fetchLearningAccounts,
  fetchLearningAdmins,
  fetchLearningMeta,
  fetchMyCourse,
  fetchMyAttempts,
  fetchMyCourses,
  fetchParticipantItems,
  fetchTestConfig,
  importLearningAccounts,
  importQuestions,
  issueLearningAccountLoginCode,
  previewQuestionsImport,
  reorderCourseItems,
  resetParticipantAttempts,
  revokeLearningAdmin,
  setCoursePublished,
  submitAttempt,
  unblockLearningAccount,
  unenrollParticipant,
  updateCourse,
  updateCourseItem,
  updateTestSettings,
  updateQuestion,
  uploadCourseCover,
  uploadMaterialFile,
  type LearningAccountCreate,
  type LearningCourseCreate,
  type LearningCourseUpdate,
  type LearningItemCreate,
  type LearningItemUpdate,
  type LearningQuestionCreate,
  type LearningTestSettingsUpdate,

  fetchCategories,
  createCategory,
  updateCategory,
  reorderCategories,
  deleteCategory,
  LearningCategoryCreate,
  LearningCategoryReorder,
  LearningCategoryUpdate,} from '../api/learning'
import { DEFAULT_VIDEO_IFRAME_ORIGINS } from '../utils/videoEmbed'

// ── Запросы ──────────────────────────────────────────────────────────────────

/** «Мои курсы» — виджет главной; данные и для сотрудника, и для learner. */
export function useMyCoursesQuery(enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: queryKeys.learning.myCourses(),
    queryFn: fetchMyCourses,
    // enabled может быть реактивным (виджет скрывается/появляется) — не unref'им:
    // vue-query отслеживает ref/getter в опциях (ревью 2026-08-28).
    enabled: computed(() => toValue(enabled)),
  })
}

// ── Категории курсов (справочник, миграция 109) ──────────────────────────────

export function useCategoriesQuery(enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: queryKeys.learning.categories(),
    queryFn: fetchCategories,
    enabled: computed(() => toValue(enabled)),
  })
}

export function useCreateCategoryMutation() {
  return useInvalidatingMutation(
    (body: LearningCategoryCreate) => createCategory(body),
    (qc) => [
      qc.invalidateQueries({ queryKey: queryKeys.learning.categories() }),
      qc.invalidateQueries({ queryKey: queryKeys.learning.adminCourses() }),
    ],
  )
}

export function useUpdateCategoryMutation() {
  return useInvalidatingMutation(
    (vars: { id: string; body: LearningCategoryUpdate }) => updateCategory(vars.id, vars.body),
    (qc) => [
      qc.invalidateQueries({ queryKey: queryKeys.learning.categories() }),
      qc.invalidateQueries({ queryKey: queryKeys.learning.myCourses() }),
      qc.invalidateQueries({ queryKey: queryKeys.learning.adminCourses() }),
    ],
  )
}

export function useDeleteCategoryMutation() {
  return useInvalidatingMutation(
    (id: string) => deleteCategory(id),
    (qc) => [
      qc.invalidateQueries({ queryKey: queryKeys.learning.categories() }),
      qc.invalidateQueries({ queryKey: queryKeys.learning.myCourses() }),
      qc.invalidateQueries({ queryKey: queryKeys.learning.adminCourses() }),
    ],
  )
}

export function useReorderCategoriesMutation() {
  return useInvalidatingMutation(
    (body: LearningCategoryReorder) => reorderCategories(body),
    (qc) => [qc.invalidateQueries({ queryKey: queryKeys.learning.categories() })],
  )
}

export function useAdminCoursesQuery(
  params: MaybeRef<{ q?: string; limit: number; offset: number }>,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.learning.adminCourses(toValue(params))),
    queryFn: () => fetchAdminCourses(unref(params)),
    placeholderData: (prev) => prev,
  })
}

export function useAdminCourseQuery(courseId: MaybeRef<string | null>) {
  return useQuery({
    // Ключ и enabled обязаны оставаться реактивными: drawer создаёт запрос при
    // courseId=null и переоткрывает его с реальным id. unref здесь «заморозил»
    // бы опции навсегда (ревью 2026-08-28).
    queryKey: computed(() => queryKeys.learning.adminCourse(toValue(courseId) ?? '')),
    queryFn: () => fetchAdminCourse(toValue(courseId) as string),
    enabled: computed(() => toValue(courseId) !== null),
  })
}

export function useAdminProgressQuery(courseId: MaybeRef<string | null>) {
  return useQuery({
    queryKey: computed(() => queryKeys.learning.adminProgress(toValue(courseId) ?? '')),
    queryFn: () => fetchCourseProgress(toValue(courseId) as string),
    enabled: computed(() => toValue(courseId) !== null),
  })
}

export function useAdminTestQuery(itemId: MaybeRef<string | null>) {
  return useQuery({
    queryKey: computed(() => queryKeys.learning.adminTest(toValue(itemId) ?? '')),
    queryFn: () => fetchTestConfig(toValue(itemId) as string),
    enabled: computed(() => toValue(itemId) !== null),
  })
}

export function useAdminAccountsQuery(
  params: MaybeRef<{ q?: string; limit: number; offset: number }>,
  enabled: MaybeRef<boolean> = true,
) {
  return useQuery({
    queryKey: computed(() => queryKeys.learning.adminAccounts(toValue(params))),
    queryFn: () => fetchLearningAccounts(unref(params)),
    placeholderData: (prev) => prev,
    enabled: computed(() => toValue(enabled)),
  })
}

// ── Мутации: курсы ───────────────────────────────────────────────────────────

function useInvalidatingMutation<TVars, TResult = unknown>(
  mutationFn: (vars: TVars) => Promise<TResult>,
  invalidate: (qc: ReturnType<typeof useQueryClient>, vars: TVars) => Promise<unknown>[],
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: async (_data, vars) => {
      await Promise.all(invalidate(qc, vars))
    },
  })
}

export function useCreateCourseMutation() {
  return useInvalidatingMutation(
    (body: LearningCourseCreate) => createCourse(body),
    (qc) => [qc.invalidateQueries({ queryKey: queryKeys.learning.adminCourses() })],
  )
}

export function useUpdateCourseMutation() {
  return useInvalidatingMutation(
    (vars: { courseId: string; body: LearningCourseUpdate }) =>
      updateCourse(vars.courseId, vars.body),
    (qc, vars) => [
      qc.invalidateQueries({ queryKey: queryKeys.learning.adminCourses() }),
      qc.invalidateQueries({ queryKey: queryKeys.learning.adminCourse(vars.courseId) }),
    ],
  )
}

export function useSetCoursePublishedMutation() {
  return useInvalidatingMutation(
    (vars: { courseId: string; published: boolean }) =>
      setCoursePublished(vars.courseId, vars.published),
    (qc, vars) => [
      qc.invalidateQueries({ queryKey: queryKeys.learning.adminCourses() }),
      qc.invalidateQueries({ queryKey: queryKeys.learning.adminCourse(vars.courseId) }),
    ],
  )
}

export function useDeleteCourseMutation() {
  return useInvalidatingMutation(
    (courseId: string) => deleteCourse(courseId),
    (qc) => [qc.invalidateQueries({ queryKey: queryKeys.learning.adminCourses() })],
  )
}

// ── Мутации: обложка курса (этап 2, ТЗ §6.2) ─────────────────────────────────

export function useUploadCoverMutation() {
  return useCourseScopedMutation(
    (vars: { courseId: string; file: File }) => uploadCourseCover(vars.courseId, vars.file),
  )
}

export function useDeleteCoverMutation() {
  return useCourseScopedMutation((vars: { courseId: string }) =>
    deleteCourseCover(vars.courseId),
  )
}

// ── Мутации: импорт вопросов (этап 2, §13/§15) ───────────────────────────────

export function usePreviewQuestionsImportMutation() {
  return useMutation({
    mutationFn: (vars: { itemId: string; file: File }) =>
      previewQuestionsImport(vars.itemId, vars.file),
  })
}

export function useImportQuestionsMutation() {
  return useInvalidatingMutation(
    (vars: { itemId: string; file: File }) => importQuestions(vars.itemId, vars.file),
    (qc, vars) => [qc.invalidateQueries({ queryKey: queryKeys.learning.adminTest(vars.itemId) })],
  )
}

// ── Мутации: элементы ────────────────────────────────────────────────────────

function useCourseScopedMutation<TVars, TResult = unknown>(
  mutationFn: (vars: TVars) => Promise<TResult>,
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: async (_data, vars) => {
      const courseId =
        typeof vars === 'object' && vars !== null && 'courseId' in vars
          ? String((vars as { courseId: unknown }).courseId)
          : ''
      await Promise.all([
        qc.invalidateQueries({ queryKey: queryKeys.learning.adminCourses() }),
        courseId
          ? qc.invalidateQueries({ queryKey: queryKeys.learning.adminCourse(courseId) })
          : Promise.resolve(),
        courseId
          ? qc.invalidateQueries({ queryKey: queryKeys.learning.adminProgress(courseId) })
          : Promise.resolve(),
      ])
    },
  })
}

export function useAddItemMutation() {
  return useCourseScopedMutation(
    ({ courseId, body }: { courseId: string; body: LearningItemCreate }) =>
      addCourseItem(courseId, body),
  )
}

export function useUpdateItemMutation() {
  return useCourseScopedMutation(
    (vars: { courseId: string; itemId: string; body: LearningItemUpdate }) =>
      updateCourseItem(vars.itemId, vars.body),
  )
}

export function useDeleteItemMutation() {
  return useCourseScopedMutation(
    (vars: { courseId: string; itemId: string }) => deleteCourseItem(vars.itemId),
  )
}

export function useReorderItemsMutation() {
  return useCourseScopedMutation(
    ({ courseId, orderedIds }: { courseId: string; orderedIds: string[] }) =>
      reorderCourseItems(courseId, orderedIds),
  )
}

export function useUploadMaterialMutation() {
  return useCourseScopedMutation(
    (vars: { courseId: string; itemId: string; file: File }) =>
      uploadMaterialFile(vars.itemId, vars.file),
  )
}

// ── Мутации: тесты и вопросы ─────────────────────────────────────────────────

export function useUpdateTestSettingsMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ itemId, body }: { itemId: string; body: LearningTestSettingsUpdate }) =>
      updateTestSettings(itemId, body),
    onSuccess: async (_d, vars) => {
      await qc.invalidateQueries({ queryKey: queryKeys.learning.adminTest(vars.itemId) })
    },
  })
}

export function useAddQuestionMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ itemId, body }: { itemId: string; body: LearningQuestionCreate }) =>
      addQuestion(itemId, body),
    onSuccess: async (_d, vars) => {
      await qc.invalidateQueries({ queryKey: queryKeys.learning.adminTest(vars.itemId) })
    },
  })
}

export function useUpdateQuestionMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      itemId,
      questionId,
      body,
    }: {
      itemId: string
      questionId: string
      body: LearningQuestionCreate
    }) => updateQuestion(itemId, questionId, body),
    onSuccess: async (_d, vars) => {
      await qc.invalidateQueries({ queryKey: queryKeys.learning.adminTest(vars.itemId) })
    },
  })
}

export function useDeleteQuestionMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ itemId, questionId }: { itemId: string; questionId: string }) =>
      deleteQuestion(itemId, questionId),
    onSuccess: async (_d, vars) => {
      await qc.invalidateQueries({ queryKey: queryKeys.learning.adminTest(vars.itemId) })
    },
  })
}

// ── Мутации: участники ───────────────────────────────────────────────────────

/** Групповое зачисление:invalidate прогресса и курса (этап 2). */
export function useBulkEnrollMutation() {
  return useCourseScopedMutation<
    { courseId: string; userIds: string[] },
    { enrolled: number; skipped_duplicates: number; errors: { user_id: string; message: string }[] }
  >(
    (vars) => bulkEnrollParticipants(vars.courseId, vars.userIds),
  )
}

export function useEnrollParticipantMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      courseId,
      body,
    }: {
      courseId: string
      body: { user_id?: string | null; learning_account_id?: string | null }
    }) => enrollParticipant(courseId, body),
    onSuccess: async (_d, vars) => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: queryKeys.learning.adminCourse(vars.courseId) }),
        qc.invalidateQueries({ queryKey: queryKeys.learning.adminProgress(vars.courseId) }),
      ])
    },
  })
}

export function useUnenrollParticipantMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ courseId, participantId }: { courseId: string; participantId: string }) =>
      unenrollParticipant(courseId, participantId),
    onSuccess: async (_d, vars) => {
      await Promise.all([
        qc.invalidateQueries({ queryKey: queryKeys.learning.adminCourse(vars.courseId) }),
        qc.invalidateQueries({ queryKey: queryKeys.learning.adminProgress(vars.courseId) }),
      ])
    },
  })
}

/** Детализация «как решён курс» у участника (раскрываемая строка таблицы). */
export function useParticipantItemsQuery(
  courseId: MaybeRef<string>,
  participantId: MaybeRef<string>,
  enabled: MaybeRef<boolean> = true,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.learning.participantItems(toValue(courseId), toValue(participantId)),
    ),
    queryFn: () => fetchParticipantItems(toValue(courseId), toValue(participantId)),
    enabled: computed(() => toValue(enabled) && toValue(participantId) !== ''),
  })
}

/** Сброс попыток теста: пересдает участник — прогресс курса и детали меняются. */
export function useResetParticipantAttemptsMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      courseId,
      participantId,
      itemId,
    }: { courseId: string; participantId: string; itemId: string }) =>
      resetParticipantAttempts(courseId, participantId, itemId),
    onSuccess: async (_d, vars) => {
      await Promise.all([
        qc.invalidateQueries({
          queryKey: queryKeys.learning.participantItems(vars.courseId, vars.participantId),
        }),
        qc.invalidateQueries({ queryKey: queryKeys.learning.adminProgress(vars.courseId) }),
      ])
    },
  })
}

// ── Мутации: внешние учётки ──────────────────────────────────────────────────
export function useCreateAccountMutation() {
  return useInvalidatingMutation(
    (body: LearningAccountCreate) => createLearningAccount(body),
    (qc) => [qc.invalidateQueries({ queryKey: queryKeys.learning.adminAccounts() })],
  )
}

export function useImportAccountsMutation() {
  return useInvalidatingMutation(
    (file: File) => importLearningAccounts(file),
    (qc) => [qc.invalidateQueries({ queryKey: queryKeys.learning.adminAccounts() })],
  )
}

export function useIssueAccountLoginCodeMutation() {
  return useInvalidatingMutation(
    (accountId: string) => issueLearningAccountLoginCode(accountId),
    (qc) => [qc.invalidateQueries({ queryKey: queryKeys.learning.adminAccounts() })],
  )
}

export function useBlockAccountMutation() {
  return useInvalidatingMutation(
    ({ accountId, blocked }: { accountId: string; blocked: boolean }) =>
      (blocked ? blockLearningAccount : unblockLearningAccount)(accountId),
    (qc) => [qc.invalidateQueries({ queryKey: queryKeys.learning.adminAccounts() })],
  )
}

// ── Методисты (только глобальный админ) ─────────────────────────────────────

export function useLearningAdminsQuery() {
  return useQuery({
    queryKey: queryKeys.learning.admins(),
    queryFn: fetchLearningAdmins,
  })
}

export function useAssignMethodistMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => assignLearningAdmin({ user_id: userId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.learning.admins() }),
  })
}

export function useRevokeMethodistMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => revokeLearningAdmin(userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.learning.admins() }),
  })
}

// ── Learner: раздел «Обучение» ───────────────────────────────────────────────

export function useMyCourseQuery(slug: MaybeRef<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.learning.myCourse(toValue(slug))),
    queryFn: () => fetchMyCourse(toValue(slug)),
  })
}

export function useMyAttemptsQuery(testItemId: MaybeRef<string | null>) {
  return useQuery({
    queryKey: computed(() => queryKeys.learning.myAttempts(toValue(testItemId) ?? '')),
    queryFn: () => fetchMyAttempts(toValue(testItemId) as string),
    enabled: computed(() => toValue(testItemId) !== null),
  })
}

export function useCompleteMaterialMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { itemId: string; slug: string }) => completeMaterial(vars.itemId),
    onSuccess: (_d, vars) =>
      Promise.all([
        qc.invalidateQueries({ queryKey: queryKeys.learning.myCourse(vars.slug) }),
        qc.invalidateQueries({ queryKey: queryKeys.learning.myCourses() }),
      ]),
  })
}

export function useSubmitAttemptMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: {
      attemptId: string
      answers: Record<string, string[]>
      testItemId: string
      slug: string
    }) => submitAttempt(vars.attemptId, vars.answers),
    onSuccess: (_d, vars) =>
      Promise.all([
        qc.invalidateQueries({ queryKey: queryKeys.learning.myAttempts(vars.testItemId) }),
        qc.invalidateQueries({ queryKey: queryKeys.learning.myCourse(vars.slug) }),
        qc.invalidateQueries({ queryKey: queryKeys.learning.myCourses() }),
      ]),
  })
}

// ── Мета модуля: разрешённые iframe-origin'ы (гейт видео-плеера) ─────────────
// Единый источник для обоих контуров (learn-сборка не имеет /bootstrap).
// Пока мета не загружена — дефолт (зеркало DEFAULT_VIDEO_IFRAME_ORIGINS
// backend'а), чтобы бейдж/плеер не мигали «выключенными».

export function useVideoOriginsQuery() {
  const query = useQuery({
    queryKey: queryKeys.learning.meta(),
    queryFn: fetchLearningMeta,
    staleTime: 5 * 60 * 1000,
  })
  const origins = computed(() => query.data.value?.video_iframe_origins ?? DEFAULT_VIDEO_IFRAME_ORIGINS)
  return { query, origins }
}
