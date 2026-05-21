import { i18n } from '../i18n'

export interface TourTarget {
  selector: string
  labelKey: string
  groupKey: string
}

export const TOUR_TARGETS: TourTarget[] = [
  { selector: '.n-menu-item:has([data-tour-id="home"])', labelKey: 'nav.home', groupKey: 'nav.groups.feed' },
  { selector: '.n-menu-item:has([data-tour-id="news"])', labelKey: 'nav.news', groupKey: 'nav.groups.feed' },
  { selector: '.n-menu-item:has([data-tour-id="kb"])', labelKey: 'nav.kb', groupKey: 'nav.groups.work' },
  { selector: '.n-menu-item:has([data-tour-id="files"])', labelKey: 'nav.files', groupKey: 'nav.groups.work' },
  { selector: '.n-menu-item:has([data-tour-id="links"])', labelKey: 'nav.links', groupKey: 'nav.groups.services' },
  { selector: '.n-menu-item:has([data-tour-id="staff"])', labelKey: 'nav.staff', groupKey: 'nav.groups.services' },
  { selector: '.n-menu-item:has([data-tour-id="meetings"])', labelKey: 'nav.meetings', groupKey: 'nav.groups.services' },
  { selector: '.n-menu-item:has([data-tour-id="photo-gallery"])', labelKey: 'nav.photoGallery', groupKey: 'nav.groups.services' },
  { selector: '.n-menu-item:has([data-tour-id="video-gallery"])', labelKey: 'nav.videoGallery', groupKey: 'nav.groups.services' },
  { selector: '.n-menu-item:has([data-tour-id="profile"])', labelKey: 'nav.profile', groupKey: 'nav.groups.account' },
  { selector: '.n-menu-item:has([data-tour-id="my-feedback"])', labelKey: 'feedback.myTickets', groupKey: 'nav.groups.account' },
  { selector: '.n-menu-item:has([data-tour-id="admin"])', labelKey: 'nav.admin', groupKey: 'nav.groups.account' },
  { selector: '.app-header .user-pill', labelKey: 'admin.modules.onboarding.targetUserPill', groupKey: 'admin.modules.onboarding.targetGroupHeader' },
  { selector: '.app-header', labelKey: 'admin.modules.onboarding.targetHeader', groupKey: 'admin.modules.onboarding.targetGroupHeader' },
  { selector: '.app-sidebar', labelKey: 'admin.modules.onboarding.targetSidebar', groupKey: 'admin.modules.onboarding.targetGroupLayout' },
]

export interface TourTargetOption {
  label: string
  value: string
  group: string
  selector: string
}

export function getTourTargetOptions(): TourTargetOption[] {
  const t = i18n.global.t
  return TOUR_TARGETS.map((tt) => ({
    label: t(tt.labelKey),
    value: tt.selector,
    selector: tt.selector,
    group: t(tt.groupKey),
  }))
}

export function tourTargetLabelFor(selector: string): string | null {
  const t = i18n.global.t
  const found = TOUR_TARGETS.find((tt) => tt.selector === selector)
  return found ? t(found.labelKey) : null
}
