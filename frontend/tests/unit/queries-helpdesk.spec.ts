import { describe, it, expect, vi, beforeEach } from 'vitest'

// ── Mocks для всех API-клиентов helpdesk ───────────────────────────────────
const mockFetchHelpdeskAgents = vi.fn()
const mockFetchHelpdeskMailbox = vi.fn()
const mockAddHelpdeskAgent = vi.fn()
const mockUpdateHelpdeskAgent = vi.fn()
const mockDeleteHelpdeskAgent = vi.fn()
const mockPutHelpdeskMailbox = vi.fn()
const mockFetchHelpdeskMaxBot = vi.fn()
const mockPutHelpdeskMaxBot = vi.fn()
const mockFetchMyTickets = vi.fn()
const mockFetchMyTicket = vi.fn()
const mockCreateMyTicket = vi.fn()
const mockReplyMyTicket = vi.fn()
const mockFetchAgentTickets = vi.fn()
const mockFetchAgentTicket = vi.fn()
const mockReplyAgentTicket = vi.fn()
const mockAssignTicket = vi.fn()
const mockTakeTicket = vi.fn()
const mockChangeTicketStatus = vi.fn()
const mockReopenTicket = vi.fn()

vi.mock('../../src/api/helpdesk', () => ({
  fetchHelpdeskAgents: mockFetchHelpdeskAgents,
  fetchHelpdeskMailbox: mockFetchHelpdeskMailbox,
  addHelpdeskAgent: mockAddHelpdeskAgent,
  updateHelpdeskAgent: mockUpdateHelpdeskAgent,
  deleteHelpdeskAgent: mockDeleteHelpdeskAgent,
  putHelpdeskMailbox: mockPutHelpdeskMailbox,
  fetchHelpdeskMaxBot: mockFetchHelpdeskMaxBot,
  putHelpdeskMaxBot: mockPutHelpdeskMaxBot,
  fetchMyTickets: mockFetchMyTickets,
  fetchMyTicket: mockFetchMyTicket,
  createMyTicket: mockCreateMyTicket,
  replyMyTicket: mockReplyMyTicket,
  fetchAgentTickets: mockFetchAgentTickets,
  fetchAgentTicket: mockFetchAgentTicket,
  replyAgentTicket: mockReplyAgentTicket,
  assignTicket: mockAssignTicket,
  takeTicket: mockTakeTicket,
  changeTicketStatus: mockChangeTicketStatus,
  reopenTicket: mockReopenTicket,
}))

// ── Mock @tanstack/vue-query: захват queryFn/mutationFn для проверки ─────────
const capturedQueries: any[] = []
const capturedMutations: any[] = []
const mockInvalidate = vi.fn()

vi.mock('@tanstack/vue-query', () => ({
  useQuery: vi.fn((opts: any) => {
    capturedQueries.push(opts)
    return { data: { value: undefined }, isLoading: { value: false } }
  }),
  useMutation: vi.fn((opts: any) => {
    capturedMutations.push(opts)
    return { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: { value: false } }
  }),
  useQueryClient: vi.fn(() => ({ invalidateQueries: mockInvalidate })),
}))

