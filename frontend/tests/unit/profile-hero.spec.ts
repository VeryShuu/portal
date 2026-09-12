import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string) => k,
    locale: { value: 'ru' },
  }),
}))

vi.mock('naive-ui', () => ({
  NAvatar: {
    props: ['size', 'src', 'round', 'imgProps'],
    template:
      '<div class="n-avatar" :data-size="size" :data-src="src"><slot /></div>',
  },
  NIcon: { template: '<span class="n-icon"><slot /></span>' },
  // n-upload-stub: клик запускает customRequest с файлом — имитация выбора файла.
  NUpload: {
    props: ['customRequest', 'accept', 'showFileList'],
    template: '<div class="n-upload-stub" @click="run"><slot /></div>',
    methods: {
      run() {
        const { customRequest } = this as unknown as {
          customRequest?: (o: Record<string, unknown>) => void
        }
        if (!customRequest) return
        void customRequest({
          file: { file: new File(['x'], 'a.png', { type: 'image/png' }) },
          onFinish: () => {},
          onError: () => {},
        })
      },
    },
  },
  NPopconfirm: {
    name: 'NPopconfirm',
    emits: ['positive-click'],
    template: '<div class="n-popconfirm-stub"><slot name="trigger" /><slot /></div>',
  },
  NModal: { props: ['show'], template: '<div class="n-modal-stub"><slot /><slot name="footer" /></div>' },
  NButton: { template: '<button class="n-button-stub"><slot /></button>' },
  NSlider: { props: ['value', 'min', 'max', 'step'], template: '<div class="n-slider-stub" />' },
  useMessage: () => ({ success: vi.fn(), error: vi.fn() }),
}))

vi.mock('@vicons/ionicons5', () => {
  const stub = { template: '<span />' }
  return {
    CameraOutline: stub,
    CropOutline: stub,
    KeyOutline: stub,
    ShieldOutline: stub,
    TrashOutline: stub,
  }
})

const authState: {
  user: Record<string, unknown> | null
  isAdmin: boolean
  isLocalUser: boolean
  setUser: (u: never) => void
} = {
  user: null,
  isAdmin: false,
  isLocalUser: false,
  setUser: vi.fn(),
}

vi.mock('../../src/stores/auth', () => ({
  useAuthStore: () => authState,
}))

const setQueryData = vi.fn()

vi.mock('@tanstack/vue-query', () => ({
  useQueryClient: () => ({ setQueryData }),
}))

vi.mock('../../src/api/users', () => ({
  uploadAvatar: vi.fn().mockResolvedValue({ id: 'me', avatar_url: '/media/avatars/me_1.webp' }),
  deleteAvatar: vi.fn().mockResolvedValue({ id: 'me', avatar_url: null }),
  adminUploadUserAvatar: vi.fn().mockResolvedValue({ id: 'u1', avatar_url: '/media/avatars/u1_1.webp' }),
  adminDeleteUserAvatar: vi.fn().mockResolvedValue({ id: 'u1', avatar_url: null }),
  adminPatchUserProfile: vi.fn(),
}))

vi.mock('../../src/utils/formatDate', () => ({
  formatDateShort: (iso: string) => `FMT(${iso})`,
}))

import ProfileHero from '../../src/components/profile/ProfileHero.vue'
import AvatarAdjustModal from '../../src/components/profile/AvatarAdjustModal.vue'

const otherUser = {
  id: 'u1',
  full_name: 'Иванов Иван',
  position: 'Инженер',
  department: 'IT',
  role: 'reader',
  avatar_url: '/media/avatars/u1_1.webp',
  avatar_focal_x: null,
  avatar_focal_y: null,
  avatar_focal_zoom: null,
  current_status: 'working',
  current_status_until: null,
}

function mountHero(props: { user: Record<string, unknown>; isOwn: boolean }) {
  return mount(ProfileHero, { props: props as never })
}

beforeEach(() => {
  vi.clearAllMocks()
  authState.user = { id: 'me', role: 'admin' }
  authState.isAdmin = true
})

