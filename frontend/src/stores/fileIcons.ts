import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, apiUpload } from '../api'
import wordUrl from '../assets/file-icons/microsoft-word.svg?url'
import excelUrl from '../assets/file-icons/microsoft-excel.svg?url'

export interface FileIconEntry {
  extension: string
  url: string
  updated_at: number
}

interface ListResponse {
  items: FileIconEntry[]
}

const BUNDLED_ICONS: Record<string, string> = {
  doc: wordUrl,
  docx: wordUrl,
  xls: excelUrl,
  xlsx: excelUrl,
}

export const useFileIconsStore = defineStore('fileIcons', () => {
  const customByExt = ref<Record<string, string>>({})
  const versions = ref<Record<string, number>>({})
  const loaded = ref(false)
  let inflight: Promise<void> | null = null

  function _resolveUrl(ext: string, updatedAt: number): string {
    return `/api/v1/files/icons/${ext}?v=${updatedAt}`
  }

  function _setEntries(entries: FileIconEntry[]): void {
    const map: Record<string, string> = {}
    const ver: Record<string, number> = {}
    for (const e of entries) {
      map[e.extension] = _resolveUrl(e.extension, e.updated_at)
      ver[e.extension] = e.updated_at
    }
    customByExt.value = map
    versions.value = ver
  }

  async function load(): Promise<void> {
    if (loaded.value) return
    if (!inflight) {
      inflight = (async () => {
        try {
          const data = await api<ListResponse>('/files/icons')
          _setEntries(data.items)
          loaded.value = true
        } catch (err) {
          console.error('[fileIcons] Failed to load mappings:', err)
        } finally {
          inflight = null
        }
      })()
    }
    return inflight
  }

  async function refresh(): Promise<void> {
    loaded.value = false
    await load()
  }

  function iconUrlFor(ext: string): string | null {
    const e = ext.toLowerCase()
    if (customByExt.value[e]) return customByExt.value[e]
    if (BUNDLED_ICONS[e]) return BUNDLED_ICONS[e]
    return null
  }

  async function upload(ext: string, file: File): Promise<FileIconEntry> {
    const e = ext.trim().toLowerCase().replace(/^\./, '')
    const fd = new FormData()
    fd.append('file', file)
    const entry = await apiUpload<FileIconEntry>(`/admin/files/icons/${e}`, fd)
    customByExt.value = {
      ...customByExt.value,
      [entry.extension]: _resolveUrl(entry.extension, entry.updated_at),
    }
    versions.value = { ...versions.value, [entry.extension]: entry.updated_at }
    return entry
  }

  async function remove(ext: string): Promise<void> {
    const e = ext.trim().toLowerCase().replace(/^\./, '')
    await api(`/admin/files/icons/${e}`, { method: 'DELETE' })
    const next = { ...customByExt.value }
    const nextVer = { ...versions.value }
    delete next[e]
    delete nextVer[e]
    customByExt.value = next
    versions.value = nextVer
  }

  return {
    customByExt,
    versions,
    loaded,
    load,
    refresh,
    iconUrlFor,
    upload,
    remove,
    bundledIcons: BUNDLED_ICONS,
  }
})
