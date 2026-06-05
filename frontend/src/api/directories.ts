import { api, BASE_URL } from './index'

export type FieldType = 'text' | 'number' | 'email' | 'url' | 'multiline'

export interface DirectoryField {
  key: string
  label_ru: string
  label_en?: string | null
  type: FieldType
  required: boolean
  sort_order: number
}

export interface DirectoryChannel {
  key: string
  label_ru: string
  label_en?: string | null
  sort_order: number
}

export interface DirectoryPublic {
  id: string
  slug: string
  label_ru: string
  label_en: string | null
  icon: string | null
  description: string | null
  field_schema: DirectoryField[]
  channels: DirectoryChannel[]
  enabled: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

export interface DirectoryList {
  items: DirectoryPublic[]
  total: number
}

export interface ContactPublic {
  id: string
  role: string | null
  channel: string
  label: string | null
  value: string
  sort_order: number
}

export interface ContactInput {
  role?: string | null
  channel: string
  label?: string | null
  value: string
  sort_order?: number
}

export interface EntryPublic {
  id: string
  directory_id: string
  name: string
  folder_id: string | null
  folder_name: string | null
  attributes: Record<string, string>
  note: string | null
  sort_order: number
  created_by: string | null
  created_at: string
  updated_at: string
  contacts: ContactPublic[]
}

export interface EntryList {
  items: EntryPublic[]
  total: number
  limit: number
  offset: number
}

export interface CreateDirectoryDto {
  slug: string
  label_ru: string
  label_en?: string | null
  icon?: string | null
  description?: string | null
  field_schema?: DirectoryField[]
  channels?: DirectoryChannel[]
  enabled?: boolean
  sort_order?: number
}

export interface UpdateDirectoryDto {
  label_ru?: string
  label_en?: string | null
  icon?: string | null
  description?: string | null
  field_schema?: DirectoryField[]
  channels?: DirectoryChannel[]
  enabled?: boolean
  sort_order?: number
}

export interface CreateEntryDto {
  name: string
  folder_id?: string | null
  attributes?: Record<string, string>
  note?: string | null
  sort_order?: number
  contacts?: ContactInput[]
}

export interface UpdateEntryDto {
  name?: string
  folder_id?: string | null
  attributes?: Record<string, string>
  note?: string | null
  sort_order?: number
  contacts?: ContactInput[]
}

export interface EntryReorderItem {
  id: string
  sort_order: number
}

export type ExportFormat = 'csv' | 'xlsx' | 'pdf'

export async function fetchDirectories(): Promise<DirectoryList> {
  return api<DirectoryList>('/directories')
}

export async function createDirectory(dto: CreateDirectoryDto): Promise<DirectoryPublic> {
  return api<DirectoryPublic>('/directories', { method: 'POST', body: dto })
}

export async function updateDirectory(
  id: string,
  dto: UpdateDirectoryDto,
): Promise<DirectoryPublic> {
  return api<DirectoryPublic>(`/directories/${id}`, { method: 'PATCH', body: dto })
}

export async function deleteDirectory(id: string): Promise<void> {
  await api(`/directories/${id}`, { method: 'DELETE' })
}

export async function fetchEntries(
  slug: string,
  params?: { q?: string; limit?: number; offset?: number },
): Promise<EntryList> {
  return api<EntryList>(`/directories/${slug}/entries`, { params })
}

export async function fetchEntry(slug: string, entryId: string): Promise<EntryPublic> {
  return api<EntryPublic>(`/directories/${slug}/entries/${entryId}`)
}

export async function createEntry(slug: string, dto: CreateEntryDto): Promise<EntryPublic> {
  return api<EntryPublic>(`/directories/${slug}/entries`, { method: 'POST', body: dto })
}

export async function updateEntry(
  slug: string,
  entryId: string,
  dto: UpdateEntryDto,
): Promise<EntryPublic> {
  return api<EntryPublic>(`/directories/${slug}/entries/${entryId}`, {
    method: 'PATCH',
    body: dto,
  })
}

export async function deleteEntry(slug: string, entryId: string): Promise<void> {
  await api(`/directories/${slug}/entries/${entryId}`, { method: 'DELETE' })
}

export async function reorderEntries(slug: string, items: EntryReorderItem[]): Promise<void> {
  await api(`/directories/${slug}/entries/reorder`, { method: 'PATCH', body: { items } })
}

export function buildEntriesExportUrl(slug: string, format: ExportFormat): string {
  return `${BASE_URL}/directories/${slug}/export?format=${format}`
}
