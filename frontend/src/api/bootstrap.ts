import { api } from './index'
import type { UserMe } from './auth'
import type { BrandingSettings } from '../stores/branding'
import type { ModuleSettingsResponse } from '../stores/modules'

export interface GalleryLinks {
  photo_gallery_url: string | null
  photo_gallery_mode: string
  photo_gallery_new_tab: boolean
  video_gallery_url: string | null
}

export interface BootstrapData {
  user: UserMe
  branding: BrandingSettings & {
    has_favicon?: boolean
    has_login_bg?: boolean
    has_logo?: boolean
    allowed_iframe_origins?: string[]
  }
  modules: ModuleSettingsResponse
  gallery_links: GalleryLinks
  unread_count: number
  is_helpdesk_agent?: boolean
}

export function fetchBootstrap(): Promise<BootstrapData> {
  return api<BootstrapData>('/bootstrap')
}
