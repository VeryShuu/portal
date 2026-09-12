/**
 * Unit-тесты профиля: карточка настроек уведомлений (self) и админская
 * карточка чат-уведомлений (чужой профиль).
 *
 * Профиль: 3 переключателя (email/inapp — колонки, chat — preferences JSONB);
 * Save шлёт ОБА запроса (patchMyProfile + patchMyPreferences).
 * Админ: загрузка состояния + toggle → PATCH.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

const messageMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}))

const authMock = vi.hoisted(() => ({
  user: null as Record<string, unknown> | null,
  setUser: vi.fn(),
  isAdmin: false,
  isLocalUser: false,
}))

vi.mock('naive-ui', () => ({
  NForm: { template: '<form><slot /></form>' },
  NSwitch: {
    template: '<input class="n-switch" type="checkbox" :checked="value" :data-loading="loading" @change="$emit(\'update:value\', $event.target.checked)" />',
    props: ['value', 'loading', 'disabled'],
    emits: ['update:value'],
  },
  NButton: { template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>', props: ['size', 'type', 'disabled', 'loading'], emits: ['click'] },
  NSpin: { template: '<div class="n-spin"><slot /></div>', props: ['show'] },
  useMessage: () => messageMock,
}))

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => authMock,
}))

const usersApiMock = vi.hoisted(() => ({
  patchMyProfile: vi.fn(async () => ({})),
  patchMyPreferences: vi.fn(async () => ({})),
  fetchAdminNotificationPreferences: vi.fn(async () => ({ chat_notifications_enabled: false })),
  patchAdminNotificationPreferences: vi.fn(async () => ({ chat_notifications_enabled: true })),
}))

vi.mock('../../src/api/users', () => usersApiMock)
vi.mock('../../src/utils/parseApiError', () => ({
  parseApiError: () => 'Ошибка',
}))

import ProfilePreferencesCard from '../../src/components/profile/ProfilePreferencesCard.vue'
import AdminChatNotificationsCard from '../../src/components/profile/AdminChatNotificationsCard.vue'

function mountProfile() {
  return mount(ProfilePreferencesCard, { global: { plugins: [i18n] } })
}

describe('ProfilePreferencesCard (свой профиль)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authMock.user = {
      id: 'u1',
      notify_email: true,
      notify_inapp: false,
      preferences: { chat_notifications_enabled: true },
    }
  })

  it('chat-флаг читается из preferences JSONB', () => {
    const w = mountProfile()
    const switches = w.findAll('.n-switch')
    expect(switches).toHaveLength(3)
    // email=true, inapp=false, chat=true
    expect((switches[0].element as HTMLInputElement).checked).toBe(true)
    expect((switches[1].element as HTMLInputElement).checked).toBe(false)
    expect((switches[2].element as HTMLInputElement).checked).toBe(true)
  })

  it('chat выключен по умолчанию (opt-in) когда ключа нет', () => {
    authMock.user = { id: 'u1', notify_email: true, notify_inapp: true, preferences: {} }
    const w = mountProfile()
    expect((w.findAll('.n-switch')[2].element as HTMLInputElement).checked).toBe(false)
  })

  it('Save шлёт оба запроса: profile (колонки) + preferences (chat)', async () => {
    const w = mountProfile()
    await w.findAll('.n-switch')[2].setValue(false)
    await w.find('.n-button').trigger('click')
    await flushPromises()

    expect(usersApiMock.patchMyProfile).toHaveBeenCalledWith({
      notify_email: true,
      notify_inapp: false,
    })
    expect(usersApiMock.patchMyPreferences).toHaveBeenCalledWith({
      chat_notifications_enabled: false,
    })
    expect(authMock.setUser).toHaveBeenCalled()
    expect(messageMock.success).toHaveBeenCalled()
  })

  it('ошибка сохранения → message.error, setUser не вызывается', async () => {
    usersApiMock.patchMyProfile.mockRejectedValueOnce(new Error('boom'))
    const w = mountProfile()
    await w.find('.n-button').trigger('click')
    await flushPromises()
    expect(messageMock.error).toHaveBeenCalled()
    expect(authMock.setUser).not.toHaveBeenCalled()
  })
})

describe('AdminChatNotificationsCard (чужой профиль, admin)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('загружает состояние при монтировании', async () => {
    usersApiMock.fetchAdminNotificationPreferences.mockResolvedValueOnce({
      chat_notifications_enabled: true,
    })
    const w = mount(AdminChatNotificationsCard, {
      props: { userId: 'u2' },
      global: { plugins: [i18n] },
    })
    await flushPromises()
    expect(usersApiMock.fetchAdminNotificationPreferences).toHaveBeenCalledWith('u2')
    expect((w.find('.n-switch').element as HTMLInputElement).checked).toBe(true)
  })

  it('toggle → PATCH с новым значением, состояние обновляется', async () => {
    usersApiMock.fetchAdminNotificationPreferences.mockResolvedValueOnce({
      chat_notifications_enabled: false,
    })
    const w = mount(AdminChatNotificationsCard, {
      props: { userId: 'u2' },
      global: { plugins: [i18n] },
    })
    await flushPromises()
    await w.find('.n-switch').setValue(true)
    await flushPromises()

    expect(usersApiMock.patchAdminNotificationPreferences).toHaveBeenCalledWith('u2', {
      chat_notifications_enabled: true,
    })
    expect((w.find('.n-switch').element as HTMLInputElement).checked).toBe(true)
    expect(messageMock.success).toHaveBeenCalled()
  })
})
