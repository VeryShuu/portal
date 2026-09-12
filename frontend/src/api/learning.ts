import { ofetch } from 'ofetch'
import { api, apiUpload, BASE_URL } from './index'
import type { components } from './types.gen'

// ── Типы из OpenAPI (backend/app/schemas/learning.py) ───────────────────────

export type LearningCourse = components['schemas']['CourseOut']
export type LearningCourseList = components['schemas']['CourseListOut']
export type LearningCourseDetail = components['schemas']['CourseDetailOut']
export type LearningCourseCreate = components['schemas']['CourseCreate']
export type LearningCourseUpdate = components['schemas']['CourseUpdate']
export type LearningItem = components['schemas']['ItemOut']
export type LearningItemCreate = components['schemas']['ItemCreate']
export type LearningItemUpdate = components['schemas']['ItemUpdate']
export type LearningTestSettingsUpdate = components['schemas']['TestSettingsUpdate']
// QuestionCreate из OpenAPI требует sort_order в вариантах — но это внутренняя
    // нормализация бэкенда (sort_order выставляется по порядку ввода), фронт его
    // не присылает. Фронтовой контракт — без sort_order.
export interface LearningOptionIn {
  text: string
  is_correct: boolean
}

export interface LearningQuestionCreate {
  text: string
  multi: boolean
  options: LearningOptionIn[]
}

// Админские view теста/вопросов: эндпоинты отдают dict (без response_model),
// поэтому этих схем в OpenAPI нет — контракт фиксируем здесь (прецедент
// HelpdeskInboxParams в api/helpdesk.ts).
export interface LearningTestSettings {
  pass_score: number
  max_attempts: number
  shuffle_questions: boolean
  shuffle_answers: boolean
}

export interface LearningOptionOut {
  id: string
  text: string
  is_correct: boolean
  sort_order: number
}

export interface LearningQuestionOut {
  id: string
  text: string
  multi: boolean
  sort_order: number
  options: LearningOptionOut[]
}
// ParticipantOut в OpenAPI занят helpdesk-схемой; learning-вариант объявляем явно.
export interface LearningParticipantRow {
  id: string
  participant_kind: 'staff' | 'external'
  display_name: string
  email: string | null
  enrolled_at: string
  progress_completed: number
  progress_total: number
  has_certificate?: boolean
}
export type LearningProgress = {
  course_id: string
  total_items: number
  participants: LearningParticipantRow[]
}
// Детализация «как решён курс» у участника (панель участников, 2026-09-01).
export interface LearningParticipantItemStatus {
  item_id: string
  title: string
  type: 'material' | 'test'
  completed: boolean
  test_passed: boolean
  attempts_submitted: number
}
export type LearningParticipantItems = {
  participant_id: string
  items: LearningParticipantItemStatus[]
}
export type LearningAccount = components['schemas']['LearningAccountOut']
export type LearningAccountList = components['schemas']['LearningAccountListOut']
export type LearningAccountCreate = components['schemas']['LearningAccountCreate']
export type LearningAccountImport = components['schemas']['LearningAccountImportOut']
export type MyCourse = components['schemas']['MyCourseOut']

/** Тестовый конфиг = настройки + вопросы с ответами (админский view). */
export interface LearningTestConfig extends LearningTestSettings {
  questions: LearningQuestionOut[]
  time_limit_minutes: number | null
}

// ── Курсы ────────────────────────────────────────────────────────────────────

export function fetchAdminCourses(params: { q?: string; limit?: number; offset?: number } = {}) {
  return api<LearningCourseList>('/learning/admin/courses', { query: params })
}

export function fetchAdminCourse(courseId: string) {
  return api<LearningCourseDetail>(`/learning/admin/courses/${courseId}`)
}

export function createCourse(body: LearningCourseCreate) {
  return api<LearningCourse>('/learning/admin/courses', { method: 'POST', body })
}

export function updateCourse(courseId: string, body: LearningCourseUpdate) {
  return api<LearningCourse>(`/learning/admin/courses/${courseId}`, { method: 'PATCH', body })
}