describe('ProfileHero — контролы аватара', () => {
  it('reader не видит контролы в чужом профиле', () => {
    authState.isAdmin = false
    const wrapper = mountHero({ user: otherUser, isOwn: false })
    expect(wrapper.find('.avatar-controls').exists()).toBe(false)
  })

  it('admin видит контролы в чужом профиле', () => {
    const wrapper = mountHero({ user: otherUser, isOwn: false })
    expect(wrapper.find('.avatar-controls').exists()).toBe(true)
  })

  it('владелец видит контролы в своём профиле', () => {
    authState.isAdmin = false
    const wrapper = mountHero({ user: { ...otherUser, id: 'me' }, isOwn: true })
    expect(wrapper.find('.avatar-controls').exists()).toBe(true)
  })

  it('админ: загрузка идёт через adminUploadUserAvatar и обновляет кэш', async () => {
    const { adminUploadUserAvatar } = await import('../../src/api/users')
    const wrapper = mountHero({ user: otherUser, isOwn: false })
    await wrapper.find('.n-upload-stub').trigger('click')
    await Promise.resolve()

    expect(adminUploadUserAvatar).toHaveBeenCalledWith('u1', expect.any(File))
    expect(setQueryData).toHaveBeenCalled()
    // после загрузки открывается модалка подгонки
    expect(wrapper.findComponent(AvatarAdjustModal).props('show')).toBe(true)
  })

  it('владелец: загрузка идёт через uploadAvatar и обновляет auth-store', async () => {
    authState.isAdmin = false
    authState.user = { id: 'me', role: 'reader' }
    const { uploadAvatar } = await import('../../src/api/users')
    const wrapper = mountHero({ user: { ...otherUser, id: 'me' }, isOwn: true })
    await wrapper.find('.n-upload-stub').trigger('click')
    await Promise.resolve()

    expect(uploadAvatar).toHaveBeenCalledWith(expect.any(File))
    expect(authState.setUser).toHaveBeenCalled()
  })

  it('админ: удаление через popconfirm вызывает adminDeleteUserAvatar', async () => {
    const { adminDeleteUserAvatar } = await import('../../src/api/users')
    const wrapper = mountHero({ user: otherUser, isOwn: false })
    wrapper.findComponent({ name: 'NPopconfirm' }).vm.$emit('positive-click')
    await Promise.resolve()

    expect(adminDeleteUserAvatar).toHaveBeenCalledWith('u1')
  })

  it('владелец: удаление вызывает deleteAvatar', async () => {
    authState.isAdmin = false
    authState.user = { id: 'me', role: 'reader' }
    const { deleteAvatar } = await import('../../src/api/users')
    const wrapper = mountHero({ user: { ...otherUser, id: 'me' }, isOwn: true })
    wrapper.findComponent({ name: 'NPopconfirm' }).vm.$emit('positive-click')
    await Promise.resolve()

    expect(deleteAvatar).toHaveBeenCalled()
  })
})

describe('ProfileHero — лайтбокс аватара', () => {
  it('клик по аватару открывает лайтбокс', async () => {
    const wrapper = mountHero({ user: otherUser, isOwn: false })
    expect(wrapper.find('.profile-avatar-lightbox__img').exists()).toBe(false)

    await wrapper.find('.profile-avatar-btn').trigger('click')
    expect(wrapper.find('.profile-avatar-lightbox__img').exists()).toBe(true)
    expect(wrapper.find('.profile-avatar-lightbox__img').attributes('src')).toBe(otherUser.avatar_url)
  })

  it('без аватара кнопка-лайтбокс не рендерится', () => {
    const wrapper = mountHero({ user: { ...otherUser, avatar_url: null }, isOwn: false })
    expect(wrapper.find('.profile-avatar-btn').exists()).toBe(false)
  })

  it('зум-кнопки лайтбокса меняют масштаб', async () => {
    const wrapper = mountHero({ user: otherUser, isOwn: false })
    await wrapper.find('.profile-avatar-btn').trigger('click')

    const buttons = wrapper.findAll('.profile-avatar-lightbox__toolbar button')
    await buttons[0].trigger('click') // zoom out
    await buttons[1].trigger('click') // zoom in
    expect(wrapper.find('.profile-avatar-lightbox__toolbar span').text()).toBe('100%')
  })
})

describe('ProfileHero — сохранение фокала', () => {
  it('admin: событие saved обновляет фокал в query-кэше', () => {
    const wrapper = mountHero({ user: { ...otherUser }, isOwn: false })
    wrapper.findComponent(AvatarAdjustModal).vm.$emit('saved', { x: 10, y: 20, zoom: 150 })

    const [key, updater] = setQueryData.mock.calls[setQueryData.mock.calls.length - 1]
    expect(key).toEqual(['users', 'detail', 'u1'])
    expect(updater({ id: 'u1', avatar_focal_x: null })).toMatchObject({
      avatar_focal_x: 10,
      avatar_focal_y: 20,
      avatar_focal_zoom: 150,
    })
  })

  it('владелец: событие saved обновляет auth-store', () => {
    authState.isAdmin = false
    authState.user = { id: 'me', role: 'reader', avatar_url: '/media/avatars/me_1.webp' }
    const wrapper = mountHero({ user: { ...otherUser, id: 'me' }, isOwn: true })
    wrapper.findComponent(AvatarAdjustModal).vm.$emit('saved', { x: 10, y: 20, zoom: 150 })

    expect(authState.setUser).toHaveBeenCalledWith(
      expect.objectContaining({ avatar_focal_x: 10, avatar_focal_y: 20, avatar_focal_zoom: 150 }),
    )
  })
})
