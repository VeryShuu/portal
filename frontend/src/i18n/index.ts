import { createI18n } from 'vue-i18n'
import ru from './ru.json'
import en from './en.json'

export type AppLocale = 'ru' | 'en'

export const i18n = createI18n({
  legacy: false,
  locale: (localStorage.getItem('lang') ?? 'ru') as AppLocale,
  fallbackLocale: 'ru',
  messages: { ru, en },
})

export async function loadLocale(_locale: AppLocale): Promise<void> {
  // Both locales are bundled statically — nothing to load dynamically
}
