import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { queryKeys } from './keys'
import {
  type HelpdeskAgentIn,
  type HelpdeskInboxParams,
  type HelpdeskMailboxSettingsIn,
  type HelpdeskMessageCreateDto,
  type HelpdeskMyListParams,
  type HelpdeskTicketCreateDto,
  addHelpdeskAgent,
  assignTicket,
  changeTicketStatus,
  createMyTicket,
  deleteHelpdeskAgent,
  fetchAgentTicket,
  fetchAgentTickets,
  fetchHelpdeskAgents,
  fetchHelpdeskMailbox,
  fetchMyTicket,
  fetchMyTickets,
  putHelpdeskMailbox,
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

// ── Tickets: requester (my) ────────────────────────────────────────────────

export function useMyTicketsQuery(params: HelpdeskMyListParams = {}) {
  return useQuery({
    queryKey: queryKeys.helpdesk.myTickets(params as Record<string, unknown>),
    queryFn: () => fetchMyTickets(params),
    staleTime: 0,
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
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.helpdesk.myTickets() }),
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
    },
  })
}

export function useChangeTicketStatusMutation(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (status: 'open' | 'pending' | 'resolved' | 'closed') =>
      changeTicketStatus(id, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.agentTicket(id) })
      qc.invalidateQueries({ queryKey: queryKeys.helpdesk.inbox() })
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
    },
  })
}

