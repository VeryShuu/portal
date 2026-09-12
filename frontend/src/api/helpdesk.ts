import { api, apiUpload } from './index'
import type { components } from './types.gen'

// ── Tickets (requester + agent) ────────────────────────────────────────────

export type HelpdeskStatus = components['schemas']['HelpdeskStatus']
export type HelpdeskSource = components['schemas']['HelpdeskSource']
export type HelpdeskDirection = components['schemas']['HelpdeskDirection']

/** Сообщение тикета — агентский/requester-view ``MessageOut``. */
export type HelpdeskMessage = components['schemas']['MessageOut']

/**
 * Адресат письма (Cc / участник тикета) — миграция 083 (``ParticipantOut``).
 * ``is_requester = true`` только в ``ticket.participants`` для автора заявки
 * (подсветка в блоке «Участники»).
 */
export type HelpdeskParticipant = components['schemas']['ParticipantOut']

/** Метаданные вложения сообщения (``AttachmentOut``); файл — отдельным endpoint. */
export type HelpdeskAttachmentMeta = components['schemas']['AttachmentOut']

/**
 * Компактная карточка тикета для списков (``TicketListItemOut``). ``unread``
 * — подсветка непрочитанных ответов второй стороны (миграция 080);
 * ``undefined``/``null`` — состояние неизвестно (не-агентские списки).
 */
export type HelpdeskTicketListItem = components['schemas']['TicketListItemOut']

/** Профиль заявителя из справочника сотрудников (``RequesterProfileOut``). */
export type HelpdeskRequesterProfile = components['schemas']['RequesterProfileOut']

export type HelpdeskTicketList = components['schemas']['TicketListOut']

/**
 * Деталь тикета — агентский view (``TicketAgentOut``), надмножество
 * requester-view (``TicketOut``): служебные поля ``assigned_at``/``closed_at``/
 * ``closed_by_user_id``/``references_archived_ticket_number`` и «Участники»
 * ``participants`` (миграция 083, только агентский ответ; requester-view поле
 * не содержит — PII-минимизация; источник для pre-fill «Ответить всем»).
 */
export type HelpdeskTicketDetail = components['schemas']['TicketAgentOut']

// ── Types not present in OpenAPI schema (фронтовые: наборы query-параметров) ──

export interface HelpdeskInboxParams {
  status?: HelpdeskStatus
  assignee?: string
  unassigned?: boolean
  source?: HelpdeskSource
  activeOnly?: boolean
  assigned?: boolean
  q?: string
  /** Поле серверной сортировки (number/status/requester/assignee/created_at/last_activity_at). */
  sort?: string
  /** Направление сортировки. */
  order?: 'asc' | 'desc'
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
  /** Поле серверной сортировки (number/status/requester/assignee/created_at/last_activity_at). */
  sort?: string
  /** Направление сортировки. */
  order?: 'asc' | 'desc'
  limit?: number
  offset?: number
}

/** Лёгкий ответ ``GET /tickets/my/counts`` и ``GET /tickets/counts`` (``TicketCountsOut``) — для бейджей в меню. */
export type HelpdeskTicketCounts = components['schemas']['TicketCountsOut']

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

// нет в OpenAPI — фронтовый тип (form-модель создания тикета; multipart
// собирается в ``createMyTicket``, ``files`` передаются отдельным аргументом
// ``File[]`` — в generated-``Body_create_ticket_...`` они отражены как ``string[]``).
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

