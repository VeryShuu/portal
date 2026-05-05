const KEY = 'recent_kb_articles'
const MAX = 5

export interface RecentArticle {
  id: string
  title: string
}

function isRecentArticle(item: unknown): item is RecentArticle {
  return (
    typeof item === 'object' &&
    item !== null &&
    typeof (item as RecentArticle).id === 'string' &&
    typeof (item as RecentArticle).title === 'string'
  )
}

function load(): RecentArticle[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) ?? '[]')
    if (!Array.isArray(parsed)) return []
    return parsed.filter(isRecentArticle)
  } catch {
    return []
  }
}

export function trackArticleView(article: RecentArticle): void {
  const items = load().filter((a) => a.id !== article.id)
  items.unshift(article)
  localStorage.setItem(KEY, JSON.stringify(items.slice(0, MAX)))
}

export function getRecentArticles(): RecentArticle[] {
  return load()
}