export function setCoursePublished(courseId: string, published: boolean) {
  return api<{ ok: boolean; status: string }>(
    `/learning/admin/courses/${courseId}/${published ? 'publish' : 'unpublish'}`,
    { method: 'POST' },
  )
}

export function deleteCourse(courseId: string) {
  return api<{ ok: boolean }>(`/learning/admin/courses/${courseId}`, { method: 'DELETE' })
}

// ── Элементы ─────────────────────────────────────────────────────────────────

export function addCourseItem(courseId: string, body: LearningItemCreate) {
  return api<{ id: string; sort_order: number }>(`/learning/admin/courses/${courseId}/items`, {
    method: 'POST',
    body,
  })
}

export function updateCourseItem(itemId: string, body: LearningItemUpdate) {
  return api<{ ok: boolean }>(`/learning/admin/courses/items/${itemId}`, {
    method: 'PATCH',
    body,
  })
}

export function deleteCourseItem(itemId: string) {
  return api<{ ok: boolean }>(`/learning/admin/courses/items/${itemId}`, { method: 'DELETE' })
}

export function reorderCourseItems(courseId: string, orderedIds: string[]) {
  return api<{ ok: boolean }>(`/learning/admin/courses/${courseId}/items/reorder`, {
    method: 'POST',
    body: { ordered_ids: orderedIds },
  })
}

export function uploadMaterialFile(itemId: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<{ ok: boolean; file_path: string; mime: string }>(
    `/learning/admin/courses/items/${itemId}/file`,
    form,
  )
}

// ── Обложка курса (этап 2, ТЗ §6.2) ──────────────────────────────────────────

export function uploadCourseCover(courseId: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<LearningCourse>(`/learning/admin/courses/${courseId}/cover`, form)
}

export function deleteCourseCover(courseId: string) {
  return api<LearningCourse>(`/learning/admin/courses/${courseId}/cover`, { method: 'DELETE' })
}

// ── Тесты и вопросы ──────────────────────────────────────────────────────────

export function fetchTestConfig(itemId: string) {
  return api<LearningTestConfig>(`/learning/admin/courses/items/${itemId}/test`)
}

export function updateTestSettings(itemId: string, body: LearningTestSettingsUpdate) {
  return api<{ ok: boolean }>(`/learning/admin/courses/items/${itemId}/test`, {
    method: 'PATCH',
    body,
  })
}

export function addQuestion(itemId: string, body: LearningQuestionCreate) {
  return api<{ ok: boolean; question_id: string }>(
    `/learning/admin/courses/items/${itemId}/questions`,
    { method: 'POST', body },
  )
}

export function updateQuestion(itemId: string, questionId: string, body: LearningQuestionCreate) {
  return api<{ ok: boolean }>(
    `/learning/admin/courses/items/${itemId}/questions/${questionId}`,
    { method: 'PATCH', body },
  )
}

export function deleteQuestion(itemId: string, questionId: string) {
  return api<{ ok: boolean }>(
    `/learning/admin/courses/items/${itemId}/questions/${questionId}`,
    { method: 'DELETE' },
  )
}

// ── Участники и прогресс ─────────────────────────────────────────────────────

export function enrollParticipant(
  courseId: string,
  body: components['schemas']['ParticipantEnroll'],
) {
  return api<{ ok: boolean; participant_id: string }>(
    `/learning/admin/courses/${courseId}/participants`,
    { method: 'POST', body },
  )
}

/** Групповое зачисление сотрудников (этап 2): дубли пропускаются. */
export function bulkEnrollParticipants(courseId: string, userIds: string[]) {
  return api<{ enrolled: number; skipped_duplicates: number; errors: { user_id: string; message: string }[] }>(
    `/learning/admin/courses/${courseId}/participants/bulk`,
    { method: 'POST', body: { user_ids: userIds } },
  )
}

export function unenrollParticipant(courseId: string, participantId: string) {
  return api<{ ok: boolean }>(
    `/learning/admin/courses/${courseId}/participants/${participantId}`,
    { method: 'DELETE' },
  )
}

