import { computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NIcon, NTag, type DataTableColumns } from 'naive-ui'
import { CreateOutline, TrashOutline, ShieldCheckmarkOutline, HomeOutline } from '@vicons/ionicons5'
import type { ServiceLink } from '../api/links'

/**
 * Колонки таблицы ссылок для админки.
 * Чистая функция от колбэков (onEdit/onDelete) — образец useUsersTableColumns.
 * Возвращает computed, чтобы t() обновлялся при смене локали.
 */
export function useLinkColumns(
  onEdit: (link: ServiceLink) => void,
  onDelete: (link: ServiceLink) => void,
) {
  const { t } = useI18n()

  const linkColumns = computed<DataTableColumns<ServiceLink>>(() => [
    {
      title: '',
      key: 'icon',
      width: 44,
      align: 'center',
      render: (row) =>
        row.icon_url
          ? h('img', { src: row.icon_url, style: 'width:24px;height:24px;object-fit:contain;vertical-align:middle', alt: '' })
          : null,
    },
    {
      title: t('admin.links.columns.title'),
      key: 'title',
      sorter: 'default',
      ellipsis: { tooltip: true },
    },
    {
      title: t('admin.links.columns.url'),
      key: 'url',
      ellipsis: { tooltip: true },
      render: (row) => h('span', { style: 'font-size:12px;color:var(--color-text-muted)' }, row.url),
    },
    {
      title: t('admin.links.columns.category'),
      key: 'category',
      width: 130,
      render: (row) => row.category ?? '—',
    },
    {
      title: t('admin.links.columns.sso'),
      key: 'supports_sso',
      width: 70,
      align: 'center',
      render: (row) =>
        row.supports_sso
          ? h(NIcon, { color: 'var(--color-brand-sky)', size: 18 }, { default: () => h(ShieldCheckmarkOutline) })
          : h('span', { style: 'color:var(--color-text-subtle)' }, '—'),
    },
    {
      title: t('admin.links.columns.active'),
      key: 'is_active',
      width: 90,
      align: 'center',
      render: (row) =>
        h(NTag, { size: 'small', type: row.is_active ? 'success' : 'default', bordered: false },
          { default: () => row.is_active ? t('common.yes') : t('common.no') }),
    },
    {
      title: t('admin.links.columns.showOnHome'),
      key: 'show_on_home',
      width: 90,
      align: 'center',
      render: (row) =>
        row.show_on_home
          ? h(NIcon, { color: 'var(--color-brand-sky)', size: 18 }, { default: () => h(HomeOutline) })
          : h('span', { style: 'color:var(--color-text-subtle)' }, '—'),
    },
    {
      title: t('admin.links.columns.actions'),
      key: 'actions',
      width: 100,
      align: 'center',
      render: (row) =>
        h('div', { style: 'display:flex;gap:6px;justify-content:center' }, [
          h(NButton, {
            size: 'small', quaternary: true, circle: true,
            title: t('common.edit'),
            onClick: () => onEdit(row),
          }, { icon: () => h(NIcon, null, { default: () => h(CreateOutline) }) }),
          h(NButton, {
            size: 'small', quaternary: true, circle: true, type: 'error',
            title: t('common.delete'),
            onClick: () => onDelete(row),
          }, { icon: () => h(NIcon, null, { default: () => h(TrashOutline) }) }),
        ]),
    },
  ])

  return { linkColumns }
}
