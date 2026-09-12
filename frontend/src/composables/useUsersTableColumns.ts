import { computed, h } from 'vue'
import type { Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import {
  NButton, NIcon, NTag, NSelect, type DataTableColumns, type SelectOption,
} from 'naive-ui'
import {
  CreateOutline, TrashOutline, KeyOutline, EyeOutline,
} from '@vicons/ionicons5'
import type { UserPublic } from '../api/users'

export function useUsersTableColumns(
  roleOptions: Ref<SelectOption[]>,
  onRoleChange: (user: UserPublic, role: string) => void,
  onEdit: (user: UserPublic) => void,
  onResetPwd: (user: UserPublic) => void,
  onDelete: (user: UserPublic) => void,
) {
  const { t } = useI18n()
  const router = useRouter()

  const userColumns = computed<DataTableColumns<UserPublic>>(() => [
    {
      title: t('admin.users.columns.fullName'),
      key: 'full_name',
      sorter: 'default',
      ellipsis: { tooltip: true },
    },
    {
      title: t('admin.users.columns.email'),
      key: 'email',
      ellipsis: { tooltip: true },
    },
    {
      title: t('admin.users.columns.department'),
      key: 'department',
      ellipsis: { tooltip: true },
      render: (row) => row.department ?? '—',
    },
    {
      title: t('admin.users.columns.role'),
      key: 'role',
      width: 160,
      render: (row) =>
        h(NSelect, {
          value: row.role,
          options: roleOptions.value,
          size: 'small',
          style: 'width:140px',
          onUpdateValue: (val: string) => onRoleChange(row, val),
        }),
    },
    {
      title: t('admin.users.columns.authSource'),
      key: 'auth_source',
      width: 110,
      render: (row) =>
        h(NTag, { size: 'small', type: row.auth_source === 'local' ? 'warning' : 'info', bordered: false },
          { default: () => row.auth_source === 'local' ? 'Local' : 'SSO' }),
    },
    {
      title: t('admin.users.columns.lastLoginAt'),
      key: 'last_login_at',
      width: 160,
      render: (row) => row.last_login_at ? new Date(row.last_login_at).toLocaleString() : '—',
    },
    {
      title: t('admin.users.columns.actions'),
      key: 'actions',
      width: 148,
      align: 'center',
      render: (row) =>
        h('div', { style: 'display:flex;gap:4px;justify-content:center' }, [
          h(NButton, {
            size: 'small', quaternary: true, circle: true,
            title: t('admin.users.actions.viewProfile'),
            onClick: () => router.push({ name: 'user-profile', params: { id: row.id } }),
          }, { icon: () => h(NIcon, null, { default: () => h(EyeOutline) }) }),
          row.auth_source === 'local'
            ? h(NButton, {
                size: 'small', quaternary: true, circle: true,
                title: t('admin.users.actions.edit'),
                onClick: () => onEdit(row),
              }, { icon: () => h(NIcon, null, { default: () => h(CreateOutline) }) })
            : null,
          row.auth_source === 'local'
            ? h(NButton, {
                size: 'small', quaternary: true, circle: true,
                title: t('admin.users.actions.resetPwd'),
                onClick: () => onResetPwd(row),
              }, { icon: () => h(NIcon, null, { default: () => h(KeyOutline) }) })
            : null,
          h(NButton, {
            size: 'small', quaternary: true, circle: true, type: 'error',
            title: t('admin.users.actions.delete'),
            onClick: () => onDelete(row),
          }, { icon: () => h(NIcon, null, { default: () => h(TrashOutline) }) }),
        ]),
    },
  ])

  return { userColumns }
}
