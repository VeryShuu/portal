import { createI18n } from 'vue-i18n'
import ru from './ru.json'

export type AppLocale = 'ru' | 'en'

export const i18n = createI18n({
  legacy: false,
  locale: (localStorage.getItem('lang') ?? 'ru') as AppLocale,
  fallbackLocale: 'ru',
  messages: { ru },
})

const _loaded = new Set<AppLocale>(['ru'])

export async function loadLocale(locale: AppLocale): Promise<void> {
  if (_loaded.has(locale)) return
  const messages = await import(`./${locale}.json`)
  i18n.global.setLocaleMessage(locale, messages.default)
  _loaded.add(locale)
}
