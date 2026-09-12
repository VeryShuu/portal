import { reactive } from 'vue'

/**
 * audit M2: гибридная page→cursor пагинация для Naive UI NDataTable (:remote).
 *
 * Проблема: NDataTable работает на page-based модели (прыжок на страницу N),
 * а keyset-cursor — linear next/prev. Полная cursor-only миграция сломала бы
 * random access (нельзя прыгнуть на страницу 5 без прохода 1-4).
 *
 * Решение (гибрид): кеш ``Map<pageNumber, cursor>``. При переходе на страницу N
 * берём cursor страницы N-1 (если есть) → keyset-путь (быстро). Если cursor'а
 * нет (прыжок через несколько страниц) → fallback на OFFSET (backward-compat,
 * медленно, но корректно). Sequential forward/back перебор — всегда keyset.
 *
 * Cursor обновляется из ответа сервера (``next_cursor``): после загрузки страницы
 * N сохраняем её cursor для страницы N+1. Сброс фильтров очищает кеш.
 *
 * Используется AuditTab + EmailOutboxTab (audit M2).
 */
export interface CursorPagerState {
  /** Текущая страница (1-based). */
  page: number
  /** Размер страницы. */
  pageSize: number
  /** page N → cursor страницы N-1 (для загрузки страницы N через keyset). */
  cursors: Map<number, string>
  /** Когда cursor для текущей страницы отсутствует — используем offset (fallback). */
  offsetOnly: boolean
}

export function useCursorPager(pageSize = 50) {
  const pager = reactive<CursorPagerState>({
    page: 1,
    pageSize,
    cursors: new Map(),
    offsetOnly: false,
  })

  /** Функция возвращает params {cursor?, offset?} для загрузки текущей страницы. */
  function buildParams(): { cursor?: string; offset: number; limit: number } {
    const prevCursor = pager.cursors.get(pager.page - 1)
    if (prevCursor && !pager.offsetOnly) {
      // keyset: O(log n) по композитному индексу.
      return { cursor: prevCursor, offset: 0, limit: pager.pageSize }
    }
    // fallback: OFFSET (медленно на глубине, но корректно для random access).
    return { offset: (pager.page - 1) * pager.pageSize, limit: pager.pageSize }
  }

  /** Сохраняет cursor из ответа сервера для следующей страницы. */
  function consumeResponse(nextCursor: string | null | undefined) {
    if (nextCursor) {
      pager.cursors.set(pager.page, nextCursor)
    } else {
      // последняя страница — очищаем cursor для page+1, чтобы не зависал.
      pager.cursors.delete(pager.page)
    }
  }

  function goToPage(page: number) {
    pager.page = page
  }

  function setPageSize(size: number) {
    pager.pageSize = size
    reset()
  }

  /** Полный сброс кеша курсоров (при смене фильтров / page-size). */
  function reset() {
    pager.page = 1
    pager.cursors = new Map()
    pager.offsetOnly = false
  }

  /** Принудительный fallback в OFFSET-режим (если курсор повреждён/устарел). */
  function forceOffset() {
    pager.offsetOnly = true
  }

  return { pager, buildParams, consumeResponse, goToPage, setPageSize, reset, forceOffset }
}

/** Тип возврата для удобства аннотаций. */
export type CursorPager = ReturnType<typeof useCursorPager>
