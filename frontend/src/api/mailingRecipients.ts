import { api } from './index'

export interface MailingRecipient {
  id: string
  name: string
  email: string
  label: string | null
  created_at: string
  updated_at: string
}

export interface MailingRecipientList {
  items: MailingRecipient[]
  total: number
  limit: number
  offset: number
}

export interface CreateMailingRecipientDto {
  name: string
  email: string
  label?: string | null
}

export interface UpdateMailingRecipientDto {
  name?: string
  email?: string
  label?: string | null
}

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