/** Статус решения курса участником: каждый элемент с флагом и попытками. */
export function fetchParticipantItems(courseId: string, participantId: string) {
  return api<LearningParticipantItems>(
    `/learning/admin/courses/${courseId}/participants/${participantId}/items`,
  )
}

/** Сброс попыток теста участнику: попытки + отметка «пройдено» (аудит на бэке). */
export function resetParticipantAttempts(courseId: string, participantId: string, itemId: string) {
  return api<{ ok: boolean; deleted_attempts: number }>(
    `/learning/admin/courses/${courseId}/participants/${participantId}/items/${itemId}/reset-attempts`,
    { method: 'POST' },
  )
}

/** Сертификат участника (PDF): скачивание выданного либо выпуск за пройденный курс. */
export function fetchParticipantCertificateBlob(courseId: string, participantId: string) {
  return apiBlob(
    `/learning/admin/courses/${courseId}/participants/${participantId}/certificate`,
  )
}


export function fetchCourseProgress(courseId: string) {
  return api<LearningProgress>(`/learning/admin/courses/${courseId}/progress`)
}

/** Blob-запрос (скачивание xlsx/pdf) с cookie-сессией портала. */
function apiBlob(path: string): Promise<Blob> {
  return ofetch(path, { baseURL: BASE_URL, credentials: 'include', responseType: 'blob' }) as Promise<Blob>
}

/** Экспорт прогресса курса в xlsx (этап 2): blob для скачивания. */
export function exportProgressBlob(courseId: string) {
  return apiBlob(`/learning/admin/courses/${courseId}/progress/export`)
}

// ── Внешние учётки ───────────────────────────────────────────────────────────

// ── Категории курсов (справочник модуля, миграция 109) ───────────────────────

export type LearningCategory = components['schemas']['CategoryOut']
export type LearningCategoryCreate = components['schemas']['CategoryCreate']
export type LearningCategoryUpdate = components['schemas']['CategoryUpdate']
export type LearningCategoryReorder = components['schemas']['CategoryReorder']

export function fetchCategories() {
  return api<LearningCategory[]>('/learning/admin/categories')
}

export function createCategory(body: LearningCategoryCreate) {
  return api<LearningCategory>('/learning/admin/categories', { method: 'POST', body })
}

export function updateCategory(id: string, body: LearningCategoryUpdate) {
  return api<LearningCategory>(`/learning/admin/categories/${id}`, { method: 'PATCH', body })
}

export function reorderCategories(body: LearningCategoryReorder) {
  return api<{ ok: boolean }>('/learning/admin/categories/reorder', { method: 'POST', body })
}

export function deleteCategory(id: string) {
  return api<{ ok: boolean }>(`/learning/admin/categories/${id}`, { method: 'DELETE' })
}

export function fetchLearningAccounts(
  params: { q?: string; limit?: number; offset?: number; status?: string } = {},
) {
  return api<LearningAccountList>('/learning/admin/accounts', { query: params })
}

export function createLearningAccount(body: LearningAccountCreate) {
  return api<LearningAccount>('/learning/admin/accounts', { method: 'POST', body })
}

export function importLearningAccounts(file: File) {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<LearningAccountImport>('/learning/admin/accounts/import', form)
}

export function downloadLearningAccountsTemplate() {
  return apiBlob('/learning/admin/accounts/template')
}

// ── Импорт вопросов из xlsx (этап 2, ТЗ §13/§15) ─────────────────────────────

export interface QuestionsImportRow {
  row: number
  text: string
  multi: boolean
  options: { text: string; is_correct: boolean }[]
}

export interface QuestionsImportError {
  row: number
  message: string
}

export interface QuestionsImportPreview {
  questions: QuestionsImportRow[]
  errors: QuestionsImportError[]
}

export interface QuestionsImportResult {
  created: number
  errors: QuestionsImportError[]
}

/** Шаблон импорта вопросов: колонки = тем же кодом, что валидирует импорт. */
export function downloadQuestionsTemplate(itemId: string) {
  return apiBlob(`/learning/admin/courses/items/${itemId}/questions/template`)
}

