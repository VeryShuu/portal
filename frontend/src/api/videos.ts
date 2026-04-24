import { api } from './index'

export interface VideoItem {
  uuid: string
  name: string
  duration: number
  views: number
  thumbnail_url: string
  watch_url: string
  created_at: string
}

export interface VideosRecentResponse {
  configured: boolean
  public_url: string
  items: VideoItem[]
}

export interface VideosConfigResponse {
  configured: boolean
  public_url: string
}

export function fetchVideosConfig(): Promise<VideosConfigResponse> {
  return api<VideosConfigResponse>('/videos/config')
}

export function fetchRecentVideos(): Promise<VideosRecentResponse> {
  return api<VideosRecentResponse>('/videos/recent')
}
