import { nextTick, ref, type Ref } from 'vue'
import Sortable from 'sortablejs'
import { useDialog, useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { useQueryClient } from '@tanstack/vue-query'
import {
  fetchUsers,
  saveStaffOrder,
  type UserPublic,
} from '../api/users'
import { queryKeys } from '../queries/keys'

export interface StaffEditGroup {
  department: string
  users: UserPublic[]
}

const EDIT_PAGE_SIZE = 1000

export interface UseStaffEditOptions {
  editRootRef: Ref<HTMLElement | null>
}

export function useStaffEdit(options: UseStaffEditOptions) {
  const { editRootRef } = options
  const { t } = useI18n()
  const message = useMessage()
  const dialog = useDialog()
  const queryClient = useQueryClient()

  const editMode = ref(false)
  const editGroups = ref<StaffEditGroup[]>([])
  const dirty = ref(false)
  const saving = ref(false)
  const entering = ref(false)

  const sortableInstances: Sortable[] = []

  function buildGroupsFromList(items: UserPublic[]): StaffEditGroup[] {
    const map = new Map<string, UserPublic[]>()
    const order: string[] = []
    for (const u of items) {
      const dept = u.department?.trim() || ''
      if (!map.has(dept)) {
        map.set(dept, [])
        order.push(dept)
      }
      map.get(dept)!.push(u)
    }
    return order.map((d) => ({ department: d, users: map.get(d) ?? [] }))
  }

  function destroySortables(): void {
    for (const inst of sortableInstances) inst.destroy()
    sortableInstances.length = 0
  }

  function bindSortables(): void {
    destroySortables()
    const root = editRootRef.value
    if (!root) return

    sortableInstances.push(
      Sortable.create(root, {
        handle: '.drag-handle--dept',
        animation: 150,
        ghostClass: 'sortable-ghost',
        chosenClass: 'sortable-chosen',
        dragClass: 'sortable-drag',
        draggable: '.staff-edit__group',
        onStart() {
          root.classList.add('is-dragging-dept')
        },
        onEnd(evt) {
          root.classList.remove('is-dragging-dept')
          const oldIdx = evt.oldIndex
          const newIdx = evt.newIndex
          if (oldIdx == null || newIdx == null || oldIdx === newIdx) return

          const item = evt.item
          const parent = evt.from as HTMLElement
          if (item.parentElement === parent) {
            parent.removeChild(item)
            const refNode = parent.children[oldIdx] ?? null
            parent.insertBefore(item, refNode)
          }

          const next = [...editGroups.value]
          const [moved] = next.splice(oldIdx, 1)
          if (!moved) return
          next.splice(newIdx, 0, moved)
          editGroups.value = next
          dirty.value = true
        },
      }),
    )

    const lists = root.querySelectorAll<HTMLElement>('.staff-edit__user-list')
    lists.forEach((listEl) => {
      sortableInstances.push(
        Sortable.create(listEl, {
          handle: '.drag-handle--user',
          animation: 150,
          ghostClass: 'sortable-ghost',
          chosenClass: 'sortable-chosen',
          draggable: '.staff-edit__user',
          group: 'staff-users',
          onEnd(evt) {
            const fromList = evt.from as HTMLElement
            const toList = evt.to as HTMLElement
            const rawFromIdx = fromList.dataset.deptIdx
            const rawToIdx = toList.dataset.deptIdx
            const fromIdx =
              rawFromIdx != null && rawFromIdx !== ''
                ? Number.parseInt(rawFromIdx, 10)
                : Number.NaN
            const toIdx =
              rawToIdx != null && rawToIdx !== ''
                ? Number.parseInt(rawToIdx, 10)
                : Number.NaN
            const oldIdx = evt.oldIndex
            const newIdx = evt.newIndex
            if (oldIdx == null || newIdx == null) return
            if (
              !Number.isFinite(fromIdx) ||
              !Number.isFinite(toIdx) ||
              !editGroups.value[fromIdx] ||
              !editGroups.value[toIdx]
            ) {
              return
            }
            if (oldIdx === newIdx && fromIdx === toIdx) return

            const item = evt.item
            if (item.parentElement === toList) {
              toList.removeChild(item)
            }
            const refNode = fromList.children[oldIdx] ?? null
            fromList.insertBefore(item, refNode)

            const next = editGroups.value.map((g) => ({
              ...g,
              users: [...g.users],
            }))
            const [moved] = next[fromIdx].users.splice(oldIdx, 1)
            if (!moved) return
            if (fromIdx !== toIdx) {
              const newDept = next[toIdx].department
              moved.department = newDept || null
            }
            next[toIdx].users.splice(newIdx, 0, moved)
            editGroups.value = next
            dirty.value = true
          },
        }),
      )
    })
  }

  async function enterEdit(): Promise<void> {
    if (entering.value || editMode.value) return
    entering.value = true
    try {
      const res = await fetchUsers({
        sort: 'staff_custom',
        include_hidden: true,
        page: 1,
        page_size: EDIT_PAGE_SIZE,
      })
      editGroups.value = buildGroupsFromList(res.items)
      dirty.value = false
      editMode.value = true
      await nextTick()
      bindSortables()
    } catch {
      message.error(t('staff.edit.loadError'))
    } finally {
      entering.value = false
    }
  }

  function finalizeExit(): void {
    editMode.value = false
    dirty.value = false
    editGroups.value = []
    destroySortables()
  }

  function cancelEdit(): void {
    if (!dirty.value) {
      finalizeExit()
      return
    }
    dialog.warning({
      title: t('staff.edit.discardTitle'),
      content: t('staff.edit.discardContent'),
      positiveText: t('staff.edit.discard'),
      negativeText: t('common.cancel'),
      onPositiveClick: () => {
        finalizeExit()
      },
    })
  }

  function toggleUserHidden(userId: string): void {
    const next = editGroups.value.map((g) => ({
      ...g,
      users: g.users.map((u) =>
        u.id === userId ? { ...u, staff_hidden: !u.staff_hidden } : u,
      ),
    }))
    editGroups.value = next
    dirty.value = true
  }

  async function saveEdit(): Promise<void> {
    if (saving.value) return
    saving.value = true
    try {
      const departments = editGroups.value
        .map((g) => g.department)
        .filter((d) => !!d)
      const usersPayload: { id: string; sort_order: number }[] = []
      const hiddenIds: string[] = []
      for (const g of editGroups.value) {
        g.users.forEach((u, idx) => {
          usersPayload.push({ id: u.id, sort_order: idx })
          if (u.staff_hidden) hiddenIds.push(u.id)
        })
      }
      await saveStaffOrder({
        departments,
        users: usersPayload,
        hidden_user_ids: hiddenIds,
      })
      message.success(t('staff.edit.saved'))
      dirty.value = false
      editMode.value = false
      destroySortables()
      queryClient.invalidateQueries({ queryKey: queryKeys.users.all })
    } catch {
      message.error(t('staff.edit.saveError'))
    } finally {
      saving.value = false
    }
  }

  return {
    editMode,
    editGroups,
    dirty,
    saving,
    entering,
    enterEdit,
    cancelEdit,
    saveEdit,
    toggleUserHidden,
    bindSortables,
    destroySortables,
    buildGroupsFromList,
  }
}
