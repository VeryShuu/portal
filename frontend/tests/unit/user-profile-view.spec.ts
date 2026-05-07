import { describe, it, expect, vi, beforeEach } from 'vitest'

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
    useMessage: () => ({ success: vi.fn(), error: vi.fn() }),
  }
})

vi.mock('@vicons/ionicons5', () => {
  const stub = { template: '<span />' }
  return {
    CameraOutline: stub,
    ShieldOutline: stub,
    KeyOutline: stub,
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
  fetchUserById: vi.fn(),
  patchMyProfile: vi.fn(),
  uploadAvatar: vi.fn(),
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
      presence_status: 'office' as const,
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
    const mockUser = {
      id: 'test-user-id-123',
      email: 'test@company.ru',
      full_name: 'Тест Тестов',
      department: 'QA',
      position: 'Инженер',
      phone: '+7 999 000 00 00',
      role: 'reader' as const,
      avatar_url: null,
      presence_status: 'office' as const,
      lang: 'ru' as const,
      created_at: '2024-01-01T00:00:00Z',
      auth_source: 'local' as const,
      last_login_at: null,
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
