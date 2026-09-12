/**
 * Единый разбор ссылок на видео портала → URL для iframe-плеера.
 * Потребители: learning (VideoEmbed в материалах курса) и rich-редактор
 * (диалог «Вставить видео» в новостях/БЗ — конвертация до вставки в HTML).
 *
 * Список разрешённых origin'ов — runtime-настройка ``system.json →
 * video_iframe_origins`` (Admin UI → System); она же является CSP frame-src
 * (nginx/render-config.sh) и sanitize-гейтом новостей/БЗ
 * (bootstrap → branding.allowed_iframe_origins). Гейт парсера обязан совпадать
 * с CSP: «умеет больше, чем CSP» парсер предлагал бы iframe, который браузер
 * заблокирует. Живой список приходит с backend (/learning/meta на обоих
 * контурах, /bootstrap на портале); без него используется дефолт — зеркало
 * backend-константы DEFAULT_VIDEO_IFRAME_ORIGINS.
 *
 * Неизвестные/неразрешённые ссылки возвращают null — вызывающий код оставляет
 * материал внешней ссылкой (learning, ТЗ §6.2) или показывает ошибку
 * (редактор).
 */

export type VideoProvider = 'youtube' | 'rutube' | 'vk' | 'vimeo' | 'corporate'

export interface VideoEmbedInfo {
  embedUrl: string
  provider: VideoProvider
}

/**
 * Дефолт разрешения — зеркало DEFAULT_VIDEO_IFRAME_ORIGINS
 * (backend/app/core/constants.py). Единственное назначение — работа парсера
 * до загрузки /learning/meta; источник истины — настройка в system.json.
 */
export const DEFAULT_VIDEO_IFRAME_ORIGINS: string[] = [
  'https://video.mage.ru',
  'https://www.youtube-nocookie.com',
  'https://rutube.ru',
  'https://vk.com',
  'https://vkvideo.ru',
  'https://player.vimeo.com',
]

// Публичные видеохостинги: разрешаем только известные пути, ведущие к
// каноническому embed-URL плеера (watch-страницы сами запрещают фрейминг
// через X-Frame-Options). embedOrigin — origin из allowedOrigins, который
// обязан быть разрешён (CSP frame-src), чтобы iframe загрузился.
interface ProviderSpec {
  provider: Exclude<VideoProvider, 'corporate'>
  sourceHosts: Set<string>
  embedOrigin: string
  convert: (url: URL) => string | null
}

const YOUTUBE_HOSTS = new Set([
  'youtube.com',
  'www.youtube.com',
  'm.youtube.com',
  'youtu.be',
  'www.youtu.be',
  'youtube-nocookie.com',
  'www.youtube-nocookie.com',
])
const RUTUBE_HOSTS = new Set(['rutube.ru', 'www.rutube.ru'])
const VK_HOSTS = new Set(['vk.com', 'www.vk.com', 'vkvideo.ru', 'www.vkvideo.ru', 'm.vk.com'])
const VIMEO_HOSTS = new Set(['vimeo.com', 'www.vimeo.com', 'player.vimeo.com'])

const PROVIDERS: ProviderSpec[] = [
  {
    provider: 'youtube',
    sourceHosts: YOUTUBE_HOSTS,
    embedOrigin: 'https://www.youtube-nocookie.com',
    convert: (url) => {
      const id = parseYouTubeId(url)
      return id ? `https://www.youtube-nocookie.com/embed/${id}` : null
    },
  },
  {
    provider: 'rutube',
    sourceHosts: RUTUBE_HOSTS,
    embedOrigin: 'https://rutube.ru',
    convert: (url) => {
      const embed = url.pathname.match(/^\/play\/embed\/([0-9a-f]+)\/?$/i)
      if (embed) return `https://rutube.ru/play/embed/${embed[1]}`
      const video = url.pathname.match(/^\/video\/([0-9a-f]+)\/?$/i)
      return video ? `https://rutube.ru/play/embed/${video[1]}` : null
    },
  },
  {
    provider: 'vk',
    sourceHosts: VK_HOSTS,
    embedOrigin: 'https://vkvideo.ru',
    convert: convertVk,
  },
  {
    provider: 'vimeo',
    sourceHosts: VIMEO_HOSTS,
    embedOrigin: 'https://player.vimeo.com',
    convert: (url) => {
      if (url.hostname === 'player.vimeo.com') {
        return url.pathname.match(/^\/video\/(\d+)\/?$/) ? url.toString() : null
      }
      const video = url.pathname.match(/^\/(?:video\/)?(\d+)\/?$/)
      return video ? `https://player.vimeo.com/video/${video[1]}` : null
    },
  },
]

function parseYouTubeId(url: URL): string | null {
  if (url.hostname === 'youtu.be' || url.hostname === 'www.youtu.be') {
    return url.pathname.split('/').filter(Boolean)[0] ?? null
  }
  if (url.pathname === '/watch') {
    return url.searchParams.get('v')
  }
  const shortsOrEmbed = url.pathname.match(/^\/(?:shorts|embed|live)\/([\w-]+)\/?$/)
  return shortsOrEmbed ? shortsOrEmbed[1] : null
}

// Путь /video<oid>_<id>[_<hash>]; oid бывает отрицательным (видео сообществ).
const VK_VIDEO_PATH_RE = /^\/video(-?\d+)_(\d+)(?:_([A-Za-z0-9]+))?\/?$/