export function previewQuestionsImport(itemId: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<QuestionsImportPreview>(
    `/learning/admin/courses/items/${itemId}/questions/import/preview`,
    form,
  )
}

export function importQuestions(itemId: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<QuestionsImportResult>(
    `/learning/admin/courses/items/${itemId}/questions/import`,
    form,
  )
}

/** Ручная выдача одноразового кода входа (запасной путь «письмо не дошло»). */
export function issueLearningAccountLoginCode(accountId: string) {
  return api<{ code: string; expires_at: string }>(
    `/learning/admin/accounts/${accountId}/login-code`,
    { method: 'POST' },
  )
}

export function blockLearningAccount(accountId: string) {
  return api<{ ok: boolean }>(`/learning/admin/accounts/${accountId}/block`, { method: 'POST' })
}

export function unblockLearningAccount(accountId: string) {
  return api<{ ok: boolean }>(`/learning/admin/accounts/${accountId}/unblock`, { method: 'POST' })
}

// ── Сотрудник/learner: мои курсы (виджет главной) ────────────────────────────

export function fetchMyCourses() {
  return api<MyCourse[]>('/learning/me/courses')
}

// ── Мета модуля (обоим контурам; гейт видео-плеера, без секретов) ────────────

export type LearningMeta = components['schemas']['LearningMetaOut']

export function fetchLearningMeta() {
  return api<LearningMeta>('/learning/meta')
}

// ── Learner: раздел «Обучение» (портал, инкремент learner-страниц) ───────────

export type MyCourseDetail = components['schemas']['MyCourseDetailOut']
export type MyCourseItem = components['schemas']['MyCourseItemOut']
export type AttemptView = components['schemas']['AttemptView']
export type AttemptResult = components['schemas']['AttemptResult']
export type AttemptBrief = components['schemas']['AttemptBrief']
export type MyAttempts = components['schemas']['MyAttemptsOut']
export type LearnerQuestion = components['schemas']['LearnerQuestionOut']
export type LearnerOption = components['schemas']['LearnerOptionOut']

export function fetchMyCourse(slug: string) {
  return api<MyCourseDetail>(`/learning/me/courses/${slug}`)
}

export function completeMaterial(itemId: string) {
  return api<{ ok: boolean; already_completed: boolean }>(
    `/learning/me/items/${itemId}/complete`,
    { method: 'POST' },
  )
}

/** PDF материала: стриминг, cookie портальной сессии — обычная ссылка. */
export function materialFileUrl(itemId: string) {
  return `/api/v1/learning/me/items/${itemId}/file`
}

/** PDF сертификата за пройденный курс: та же схема, что у материала. */
export function certificateFileUrl(slug: string) {
  return `/api/v1/learning/me/courses/${slug}/certificate`
}

export function fetchMyAttempts(testItemId: string) {
  return api<MyAttempts>(`/learning/me/tests/${testItemId}/my-attempts`)
}

export function startAttempt(testItemId: string) {
  return api<AttemptView>(`/learning/me/tests/${testItemId}/attempts`, { method: 'POST' })
}

export function fetchAttempt(attemptId: string) {
  return api<AttemptView | AttemptResult>(`/learning/me/attempts/${attemptId}`)
}

export function submitAttempt(attemptId: string, answers: Record<string, string[]>) {
  return api<AttemptResult>(`/learning/me/attempts/${attemptId}/submit`, {
    method: 'POST',
    body: { answers },
  })
}

// ── Методисты (learning_admins; назначает только глобальный админ, §3 ТЗ) ────

export type LearningAdmin = components['schemas']['LearningAdminOut']
export type LearningAdminCreate = components['schemas']['LearningAdminCreate']

export function fetchLearningAdmins() {
  return api<LearningAdmin[]>('/learning/admins')
}

export function assignLearningAdmin(body: LearningAdminCreate) {
  return api<{ ok: boolean; user_id: string }>('/learning/admins', { method: 'POST', body })
}

export function revokeLearningAdmin(userId: string) {
  return api<{ ok: boolean }>(`/learning/admins/${userId}`, { method: 'DELETE' })
}
