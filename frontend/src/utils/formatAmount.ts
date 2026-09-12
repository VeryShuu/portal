/**
 * 1234567.5 → «1 234 567,5» — группировка разрядов по локали
 * (неразрывные пробелы). Суммы согласования показываются и в списке,
 * и в карточке — формат должен совпадать.
 */
export function formatAmount(amount: number, locale = 'ru'): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(amount)
}
