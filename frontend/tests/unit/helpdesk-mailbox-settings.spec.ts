/**
 * Unit-тесты HelpdeskMailboxSettings.vue — форма настроек mailbox-ингресса.
 *
 * Покрытие:
 * - watch(data) инициализирует форму: отсутствующие smtp_host/smtp_username
 *   (опциональные поля схемы) → null, а не undefined
 * - заполненные smtp_host/smtp_username пробрасываются в форму как есть
 * - write-only пароли никогда не предзаполняются (imap/smtp → null)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

const { useQueryMock, useMutationMock, queryClientMock, messageMock } = vi.hoisted(() => ({
  useQueryMock: vi.fn(),
  useMutationMock: vi.fn(),
  queryClientMock: { invalidateQueries: vi.fn().mockResolvedValue(undefined) },
  messageMock: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

vi.mock('@tanstack/vue-query', () => ({
  useQuery: useQueryMock,
  useMutation: useMutationMock,
  useQueryClient: () => queryClientMock,
}))

vi.mock('naive-ui', () => ({
  NSpin: { template: '<div class="n-spin"><slot /></div>', props: ['show'] },
  NForm: { template: '<form><slot /></form>', props: ['labelPlacement', 'showFeedback'] },
  NFormItem: { template: '<div class="n-form-item"><slot /></div>', props: ['label'] },
  NInput: {
    template: '<input class="n-input" :value="value" />',
    props: ['value', 'type', 'placeholder', 'autocomplete', 'showPasswordOn', 'inputProps'],
  },
  NInputNumber: {
    template: '<input type="number" :value="value" />',
    props: ['value', 'min', 'max'],
  },
  NCheckbox: {
    template: '<input type="checkbox" :checked="checked" />',
    props: ['checked'],
  },
  NButton: {
    template: '<button :disabled="disabled"><slot /></button>',
    props: ['type', 'disabled', 'loading'],
  },
  useMessage: () => messageMock,
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

import HelpdeskMailboxSettings from '../../src/components/admin/HelpdeskMailboxSettings.vue'

/** Валидный HelpdeskMailboxSettingsOut БЕЗ опциональных smtp-полей. */
const MAILBOX_OUT = {
  configured: true,
  imap_host: 'imap.company.local',
  imap_port: 993,
  imap_username: 'support@company.local',
  imap_password_set: true,
  imap_use_ssl: true,
  imap_folder: 'INBOX',
  poll_interval_seconds: 60,
  delete_after_fetch: false,
  support_address: 'support@company.local',
  support_reply_to: null,
  smtp_port: 25,
  smtp_password_set: false,
  smtp_use_tls: false,
  smtp_use_starttls: false,
}

function setupMailbox(out: object | undefined) {
  useQueryMock.mockReturnValue({ data: ref(out), isLoading: ref(false) })
  const mutateAsync = vi.fn().mockResolvedValue(undefined)
  useMutationMock.mockReturnValue({ mutateAsync, isPending: ref(false) })
  return mutateAsync
}

describe('HelpdeskMailboxSettings.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('отсутствующие smtp_host/smtp_username инициализируются как null', async () => {
    setupMailbox({ ...MAILBOX_OUT })
    const wrapper = mount(HelpdeskMailboxSettings)
    await new Promise((r) => setTimeout(r, 0))

    const form = (wrapper.vm as any).form
    expect(form).toBeTruthy()
    expect(form.smtp_host).toBeNull()
    expect(form.smtp_username).toBeNull()
    // Остальные smtp-поля — из ответа.
    expect(form.smtp_port).toBe(25)
    expect(form.imap_host).toBe('imap.company.local')
  })

  it('заполненные smtp_host/smtp_username попадают в форму', async () => {
    setupMailbox({
      ...MAILBOX_OUT,
      smtp_host: 'smtp.company.local',
      smtp_username: 'noreply@company.local',
    })
    const wrapper = mount(HelpdeskMailboxSettings)
    await new Promise((r) => setTimeout(r, 0))

    const form = (wrapper.vm as any).form
    expect(form.smtp_host).toBe('smtp.company.local')
    expect(form.smtp_username).toBe('noreply@company.local')
  })

  it('write-only пароли никогда не предзаполняются', async () => {
    setupMailbox({ ...MAILBOX_OUT, smtp_host: 'smtp.company.local', smtp_username: 'noreply' })
    const wrapper = mount(HelpdeskMailboxSettings)
    await new Promise((r) => setTimeout(r, 0))

    const form = (wrapper.vm as any).form
    expect(form.imap_password).toBeNull()
    expect(form.smtp_password).toBeNull()
  })
})
