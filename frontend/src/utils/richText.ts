/**
 * Rich-текст (Markdown) → чистый однострочный текст для превью-отрывков.
 *
 * Логика перенесена 1:1 из NewsCard.excerpt (прод-кейс 2026-09-03: карточка
 * курса показывала сырые `&nbsp;` и `**` — rich-описание нельзя вставлять
 * как plain-строку): картинки/код-блоки удаляются, ссылки схлопываются в
 * текст, HTML-сущности разворачиваются через textContent, остатки разметки
 * и лишние пробелы срезаются.
 */
export function richToPlainText(raw: string, limit = 160): string {
  const stripped = raw
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]*)`/g, '$1')
  const el = document.createElement('div')
  el.innerHTML = stripped
  const text = (el.textContent ?? '')
    .replace(/[#*_`>[\]]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  return text.length > limit ? text.slice(0, limit) + '…' : text
}
