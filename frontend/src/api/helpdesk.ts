import { api, apiUpload } from './index'

// ── Tickets (requester + agent) ────────────────────────────────────────────

export type HelpdeskStatus = 'new' | 'open' | 'pending' | 'closed'
export type HelpdeskSource = 'email' | 'web'
export type HelpdeskDirection = 'inbound' | 'outbound'
export type HelpdeskVisibility = 'public' | 'internal'

export interface HelpdeskMessage {
  id: string
  direction: HelpdeskDirection
  visibility: HelpdeskVisibility
  source: HelpdeskSource
  author_email: string
  author_name: string | null
  author_user_id: string | null
  body_text: string
  body_html: string | null
  attachments: HelpdeskAttachmentMeta[]
  /**
   * Cc конкретного сообщения (миграция 083): ``[{email, name, is_requester}]``.
   * Для inbound — из заголовка ``Cc`` входящего письма; для outbound — список,
   * который агент указал при ответе («Ответить всем»). Пустой массив для
   * сообщений без копии. В UI — компактный бейдж «Cc: …» под телом (agent-mode).
   */
  cc: HelpdeskParticipant[]
  created_at: string
}

/** Адресат письма (Cc / участник тикета) — миграция 083. */
export interface HelpdeskParticipant {
  email: string
  name: string | null
  /** ``true`` только в ``ticket.participants`` для автора заявки (подсветка). */
  is_requester?: boolean
}

export interface HelpdeskAttachmentMeta {
  id: string
  filename: string
  original_name: string
  content_type: string
  size_bytes: number
  created_at: string
}

export interface HelpdeskTicketListItem {
  id: string
  number: number
  subject: string
  status: HelpdeskStatus
  source: HelpdeskSource
  requester_email: string
  requester_user_id: string | null
  requester_name: string | null
  assignee_user_id: string | null
  assignee_name: string | null
  last_activity_at: string
  created_at: string
  /**
   * Подсветка непрочитанных ответов заявителя для агента (миграция 080).
   * ``undefined`` — состояние неизвестно (requester-view ``/tickets/my`` и
   * прочие не-агентские списки, где unread-семантика другая). ``true`` — у
   * тикета есть публичные входящие сообщения новее ``last_seen_at`` агента.
   */
  unread?: boolean
}

export interface HelpdeskRequesterProfile {
  email: string
  full_name: string
  department: string | null
  position: string | null
  city: string | null
  mobile_phone: string | null
  internal_phone: string | null
}

export interface HelpdeskTicketList {
  items: HelpdeskTicketListItem[]
  total: number
  limit: number
  offset: number
}

export interface HelpdeskTicketDetail extends HelpdeskTicketListItem {
  description: string
  description_html: string | null
  assignee_name: string | null
  messages: HelpdeskMessage[]
  requester_profile?: HelpdeskRequesterProfile | null
  // agent-only fields (optional, отсутствуют в requester-view)
  assigned_at?: string | null
  closed_at?: string | null
  closed_by_user_id?: string | null
  references_archived_ticket_number?: number | null
  /**
   * Все участники тикета «в сборе» (миграция 083): requester + все Cc + все
   * авторы сообщений. Только в агентском view (``fetchAgentTicket``); в
   * requester-view поле отсутствует (PII-минимизация). Источник для блока
   * «Участники» в сайдбаре и для pre-fill чекбокса «Ответить всем».
   */
  participants?: HelpdeskParticipant[]
}

export interface HelpdeskInboxParams {
  status?: HelpdeskStatus
  assignee?: string
  unassigned?: boolean
  source?: HelpdeskSource
  activeOnly?: boolean
  assigned?: boolean
  q?: string
  limit?: number
  offset?: number
}

export interface HelpdeskMyListParams {
  status?: HelpdeskStatus
  /** Только неназначенные (без агента) — блок «ожидают принятия». */
  unassigned?: boolean
  /** Только назначенные (с агентом) — блок «в работе у специалиста». */
  assigned?: boolean
  /** Только активные (new/open/pending) — закрытые скрыты (они в архиве
   *  заявителя). Игнорируется, если задан ``status`` (он точнее). */
  activeOnly?: boolean
  limit?: number
  offset?: number
}

