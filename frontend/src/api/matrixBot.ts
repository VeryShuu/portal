import { api } from './index'
import type { components } from './types.gen'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

export type MatrixBotSettingsOut = components['schemas']['MatrixBotSettingsOut']
export type MatrixBotSettingsIn = components['schemas']['MatrixBotSettingsIn']
export type MatrixBotTestResult = components['schemas']['MatrixBotTestResult']

/** Кому отправить тест: MXID как есть / email → конвенция / localpart → @localpart:server. */
export type MatrixBotTestTarget = string | null

export function fetchMatrixBot(): Promise<MatrixBotSettingsOut> {
  return api<MatrixBotSettingsOut>('/admin/matrix-bot')
}

export function testMatrixBot(target: MatrixBotTestTarget = null): Promise<MatrixBotTestResult> {
  return api<MatrixBotTestResult>('/admin/matrix-bot/test', {
    method: 'POST',
    body: { target },
  })
}

export function putMatrixBot(dto: MatrixBotSettingsIn): Promise<MatrixBotSettingsOut> {
  return api<MatrixBotSettingsOut>('/admin/matrix-bot', { method: 'PUT', body: dto })
}
