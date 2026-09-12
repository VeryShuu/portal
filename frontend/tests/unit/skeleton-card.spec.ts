import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'

describe('SkeletonCard.vue', () => {
  it('renders news variant by default', async () => {
    const { default: SkeletonCard } = await import('../../src/components/SkeletonCard.vue')
    const wrapper = mount(SkeletonCard)
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.find('.skeleton-card--news').exists()).toBe(true)
  })

  it('renders article variant', async () => {
    const { default: SkeletonCard } = await import('../../src/components/SkeletonCard.vue')
    const wrapper = mount(SkeletonCard, { props: { variant: 'article' } })
    expect(wrapper.find('.skeleton-card').exists()).toBe(true)
  })

  it('renders list variant', async () => {
    const { default: SkeletonCard } = await import('../../src/components/SkeletonCard.vue')
    const wrapper = mount(SkeletonCard, { props: { variant: 'list' } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders file-row variant', async () => {
    const { default: SkeletonCard } = await import('../../src/components/SkeletonCard.vue')
    const wrapper = mount(SkeletonCard, { props: { variant: 'file-row' } })
    expect(wrapper.find('.skeleton-file-row').exists()).toBe(true)
  })

  it('renders folder-item variant', async () => {
    const { default: SkeletonCard } = await import('../../src/components/SkeletonCard.vue')
    const wrapper = mount(SkeletonCard, { props: { variant: 'folder-item' } })
    expect(wrapper.find('.skeleton-folder-item').exists()).toBe(true)
  })
})
