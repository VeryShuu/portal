import { computed, onMounted, ref, toRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { useManageDrawer } from '../../composables/useManageDrawer'
import { useFilesData } from '../../composables/useFilesData'
import { useAuthStore } from '../../stores/auth'
import { useFilesSelection } from '../../composables/useFilesSelection'
import { useFilesUpload } from '../../composables/useFilesUpload'
import { useFilesBulkOps } from '../../composables/useFilesBulkOps'
import { useCollabora } from '../../composables/useCollabora'
import { isPreviewableImage, isPreviewablePdf } from '../../api/files'
import { useFilesActions } from './useFilesActions'

export function useFilesPageController() {
  const { t } = useI18n()
  const route = useRoute()
  const message = useMessage()
  const store = useFilesData()
  const auth = useAuthStore()
  const manage = useManageDrawer(['file-icons', 'file-shares'])

  const actions = useFilesActions(store)

  const selection = useFilesSelection(toRef(store, 'ncItems'), toRef(store, 'selectedFolderId'), {
    onOpenDir(item) {
      const node = store.findNodeByNcPath(item.nc_path)
      if (node) store.selectFolder(node.id)
    },
    onPreview(item) {
      if (isPreviewableImage(item)) actions.onPreviewImage(item)
      else if (isPreviewablePdf(item)) actions.onPreviewPdf(item)
    },
  })
  const upload = useFilesUpload(toRef(store, 'selectedFolderId'), () => store.refreshCurrent())
  const bulk = useFilesBulkOps({
    folderId: toRef(store, 'selectedFolderId'),
    selectedFilenames: selection.selectedFilenames,
    clearSelection: selection.clearSelection,
    onAfterMutation: () => store.refreshCurrent(),
  })
  const collabora = useCollabora(toRef(store, 'selectedFolderId'))

  const dragHandlers = {
    onMainDragEnter: upload.onMainDragEnter,
    onMainDragOver: upload.onMainDragOver,
    onMainDragLeave: upload.onMainDragLeave,
    onMainDrop: upload.onMainDrop,
  }

  const showCreateModal = ref(false)
  const createParentId = ref<string | null>(null)
  const creating = ref(false)
  const showPermsModal = ref(false)
  const permsForFolderId = ref<string | null>(null)
  const permsForFolderNode = computed(() =>
    permsForFolderId.value ? store.findNodeById(permsForFolderId.value) : null,
  )
  const sharesView = ref<'folders' | 'my' | 'shared-with-me'>('folders')

  function onSelectFolder(id: string) {
    sharesView.value = 'folders'
    store.selectFolder(id)
  }

  function onCreateRoot() {
    createParentId.value = null
    showCreateModal.value = true
  }

  function onCreateChild(folderId: string) {
    createParentId.value = folderId
    showCreateModal.value = true
  }

  function onManage(folderId: string) {
    permsForFolderId.value = folderId
    showPermsModal.value = true
  }

  async function onSubmitCreate(payload: { name: string; description: string | null }) {
    creating.value = true
    try {
      await store.createFolder({ name: payload.name, parent_id: createParentId.value, description: payload.description })
      showCreateModal.value = false
      message.success(t('files.folders.created'))
    } catch {
      message.error(t('files.error.createFolder'))
    } finally {
      creating.value = false
    }
  }

  onMounted(async () => {
    if (route.query.tab === 'shared-with-me') sharesView.value = 'shared-with-me'
    else if (route.query.tab === 'my-shares') sharesView.value = 'my'
    try {
      await store.loadTree()
    } catch {
      message.error(t('files.error.loadTree'))
    }
    const folderParam = route.query.folder
    if (typeof folderParam === 'string' && folderParam) {
      store.selectFolder(folderParam)
    }
  })

  watch(
    () => store.selectedFolderId,
    async (id) => {
      if (id) {
        try {
          await store.loadDetail(id)
        } catch {
          message.error(t('files.error.loadFolder'))
        }
      }
    },
  )

  return {
    store,
    auth,
    manage,
    selection,
    upload,
    bulk,
    collabora,
    dragHandlers,
    showCreateModal,
    createParentId,
    creating,
    showPermsModal,
    permsForFolderId,
    permsForFolderNode,
    sharesView,
    onSelectFolder,
    onCreateRoot,
    onCreateChild,
    onManage,
    onSubmitCreate,
    ...actions,
  }
}
