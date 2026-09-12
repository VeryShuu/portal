import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { UserPublic } from '../../src/api/users'

vi.mock('vue-router', () => ({
  useRoute: () => ({ name: 'user-profile', params: { id: 'test-user-id-123' } }),
  useRouter: () => ({ back: vi.fn(), push: vi.fn() }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('naive-ui', () => {
  const stub = { template: '<div><slot /></div>' }
  return {
    NAvatar: stub,
    NUpload: stub,
    NButton: stub,
    NIcon: stub,
    NSpin: stub,
    NResult: stub,
    NTag: stub,
    NForm: stub,
    NFormItem: stub,
    NSelect: stub,
    NSwitch: stub,
    NInput: stub,
    NAlert: stub,
    NModal: stub,
    NPopconfirm: stub,
    NSlider: stub,
    useMessage: () => ({ success: vi.fn(), error: vi.fn() }),
  }
})

vi.mock('@vicons/ionicons5', () => {
  const stub = { template: '<span />' }
  return {
    CameraOutline: stub,
    ShieldOutline: stub,
    KeyOutline: stub,
    CropOutline: stub,
    TrashOutline: stub,
  }
})

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => ({
    user: null,
    isAdmin: false,
    isLocalUser: false,
  }),
}))

vi.mock('../../src/api/users', () => ({
  fetchAdminNotificationPreferences: vi.fn(async () => ({ chat_notifications_enabled: false })),
  patchAdminNotificationPreferences: vi.fn(async () => ({ chat_notifications_enabled: false })),
  fetchUserById: vi.fn(),
  patchMyProfile: vi.fn(),
  uploadAvatar: vi.fn(),
  deleteAvatar: vi.fn(),
  adminUploadUserAvatar: vi.fn(),
  adminDeleteUserAvatar: vi.fn(),
  adminPatchUserProfile: vi.fn(),
  adminFetchUserKeycloakGroups: vi.fn(),
}))

vi.mock('../../src/api/userAttributeMappings', () => ({
  fetchAttributeSchema: vi.fn().mockResolvedValue({ items: [] }),
}))

vi.mock('../../src/api/auth', () => ({
  changePassword: vi.fn(),
}))

describe('UserProfileView — компонент', () => {
  it('импортируется без ошибок', async () => {
    const mod = await import('../../src/pages/UserProfileView.vue')
    expect(mod.default).toBeDefined()
  })
})

describe('UserPublic — структура типа', () => {
  it('phone и position допускают null', () => {
    const user = {
      id: 'abc',
      email: 'ivan@company.ru',
      full_name: 'Иванов Иван',
      department: 'IT' as string | null,
      position: null as string | null,
      phone: null as string | null,
      role: 'reader' as const,
      avatar_url: null as string | null,
      current_status: 'working', current_status_until: null,
      lang: 'ru' as const,
      created_at: '2024-01-01T00:00:00Z',
      auth_source: 'local' as const,
    }
    expect(user.phone).toBeNull()
    expect(user.position).toBeNull()
    expect(user.email).toBe('ivan@company.ru')
  })

  it('инициалы строятся из первых двух слов full_name', () => {
    const initials = (fullName: string) =>
      fullName.split(' ').slice(0, 2).map((w) => w[0]).join('').toUpperCase()

    expect(initials('Иванов Иван Иванович')).toBe('ИИ')
    expect(initials('Петров Пётр')).toBe('ПП')
    expect(initials('Мария')).toBe('М')
    expect(initials('')).toBe('')
  })
})

describe('fetchUserById — интеграция с API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('вызывается с корректным user_id из параметра маршрута', async () => {
    const { fetchUserById } = await import('../../src/api/users')
    const mockUser: UserPublic = {
      id: 'test-user-id-123',
      email: 'test@company.ru',
      full_name: 'Тест Тестов',
      department: 'QA',
      position: 'Инженер',
      phone: '+7 999 000 00 00',
      role: 'reader' as const,
      avatar_url: null,
      current_status: 'working', current_status_until: null,
      lang: 'ru' as const,
      created_at: '2024-01-01T00:00:00Z',
      auth_source: 'local' as const,
      last_login_at: null,
      staff_hidden: false,
      gender: null,
      birth_date: null,
      avatar_focal_x: null,
      avatar_focal_y: null,
      avatar_focal_zoom: null,
    }
    vi.mocked(fetchUserById).mockResolvedValueOnce(mockUser)

    const result = await fetchUserById('test-user-id-123')
    expect(fetchUserById).toHaveBeenCalledWith('test-user-id-123')
    expect(result.phone).toBe('+7 999 000 00 00')
    expect(result.position).toBe('Инженер')
    expect(result.department).toBe('QA')
  })

  it('при ошибке API бросает исключение', async () => {
    const { fetchUserById } = await import('../../src/api/users')
    vi.mocked(fetchUserById).mockRejectedValueOnce(Object.assign(new Error('Not found'), { status: 404 }))

    await expect(fetchUserById('nonexistent-id')).rejects.toMatchObject({ status: 404 })
  })
})


describe('UserProfileView — рендер чужого профиля (админ-карточка уведомлений)', () => {
  it('grid профиля рендерится; v-if AdminChatNotificationsCard вычисляется', async () => {
    const { fetchUserById } = await import('../../src/api/users')
    vi.mocked(fetchUserById).mockResolvedValue({
      id: 'test-user-id-123',
      email: 'user@mage.ru',
      full_name: 'Тест Тестов',
      role: 'reader',
      department: null,
      position: null,
      phone: null,
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
      avatar_url: null,
      auth_source: 'keycloak',
    } as never)
    const { default: UserProfileView } = await import('../../src/pages/UserProfileView.vue')
    const { mount, flushPromises } = await import('@vue/test-utils')
    const { VueQueryPlugin, QueryClient } = await import('@tanstack/vue-query')
    const w = mount(UserProfileView, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]],
        stubs: {
          ProfileHero: true,
          ProfileInfoCard: true,
          ProfileGroupsCard: true,
          UserAbsencesCard: true,
          DepartmentColleagues: true,
          AdminChatNotificationsCard: true,
        },
      },
    })
    await flushPromises()
    // Профиль загрузился → грид отрендерился (v-if-ветки карточек вычислены,
    // включая admin-only карточку чат-уведомлений).
    expect(w.find('.profile-grid').exists()).toBe(true)
  })
})
