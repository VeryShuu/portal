import { api } from './index'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

export type SignatureCity = components['schemas']['SignatureCity']
export type SignaturePrefill = components['schemas']['SignaturePrefill']
export type SignatureConfig = components['schemas']['SignatureConfigResponse']
export type SignatureGenerateRequest = components['schemas']['SignatureGenerateRequest']
export type SignatureGenerateResponse = components['schemas']['SignatureGenerateResponse']
export type SignatureSettings = components['schemas']['SignatureSettings']

// ── Types not present in OpenAPI schema (kept as manual interfaces) ───────────

// В схемах это inline-enum — выводим из тела запроса /generate, чтобы union
// не разъезжался со схемой.
export type SignatureLanguage = components['schemas']['SignatureGenerateRequest']['language']
export type SignatureDevice = components['schemas']['SignatureGenerateRequest']['device']

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
