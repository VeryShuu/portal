import { api } from './index'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

export type MailingRecipient = components['schemas']['MailingRecipientPublic']
export type MailingRecipientList = components['schemas']['MailingRecipientList']
export type CreateMailingRecipientDto = components['schemas']['CreateMailingRecipientRequest']
export type UpdateMailingRecipientDto = components['schemas']['UpdateMailingRecipientRequest']

export async function fetchMailingRecipients(params?: {
  q?: string
  limit?: number
  offset?: number
}): Promise<MailingRecipientList> {
  return api<MailingRecipientList>('/mailing-recipients', { params })
}

export async function createMailingRecipient(
  dto: CreateMailingRecipientDto,
): Promise<MailingRecipient> {
  return api<MailingRecipient>('/mailing-recipients', { method: 'POST', body: dto })
}

export async function updateMailingRecipient(
  id: string,
  dto: UpdateMailingRecipientDto,
): Promise<MailingRecipient> {
  return api<MailingRecipient>(`/mailing-recipients/${id}`, { method: 'PUT', body: dto })
}

export async function deleteMailingRecipient(id: string): Promise<void> {
  await api(`/mailing-recipients/${id}`, { method: 'DELETE' })
}
