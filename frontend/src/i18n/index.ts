import { createI18n } from 'vue-i18n'
import ru from './ru.json'
import en from './en.json'

export type AppLocale = 'ru' | 'en'

/**
 * Правило плюрализации для русского языка (CLDR one/few/many).
 *
 * Vue-i18n по умолчанию знает только English-логику (one/other), поэтому для
 * славянских форм (1 день / 2 дня / 5 дней) нужно явное правило. Pipe-формат
 * сообщения ``{n} … | {n} … | {n} …`` индексируется возвращаемым значением:
 * 0 = one (1, 21, 31…), 1 = few (2–4, 22–24…), 2 = many (0, 5–20, 25–30…).
 * Подростки 11–14 всегда «many». Источник логики — CLDR/ICU Russian plural rule.
 *
 * ``choicesLength`` = число сегментов в pipe-сообщении (3 для one|few|many).
 * Ветвь ``choicesLength < 3`` — запасная для 2-сегментных one|other форматов.
 */
function russianPluralRule(choice: number, choicesLength: number): number {
  const teen = choice > 10 && choice < 20
  const endsWithOne = choice % 10 === 1
  const endsWithTwoFour = choice % 10 >= 2 && choice % 10 <= 4
  if (!teen && endsWithOne) return 0
  if (!teen && endsWithTwoFour) return 1
  // 2-сегментный формат сворачивает few+many в «other» (индекс 1).
  return choicesLength < 3 ? 1 : 2
}

export const i18n = createI18n({
  legacy: false,
  locale: (localStorage.getItem('lang') ?? 'ru') as AppLocale,
  fallbackLocale: 'ru',
  messages: { ru, en },
  pluralRules: {
    ru: russianPluralRule,
  },
})

export async function loadLocale(_locale: AppLocale): Promise<void> {
  // Both locales are bundled statically — nothing to load dynamically
}
