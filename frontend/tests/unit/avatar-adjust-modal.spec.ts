import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (k: string) => k,
    locale: { value: 'ru' },
  }),
}))

const messageError = vi.fn()

vi.mock('naive-ui', () => ({
  NModal: {
    props: ['show'],
    template: '<div class="n-modal-stub" :data-show="show"><slot /><slot name="footer" /></div>',
  },
  NButton: {
    template: '<button class="n-button-stub" @click="$emit(\'click\')"><slot /></button>',
    emits: ['click'],
  },
  NSlider: {
    props: ['value', 'min', 'max', 'step'],
    template: '<div class="n-slider-stub" />',
  },
  useMessage: () => ({ success: vi.fn(), error: messageError }),
}))

vi.mock('../../src/api/users', () => ({
  patchMyProfile: vi.fn().mockResolvedValue({}),
  adminPatchUserProfile: vi.fn().mockResolvedValue({}),
}))

import AvatarAdjustModal from '../../src/components/profile/AvatarAdjustModal.vue'
import { patchMyProfile, adminPatchUserProfile } from '../../src/api/users'

function mountModal(props: Partial<InstanceType<typeof AvatarAdjustModal>['$props']> = {}) {
  return mount(AvatarAdjustModal, {
    props: {
      show: true,
      avatarUrl: '/media/avatars/u1_1.webp',
      focalX: 50,
      focalY: 50,
      focalZoom: 100,
      isOwn: true,
      ...props,
    } as never,
  })
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('AvatarAdjustModal', () => {
  it('стрелки сдвигают фокал и сохраняют через PATCH (debounce 350мс)', async () => {
    const wrapper = mountModal()
    await wrapper.find('.avatar-adjust__preview').trigger('keydown', {
      key: 'ArrowRight',
      shiftKey: true,
    })

    expect(patchMyProfile).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(400)

    expect(patchMyProfile).toHaveBeenCalledWith({
      avatar_focal_x: 60,
      avatar_focal_y: 50,
      avatar_focal_zoom: 100,
    })
  })

  it('колесо мыши меняет зум (клампится в 100..300)', async () => {
    const wrapper = mountModal()
    const preview = wrapper.find('.avatar-adjust__preview')
    await preview.trigger('wheel', { deltaY: -100 })
    await vi.advanceTimersByTimeAsync(400)

    expect(patchMyProfile).toHaveBeenCalledWith(
      expect.objectContaining({ avatar_focal_zoom: 110 }),
    )

    // сильный зум-аут клампится к дефолту: зум 100% хранится как null
    await preview.trigger('wheel', { deltaY: 10000 })
    await vi.advanceTimersByTimeAsync(400)
    expect(patchMyProfile).toHaveBeenLastCalledWith(
      expect.objectContaining({ avatar_focal_zoom: null }),
    )
  })

  it('emits saved с актуальными значениями фокала', async () => {
    const wrapper = mountModal()
    await wrapper.find('.avatar-adjust__preview').trigger('keydown', { key: 'ArrowUp' })
    await vi.advanceTimersByTimeAsync(400)

    const saved = wrapper.emitted('saved')
    expect(saved).toBeTruthy()
    expect(saved![0][0]).toMatchObject({ x: 50, y: 49, zoom: 100 })
  })

  it('admin-режим персистит через adminPatchUserProfile', async () => {
    const wrapper = mountModal({ isOwn: false, userId: 'u1' })
    await wrapper.find('.avatar-adjust__preview').trigger('keydown', { key: 'ArrowLeft' })
    await vi.advanceTimersByTimeAsync(400)

    expect(adminPatchUserProfile).toHaveBeenCalledWith('u1', {
      avatar_focal_x: 49,
      avatar_focal_y: 50,
      avatar_focal_zoom: 100,
    })
    expect(patchMyProfile).not.toHaveBeenCalled()
  })

  it('фокальный маркер рендерится в позиции фокала', () => {
    const wrapper = mountModal({ focalX: 30, focalY: 70 })
    const marker = wrapper.find('.avatar-adjust__focal')
    expect(marker.attributes('style')).toContain('left: 30%')
    expect(marker.attributes('style')).toContain('top: 70%')
  })

  it('drag указателем двигает фокал (getBoundingClientRect заглушен)', async () => {
    const wrapper = mountModal()
    const preview = wrapper.find('.avatar-adjust__preview')
    // jsdom отдаёт нулевой rect — подменяем на квадрат 200×200.
    ;(preview.element as HTMLElement).getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 200, height: 200, right: 200, bottom: 200, x: 0, y: 0 }) as DOMRect

    await preview.trigger('pointerdown', { pointerId: 1, clientX: 50, clientY: 100 })
    await preview.trigger('pointermove', { pointerId: 1, clientX: 50, clientY: 100 })
    await preview.trigger('pointerup', { pointerId: 1, clientX: 50, clientY: 100 })
    await vi.advanceTimersByTimeAsync(400)

    // 50/200 = 25%, 100/200 = 50%
    expect(patchMyProfile).toHaveBeenCalledWith({
      avatar_focal_x: 25,
      avatar_focal_y: 50,
      avatar_focal_zoom: 100,
    })
  })

  it('кнопка «Сбросить» возвращает фокал в дефолт (null)', async () => {
    const wrapper = mountModal({ focalX: 30, focalY: 70, focalZoom: 200 })
    const resetBtn = wrapper.findAll('.n-button-stub').find((b) => b.text().includes('users.profile.avatarAdjust.reset'))
    await resetBtn!.trigger('click')
    await vi.advanceTimersByTimeAsync(400)

    expect(patchMyProfile).toHaveBeenCalledWith({
      avatar_focal_x: null,
      avatar_focal_y: null,
      avatar_focal_zoom: null,
    })
    expect(wrapper.emitted('saved')![0][0]).toMatchObject({ x: null, y: null, zoom: null })
  })

  it('ошибка сохранения показывает message.error и не эмитит saved', async () => {
    const { patchMyProfile: patch } = await import('../../src/api/users')
    ;(patch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('boom'))
    const wrapper = mountModal()
    await wrapper.find('.avatar-adjust__preview').trigger('keydown', { key: 'ArrowDown' })
    await vi.advanceTimersByTimeAsync(400)

    expect(messageError).toHaveBeenCalled()
    expect(wrapper.emitted('saved')).toBeFalsy()
  })
})
