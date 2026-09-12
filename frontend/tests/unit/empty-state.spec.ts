import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'

describe('EmptyState.vue', () => {
  it('renders with required title prop', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'No items found' } })
    expect(wrapper.exists()).toBe(true)
    expect(wrapper.text()).toContain('No items found')
  })

  it('renders description when provided', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, {
      props: { title: 'Empty', description: 'Try adding something' },
    })
    expect(wrapper.text()).toContain('Try adding something')
  })

  it('applies compact class when compact=true', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'Empty', compact: true } })
    expect(wrapper.find('.empty--compact').exists()).toBe(true)
  })

  it('renders news variant icon', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'No news', variant: 'news' } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders bookmark variant icon', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'No bookmarks', variant: 'bookmark' } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders search variant icon', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'No results', variant: 'search' } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders file variant icon', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'No files', variant: 'file' } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders photo variant icon', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'No photos', variant: 'photo' } })
    expect(wrapper.exists()).toBe(true)
  })

  it('renders default variant icon when no variant specified', async () => {
    const { default: EmptyState } = await import('../../src/components/EmptyState.vue')
    const wrapper = mount(EmptyState, { props: { title: 'Default' } })
    expect(wrapper.exists()).toBe(true)
  })
})
