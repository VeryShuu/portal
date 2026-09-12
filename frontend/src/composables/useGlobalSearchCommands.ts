import { computed, type ComputedRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import {
  NewspaperOutline, PersonOutline, SettingsOutline, LogOutOutline,
  ColorPaletteOutline, BookOutline, HomeOutline,
  PricetagsOutline, TimeOutline, LinkOutline, DocumentOutline,
  ImageOutline, CalendarOutline, MailOutline,
} from '@vicons/ionicons5'
import { ROUTES } from '../router'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'

export interface SearchCommand {
  id: string
  icon: unknown
  label: string
  shortcut?: string
  action: () => void
}

export function useGlobalSearchCommands(query: Ref<string>, close: () => void) {
  const { t } = useI18n()
  const router = useRouter()
  const auth = useAuthStore()
  const themeStore = useThemeStore()

  const isCommandMode = computed(() => query.value.startsWith('>'))
  const commandQuery = computed(() => query.value.slice(1).trim().toLowerCase())

  const allCommands: ComputedRef<SearchCommand[]> = computed(() => {
    const cmds: SearchCommand[] = [
      { id: 'go-home', icon: HomeOutline, label: t('search.commands.goHome'), action: () => { router.push(ROUTES.HOME); close() } },
      { id: 'go-news', icon: NewspaperOutline, label: t('search.commands.goNews'), action: () => { router.push(ROUTES.NEWS); close() } },
      { id: 'go-kb', icon: BookOutline, label: t('search.commands.goKb'), action: () => { router.push(ROUTES.KB); close() } },
      { id: 'go-profile', icon: PersonOutline, label: t('search.commands.goProfile'), action: () => { router.push(ROUTES.PROFILE); close() } },
      { id: 'toggle-theme', icon: ColorPaletteOutline, label: t('search.commands.toggleTheme'), shortcut: t('nav.toggleTheme'), action: () => { themeStore.toggle(); close() } },
      { id: 'logout', icon: LogOutOutline, label: t('search.commands.logout'), action: () => { auth.logout(); close() } },
    ]
    if (auth.isEditor) {
      cmds.splice(1, 0, {
        id: 'create-news',
        icon: NewspaperOutline,
        label: t('search.commands.createNews'),
        action: () => { router.push(`${ROUTES.NEWS}/create`); close() },
      })
    }
    if (auth.isEditor) {
      cmds.push({
        id: 'manage-news-categories',
        icon: PricetagsOutline,
        label: t('search.commands.manageNewsCategories'),
        action: () => { router.push({ path: ROUTES.NEWS, query: { manage: 'categories' } }); close() },
      })
      cmds.push({
        id: 'manage-mailing-recipients',
        icon: MailOutline,
        label: t('search.commands.manageMailingRecipients'),
        action: () => { router.push({ path: ROUTES.NEWS, query: { manage: 'mailingRecipients' } }); close() },
      })
    }
    if (auth.isAdmin) {
      cmds.push(
        {
          id: 'go-admin',
          icon: SettingsOutline,
          label: t('search.commands.goAdmin'),
          action: () => { router.push(ROUTES.ADMIN); close() },
        },
        {
          id: 'manage-world-clock',
          icon: TimeOutline,
          label: t('search.commands.manageWorldClock'),
          action: () => { router.push({ path: ROUTES.HOME, query: { manage: 'world-clock' } }); close() },
        },
        {
          id: 'manage-links',
          icon: LinkOutline,
          label: t('search.commands.manageLinks'),
          action: () => { router.push({ path: ROUTES.LINKS, query: { manage: 'links' } }); close() },
        },
        {
          id: 'manage-file-icons',
          icon: DocumentOutline,
          label: t('search.commands.manageFileIcons'),
          action: () => { router.push({ path: ROUTES.FILES, query: { manage: 'file-icons' } }); close() },
        },
        {
          id: 'manage-kb',
          icon: BookOutline,
          label: t('search.commands.manageKb'),
          action: () => { router.push({ path: ROUTES.KB, query: { manage: 'kb' } }); close() },
        },
        {
          id: 'manage-photos-module',
          icon: ImageOutline,
          label: t('search.commands.managePhotosModule'),
          action: () => { router.push({ path: ROUTES.PHOTOS, query: { manage: 'module' } }); close() },
        },
        {
          id: 'manage-meetings-module',
          icon: CalendarOutline,
          label: t('search.commands.manageMeetingsModule'),
          action: () => { router.push({ path: ROUTES.MEETINGS, query: { manage: 'module' } }); close() },
        },
      )
    }
    return cmds
  })

  const filteredCommands = computed(() => {
    const q = commandQuery.value
    if (!q) return allCommands.value
    return allCommands.value.filter((c) => c.label.toLowerCase().includes(q))
  })

  return { isCommandMode, filteredCommands }
}
