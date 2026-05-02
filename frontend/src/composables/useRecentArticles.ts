const KEY = 'recent_kb_articles'
const MAX = 5

export interface RecentArticle {
  id: string
  title: string
}

function load(): RecentArticle[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? '[]')
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