// нет в OpenAPI — фронтовый тип (form-модель ответа; multipart собирается в
// ``replyMyTicket``/``replyAgentTicket``, ``files`` — отдельным аргументом).
export interface HelpdeskMessageCreateDto {
  /** Plain-текст (опционально — бэк деривит из body_html, если пуст). */
  body_text?: string
  /** HTML из rich-редактора (TipTap). Основной формат хранения. */
  body_html?: string | null
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
  status: components['schemas']['TicketStatusIn']['status'],
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
 * Полностью удалить заявку (hard-delete: БД + файлы вложений/inline-картинок).
 * Только администратор — бэкенд возвращает 403 для прочих ролей. Необратимая
 * операция (спам-очистка / GDPR), в отличие от ``close``/``reopen``. Возвращает
 * ``void`` (204 No Content); после вызова карточка тикета больше недоступна.
 */
export function deleteTicket(id: string): Promise<void> {
  return api<void>(`/helpdesk/tickets/${id}`, { method: 'DELETE' })
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

export type HelpdeskAgent = components['schemas']['AgentOut']
export type HelpdeskAgentList = components['schemas']['AgentListOut']
export type HelpdeskAgentIn = components['schemas']['AgentIn']

// Компактный пункт списка смены ответственного: user_id + ФИО + email
// (``AgentOptionOut``). Без флагов уведомлений (PII-минимизация) — агенту для
// смены ответственного достаточно знать, кому можно передать заявку. На фронте
// рендерится простым списком в popover (без поиска — агентов поддержки ~5).
export type HelpdeskAgentOption = components['schemas']['AgentOptionOut']
export type HelpdeskAgentOptionList = components['schemas']['AgentOptionListOut']

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

export type HelpdeskMailboxSettingsOut = components['schemas']['HelpdeskMailboxSettingsOut']
export type HelpdeskMailboxSettingsIn = components['schemas']['HelpdeskMailboxSettingsIn']

// нет в OpenAPI — фронтовый тип: ``POST /settings/mailbox/test`` и ``/test-smtp``
// возвращают untyped-``dict`` (без response_schema в OpenAPI).
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

export function testHelpdeskMailboxSmtp(): Promise<HelpdeskMailboxTestResult> {
  return api<HelpdeskMailboxTestResult>('/helpdesk/settings/mailbox/test-smtp', {
    method: 'POST',
  })
}

// ── MAX-messenger bot settings ─────────────────────────────────────────────

export type HelpdeskMaxBotSettingsOut = components['schemas']['HelpdeskMaxBotSettingsOut']
export type HelpdeskMaxBotSettingsIn = components['schemas']['HelpdeskMaxBotSettingsIn']
export type HelpdeskMaxBotTestResult = components['schemas']['HelpdeskMaxBotTestResult']

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

// ── Daily digest settings ───────────────────────────────────────────────────

export type HelpdeskDigestSchedule = components['schemas']['HelpdeskDigestSettingsOut']['digest_schedule']
export type HelpdeskDigestSettingsOut = components['schemas']['HelpdeskDigestSettingsOut']
export type HelpdeskDigestSettingsIn = components['schemas']['HelpdeskDigestSettingsIn']

export function fetchHelpdeskDigest(): Promise<HelpdeskDigestSettingsOut> {
  return api<HelpdeskDigestSettingsOut>('/helpdesk/settings/digest')
}

export function putHelpdeskDigest(
  dto: HelpdeskDigestSettingsIn,
): Promise<HelpdeskDigestSettingsOut> {
  return api<HelpdeskDigestSettingsOut>('/helpdesk/settings/digest', {
    method: 'PUT',
    body: dto,
  })
}

// ── User search (CC typeahead) ──────────────────────────────────────────────

/** Результат поиска пользователя для CC-селектора агента (``GET /users/search``). */
export type HelpdeskUserOption = components['schemas']['HelpdeskUserOption']

/**
 * Поиск пользователя по справочнику (Keycloak) для CC-селектора «Ответить всем».
 * ``<3 символов`` → пустой список (бэк отдаёт ``[]``, не 422 — чтобы не ломать
 * empty-state ``n-select``). Компонент ``CcRecipientPicker`` дёргает это при
 * вводе и сам добавляет synthetic «external»-опцию для email'ов не из справочника.
 */
export function searchHelpdeskUsers(q: string): Promise<HelpdeskUserOption[]> {
  return api<HelpdeskUserOption[]>('/helpdesk/users/search', { params: { q } })
}