/** Лёгкий ответ ``GET /tickets/my/counts`` и ``GET /tickets/counts`` — для бейджей в меню. */
export interface HelpdeskTicketCounts {
  /** Активные тикеты (new/open/pending, без closed). У заявителя — свои;
   *  у агента — назначенные ему. */
  active: number
}

export function fetchMyTickets(params: HelpdeskMyListParams = {}): Promise<HelpdeskTicketList> {
  // activeOnly (camelCase) → active_only (snake_case для бэкенд Query), как в
  // fetchAgentTickets.
  const { activeOnly, ...rest } = params
  const query: Record<string, unknown> = { ...rest }
  if (activeOnly) query.active_only = true
  return api<HelpdeskTicketList>('/helpdesk/tickets/my', { params: query })
}

/** Счётчик своих открытых тикетов (new/open/pending) — для бейджа в меню. */
export function fetchMyTicketCounts(): Promise<HelpdeskTicketCounts> {
  return api<HelpdeskTicketCounts>('/helpdesk/tickets/my/counts')
}

export function fetchMyTicket(id: string): Promise<HelpdeskTicketDetail> {
  return api<HelpdeskTicketDetail>(`/helpdesk/tickets/my/${id}`)
}

export function fetchAgentTickets(params: HelpdeskInboxParams = {}): Promise<HelpdeskTicketList> {
  // activeOnly (camelCase) → active_only (snake_case для бэкенд Query).
  const { activeOnly, ...rest } = params
  const query: Record<string, unknown> = { ...rest }
  if (activeOnly) query.active_only = true
  return api<HelpdeskTicketList>('/helpdesk/tickets', { params: query })
}

/** Счётчик тикетов, назначенных агенту (new/open/pending) — для бейджа в меню. */
export function fetchAgentTicketCounts(): Promise<HelpdeskTicketCounts> {
  return api<HelpdeskTicketCounts>('/helpdesk/tickets/counts')
}

export function fetchAgentTicket(id: string): Promise<HelpdeskTicketDetail> {
  return api<HelpdeskTicketDetail>(`/helpdesk/tickets/${id}`)
}

export interface HelpdeskTicketCreateDto {
  subject: string
  description: string
  /** HTML из rich-редактора (TipTap). Опционально — бэк sanitize'ит (nh3) и
   *  деривирует plain из него, если ``description`` пуст. */
  description_html?: string
}

/** Создание заявки (multipart/form-data с вложениями). */
export function createMyTicket(dto: HelpdeskTicketCreateDto, files: File[] = []): Promise<HelpdeskTicketDetail> {
  const fd = new FormData()
  fd.append('subject', dto.subject)
  fd.append('description', dto.description)
  if (dto.description_html) fd.append('description_html', dto.description_html)
  for (const f of files) fd.append('files', f, f.name)
  return apiUpload<HelpdeskTicketDetail>('/helpdesk/tickets', fd)
}

export interface HelpdeskMessageCreateDto {
  /** Plain-текст (опционально — бэк деривит из body_html, если пуст). */
  body_text?: string
  /** HTML из rich-редактора (TipTap). Основной формат хранения. */
  body_html?: string | null
  visibility?: HelpdeskVisibility
  /**
   * Cc — адресаты в копии (только для агентского ответа, «Ответить всем»,
   * миграция 083). Массив голых email'ов; бэк нормализует (lowercase, дедуп,
   * отсечение support_address/агента/requester). Лимит 20 (422 свыше).
   */
  cc?: string[]
}

/** Ответ инициатора по своему тикету (multipart с вложениями). */
export function replyMyTicket(
  id: string,
  dto: HelpdeskMessageCreateDto,
  files: File[] = [],
): Promise<HelpdeskMessage> {
  const fd = new FormData()
  if (dto.body_text != null) fd.append('body_text', dto.body_text)
  if (dto.body_html != null) fd.append('body_html', dto.body_html)
  for (const f of files) fd.append('files', f, f.name)
  return apiUpload<HelpdeskMessage>(`/helpdesk/tickets/my/${id}/messages`, fd)
}

