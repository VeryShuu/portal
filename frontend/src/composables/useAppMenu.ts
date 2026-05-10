import { computed, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { NIcon, type MenuOption } from 'naive-ui'
import {
  HomeOutline, NewspaperOutline, BookOutline, FolderOpenOutline,
  GridOutline, PersonOutline, SettingsOutline, BuildOutline,
  ImagesOutline, VideocamOutline,
} from '@vicons/ionicons5'
import { useAuthStore } from '../stores/auth'
import { useModulesStore } from '../stores/modules'
import { ROUTES } from '../router'

export function useAppMenu() {
  const router = useRouter()
  const route = useRoute()
  const { t } = useI18n()
  const auth = useAuthStore()
  const modulesStore = useModulesStore()

  const photoGalleryUrl = computed(() => modulesStore.galleryLinks.photo_gallery_url)
  const photoGalleryMode = computed(() => modulesStore.galleryLinks.photo_gallery_mode)
  const photoGalleryNewTab = computed(() => modulesStore.galleryLinks.photo_gallery_new_tab)
  const videoGalleryUrl = computed(() => modulesStore.galleryLinks.video_gallery_url)

  const activeKey = computed(() => {
    const path = route.path
    if (path.startsWith(ROUTES.NEWS)) return 'news'
    if (path.startsWith(ROUTES.KB)) return 'kb'
    if (path.startsWith(ROUTES.FILES)) return 'files'
    if (path.startsWith(ROUTES.LINKS) || path.startsWith(ROUTES.BOOKMARKS)) return 'links'
    if (path.startsWith(ROUTES.PHOTOS)) return 'photo-gallery'
    if (path.startsWith(ROUTES.PROFILE)) return 'profile'
    if (path.startsWith(ROUTES.SETTINGS)) return 'settings'
    if (path.startsWith(ROUTES.ADMIN)) return 'admin'
    return 'home'
  })

  const defaultTitle = computed(() => {
    const map: Record<string, string> = {
      home: t('nav.home'),
      news: t('nav.news'),
      kb: t('nav.kb'),
      files: t('nav.files'),
      links: t('nav.links'),
      'photo-gallery': t('nav.photoGallery'),
      profile: t('nav.profile'),
      settings: t('nav.settings'),
      admin: t('nav.admin'),
    }
    return map[activeKey.value] ?? ''
  })

  function renderIcon(icon: any) {
    return () => h(NIcon, null, { default: () => h(icon) })
  }

  function groupLabel(label: string) {
    return () => h('span', { class: 'menu-group-label' }, label)
  }

  function renderNavLabel(label: string, key: string) {
    return () => h('span', { 'aria-current': activeKey.value === key ? 'page' : undefined }, label)
  }

  const menuOptions = computed<MenuOption[]>(() => {
    const items: MenuOption[] = [
      {
        type: 'group',
        key: 'g-feed',
        label: groupLabel(t('nav.groups.feed')),
        children: [
          { label: renderNavLabel(t('nav.home'), 'home'), key: 'home', icon: renderIcon(HomeOutline) },
          { label: renderNavLabel(t('nav.news'), 'news'), key: 'news', icon: renderIcon(NewspaperOutline) },
        ],
      },
      {
        type: 'group',
        key: 'g-work',
        label: groupLabel(t('nav.groups.work')),
        children: [
          { label: renderNavLabel(t('nav.kb'), 'kb'), key: 'kb', icon: renderIcon(BookOutline) },
          ...(modulesStore.isEnabled('nextcloud')
            ? [{ label: renderNavLabel(t('nav.files'), 'files'), key: 'files', icon: renderIcon(FolderOpenOutline) }]
            : []),
        ],
      },
      {
        type: 'group',
        key: 'g-services',
        label: groupLabel(t('nav.groups.services')),
        children: [
          { label: renderNavLabel(t('nav.links'), 'links'), key: 'links', icon: renderIcon(GridOutline) },
          ...((photoGalleryMode.value === 'internal' || (photoGalleryMode.value === 'external' && photoGalleryUrl.value))
            ? [{ label: renderNavLabel(t('nav.photoGallery'), 'photo-gallery'), key: 'photo-gallery', icon: renderIcon(ImagesOutline) }]
            : []),
          ...(videoGalleryUrl.value
            ? [{ label: renderNavLabel(t('nav.videoGallery'), 'video-gallery'), key: 'video-gallery', icon: renderIcon(VideocamOutline) }]
            : []),
        ],
      },
      {
        type: 'group',
        key: 'g-account',
        label: groupLabel(t('nav.groups.account')),
        children: [
          { label: renderNavLabel(t('nav.profile'), 'profile'), key: 'profile', icon: renderIcon(PersonOutline) },
          ...(auth.isEditor
            ? [{ label: renderNavLabel(t('nav.settings'), 'settings'), key: 'settings', icon: renderIcon(SettingsOutline) }]
            : []),
          ...(auth.isAdmin
            ? [{ label: renderNavLabel(t('nav.admin'), 'admin'), key: 'admin', icon: renderIcon(BuildOutline) }]
            : []),
        ],
      },
    ]
    return items
  })

  const routeMap: Record<string, string> = {
    home: ROUTES.HOME,
    news: ROUTES.NEWS,
    kb: ROUTES.KB,
    files: ROUTES.FILES,
    links: ROUTES.LINKS,
    profile: ROUTES.PROFILE,
    settings: ROUTES.SETTINGS,
    admin: ROUTES.ADMIN,
  }

  function isInternalUrl(url: string | null): boolean {
    return !!url && url.startsWith('/') && !url.startsWith('//')
  }

  function handleMenuSelect(key: string) {
    if (key === 'photo-gallery') {
      if (photoGalleryMode.value === 'internal') {
        router.push('/photos')
      } else if (photoGalleryUrl.value) {
        if (photoGalleryNewTab.value) {
          window.open(photoGalleryUrl.value, '_blank', 'noopener,noreferrer')
        } else if (isInternalUrl(photoGalleryUrl.value)) {
          router.push(photoGalleryUrl.value)
        } else if (/^https?:\/\//i.test(photoGalleryUrl.value)) {
          window.location.href = photoGalleryUrl.value
        }
      }
      return
    }
    if (key === 'video-gallery' && videoGalleryUrl.value) {
      if (isInternalUrl(videoGalleryUrl.value)) {
        router.push(videoGalleryUrl.value)
      } else {
        window.open(videoGalleryUrl.value, '_blank', 'noopener,noreferrer')
      }
      return
    }
    router.push(routeMap[key] ?? '/')
  }

  return {
    menuOptions,
    activeKey,
    defaultTitle,
    handleMenuSelect,
  }
}
