import { fetchNewsList, type News } from '../api/news'
import { globalSearch, type SearchResultItem } from '../api/kb'
import { fetchUsers, type UserPublic } from '../api/users'

export interface GlobalSearchOptions {
  newsLimit: number
  kbLimit: number
  userLimit: number
  signal?: AbortSignal
}

export interface GlobalSearchResult {
  news: News[]
  kb: SearchResultItem[]
  users: UserPublic[]
}

/**
 * Cross-domain search aggregator used by the GlobalSearch (Cmd-K) modal.
 * Wraps news/kb/users API calls in a single promise. Failures of individual
 * sources are isolated via Promise.allSettled — a partial result is preferable
 * to no result at all in the command palette UX.
 */
export async function runGlobalSearch(
  query: string,
  opts: GlobalSearchOptions,
): Promise<GlobalSearchResult> {
  const { newsLimit, kbLimit, userLimit, signal } = opts
  const [newsResult, kbResult, usersResult] = await Promise.allSettled([
    fetchNewsList(
      { page: 1, page_size: newsLimit, status: 'published', q: query },
      { signal },
    ),
    globalSearch(query, { limit: kbLimit }),
    fetchUsers({ q: query, page_size: userLimit }),
  ])
  return {
    news: newsResult.status === 'fulfilled'
      ? newsResult.value.items.slice(0, newsLimit)
      : [],
    kb: kbResult.status === 'fulfilled'
      ? kbResult.value.items.filter((r) => r.type === 'article').slice(0, kbLimit)
      : [],
    users: usersResult.status === 'fulfilled'
      ? usersResult.value.items.slice(0, userLimit)
      : [],
  }
}
