import { api, apiUpload, type PaginatedResponse } from './index'
import type { UserStatusCategory } from './users'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json
//
// Gen-схемы отдают status / results_visibility как plain string (backend не
// аннотирован Literal), а поля с default в request-моделях — как обязательные.
// Ниже — сужение к фактическим union-значениям и сохранение опциональности
// request-полей (default применит backend); новые поля из схемы подхватываются
// автоматически.

/** Lifecycle-статус новости (backend: NewsStatus). */
type NewsStatus = 'draft' | 'published' | 'archived'

/** Видимость результатов опроса (backend: PollResultsVisibility). */
type PollResultsVisibility = 'always' | 'after_vote' | 'after_close' | 'only_admin_editor'

export type News = Omit<components['schemas']['NewsPublic'], 'status'> & {
  status: NewsStatus
}

export type NewsLikeState = components['schemas']['NewsLikeState']

export type NewsVersion = components['schemas']['NewsVersionPublic']

export type CreateNewsDto = Omit<
  components['schemas']['CreateNewsRequest'],
  'body' | 'status' | 'is_pinned'
> & {
  body?: string
  status?: 'draft' | 'published'
  is_pinned?: boolean
}

export type UpdateNewsDto = Omit<components['schemas']['UpdateNewsRequest'], 'status'> & {
  status?: NewsStatus | null
}

// Статус присутствия автора сужаем к UserStatusCategory — для кольца аватарки
// (отпуск/больничный/...); остальное — как в схеме NewsAuthor.
export type NewsAuthorPublic = Omit<components['schemas']['NewsAuthor'], 'current_status'> & {
  current_status: UserStatusCategory
}

export type NewsComment = Omit<components['schemas']['NewsCommentPublic'], 'author'> & {
  author?: NewsAuthorPublic | null
}

export type NewsCommentList = Omit<components['schemas']['NewsCommentList'], 'items'> & {
  items: NewsComment[]
}

export type NewsTrashItem = Omit<
  components['schemas']['NewsWithAuthor'],
  'status' | 'author'
> & {
  status: NewsStatus
  author?: NewsAuthorPublic | null
}

export type TrashNewsList = Omit<components['schemas']['TrashNewsList'], 'items'> & {
  items: NewsTrashItem[]
}

export type NewsCategory = components['schemas']['NewsCategoryWithCount']

export type NewsCategoriesResponse = components['schemas']['CategoriesResponse']

export type NewsUploadLimits = components['schemas']['NewsUploadLimits']

export type NewsShareEmailDto = components['schemas']['NewsShareEmailRequest']

export type NewsShareEmailResult = components['schemas']['NewsShareEmailResponse']

// ── Gallery ──────────────────────────────────────────────────────────────────

export type GalleryImage = components['schemas']['GalleryImagePublic']

export type ReorderItem = components['schemas']['ReorderItem']

export type NewsInlineMediaUpload = components['schemas']['MediaUploadResponse']

// ── Attachments ───────────────────────────────────────────────────────────────

export type NewsAttachment = components['schemas']['AttachmentPublic']

// ── Polls ─────────────────────────────────────────────────────────────────────

export type PollMyAnswer = components['schemas']['PollMyAnswer']

export type PollMyVote = components['schemas']['PollMyVote']

export type NewsPollOptionPublic = components['schemas']['NewsPollOptionPublic']

export type PollCustomAnswerPublic = components['schemas']['PollCustomAnswerPublic']

export type NewsPollQuestionPublic = components['schemas']['NewsPollQuestionPublic']

export type NewsPollPublic = Omit<components['schemas']['NewsPollPublic'], 'results_visibility'> & {
  results_visibility: PollResultsVisibility
}

export type CreateNewsPollOption = Omit<components['schemas']['CreateNewsPollOption'], 'sort_order'> & {
  sort_order?: number
}

export type CreateNewsPollQuestion = Omit<
  components['schemas']['CreateNewsPollQuestion'],
  'sort_order' | 'is_required' | 'is_multiple' | 'allow_custom_answer'
> & {
  sort_order?: number
  is_required?: boolean
  is_multiple?: boolean
  allow_custom_answer?: boolean
}

export type CreateNewsPollRequest = Omit<
  components['schemas']['CreateNewsPollRequest'],
  'is_anonymous' | 'allow_revote' | 'results_visibility'
> & {
  is_anonymous?: boolean
  allow_revote?: boolean
  results_visibility?: PollResultsVisibility
}

