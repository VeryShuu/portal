import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import type { MaybeRef } from 'vue'
import { queryKeys } from './keys'
import {
  type HelpdeskAgentIn,
  type HelpdeskInboxParams,
  type HelpdeskMailboxSettingsIn,
  type HelpdeskMaxBotSettingsIn,
  type HelpdeskMessageCreateDto,
  type HelpdeskMyListParams,
  type HelpdeskTicketCreateDto,
  addHelpdeskAgent,
  assignTicket,
  changeTicketStatus,
  createMyTicket,
  deleteHelpdeskAgent,
  fetchAgentTicket,
  fetchAgentTicketCounts,
  fetchAgentTickets,
  fetchAssignableAgents,
  fetchHelpdeskAgents,
  fetchHelpdeskMailbox,
  fetchHelpdeskMaxBot,
  fetchMyTicket,
  fetchMyTicketCounts,
  fetchMyTickets,
  putHelpdeskMailbox,
  putHelpdeskMaxBot,
  reopenTicket,
  replyAgentTicket,
  replyMyTicket,
  takeTicket,
  updateHelpdeskAgent,
} from '../api/helpdesk'

export function useHelpdeskAgentsQuery() {
  return useQuery({
    queryKey: queryKeys.helpdesk.agents(),
    queryFn: () => fetchHelpdeskAgents(),
    staleTime: 30_000,
  })
}

// Список активных helpdesk-агентов для списка смены ответственного в карточке
// тикета (рендерится простым списком в popover — без поиска, т.к. агентов
// поддержки обычно ~5 человек). Доступ — любой helpdesk-агент (не admin-only).
// ``enabled`` принимает реактивный ``Ref<boolean>`` — карточка тикета активирует
// запрос только при открытии popover'а смены (большинство открытий карточки —
// для ответа, а не смены ответственного, и лишний JOIN users на каждый просмотр
// не нужен). ``staleTime`` 60 c — состав агентов меняется редко, повторные
// открытия в течение минуты берут кеш.
export function useAssignableAgentsQuery(enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: queryKeys.helpdesk.assignableAgents(),
    queryFn: () => fetchAssignableAgents(),
    enabled,
    staleTime: 60_000,
  })
}

export function useHelpdeskMailboxQuery() {
  return useQuery({
    queryKey: queryKeys.helpdesk.mailbox(),
    queryFn: () => fetchHelpdeskMailbox(),
    staleTime: 30_000,
  })
}

export function useAddHelpdeskAgentMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (dto: HelpdeskAgentIn) => addHelpdeskAgent(dto),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agents() }),
  })
}

export function useUpdateHelpdeskAgentMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, dto }: { userId: string; dto: HelpdeskAgentIn }) =>
      updateHelpdeskAgent(userId, dto),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agents() }),
  })
}

export function useDeleteHelpdeskAgentMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => deleteHelpdeskAgent(userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agents() }),
  })
}

export function usePutHelpdeskMailboxMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (dto: HelpdeskMailboxSettingsIn) => putHelpdeskMailbox(dto),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.helpdesk.mailbox() }),
  })
}

// ── MAX-messenger bot settings ─────────────────────────────────────────────

export function useHelpdeskMaxBotQuery() {
  return useQuery({
    queryKey: queryKeys.helpdesk.maxBot(),
    queryFn: () => fetchHelpdeskMaxBot(),
    staleTime: 30_000,
  })
}

export function usePutHelpdeskMaxBotMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (dto: HelpdeskMaxBotSettingsIn) => putHelpdeskMaxBot(dto),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.helpdesk.maxBot() }),
  })
}

// ── Tickets: requester (my) ────────────────────────────────────────────────

export function useMyTicketsQuery(params: HelpdeskMyListParams = {}) {
  return useQuery({
    queryKey: queryKeys.helpdesk.myTickets(params as Record<string, unknown>),
    queryFn: () => fetchMyTickets(params),
    staleTime: 0,
  })
}

/**
 * Счётчик своих открытых тикетов (new/open/pending) — для бейджа в меню
 * пункта «Поддержка». Polling 60s + автообновление после мутаций (create/
 * reply/status/reopen инвалидируют ``myTicketCounts`` → мгновенный refetch).
 * ``refetchIntervalInBackground: false`` — не гоняем трафик в неактивной вкладке.
 *
 * ``enabled`` — для кондиционального отключения (например, при выключенном
 * модуле helpdesk меню не дёргает endpoint). Образец — useQuery-options в
 * @tanstack/vue-query: ``{ enabled: boolean }``.
 */
