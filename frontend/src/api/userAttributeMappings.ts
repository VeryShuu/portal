import { api } from './index'

export interface UserAttributeMapping {
  id: string
  attr_key: string
  label_ru: string
  label_en: string | null
  sort_order: number
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface UserAttributeMappingSchema {
  attr_key: string
  label_ru: string
  label_en: string | null
  sort_order: number
}

export interface CreateUserAttributeMappingDto {
  attr_key: string
  label_ru: string
  label_en?: string | null
  sort_order?: number
  enabled?: boolean
}

export interface UpdateUserAttributeMappingDto {
  label_ru?: string
  label_en?: string | null
  sort_order?: number
  enabled?: boolean
}

export interface DiscoverAttributeItem {
  attr_key: string
  sample: string | null
  occurrences: number
}

export async function fetchAttributeSchema(): Promise<{ items: UserAttributeMappingSchema[] }> {
  return api<{ items: UserAttributeMappingSchema[] }>('/user-attribute-mappings/schema')
}

export async function fetchAttributeMappings(): Promise<{ items: UserAttributeMapping[]; total: number }> {
  return api<{ items: UserAttributeMapping[]; total: number }>('/user-attribute-mappings')
}

export async function discoverAttributes(): Promise<{ items: DiscoverAttributeItem[] }> {
  return api<{ items: DiscoverAttributeItem[] }>('/user-attribute-mappings/discover')
}

export async function createAttributeMapping(dto: CreateUserAttributeMappingDto): Promise<UserAttributeMapping> {
  return api<UserAttributeMapping>('/user-attribute-mappings', { method: 'POST', body: dto })
}

export async function updateAttributeMapping(id: string, dto: UpdateUserAttributeMappingDto): Promise<UserAttributeMapping> {
  return api<UserAttributeMapping>(`/user-attribute-mappings/${id}`, { method: 'PUT', body: dto })
}

export async function deleteAttributeMapping(id: string): Promise<void> {
  await api(`/user-attribute-mappings/${id}`, { method: 'DELETE' })
}
