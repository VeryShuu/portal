import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type DOMWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

/**
 * Learn-контур (ADR-051): passwordless-вход (миграция 113) и реакция на
 * истечение learner-сессии.
 *
 * Контракты:
 * - шаг 1 (email): запрос кода → экран ввода кода; ответ сервера нейтрален
 *   независимо от существования email (§10.4); 429/сеть — понятные ошибки;
 * - шаг 2 (код): verify → курсы (или ?redirect); 400 — «код неверный/устарел»,
 *   поле чистится, редиректа нет; 429 — лимит попыток;
 * - «изменить email» возвращает на шаг 1;
 * - auth:expired → редирект на логин с ?redirect (кроме публичных страниц).
 */

const mocks = vi.hoisted(() => ({
  messageSuccess: vi.fn(),
  messageError: vi.fn(),
  routerPush: vi.fn(),
  routeQuery: { value: {} as Record<string, unknown> },
  routeName: { value: 'learn-login' as unknown },
  authApi: {
    learningRequestCode: vi.fn(),
    learningVerifyCode: vi.fn(),
    learnerLogout: vi.fn(),
    fetchMyCourses: vi.fn(),
  },
}))

vi.mock('naive-ui', () => {
  const NButton = {
    template:
      '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['disabled', 'loading', 'block', 'type', 'quaternary', 'size'],
    emits: ['click'],
  }
  const NInput = {
    template:
      '<input class="n-input" :value="value" :placeholder="placeholder" :disabled="disabled" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'placeholder', 'disabled', 'type', 'inputProps', 'maxlength'],
    emits: ['update:value'],
  }
  const NForm = {
    // attr-type=submit кнопка триггерит нативный submit формы — транслируем
    // его в компонентный submit (как реальный NForm). validate резолвится:
    // страница вызывает его через template-ref перед сабмитом.
    template: '<form @submit.prevent="$emit(\'submit\', $event)"><slot /></form>',
    props: ['model', 'rules', 'showLabel'],
    emits: ['submit'],
    methods: { validate: () => Promise.resolve() },
  }
  const NFormItem = {
    template: '<div class="n-form-item"><slot name="label" /><slot /></div>',
    props: ['path', 'label', 'validationStatus', 'feedback'],
  }
  const NCard = { template: '<div class="n-card"><div class="n-card__header"><slot name="header" /></div><slot /></div>', props: ['title'] }
  const NIcon = { template: '<i><slot /></i>' }
  return {
    NButton,
    NInput,
    NForm,
    NFormItem,
    NCard,
    NIcon,
    NDialogProvider: { template: '<div><slot /></div>' },
    NMessageProvider: { template: '<div><slot /></div>' },
    NNotificationProvider: { template: '<div><slot /></div>' },
    useMessage: () => ({ success: mocks.messageSuccess, error: mocks.messageError }),
  }
})

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.routerPush }),
  useRoute: () => ({ query: mocks.routeQuery.value, name: mocks.routeName.value }),
  RouterLink: { template: '<a><slot /></a>', props: ['to'] },
  RouterView: { template: '<div />' },
}))

vi.mock('../../src/api/learningAuth', () => mocks.authApi)
// Страница логина пробно дёргает /learning/me/courses (fetchMyCourses).
vi.mock('../../src/api/learning', () => ({ fetchMyCourses: mocks.authApi.fetchMyCourses }))

import LearnLoginPage from '../../src/learn/pages/LearnLoginPage.vue'
import { listenAuthExpired } from '../../src/learn/authGuard'

interface HasInputs {
  findAll(selector: string): DOMWrapper<Element>[]
}

