/**
 * ApprovalDetailDrawer.vue: реквизиты (два вида документов), таблица товаров
 * с ценами и без (скрытие цен 1С), история, вложения, бизнес-правила
 * действий (отклонение только с комментарием; requires_manager требует
 * выбора ответственного).
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'

const i18n = createI18n({ legacy: false, locale: 'ru', missingWarn: false, fallbackWarn: false, messages: { ru: {}, en: {} } })

/** Intl в ru-локали группирует разряды неразрывными пробелами — нормализуем для сравнения. */
function normalized(s: string): string {
  return s.replace(/[\u00A0\u202F]/g, ' ')
}

vi.mock('naive-ui', () => ({
  NDrawer: { template: '<div v-if="show" class="n-drawer"><slot /></div>', props: ['show', 'width', 'placement'] },
  NDrawerContent: {
    template: '<div class="n-drawer-content"><slot name="header" /><slot /></div>',
    props: ['title', 'closable'],
  },
  NAlert: { template: '<div class="n-alert"><slot /></div>', props: ['type', 'showIcon'] },
  NButton: {
    template: '<button class="n-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'ghost', 'loading', 'disabled'],
    emits: ['click'],
  },
  NCollapse: { template: '<div class="n-collapse"><slot /></div>' },
  NCollapseItem: { template: '<div class="n-collapse-item"><slot /></div>', props: ['title', 'name'] },
  NFormItem: { template: '<div class="n-form-item"><slot /></div>', props: ['label', 'labelPlacement'] },
  NInput: {
    template: '<textarea class="n-input" :value="value ?? \'\'" :placeholder="placeholder" @input="$emit(\'update:value\', $event.target.value)" />',
    props: ['value', 'type', 'placeholder', 'autosize'],
    emits: ['update:value'],
  },
  NSelect: { template: '<div class="n-select" />', props: ['value', 'options', 'placeholder', 'clearable'] },
  NSpin: { template: '<div class="n-spin"><slot /></div>' },
  NTable: { template: '<table><slot /></table>', props: ['size', 'singleLine'] },
  NTag: { template: '<span class="n-tag"><slot /></span>', props: ['size', 'type'] },
}))

import ApprovalDetailDrawer from '../../src/components/approvals/ApprovalDetailDrawer.vue'
import type { ApprovalDocumentDetail } from '../../src/api/approvals'

function baseDoc(over: Partial<ApprovalDocumentDetail> = {}): ApprovalDocumentDetail {
  return {
    guid: 'g-1',
    doc_type: 'ЗаказПоставщику',
    number: 'УП-1',
    date: '04.09.2026',
    organization: 'МАГЭ',
    manager: 'Иванов',
    comment: 'срочно',
    requires_manager: false,
    has_prices: true,
    contractor: 'ООО Поставщик',
    project: 'Проект',
    amount: 1234.5,
    currency: 'EUR',
    activity_direction: null,
    history: [
      { period: '01.09', user: 'Петя', event: 'Старт', comment: '', stage: 'Начало' },
    ],
    products: [{ name: 'Болт', recipient: 'База флота', quantity: '10', price: 10.5, total: 1260 }],
    managers: [],
    attachments: [{ index: 0, name: 'Счёт.pdf' }],
    ...over,
  } as ApprovalDocumentDetail
}

function mountDrawer(doc: ApprovalDocumentDetail | null, props: Record<string, unknown> = {}) {
  return mount(ApprovalDetailDrawer, {
    props: {
      show: true,
      loading: false,
      error: false,
      running: false,
      doc,
      comment: '',
      managerGuid: null,
      ...props,
    },
    global: { plugins: [i18n] },
  })
}

