import { api } from './index'

export interface PhotoItem {
  id: string
  file_name: string
  local_date_time: string
  thumbnail_url: string
  original_url: string
}

export interface PhotosRecentResponse {
  configured: boolean
  public_url: string
  items: PhotoItem[]
}

export function fetchRecentPhotos(): Promise<PhotosRecentResponse> {
  return api<PhotosRecentResponse>('/photos/recent')
}
