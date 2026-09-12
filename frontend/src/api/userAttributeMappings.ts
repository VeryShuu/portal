import { api } from './index'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

export type UserAttributeMapping = components['schemas']['UserAttributeMappingPublic']
export type UserAttributeMappingSchema = components['schemas']['UserAttributeMappingSchema']
export type CreateUserAttributeMappingDto = components['schemas']['CreateUserAttributeMappingRequest']
export type UpdateUserAttributeMappingDto = components['schemas']['UpdateUserAttributeMappingRequest']
export type DiscoverAttributeItem = components['schemas']['DiscoverAttributeItem']

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