function inputByPlaceholder(w: HasInputs, placeholder: string): DOMWrapper<HTMLInputElement> {
  const found = w.findAll('input.n-input').find((i) => i.attributes('placeholder') === placeholder)
  if (!found) throw new Error(`input с placeholder «${placeholder}» не найден`)
  return found as DOMWrapper<HTMLInputElement>
}

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'ru',
    missingWarn: false,
    fallbackWarn: false,
    messages: {
      ru: {
        learning: {
          learn: {
            loginTitle: 'Вход на портал обучения',
            loginHint: 'Укажите email учётной записи — пришлём код для входа.',
            codeTitle: 'Введите код',
            codeHint: 'Код отправлен на {email}. Письмо может дойти в течение минуты.',
            email: 'Email',
            emailRequired: 'Укажите email',
            codeLabel: 'Код из письма',
            codePlaceholder: '6 цифр',
            codeRequired: 'Введите код из письма',
            loginSubmit: 'Получить код',
            verifySubmit: 'Войти',
            codeSent: 'Если учётка существует, код отправлен на email',
            invalidCode: 'Код неверный, устарел или попытки исчерпаны — запросите новый',
            resend: 'Отправить код снова',
            resendIn: 'Отправить снова ({seconds} с)',
            changeEmail: 'Изменить email',
            tooManyAttempts: 'Слишком много попыток — попробуйте позже',
            genericError: 'Ошибка. Попробуйте ещё раз',
          },
        },
      },
    },
  })
}

beforeEach(() => {
  // resetAllMocks (не clearAllMocks): сбрасывает и once-очереди реализаций,
  // иначе mockRejectedValueOnce протекает между тестами.
  vi.resetAllMocks()
  mocks.routeQuery.value = {}
  mocks.routeName.value = 'learn-login'
  // Дефолт: посетитель логина не аутентифицирован (проба onMounted → 401).
  mocks.authApi.fetchMyCourses.mockRejectedValue({ status: 401 })
})

afterEach(() => {
  vi.useRealTimers()
})

/** Шаг 1 пройден: код запрошен, на экране форма ввода кода. */
async function mountAtCodeStep(): Promise<ReturnType<typeof mount>> {
  mocks.authApi.learningRequestCode.mockResolvedValue({ ok: true })
  const w = mount(LearnLoginPage, { global: { plugins: [makeI18n()] } })
  await inputByPlaceholder(w, 'Email').setValue('a@b.ru')
  await w.find('form').trigger('submit')
  await flushPromises()
  return w
}

describe('LearnLoginPage — шаг 1 (запрос кода)', () => {
  it('email → запрос кода → экран ввода кода + нейтральный успех', async () => {
    const w = mount(LearnLoginPage, { global: { plugins: [makeI18n()] } })
    await inputByPlaceholder(w, 'Email').setValue('a@b.ru')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(mocks.authApi.learningRequestCode).toHaveBeenCalledWith('a@b.ru')
    expect(mocks.messageSuccess).toHaveBeenCalled()
    // шаг 2: поле кода на экране, поля email больше нет
    expect(inputByPlaceholder(w, '6 цифр').exists()).toBe(true)
    expect(w.findAll('input.n-input')).toHaveLength(1)
  })

  it('ошибка запроса кода остаётся на шаге email', async () => {
    mocks.authApi.learningRequestCode.mockRejectedValue(new Error('net'))
    const w = mount(LearnLoginPage, { global: { plugins: [makeI18n()] } })
    await inputByPlaceholder(w, 'Email').setValue('a@b.ru')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(mocks.messageError).toHaveBeenCalled()
    expect(inputByPlaceholder(w, 'Email').exists()).toBe(true)
  })

  it('429 на запросе кода → сообщение о лимите попыток', async () => {
    mocks.authApi.learningRequestCode.mockRejectedValue({ status: 429 })
    const w = mount(LearnLoginPage, { global: { plugins: [makeI18n()] } })
    await inputByPlaceholder(w, 'Email').setValue('a@b.ru')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(mocks.messageError).toHaveBeenCalled()
    expect(mocks.routerPush).not.toHaveBeenCalled()
  })

  it('проба onMounted прошла (валидная сессия) → авто-редирект с логина', async () => {
    mocks.authApi.fetchMyCourses.mockResolvedValueOnce([])
    mount(LearnLoginPage, { global: { plugins: [makeI18n()] } })
    await flushPromises()
    expect(mocks.routerPush).toHaveBeenCalledWith({ name: 'learning' })
  })
})