export function useMyTicketCountsQuery(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.helpdesk.myTicketCounts(),
    queryFn: () => fetchMyTicketCounts(),
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    enabled: options.enabled ?? true,
  })
}

export function useMyTicketQuery(id: string) {
  return useQuery({
    queryKey: queryKeys.helpdesk.myTicket(id),
    queryFn: () => fetchMyTicket(id),
    staleTime: 0,
  })
}

export function useCreateMyTicketMutation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ dto, files }: { dto: HelpdeskTicketCreateDto; files: File[] }) =>
      createMyTicket(dto, files),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.myTickets() })
      // Новый тикет → активный счётчик в меню вырос.
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.myTicketCounts() })
    },
  })
}

export function useReplyMyTicketMutation(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ dto, files }: { dto: HelpdeskMessageCreateDto; files: File[] }) =>
      replyMyTicket(id, dto, files),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.myTicket(id) })
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.myTickets() })
      // Ответ заявителя двигает last_activity, но статус не меняет — счётчик
      // активных не растёт. Однако агентский инбокс «в работе» может измениться
      // (assignee получил новый ответ), инвалидируем и его счётчик.
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agentTicketCounts() })
    },
  })
}

// ── Tickets: agent inbox ───────────────────────────────────────────────────

export function useAgentInboxQuery(params: HelpdeskInboxParams = {}) {
  return useQuery({
    queryKey: queryKeys.helpdesk.inbox(params as Record<string, unknown>),
    queryFn: () => fetchAgentTickets(params),
    staleTime: 0,
  })
}

/**
 * Счётчик тикетов, назначенных агенту (new/open/pending) — для бейджа в меню
 * пункта «Инбокс поддержки». Polling 60s + автообновление после мутаций
 * (assign/take/status/reopen инвалидируют ``agentTicketCounts`` → мгновенный
 * refetch). ``refetchIntervalInBackground: false`` — экономия в неактивной вкладке.
 *
 * ``enabled`` — для кондиционального отключения (например, не-агентом —
 * ``useAppMenu`` не дёргает agent-counts для обычных пользователей).
 */
export function useAgentTicketCountsQuery(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.helpdesk.agentTicketCounts(),
    queryFn: () => fetchAgentTicketCounts(),
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    enabled: options.enabled ?? true,
  })
}

export function useAgentTicketQuery(id: string) {
  return useQuery({
    queryKey: queryKeys.helpdesk.agentTicket(id),
    queryFn: () => fetchAgentTicket(id),
    staleTime: 0,
  })
}

export function useReplyAgentTicketMutation(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ dto, files }: { dto: HelpdeskMessageCreateDto; files: File[] }) =>
      replyAgentTicket(id, dto, files),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agentTicket(id) })
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.inbox() })
      // Ответ агента двигает last_activity, но статус остаётся активным — счётчик
      // назначенных не меняется. Инвалидируем заявительский счётчик (его тикет
      // обновился, но это не влияет на «открытые», только на unread — инвалидация
      // дешёвая, проще сделать единообразно).
    },
  })
}

export function useAssignTicketMutation(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (assigneeUserId: string) => assignTicket(id, assigneeUserId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agentTicket(id) })
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.inbox() })
      // Назначение меняет assignee → счётчик «моих назначенных» мог измениться.
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agentTicketCounts() })
    },
  })
}

export function useTakeTicketMutation(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => takeTicket(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agentTicket(id) })
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.inbox() })
      // Take = назначил на себя → счётчик «моих назначенных» вырос.
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agentTicketCounts() })
    },
  })
}

export function useChangeTicketStatusMutation(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (status: 'open' | 'pending' | 'closed') =>
      changeTicketStatus(id, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agentTicket(id) })
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.inbox() })
      // Смена статуса (особенно → closed) меняет счётчик активных у обеих сторон.
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agentTicketCounts() })
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.myTicketCounts() })
    },
  })
}

export function useReopenTicketMutation(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => reopenTicket(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agentTicket(id) })
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.inbox() })
      // Reopen возвращает тикет в активные → счётчики обеих сторон растут.
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agentTicketCounts() })
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.myTicketCounts() })
    },
  })
}

