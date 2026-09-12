import { watch, type Ref } from 'vue'
import { parseApiError } from '../utils/parseApiError'

/**
 * Единые тосты об ошибках мутаций (learning, ревью 2026-08-30).
 *
 * До композаблы в компонентах learning жили ~20 ручных копий
 * `watch(() => m.error.value, (e) => { if (e) message.error(parseApiError(e, t)) })`,
 * и одна пропущенная копия (bulk-зачисление) превращала отказ мутации
 * в тихий провал. Композабла делает «мутацию без тоста» невозможной:
 * список ошибок передаётся явно, единым вызовом рядом с мутациями.
 *
 * @param errors — `.error` ref'ы мутаций (TanStack useMutation)
 * @param show   — обычно `message.error` из Naive UI
 * @param t      — переводчик для parseApiError
 */
export function useMutationErrorToasts(
  errors: Array<Ref<unknown>>,
  show: (text: string) => void,
  t: (key: string) => string,
): void {
  for (const error of errors) {
    watch(error, (e) => {
      if (e) show(parseApiError(e, t))
    })
  }
}