describe('ApprovalDetailDrawer.vue', () => {
  it('loading — спиннер без контента', () => {
    const w = mountDrawer(null, { loading: true })
    expect(w.find('.apr-detail__spin').exists()).toBe(true)
  })

  it('ошибка загрузки — алерт с повтором, emit retry (не вечный спиннер)', async () => {
    // Ревью 2026-09-05: ошибка карточки оставляла бесконечный индикатор.
    const w = mountDrawer(null, { error: true })
    expect(w.find('.apr-detail__spin').exists()).toBe(false)
    expect(w.find('.n-alert').exists()).toBe(true)
    const retry = w.findAll('.n-button').find((b) => b.text().includes('retry'))
    expect(retry).toBeDefined()
    await retry!.trigger('click')
    expect(w.emitted('retry')).toHaveLength(1)
  })

  it('ЗаказПоставщику: цены, контрагент, сумма, вложения', () => {
    const w = mountDrawer(baseDoc())
    expect(w.text()).toContain('ООО Поставщик')
    // Сумма/цены форматированы (группировка разрядов, запятая — десятичная)
    expect(normalized(w.text())).toContain('1 234,5 EUR')
    expect(normalized(w.text())).toContain('10,5 EUR')
    expect(normalized(w.text())).toContain('1 260 EUR')
    expect(w.text()).toContain('Счёт.pdf')
    // Кнопки действий активны (нет requires_manager)
    const approve = w.findAll('.n-button').find((b) => !b.attributes('disabled'))
    expect(approve).toBeDefined()
  })

  it('Внутренний заказ: без цен/контрагента, товары без колонок цен', () => {
    const w = mountDrawer(
      baseDoc({
        doc_type: 'ЗаказНаВнутреннееПотребление',
        has_prices: false,
        contractor: null,
        project: null,
        amount: null,
        activity_direction: 'Бурение',
        products: [{ name: 'Смазка', recipient: 'Отдел ИТ, Мурманск', quantity: '2', price: null, total: null }],
        attachments: [],
      }),
    )
    expect(w.text()).toContain('Бурение')
    expect(w.text()).not.toContain('ООО Поставщик')
    const headers = w.findAll('th').map((th) => th.text())
    expect(headers.some((h) => h.includes('products.price'))).toBe(false)
  })

  it('Внутренний заказ (v2.1.0.0): действия доступны, Подразделение из товаров', () => {
    const w = mountDrawer(
      baseDoc({
        doc_type: 'ЗаказНаВнутреннееПотребление',
        has_prices: false,
        contractor: null,
        project: null,
        amount: null,
        activity_direction: 'Бурение',
        products: [{ name: 'Смазка', recipient: 'Отдел ИТ, Мурманск', quantity: '2', price: null, total: null }],
        attachments: [],
      }),
    )
    // Заглушки «временно недоступно» больше нет — блок действий на месте
    expect(w.find('.apr-detail__stub').exists()).toBe(false)
    expect(w.find('.apr-detail__buttons').exists()).toBe(true)
    // Шапочное подразделение — реквизитом карточки
    expect(w.text()).toContain('Отдел ИТ, Мурманск')
    expect(w.text()).toContain('props.department')
    // Колонки цен по-прежнему нет (1С скрывает цены внутренних)
    const headers = w.findAll('th').map((th) => th.text())
    expect(headers.some((h) => h.includes('products.price'))).toBe(false)
    expect(headers.some((h) => h.includes('products.recipient'))).toBe(false)
    // Внутренний с требованием ответственного — селект и блокировка
    const locked = mountDrawer(
      baseDoc({
        doc_type: 'ЗаказНаВнутреннееПотребление',
        has_prices: false,
        requires_manager: true,
        managers: [{ guid: 'm-1', name: 'Сидоров' }],
        products: [{ name: 'Смазка', recipient: '', quantity: '2', price: null, total: null }],
        attachments: [],
      }),
    )
    expect(locked.find('.n-select').exists()).toBe(true)
    const approve = locked.findAll('.n-button').find((b) => b.text().includes('actions.approve'))
    expect(approve?.attributes('disabled')).toBeDefined()
  })

  it('ЗаказПоставщику: колонка «Получатель» в таблице товаров', () => {
    const w = mountDrawer(
      baseDoc({
        products: [
          { name: 'Работы', recipient: 'База флота', quantity: '1', price: 12500.5, total: 12500.5 },
        ],
        attachments: [],
      }),
    )
    const headers = w.findAll('th').map((th) => th.text())
    expect(headers.some((h) => h.includes('products.recipient'))).toBe(true)
    expect(w.text()).toContain('База флота')
  })

  it('ссылка на задачу СЭД — гиперссылка при sed_url, скрыта без него', () => {
    const url = 'https://sed.mage.ru/client/#/card/abc/316463'
    const withSed = mountDrawer(baseDoc({ sed_url: url }))
    const link = withSed.find('.apr-detail__row a')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe(url)
    expect(link.attributes('target')).toBe('_blank')
    // без задачи СЭД (sed_url: null) строки нет вовсе
    const withoutSed = mountDrawer(baseDoc({ sed_url: null, attachments: [] }))
    expect(withoutSed.find('.apr-detail__row a').exists()).toBe(false)
  })

  it('пустой список товаров — таблица без строк', () => {
    const w = mountDrawer(baseDoc({ products: [], attachments: [] }))
    expect(w.find('.apr-detail__table-wrap').exists()).toBe(true)
    expect(w.findAll('tbody tr').length).toBe(0)
  })

  it('requires_manager: согласование заблокировано без выбора, есть селект', () => {
    const w = mountDrawer(
      baseDoc({ requires_manager: true, managers: [{ guid: 'm-1', name: 'Сидоров' }] }),
    )
    const buttons = w.findAll('.n-button')
    const approve = buttons.find((b) => b.text().includes('actions.approve'))
    expect(approve?.attributes('disabled')).toBeDefined()
    expect(w.find('.n-select').exists()).toBe(true)
  })

  it('отклонение заблокировано с пустым комментарием, emit после ввода', async () => {
    const w = mountDrawer(baseDoc())
    const reject = w.findAll('.n-button').find((b) => b.text().includes('actions.reject'))
    expect(reject?.attributes('disabled')).toBeDefined()
    await w.find('.n-input').setValue('брак')
    expect(w.emitted('update:comment')?.[0]).toEqual(['брак'])
    await w.setProps({ comment: 'брак' })
    const reject2 = w.findAll('.n-button').find((b) => b.text().includes('actions.reject'))
    expect(reject2?.attributes('disabled')).toBeUndefined()
  })

  it('кнопки эмитят approve/reject', async () => {
    const w = mountDrawer(baseDoc(), { comment: 'ок' })
    await w.findAll('.n-button').find((b) => b.text().includes('actions.approve'))!.trigger('click')
    expect(w.emitted('approve')).toHaveLength(1)
    await w.findAll('.n-button').find((b) => b.text().includes('actions.reject'))!.trigger('click')
    expect(w.emitted('reject')).toHaveLength(1)
  })
})
