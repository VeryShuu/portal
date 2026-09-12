const PHOTO_SHARE_PATH = '/p'
const FOLDER_SHARE_PATH = '/photos/public'

function originBase(): string {
  if (typeof window === 'undefined') return ''
  return window.location.origin
}

export function buildPhotoShareUrl(token: string, base: string = originBase()): string {
  return `${base}${PHOTO_SHARE_PATH}/${token}`
}

export function buildFolderShareUrl(token: string, base: string = originBase()): string {
  return `${base}${FOLDER_SHARE_PATH}/${token}`
}
