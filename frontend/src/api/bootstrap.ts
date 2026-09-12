import { api } from './index'
import type { components } from './types.gen'
import type { UserMe } from './auth'

// ── Type aliases derived from the generated OpenAPI schema ────────────────────
// Run `npm run gen:types` to regenerate types.gen.d.ts from openapi.json

/**
 * Generated BootstrapOut; `user` уточнён до общего UserMe из api/auth
 * (ролевые литералы role/lang/auth_source, как в /auth/me).
 */
export type BootstrapData = components['schemas']['BootstrapOut'] & {
  user: UserMe
}

export type GalleryLinks = components['schemas']['GalleryLinksOut']

export function fetchBootstrap(): Promise<BootstrapData> {
  return api<BootstrapData>('/bootstrap')
}