describe('src/queries/helpdesk', () => {
  beforeEach(() => {
    capturedQueries.length = 0
    capturedMutations.length = 0
    vi.clearAllMocks()
  })

  // ── Admin: agents + mailbox ──────────────────────────────────────────────
  it('useHelpdeskAgentsQuery registers query and calls fetchHelpdeskAgents', async () => {
    const { useHelpdeskAgentsQuery } = await import('../../src/queries/helpdesk')
    useHelpdeskAgentsQuery()
    expect(capturedQueries).toHaveLength(1)
    mockFetchHelpdeskAgents.mockResolvedValueOnce({ items: [], total: 0 })
    await capturedQueries[0].queryFn()
    expect(mockFetchHelpdeskAgents).toHaveBeenCalledWith()
  })

  it('useHelpdeskMailboxQuery registers query and calls fetchHelpdeskMailbox', async () => {
    const { useHelpdeskMailboxQuery } = await import('../../src/queries/helpdesk')
    useHelpdeskMailboxQuery()
    mockFetchHelpdeskMailbox.mockResolvedValueOnce({})
    await capturedQueries[0].queryFn()
    expect(mockFetchHelpdeskMailbox).toHaveBeenCalledWith()
  })

  it('useAddHelpdeskAgentMutation calls addHelpdeskAgent and invalidates', async () => {
    const { useAddHelpdeskAgentMutation } = await import('../../src/queries/helpdesk')
    useAddHelpdeskAgentMutation()
    const m = capturedMutations[capturedMutations.length - 1]
    mockAddHelpdeskAgent.mockResolvedValueOnce({})
    await m.mutationFn({ user_id: 'u1' })
    expect(mockAddHelpdeskAgent).toHaveBeenCalledWith({ user_id: 'u1' })
    await m.onSuccess()
    expect(mockInvalidate).toHaveBeenCalled()
  })

  it('useUpdateHelpdeskAgentMutation calls updateHelpdeskAgent with userId+dto', async () => {
    const { useUpdateHelpdeskAgentMutation } = await import('../../src/queries/helpdesk')
    useUpdateHelpdeskAgentMutation()
    const m = capturedMutations[capturedMutations.length - 1]
    mockUpdateHelpdeskAgent.mockResolvedValueOnce({})
    await m.mutationFn({ userId: 'u1', dto: { user_id: 'u1', notify_new: false } })
    expect(mockUpdateHelpdeskAgent).toHaveBeenCalledWith('u1', { user_id: 'u1', notify_new: false })
    await m.onSuccess()
    expect(mockInvalidate).toHaveBeenCalled()
  })

  it('useDeleteHelpdeskAgentMutation calls deleteHelpdeskAgent', async () => {
    const { useDeleteHelpdeskAgentMutation } = await import('../../src/queries/helpdesk')
    useDeleteHelpdeskAgentMutation()
    const m = capturedMutations[capturedMutations.length - 1]
    mockDeleteHelpdeskAgent.mockResolvedValueOnce(undefined)
    await m.mutationFn('u1')
    expect(mockDeleteHelpdeskAgent).toHaveBeenCalledWith('u1')
    await m.onSuccess()
    expect(mockInvalidate).toHaveBeenCalled()
  })

  it('usePutHelpdeskMailboxMutation calls putHelpdeskMailbox', async () => {
    const { usePutHelpdeskMailboxMutation } = await import('../../src/queries/helpdesk')
    usePutHelpdeskMailboxMutation()
    const m = capturedMutations[capturedMutations.length - 1]
    mockPutHelpdeskMailbox.mockResolvedValueOnce({})
    const dto = { imap_host: 'h', imap_username: 'u', support_address: 'a@b.c' }
    await m.mutationFn(dto)
    expect(mockPutHelpdeskMailbox).toHaveBeenCalledWith(dto)
    await m.onSuccess()
    expect(mockInvalidate).toHaveBeenCalled()
  })

  // ── Requester (my) tickets ───────────────────────────────────────────────
  it('useMyTicketsQuery passes params to fetchMyTickets', async () => {
    const { useMyTicketsQuery } = await import('../../src/queries/helpdesk')
    useMyTicketsQuery({ status: 'open', limit: 10 })
    mockFetchMyTickets.mockResolvedValueOnce({ items: [], total: 0 })
    await capturedQueries[0].queryFn()
    expect(mockFetchMyTickets).toHaveBeenCalledWith({ status: 'open', limit: 10 })
  })

  it('useMyTicketsQuery defaults to empty params', async () => {
    const { useMyTicketsQuery } = await import('../../src/queries/helpdesk')
    useMyTicketsQuery()
    mockFetchMyTickets.mockResolvedValueOnce({ items: [], total: 0 })
    await capturedQueries[0].queryFn()
    expect(mockFetchMyTickets).toHaveBeenCalledWith({})
  })

  it('useMyTicketQuery calls fetchMyTicket with id', async () => {
    const { useMyTicketQuery } = await import('../../src/queries/helpdesk')
    useMyTicketQuery('t1')
    mockFetchMyTicket.mockResolvedValueOnce({})
    await capturedQueries[0].queryFn()
    expect(mockFetchMyTicket).toHaveBeenCalledWith('t1')
  })

  it('useCreateMyTicketMutation calls createMyTicket with dto+files', async () => {
    const { useCreateMyTicketMutation } = await import('../../src/queries/helpdesk')
    useCreateMyTicketMutation()
    const m = capturedMutations[capturedMutations.length - 1]
    mockCreateMyTicket.mockResolvedValueOnce({})
    const dto = { subject: 's', description: 'd' }
    const files = [new File(['x'], 'f.txt')]
    await m.mutationFn({ dto, files })
    expect(mockCreateMyTicket).toHaveBeenCalledWith(dto, files)
    await m.onSuccess()
    expect(mockInvalidate).toHaveBeenCalled()
  })

  it('useCreateMyTicketMutation passes description_html through dto (rich editor)', async () => {
    // Rich-редактор при создании: dto несёт description_html (TipTap → HTML).
    // Проверяем, что мутация прокидывает его в createMyTicket как есть.
    const { useCreateMyTicketMutation } = await import('../../src/queries/helpdesk')
    useCreateMyTicketMutation()
    const m = capturedMutations[capturedMutations.length - 1]
    mockCreateMyTicket.mockResolvedValueOnce({})
    const dto = {
      subject: 's',
      description: '# Тема\nтекст',
      description_html: '<h1>Тема</h1>\n<p>текст</p>',
    }
    await m.mutationFn({ dto, files: [] })
    expect(mockCreateMyTicket).toHaveBeenCalledWith(dto, [])
  })

  it('useReplyMyTicketMutation calls replyMyTicket with id+dto+files', async () => {
    const { useReplyMyTicketMutation } = await import('../../src/queries/helpdesk')
    useReplyMyTicketMutation('t1')
    const m = capturedMutations[capturedMutations.length - 1]
    mockReplyMyTicket.mockResolvedValueOnce({})
    const dto = { body_text: 'b' }
    const files: File[] = []
    await m.mutationFn({ dto, files })
    expect(mockReplyMyTicket).toHaveBeenCalledWith('t1', dto, files)
    await m.onSuccess()
    expect(mockInvalidate).toHaveBeenCalled()
  })

  // ── Agent inbox ──────────────────────────────────────────────────────────
  it('useAgentInboxQuery passes params to fetchAgentTickets', async () => {
    const { useAgentInboxQuery } = await import('../../src/queries/helpdesk')
    useAgentInboxQuery({ status: 'open', unassigned: true })
    mockFetchAgentTickets.mockResolvedValueOnce({ items: [], total: 0 })
    await capturedQueries[0].queryFn()
    expect(mockFetchAgentTickets).toHaveBeenCalledWith({ status: 'open', unassigned: true })
  })

  it('useAgentTicketQuery calls fetchAgentTicket with id', async () => {
    const { useAgentTicketQuery } = await import('../../src/queries/helpdesk')
    useAgentTicketQuery('t1')
    mockFetchAgentTicket.mockResolvedValueOnce({})
    await capturedQueries[0].queryFn()
    expect(mockFetchAgentTicket).toHaveBeenCalledWith('t1')
  })

  it('useReplyAgentTicketMutation calls replyAgentTicket', async () => {
    const { useReplyAgentTicketMutation } = await import('../../src/queries/helpdesk')
    useReplyAgentTicketMutation('t1')
    const m = capturedMutations[capturedMutations.length - 1]
    mockReplyAgentTicket.mockResolvedValueOnce({})
    const dto = { body_text: 'b', visibility: 'public' as const }
    await m.mutationFn({ dto, files: [] })
    expect(mockReplyAgentTicket).toHaveBeenCalledWith('t1', dto, [])
    await m.onSuccess()
    expect(mockInvalidate).toHaveBeenCalled()
  })

  it('useAssignTicketMutation calls assignTicket', async () => {
    const { useAssignTicketMutation } = await import('../../src/queries/helpdesk')
    useAssignTicketMutation('t1')
    const m = capturedMutations[capturedMutations.length - 1]
    mockAssignTicket.mockResolvedValueOnce({})
    await m.mutationFn('u1')
    expect(mockAssignTicket).toHaveBeenCalledWith('t1', 'u1')
    await m.onSuccess()
    expect(mockInvalidate).toHaveBeenCalled()
  })

  it('useTakeTicketMutation calls takeTicket', async () => {
    const { useTakeTicketMutation } = await import('../../src/queries/helpdesk')
    useTakeTicketMutation('t1')
    const m = capturedMutations[capturedMutations.length - 1]
    mockTakeTicket.mockResolvedValueOnce({})
    await m.mutationFn()
    expect(mockTakeTicket).toHaveBeenCalledWith('t1')
    await m.onSuccess()
    expect(mockInvalidate).toHaveBeenCalled()
  })

  it('useChangeTicketStatusMutation calls changeTicketStatus', async () => {
    const { useChangeTicketStatusMutation } = await import('../../src/queries/helpdesk')
    useChangeTicketStatusMutation('t1')
    const m = capturedMutations[capturedMutations.length - 1]
    mockChangeTicketStatus.mockResolvedValueOnce({})
    await m.mutationFn('resolved')
    expect(mockChangeTicketStatus).toHaveBeenCalledWith('t1', 'resolved')
    await m.onSuccess()
    expect(mockInvalidate).toHaveBeenCalled()
  })

  it('useReopenTicketMutation calls reopenTicket', async () => {
    const { useReopenTicketMutation } = await import('../../src/queries/helpdesk')
    useReopenTicketMutation('t1')
    const m = capturedMutations[capturedMutations.length - 1]
    mockReopenTicket.mockResolvedValueOnce({})
    await m.mutationFn()
    expect(mockReopenTicket).toHaveBeenCalledWith('t1')
    await m.onSuccess()
    expect(mockInvalidate).toHaveBeenCalled()
  })

  // ── MAX-messenger bot ─────────────────────────────────────────────────────
  it('useHelpdeskMaxBotQuery registers query and calls fetchHelpdeskMaxBot', async () => {
    const { useHelpdeskMaxBotQuery } = await import('../../src/queries/helpdesk')
    useHelpdeskMaxBotQuery()
    mockFetchHelpdeskMaxBot.mockResolvedValueOnce({})
    await capturedQueries[capturedQueries.length - 1].queryFn()
    expect(mockFetchHelpdeskMaxBot).toHaveBeenCalledWith()
  })

  it('usePutHelpdeskMaxBotMutation calls putHelpdeskMaxBot and invalidates', async () => {
    const { usePutHelpdeskMaxBotMutation } = await import('../../src/queries/helpdesk')
    usePutHelpdeskMaxBotMutation()
    const m = capturedMutations[capturedMutations.length - 1]
    mockPutHelpdeskMaxBot.mockResolvedValueOnce({})
    const dto = { enabled: true, chat_id: '100', bot_token: 'tok' }
    await m.mutationFn(dto)
    expect(mockPutHelpdeskMaxBot).toHaveBeenCalledWith(dto)
    await m.onSuccess()
    expect(mockInvalidate).toHaveBeenCalled()
  })
})