function convertVk(url: URL): string | null {
  const video = url.pathname.match(VK_VIDEO_PATH_RE)
  if (video) {
    const params = new URLSearchParams({ oid: video[1], id: video[2] })
    if (video[3]) params.set('hash', video[3])
    return `https://vkvideo.ru/video_ext.php?${params}`
  }
  // Уже готовый embed-код: нормализуем хост на vkvideo.ru, параметры сохраняем.
  if (url.pathname === '/video_ext.php') {
    const oid = url.searchParams.get('oid')
    const id = url.searchParams.get('id')
    if (oid && id) {
      const params = new URLSearchParams({ oid, id })
      const hash = url.searchParams.get('hash')
      if (hash) params.set('hash', hash)
      return `https://vkvideo.ru/video_ext.php?${params}`
    }
  }
  return null
}

// PeerTube (корпоративный video.mage.ru и другие self-hosted инстансы из
// настройки): watch-страницы запрещают фрейминг (X-Frame-Options: DENY), для
// встраивания есть канонические embed-пути. Конвертируем их. Софт сервера коду
// неизвестен (хосты приходят из runtime-настройки), поэтому распознавание — по
// формату пути PeerTube; не-PeerTube сервер таких путей не имеет, а ложная
// конвертация дала бы 404 внутри iframe при живой исходной ссылке рядом.
const PEERTUBE_UUID = String.raw`[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}`
// id видео PeerTube — uuid или короткий id (22 символа); id плейлиста — uuid или число.
const PEERTUBE_VIDEO_ID = `(?:${PEERTUBE_UUID}|[0-9a-zA-Z]{22})`
const PEERTUBE_PLAYLIST_ID = `(?:${PEERTUBE_UUID}|\\d+)`
const PEERTUBE_WATCH_PATHS: ReadonlyArray<readonly [RegExp, string]> = [
  [new RegExp(`^/videos/watch/(${PEERTUBE_VIDEO_ID})/?$`), '/videos/embed/{id}'],
  [new RegExp(`^/w/(${PEERTUBE_VIDEO_ID})/?$`), '/videos/embed/{id}'],
  [new RegExp(`^/videos/watch/playlist/(${PEERTUBE_PLAYLIST_ID})/?$`), '/video-playlists/embed/{id}'],
  [new RegExp(`^/w/p/(${PEERTUBE_PLAYLIST_ID})/?$`), '/video-playlists/embed/{id}'],
]

function peerTubeEmbedUrl(url: URL): string | null {
  for (const [re, template] of PEERTUBE_WATCH_PATHS) {
    const match = url.pathname.match(re)
    if (!match) continue
    // Search-параметры watch-страницы (start=…) валидны и для embed-плеера.
    return `${url.origin}${template.replace('{id}', match[1])}${url.search}`
  }
  return null
}

// Корпоративные видеосерверы (и любые другие origin'ы из списка, чей формат
// плеера коду не известен): ссылка пропускается как есть — сервер сам отдаёт
// embed-страницу. Исключение — PeerTube-пути (конвертируются, см. выше) и
// голый origin без пути: это не видео-плеер, а страница сервера, которую
// браузер не отдаст в iframe — материал остаётся обычной внешней ссылкой.
// Субдомены разрешённого origin'а покрыты и CSP frame-src.
function parseCorporate(url: URL, allowedOrigins: string[]): VideoEmbedInfo | null {
  for (const raw of allowedOrigins) {
    let allowed: URL
    try {
      allowed = new URL(raw)
    } catch {
      continue
    }
    if (allowed.protocol !== url.protocol) continue
    if (allowed.port !== url.port) continue
    const host = url.hostname
    const allowedHost = allowed.hostname
    if (host === allowedHost || host.endsWith(`.${allowedHost}`)) {
      const embedUrl = peerTubeEmbedUrl(url)
      if (embedUrl) return { embedUrl, provider: 'corporate' }
      if ((url.pathname === '' || url.pathname === '/') && !url.search && !url.hash) return null
      return { embedUrl: url.toString(), provider: 'corporate' }
    }
  }
  return null
}

/**
 * Origin'ы → имена хостов (для гейтов, проверяющих голый hostname: TipTap-узел
 * IframeEmbed, сетки тестов). Невалидные записи пропускаются — настройку мог
 * править админ вручную.
 */
export function hostsFromOrigins(origins: string[]): string[] {
  const hosts = new Set<string>()
  for (const raw of origins) {
    try {
      hosts.add(new URL(raw).hostname.toLowerCase())
    } catch {
      // невалидная запись настройки — пропускаем
    }
  }
  return [...hosts]
}

/**
 * Ссылка на видео → информация для встраивания; null — если это не видео
 * из доверенного списка или origin не разрешён настройкой (материал останется
 * внешней ссылкой).
 */
export function parseVideoEmbed(
  rawUrl: string,
  allowedOrigins: string[] = DEFAULT_VIDEO_IFRAME_ORIGINS,
): VideoEmbedInfo | null {
  if (!rawUrl) return null
  let url: URL
  try {
    url = new URL(rawUrl)
  } catch {
    return null
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return null

  const host = url.hostname.toLowerCase()
  for (const spec of PROVIDERS) {
    if (!spec.sourceHosts.has(host)) continue
    if (!allowedOrigins.includes(spec.embedOrigin)) return null
    const embedUrl = spec.convert(url)
    return embedUrl ? { embedUrl, provider: spec.provider } : null
  }
  return parseCorporate(url, allowedOrigins)
}