/** Ответ агента (multipart с вложениями). */
export function replyAgentTicket(
  id: string,
  dto: HelpdeskMessageCreateDto,
  files: File[] = [],
): Promise<HelpdeskMessage> {
  const fd = new FormData()
  if (dto.body_text != null) fd.append('body_text', dto.body_text)
  if (dto.body_html != null) fd.append('body_html', dto.body_html)
  if (dto.visibility) fd.append('visibility', dto.visibility)
  // Cc — повторяющееся Form-поле (``cc=a@x&cc=b@y``), миграция 083. Бэк
  // нормализует: выкидывает support_address/агента/requester, дедуп, лимит 20.
  for (const email of dto.cc ?? []) fd.append('cc', email)
  for (const f of files) fd.append('files', f, f.name)
  return apiUpload<HelpdeskMessage>(`/helpdesk/tickets/${id}/messages`, fd)
}

export function assignTicket(id: string, assigneeUserId: string): Promise<HelpdeskTicketDetail> {
  return api<HelpdeskTicketDetail>(`/helpdesk/tickets/${id}/assign`, {
    method: 'POST',
    body: { assignee_user_id: assigneeUserId },
  })
}

export function takeTicket(id: string): Promise<HelpdeskTicketDetail> {
  return api<HelpdeskTicketDetail>(`/helpdesk/tickets/${id}/take`, { method: 'POST' })
}

export function changeTicketStatus(
  id: string,
  status: 'open' | 'pending' | 'closed',
): Promise<HelpdeskTicketDetail> {
  return api<HelpdeskTicketDetail>(`/helpdesk/tickets/${id}/status`, {
    method: 'PATCH',
    body: { status },
  })
}

export function reopenTicket(id: string): Promise<HelpdeskTicketDetail> {
  return api<HelpdeskTicketDetail>(`/helpdesk/tickets/${id}/reopen`, { method: 'POST' })
}

/**
 * Отметить тикет прочитанным (снять подсветку в инбоксе агента).
 * Вызывается карточкой тикета при открытии — UPSERT ``last_seen_at = NOW()``
 * для пары ``(ticket, agent)``. Идемпотентно: повторное открытие = no-op.
 */
export function markTicketRead(id: string): Promise<void> {
  return api<void>(`/helpdesk/tickets/${id}/read`, { method: 'POST' })
}

/**
 * Заявительский аналог ``markTicketRead`` — отметить свой тикет прочитанным.
 * Снимает подсветку в «Мои заявки»: после открытия карточки заявителем ответы
 * агентов больше не подсвечиваются как непрочитанные. Вызывается карточкой
 * ``HelpdeskMyTicketDetailPage`` при открытии (best-effort).
 */
export function markMyTicketRead(id: string): Promise<void> {
  return api<void>(`/helpdesk/tickets/my/${id}/read`, { method: 'POST' })
}

/** URL скачивания вложения (anchor с target=_blank, как в feedback). */
export function helpdeskAttachmentUrl(id: string): string {
  return `/api/v1/helpdesk/attachments/${id}`
}

// ── Agents ────────────────────────────────────────────────────────────────

export interface HelpdeskAgent {
  user_id: string
  notify_new: boolean
  added_at: string
  user_name: string | null
  user_email: string | null
}

export interface HelpdeskAgentList {
  items: HelpdeskAgent[]
  total: number
}

export interface HelpdeskAgentIn {
  user_id: string
  notify_new?: boolean
}

// Компактный пункт списка смены ответственного: user_id + ФИО + email.
// Без флагов уведомлений (PII-минимизация) — агенту для смены ответственного
// достаточно знать, кому можно передать заявку. На фронте рендерится простым
// списком в popover (без поиска — агентов поддержки обычно ~5 человек).
export interface HelpdeskAgentOption {
  user_id: string
  full_name: string | null
  email: string
}

export interface HelpdeskAgentOptionList {
  items: HelpdeskAgentOption[]
  total: number
}

export function fetchHelpdeskAgents(): Promise<HelpdeskAgentList> {
  return api<HelpdeskAgentList>('/helpdesk/agents')
}