export type UpdateNewsPollOption = components['schemas']['UpdateNewsPollOption']

export type UpdateNewsPollQuestion = components['schemas']['UpdateNewsPollQuestion']

export type UpdateNewsPollRequest = Omit<components['schemas']['UpdateNewsPollRequest'], 'results_visibility'> & {
  results_visibility?: PollResultsVisibility | null
}

export type NewsPollAnswer = components['schemas']['NewsPollAnswer']

export type NewsPollVoteRequest = components['schemas']['NewsPollVoteRequest']

// ── Types not present in OpenAPI schema (kept as manual interfaces) ───────────
// /news/{id}/poll/voters в OpenAPI типизирован как {[key: string]: unknown}[] —
// фактическая форма ответа описана вручную ниже.

export interface PollVoterChoice {
  option_id: string
  text: string | null
}

export interface PollVoterAnswer {
  question_id: string
  question_text: string | null
  choices: PollVoterChoice[]
  custom_text: string | null
}

export interface PollVoter {
  user: {
    id: string
    full_name: string
    email: string
  }
  voted_at: string
  answers: PollVoterAnswer[]
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function likeNews(id: string): Promise<NewsLikeState> {
  return api<NewsLikeState>(`/news/${id}/like`, { method: 'POST' })
}

export async function unlikeNews(id: string): Promise<NewsLikeState> {
  return api<NewsLikeState>(`/news/${id}/like`, { method: 'DELETE' })
}

export async function fetchNewsList(
  params?: { page?: number; page_size?: number; status?: string; category?: string; is_pinned?: boolean; q?: string },
  options?: { signal?: AbortSignal },
): Promise<PaginatedResponse<News>> {
  return api<PaginatedResponse<News>>('/news', { params, signal: options?.signal })
}

export async function fetchNewsById(id: string): Promise<News> {
  return api<News>(`/news/${id}`)
}

export async function createNews(dto: CreateNewsDto): Promise<News> {
  return api<News>('/news', { method: 'POST', body: dto })
}

export async function updateNews(id: string, dto: UpdateNewsDto): Promise<News> {
  return api<News>(`/news/${id}`, { method: 'PUT', body: dto })
}

export async function saveDraft(id: string, dto: UpdateNewsDto): Promise<News> {
  return api<News>(`/news/${id}/draft`, { method: 'PUT', body: dto })
}

export async function deleteNews(id: string): Promise<void> {
  await api(`/news/${id}`, { method: 'DELETE' })
}

export async function fetchNewsVersions(id: string): Promise<NewsVersion[]> {
  return api<NewsVersion[]>(`/news/${id}/versions`)
}

export async function uploadNewsCover(id: string, file: File): Promise<News> {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<News>(`/news/${id}/cover`, form)
}

export async function deleteNewsCover(id: string): Promise<News> {
  return api<News>(`/news/${id}/cover`, { method: 'DELETE' })
}

export async function fetchGallery(newsId: string): Promise<GalleryImage[]> {
  return api<GalleryImage[]>(`/news/${newsId}/gallery`)
}

export async function uploadGalleryImage(newsId: string, file: File): Promise<GalleryImage> {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<GalleryImage>(`/news/${newsId}/gallery`, form)
}

export async function uploadNewsInlineMedia(newsId: string, file: File): Promise<NewsInlineMediaUpload> {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<NewsInlineMediaUpload>(`/news/${newsId}/inline-media`, form)
}

export async function reorderGallery(newsId: string, items: ReorderItem[]): Promise<GalleryImage[]> {
  return api<GalleryImage[]>(`/news/${newsId}/gallery/reorder`, { method: 'PATCH', body: items })
}

export async function deleteGalleryImage(newsId: string, imgId: string): Promise<void> {
  await api(`/news/${newsId}/gallery/${imgId}`, { method: 'DELETE' })
}

export async function fetchAttachments(newsId: string): Promise<NewsAttachment[]> {
  return api<NewsAttachment[]>(`/news/${newsId}/attachments`)
}

export async function uploadAttachment(newsId: string, file: File): Promise<NewsAttachment> {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<NewsAttachment>(`/news/${newsId}/attachments`, form)
}

export async function deleteAttachment(newsId: string, attId: string): Promise<void> {
  await api(`/news/${newsId}/attachments/${attId}`, { method: 'DELETE' })
}

export async function fetchNewsCategories(): Promise<NewsCategory[]> {
  const res = await api<NewsCategoriesResponse>('/news-categories')
  return res.items
}

export async function createNewsCategory(name: string, color: string): Promise<NewsCategory[]> {
  const res = await api<NewsCategoriesResponse>('/news-categories', {
    method: 'POST',
    body: { name, color },
  })
  return res.items
}

export async function updateNewsCategoryColor(name: string, color: string): Promise<NewsCategory[]> {
  const res = await api<NewsCategoriesResponse>(
    `/news-categories/${encodeURIComponent(name)}/color`,
    { method: 'PATCH', body: { color } },
  )
  return res.items
}

export async function renameNewsCategory(name: string, newName: string): Promise<NewsCategory[]> {
  const res = await api<NewsCategoriesResponse>(
    `/news-categories/${encodeURIComponent(name)}`,
    { method: 'PATCH', body: { name: newName } },
  )
  return res.items
}

export async function deleteNewsCategory(name: string): Promise<NewsCategory[]> {
  const res = await api<NewsCategoriesResponse>(
    `/news-categories/${encodeURIComponent(name)}`,
    { method: 'DELETE' },
  )
  return res.items
}

export async function fetchNewsUploadLimits(): Promise<NewsUploadLimits> {
  return api<NewsUploadLimits>('/news/limits')
}

export async function listTrashNews(params?: {
  page?: number
  page_size?: number
}): Promise<TrashNewsList> {
  return api<TrashNewsList>('/news/trash', { params })
}

export async function restoreNews(id: string): Promise<News> {
  return api<News>(`/news/${id}/restore`, { method: 'POST' })
}

export async function purgeNews(id: string): Promise<void> {
  await api(`/news/${id}/purge`, { method: 'DELETE' })
}

export async function fetchNewsPoll(newsId: string): Promise<NewsPollPublic> {
  return api<NewsPollPublic>(`/news/${newsId}/poll`)
}

export async function createNewsPoll(newsId: string, dto: CreateNewsPollRequest): Promise<NewsPollPublic> {
  return api<NewsPollPublic>(`/news/${newsId}/poll`, { method: 'POST', body: dto })
}

export async function updateNewsPoll(newsId: string, dto: UpdateNewsPollRequest): Promise<NewsPollPublic> {
  return api<NewsPollPublic>(`/news/${newsId}/poll`, { method: 'PATCH', body: dto })
}

export async function deleteNewsPoll(newsId: string): Promise<void> {
  await api(`/news/${newsId}/poll`, { method: 'DELETE' })
}

export async function closeNewsPoll(newsId: string): Promise<NewsPollPublic> {
  return api<NewsPollPublic>(`/news/${newsId}/poll/close`, { method: 'POST' })
}

export async function reopenNewsPoll(newsId: string): Promise<NewsPollPublic> {
  return api<NewsPollPublic>(`/news/${newsId}/poll/reopen`, { method: 'POST' })
}

export async function voteNewsPoll(newsId: string, dto: NewsPollVoteRequest): Promise<NewsPollPublic> {
  return api<NewsPollPublic>(`/news/${newsId}/poll/vote`, { method: 'POST', body: dto })
}

export async function revokeNewsPollVote(newsId: string): Promise<NewsPollPublic> {
  return api<NewsPollPublic>(`/news/${newsId}/poll/vote`, { method: 'DELETE' })
}

export async function fetchNewsPollVoters(newsId: string): Promise<PollVoter[]> {
  return api<PollVoter[]>(`/news/${newsId}/poll/voters`)
}

export async function fetchNewsComments(
  newsId: string,
  params?: { limit?: number; offset?: number },
): Promise<NewsCommentList> {
  return api<NewsCommentList>(`/news/${newsId}/comments`, { params })
}

export async function createNewsComment(newsId: string, body: string): Promise<NewsComment> {
  return api<NewsComment>(`/news/${newsId}/comments`, { method: 'POST', body: { body } })
}

export async function updateNewsComment(
  newsId: string,
  commentId: string,
  body: string,
): Promise<NewsComment> {
  return api<NewsComment>(`/news/${newsId}/comments/${commentId}`, {
    method: 'PATCH',
    body: { body },
  })
}

export async function deleteNewsComment(newsId: string, commentId: string): Promise<void> {
  await api<void>(`/news/${newsId}/comments/${commentId}`, { method: 'DELETE' })
}

export async function shareNewsEmail(
  newsId: string,
  dto: NewsShareEmailDto,
): Promise<NewsShareEmailResult> {
  return api<NewsShareEmailResult>(`/news/${newsId}/share-email`, { method: 'POST', body: dto })
}
