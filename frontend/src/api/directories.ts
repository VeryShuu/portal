import { api, BASE_URL } from './index'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

export type FieldType = components['schemas']['DirectoryField']['type']
export type DirectoryField = components['schemas']['DirectoryField']
export type DirectoryChannel = components['schemas']['DirectoryChannel']
export type DirectoryPublic = components['schemas']['DirectoryPublic']
export type DirectoryList = components['schemas']['DirectoryList']
export type ContactPublic = components['schemas']['ContactPublic']
export type ContactInput = components['schemas']['ContactInput']

// contacts: backend всегда отдаёт список (default []), gen-схема пометила поле
// optional — восстанавливаем обязательность (consumers читают entry.contacts напрямую).
export type EntryPublic = components['schemas']['EntryPublic'] & { contacts: ContactPublic[] }

export type EntryList = Omit<components['schemas']['EntryList'], 'items'> & {
  items: EntryPublic[]
}

// sort_order в gen-схемах required (артефакт Pydantic default: клиент может
// опустить, применится default 0). Payload в DirectorySettings/EntryEditDrawer
// переиспользуется для create и update — явное значение сбросило бы порядок при PATCH.
export type CreateDirectoryDto = Omit<components['schemas']['CreateDirectoryRequest'], 'sort_order'> & {
  sort_order?: number
}

export type UpdateDirectoryDto = components['schemas']['UpdateDirectoryRequest']

export type CreateEntryDto = Omit<components['schemas']['CreateEntryRequest'], 'sort_order'> & {
  sort_order?: number
}

export type UpdateEntryDto = components['schemas']['UpdateEntryRequest']

export type EntryReorderItem = components['schemas']['EntryReorderItem']

// ── Types not present in OpenAPI schema (kept as manual interfaces) ───────────

// нет в OpenAPI — фронтовый тип: query-param union для export
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