export function addHelpdeskAgent(dto: HelpdeskAgentIn): Promise<HelpdeskAgent> {
  return api<HelpdeskAgent>('/helpdesk/agents', { method: 'POST', body: dto })
}

export function updateHelpdeskAgent(
  userId: string,
  dto: HelpdeskAgentIn,
): Promise<HelpdeskAgent> {
  return api<HelpdeskAgent>(`/helpdesk/agents/${userId}`, {
    method: 'PATCH',
    body: dto,
  })
}

export function deleteHelpdeskAgent(userId: string): Promise<void> {
  return api<void>(`/helpdesk/agents/${userId}`, { method: 'DELETE' })
}

// Список активных helpdesk-агентов для смены ответственного в карточке тикета
// (агентский endpoint, доступ — любой helpdesk-агент/админ). Возвращает компактные
// пункты без флагов уведомлений. На фронте рендерится простым списком в popover.
export function fetchAssignableAgents(): Promise<HelpdeskAgentOptionList> {
  return api<HelpdeskAgentOptionList>('/helpdesk/tickets/assignable-agents')
}

// ── Mailbox settings ──────────────────────────────────────────────────────

export interface HelpdeskMailboxSettingsOut {
  configured: boolean
  imap_host: string | null
  imap_port: number
  imap_username: string | null
  imap_password_set: boolean
  imap_use_ssl: boolean
  imap_folder: string
  poll_interval_seconds: number
  delete_after_fetch: boolean
  support_address: string | null
  support_reply_to: string | null
  updated_at: string | null
}

export interface HelpdeskMailboxSettingsIn {
  imap_host: string
  imap_port?: number
  imap_username: string
  imap_password?: string | null
  imap_use_ssl?: boolean
  imap_folder?: string
  poll_interval_seconds?: number
  delete_after_fetch?: boolean
  support_address: string
  support_reply_to?: string | null
}

export interface HelpdeskMailboxTestResult {
  ok: boolean
  detail?: string
  error?: string
}

export function fetchHelpdeskMailbox(): Promise<HelpdeskMailboxSettingsOut> {
  return api<HelpdeskMailboxSettingsOut>('/helpdesk/settings/mailbox')
}

export function putHelpdeskMailbox(
  dto: HelpdeskMailboxSettingsIn,
): Promise<HelpdeskMailboxSettingsOut> {
  return api<HelpdeskMailboxSettingsOut>('/helpdesk/settings/mailbox', {
    method: 'PUT',
    body: dto,
  })
}

export function testHelpdeskMailbox(): Promise<HelpdeskMailboxTestResult> {
  return api<HelpdeskMailboxTestResult>('/helpdesk/settings/mailbox/test', {
    method: 'POST',
  })
}

// ── MAX-messenger bot settings ─────────────────────────────────────────────

export interface HelpdeskMaxBotSettingsOut {
  /** ``true`` когда канал готов отправлять: enabled AND bot_token_set AND chat_id. */
  configured: boolean
  enabled: boolean
  bot_token_set: boolean
  chat_id: string | null
  updated_at: string | null
}

export interface HelpdeskMaxBotSettingsIn {
  enabled: boolean
  /** Write-only: пусто/undefined = «оставить прежний шифр». */
  bot_token?: string | null
  chat_id?: string | null
}

export interface HelpdeskMaxBotTestResult {
  ok: boolean
  detail?: string | null
  error?: string | null
}

export function fetchHelpdeskMaxBot(): Promise<HelpdeskMaxBotSettingsOut> {
  return api<HelpdeskMaxBotSettingsOut>('/helpdesk/settings/max-bot')
}

export function putHelpdeskMaxBot(
  dto: HelpdeskMaxBotSettingsIn,
): Promise<HelpdeskMaxBotSettingsOut> {
  return api<HelpdeskMaxBotSettingsOut>('/helpdesk/settings/max-bot', {
    method: 'PUT',
    body: dto,
  })
}

export function testHelpdeskMaxBot(): Promise<HelpdeskMaxBotTestResult> {
  return api<HelpdeskMaxBotTestResult>('/helpdesk/settings/max-bot/test', {
    method: 'POST',
  })
}
