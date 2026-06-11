import { api } from './index'

export type SignatureLanguage = 'Ru' | 'Eng'
export type SignatureDevice = 'PC' | 'Web' | 'Apple' | 'Phone'

export interface SignatureCity {
  id: number
  label_ru: string
  label_eng: string
  suffix_ru: string
  suffix_eng: string
}

export interface SignatureConfig {
  cities: SignatureCity[]
  office_phones: string[]
  support_email: string
  email_domain: string
}

export interface SignatureGenerateRequest {
  name: string
  surname: string
  position: string
  language: SignatureLanguage
  device: SignatureDevice
  city_id: number
  office_phone?: string | null
  extension?: string | null
  mobile_phone?: string | null
  email: string
}

export interface SignatureGenerateResponse {
  html: string
  filename: string
}

export interface SignatureSettings {
  cities: SignatureCity[]
  office_phones: string[]
  support_email: string
  company_url: string
  logo_base_url: string
}

export async function fetchSignatureConfig(): Promise<SignatureConfig> {
  return api<SignatureConfig>('/signature/config')
}

export async function generateSignature(
  body: SignatureGenerateRequest,
): Promise<SignatureGenerateResponse> {
  return api<SignatureGenerateResponse>('/signature/generate', {
    method: 'POST',
    body,
  })
}

export async function fetchSignatureSettings(): Promise<SignatureSettings> {
  return api<SignatureSettings>('/signature/admin/settings')
}

export async function updateSignatureSettings(
  body: SignatureSettings,
): Promise<SignatureSettings> {
  return api<SignatureSettings>('/signature/admin/settings', {
    method: 'PUT',
    body,
  })
}
