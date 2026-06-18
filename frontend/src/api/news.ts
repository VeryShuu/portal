import { api, apiUpload, type PaginatedResponse } from './index'

export interface News {
  id: string
  title: string
  body: string
  status: 'draft' | 'published' | 'archived'
  is_pinned: boolean
  categories: string[]
  cover_image_url: string | null
  cover_focal_x: number | null
  cover_focal_y: number | null
  cover_dominant_color?: string | null
  cover_webp_srcset?: string | null
  cover_avif_srcset?: string | null
  target_departments: string[] | null
  target_roles: string[] | null
  author_id: string | null
  publish_at: string | null
  archive_at: string | null
  published_at: string | null
  view_count: number
  like_count: number
  liked_by_me: boolean
  comment_count: number
  current_version: number
  has_poll?: boolean
  created_at: string
  updated_at: string
}

export interface NewsLikeState {
  like_count: number
  liked_by_me: boolean
}

export async function likeNews(id: string): Promise<NewsLikeState> {
  return api<NewsLikeState>(`/news/${id}/like`, { method: 'POST' })
}

export async function unlikeNews(id: string): Promise<NewsLikeState> {
  return api<NewsLikeState>(`/news/${id}/like`, { method: 'DELETE' })
}

export interface NewsVersion {
  id: string
  news_id: string
  version: number
  title: string
  body: string
  editor_id: string | null
  created_at: string
}

export interface CreateNewsDto {
  title: string
  body?: string
  status?: 'draft' | 'published'
  is_pinned?: boolean
  categories?: string[]
  target_departments?: string[] | null
  target_roles?: string[] | null
  publish_at?: string | null
  archive_at?: string | null
  cover_focal_x?: number | null
  cover_focal_y?: number | null
}

export interface UpdateNewsDto extends Partial<CreateNewsDto> {
  published_at?: string | null
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

// ── Gallery ──────────────────────────────────────────────────────────────────

export interface GalleryImage {
  id: string
  news_id: string
  url: string
  original_name: string
  sort_order: number
  file_size: number | null
  created_at: string
}

export interface ReorderItem {
  id: string
  sort_order: number
}

export async function fetchGallery(newsId: string): Promise<GalleryImage[]> {
  return api<GalleryImage[]>(`/news/${newsId}/gallery`)
}

export async function uploadGalleryImage(newsId: string, file: File): Promise<GalleryImage> {
  const form = new FormData()
  form.append('file', file)
  return apiUpload<GalleryImage>(`/news/${newsId}/gallery`, form)
}

export interface NewsInlineMediaUpload {
  url: string
  filename: string
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

// ── Attachments ───────────────────────────────────────────────────────────────

export interface NewsAttachment {
  id: string
  news_id: string
  original_name: string
  mime_type: string | null
  file_size: number | null
  created_at: string
  download_url: string
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

// ── Categories ────────────────────────────────────────────────────────────────

export interface NewsCategory {
  name: string
  color: string
  news_count: number
}

export interface NewsCategoriesResponse {
  items: NewsCategory[]
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

export interface NewsUploadLimits {
  news_attachment_max_size_mb: number
}

export async function fetchNewsUploadLimits(): Promise<NewsUploadLimits> {
  return api<NewsUploadLimits>('/news/limits')
}

// ── Trash ─────────────────────────────────────────────────────────────────────

export interface NewsAuthorPublic {
  id: string
  full_name: string
  department: string | null
  avatar_url: string | null
}

export interface NewsTrashItem extends News {
  deleted_at: string
  previous_status: string | null
  author: NewsAuthorPublic | null
}

export interface TrashNewsList {
  items: NewsTrashItem[]
  total: number
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

// ── Polls ─────────────────────────────────────────────────────────────────────

export interface PollMyAnswer {
  question_id: string
  option_ids: string[]
  custom_text?: string | null
}

export interface PollMyVote {
  answers: PollMyAnswer[]
  voted_at: string
}

export interface NewsPollOptionPublic {
  id: string
  text?: string | null
  image_url?: string | null
  sort_order: number
  votes_count?: number | null
  votes_percent?: number | null
}

export interface PollCustomAnswerPublic {
  text: string
  voter_id?: string | null
  voter_name?: string | null
}

export interface NewsPollQuestionPublic {
  id: string
  text: string
  sort_order: number
  is_required: boolean
  is_multiple: boolean
  max_choices?: number | null
  allow_custom_answer: boolean
  options: NewsPollOptionPublic[]
  custom_answers?: PollCustomAnswerPublic[] | null
  total_answers?: number | null
}

export interface NewsPollPublic {
  id: string
  news_id: string
  is_anonymous: boolean
  allow_revote: boolean
  results_visibility: 'always' | 'after_vote' | 'after_close' | 'only_admin_editor'
  closes_at?: string | null
  closed_at?: string | null
  is_closed: boolean
  total_voters?: number | null
  questions: NewsPollQuestionPublic[]
  my_vote?: PollMyVote | null
  can_vote: boolean
  can_see_results: boolean
}

export interface CreateNewsPollOption {
  text?: string | null
  image_url?: string | null
  sort_order?: number
}

export interface CreateNewsPollQuestion {
  text: string
  sort_order?: number
  is_required?: boolean
  is_multiple?: boolean
  max_choices?: number | null
  allow_custom_answer?: boolean
  options: CreateNewsPollOption[]
}

export interface CreateNewsPollRequest {
  is_anonymous?: boolean
  allow_revote?: boolean
  results_visibility?: 'always' | 'after_vote' | 'after_close' | 'only_admin_editor'
  closes_at?: string | null
  questions: CreateNewsPollQuestion[]
}

export interface UpdateNewsPollOption {
  id?: string | null
  text?: string | null
  image_url?: string | null
  sort_order?: number | null
}

export interface UpdateNewsPollQuestion {
  id?: string | null
  text?: string | null
  sort_order?: number | null
  is_required?: boolean | null
  is_multiple?: boolean | null
  max_choices?: number | null
  allow_custom_answer?: boolean | null
  options?: UpdateNewsPollOption[] | null
}

export interface UpdateNewsPollRequest {
  is_anonymous?: boolean | null
  allow_revote?: boolean | null
  results_visibility?: 'always' | 'after_vote' | 'after_close' | 'only_admin_editor' | null
  closes_at?: string | null
  questions?: UpdateNewsPollQuestion[] | null
}

export interface NewsPollAnswer {
  question_id: string
  option_ids: string[]
  custom_text?: string | null
}

export interface NewsPollVoteRequest {
  answers: NewsPollAnswer[]
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

export async function fetchNewsPollVoters(newsId: string): Promise<PollVoter[]> {
  return api<PollVoter[]>(`/news/${newsId}/poll/voters`)
}

// ── Comments ──────────────────────────────────────────────────────────────────

export interface NewsComment {
  id: string
  news_id: string
  body: string | null
  is_deleted: boolean
  created_at: string
  updated_at: string
  author: NewsAuthorPublic | null
}

export interface NewsCommentList {
  items: NewsComment[]
  total: number
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

// ── Share by email ────────────────────────────────────────────────────────────

export interface NewsShareEmailDto {
  recipient_ids: string[]
  message?: string | null
}

export interface NewsShareEmailResult {
  enqueued: number
}

export async function shareNewsEmail(
  newsId: string,
  dto: NewsShareEmailDto,
): Promise<NewsShareEmailResult> {
  return api<NewsShareEmailResult>(`/news/${newsId}/share-email`, { method: 'POST', body: dto })
}