describe('LearnLoginPage — шаг 2 (сверка кода)', () => {
  it('verify → курсы; с ?redirect → на сохранённый маршрут', async () => {
    const w = await mountAtCodeStep()
    mocks.authApi.learningVerifyCode.mockResolvedValue({ ok: true })

    await inputByPlaceholder(w, '6 цифр').setValue('123456')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(mocks.authApi.learningVerifyCode).toHaveBeenCalledWith('a@b.ru', '123456')
    expect(mocks.routerPush).toHaveBeenLastCalledWith({ name: 'learning' })

    // Мутация на месте: useRoute() в спеке держит ссылку на тот же объект.
    mocks.routeQuery.value.redirect = '/courses/abc'
    await inputByPlaceholder(w, '6 цифр').setValue('654321')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(mocks.routerPush).toHaveBeenLastCalledWith('/courses/abc')
  })

  it('400 (неверный/устаревший код) → ошибка, поле чистится, редиректа нет', async () => {
    const w = await mountAtCodeStep()
    mocks.authApi.learningVerifyCode.mockRejectedValue({ status: 400 })
    await inputByPlaceholder(w, '6 цифр').setValue('123456')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(mocks.messageError).toHaveBeenCalled()
    expect(inputByPlaceholder(w, '6 цифр').element.value).toBe('')
    expect(mocks.routerPush).not.toHaveBeenCalled()
  })

  it('429 на verify → лимит попыток; сеть → generic', async () => {
    const w = await mountAtCodeStep()
    mocks.authApi.learningVerifyCode.mockRejectedValueOnce({ status: 429 })
    await inputByPlaceholder(w, '6 цифр').setValue('123456')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(mocks.messageError).toHaveBeenCalledTimes(1)

    mocks.authApi.learningVerifyCode.mockRejectedValueOnce(new Error('net'))
    await inputByPlaceholder(w, '6 цифр').setValue('123456')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(mocks.messageError).toHaveBeenCalledTimes(2)
  })

  it('«изменить email» возвращает на шаг 1 и чистит код', async () => {
    const w = await mountAtCodeStep()
    await inputByPlaceholder(w, '6 цифр').setValue('123456')
    const buttons = w.findAll('button.n-button')
    const edit = buttons.find((b) => b.text() === 'Изменить email')
    await edit?.trigger('click')
    await flushPromises()
    expect(inputByPlaceholder(w, 'Email').exists()).toBe(true)
    // повторный вход в шаг 2: поле кода пусто
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(inputByPlaceholder(w, '6 цифр').element.value).toBe('')
  })
})

describe('listenAuthExpired', () => {
  it('401-событие на защищённой странице → логин с ?redirect', async () => {
    const router = {
      currentRoute: { value: { name: 'learning', fullPath: '/courses/abc' } },
      push: mocks.routerPush,
    } as never
    const off = listenAuthExpired(router)
    window.dispatchEvent(new CustomEvent('auth:expired'))
    await flushPromises()
    expect(mocks.routerPush).toHaveBeenCalledWith({
      name: 'learn-login',
      query: { redirect: '/courses/abc' },
    })
    off()
  })

  it('на публичной странице (логин) редиректа нет', async () => {
    mocks.routerPush.mockClear()
    mocks.routeName.value = 'learn-login'
    const router = {
      currentRoute: { value: { name: 'learn-login', fullPath: '/login' } },
      push: mocks.routerPush,
    } as never
    const off = listenAuthExpired(router)
    window.dispatchEvent(new CustomEvent('auth:expired'))
    await flushPromises()
    expect(mocks.routerPush).not.toHaveBeenCalled()
    off()
  })
})
