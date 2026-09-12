import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

/**
 * Видео в материалах курса: разбор ссылок (utils/videoEmbed) и клик-плей
 * компонент VideoEmbed. Allowlist зеркалит CSP frame-src (render-config.sh)
 * — «умеет больше, чем CSP» парсер не должен.
 */

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: ref('ru') }),
}))

import { parseVideoEmbed, hostsFromOrigins, DEFAULT_VIDEO_IFRAME_ORIGINS } from '../../src/utils/videoEmbed'
import VideoEmbed from '../../src/components/learning/VideoEmbed.vue'

describe('parseVideoEmbed', () => {
  it('youtube: watch / shorts / youtu.be / embed → youtube-nocookie', () => {
    for (const url of [
      'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
      'https://youtube.com/watch?v=dQw4w9WgXcQ&t=30s',
      'https://m.youtube.com/watch?v=dQw4w9WgXcQ',
      'https://youtu.be/dQw4w9WgXcQ',
      'https://www.youtube.com/shorts/dQw4w9WgXcQ',
      'https://www.youtube.com/embed/dQw4w9WgXcQ',
    ]) {
      expect(parseVideoEmbed(url)).toEqual({
        embedUrl: 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ',
        provider: 'youtube',
      })
    }
  })

  it('youtube: watch без v или неизвестный путь — null', () => {
    expect(parseVideoEmbed('https://www.youtube.com/watch?list=abc')).toBeNull()
    expect(parseVideoEmbed('https://www.youtube.com/channel/abc')).toBeNull()
  })

  it('rutube: /video/<id>/ → /play/embed/<id>, готовый embed — как есть', () => {
    expect(parseVideoEmbed('https://rutube.ru/video/abc123def0/')).toEqual({
      embedUrl: 'https://rutube.ru/play/embed/abc123def0',
      provider: 'rutube',
    })
    expect(parseVideoEmbed('https://rutube.ru/play/embed/abc123def0')).toEqual({
      embedUrl: 'https://rutube.ru/play/embed/abc123def0',
      provider: 'rutube',
    })
    expect(parseVideoEmbed('https://rutube.ru/video/not-hex/')).toBeNull()
  })

  it('vk: /video<oid>_<id>[_hash] → video_ext.php на vkvideo.ru', () => {
    expect(parseVideoEmbed('https://vk.com/video-12345_67890')).toEqual({
      embedUrl: 'https://vkvideo.ru/video_ext.php?oid=-12345&id=67890',
      provider: 'vk',
    })
    expect(parseVideoEmbed('https://vkvideo.ru/video-12345_67890_ab12cd')).toEqual({
      embedUrl: 'https://vkvideo.ru/video_ext.php?oid=-12345&id=67890&hash=ab12cd',
      provider: 'vk',
    })
    expect(parseVideoEmbed('https://m.vk.com/video9_87654321')).toEqual({
      embedUrl: 'https://vkvideo.ru/video_ext.php?oid=9&id=87654321',
      provider: 'vk',
    })
  })

  it('vk: готовый video_ext.php нормализует хост, сохраняя hash', () => {
    expect(
      parseVideoEmbed('https://vk.com/video_ext.php?oid=-7&id=42&hash=zz9'),
    ).toEqual({
      embedUrl: 'https://vkvideo.ru/video_ext.php?oid=-7&id=42&hash=zz9',
      provider: 'vk',
    })
    expect(parseVideoEmbed('https://vk.com/video_ext.php?oid=-7')).toBeNull()
  })

  it('vimeo: /<id> → player.vimeo.com, готовый embed — как есть', () => {
    expect(parseVideoEmbed('https://vimeo.com/76979871')).toEqual({
      embedUrl: 'https://player.vimeo.com/video/76979871',
      provider: 'vimeo',
    })
    expect(parseVideoEmbed('https://player.vimeo.com/video/76979871')).toEqual({
      embedUrl: 'https://player.vimeo.com/video/76979871',
      provider: 'vimeo',
    })
    expect(parseVideoEmbed('https://vimeo.com/channels/staffpicks')).toBeNull()
  })

  it('peertube (video.mage.ru): watch → embed-путь (uuid и короткий id)', () => {
    expect(
      parseVideoEmbed('https://video.mage.ru/videos/watch/44e4d865-ad2e-4702-b5cc-0d64f8dd1de3'),
    ).toEqual({
      embedUrl: 'https://video.mage.ru/videos/embed/44e4d865-ad2e-4702-b5cc-0d64f8dd1de3',
      provider: 'corporate',
    })
    // /w/<shortUUID> — короткая ссылка из кнопки «Поделиться» PeerTube
    expect(parseVideoEmbed('https://video.mage.ru/w/9vqBpmmUiwkrqFwLfpnH8i')).toEqual({
      embedUrl: 'https://video.mage.ru/videos/embed/9vqBpmmUiwkrqFwLfpnH8i',
      provider: 'corporate',
    })
    // готовый embed-URL — как есть
    expect(
      parseVideoEmbed('https://video.mage.ru/videos/embed/44e4d865-ad2e-4702-b5cc-0d64f8dd1de3'),
    ).toEqual({
      embedUrl: 'https://video.mage.ru/videos/embed/44e4d865-ad2e-4702-b5cc-0d64f8dd1de3',
      provider: 'corporate',
    })
  })

  it('peertube: плейлисты и search-параметры', () => {
    expect(parseVideoEmbed('https://video.mage.ru/w/p/12')).toEqual({
      embedUrl: 'https://video.mage.ru/video-playlists/embed/12',
      provider: 'corporate',
    })
    expect(parseVideoEmbed('https://video.mage.ru/videos/watch/playlist/12')).toEqual({
      embedUrl: 'https://video.mage.ru/video-playlists/embed/12',
      provider: 'corporate',
    })
    // start=… валиден и для embed-плеера — сохраняется
    expect(
      parseVideoEmbed('https://video.mage.ru/w/9vqBpmmUiwkrqFwLfpnH8i?start=1m30s'),
    ).toEqual({
      embedUrl: 'https://video.mage.ru/videos/embed/9vqBpmmUiwkrqFwLfpnH8i?start=1m30s',
      provider: 'corporate',
    })
  })

  it('peertube: не-видео пути и голый origin сервера — не плеер', () => {
    // путь не похож на PeerTube — пропускается как есть (прочие корпоративные
    // серверы), конвертации нет
    expect(parseVideoEmbed('https://video.mage.ru/videos/9')).toEqual({
      embedUrl: 'https://video.mage.ru/videos/9',
      provider: 'corporate',
    })
    // голый origin — не видео: материал остаётся внешней ссылкой
    // (иначе iframe получает страницу сервера с X-Frame-Options: DENY)
    expect(parseVideoEmbed('https://video.mage.ru/')).toBeNull()
    expect(parseVideoEmbed('https://video.mage.ru')).toBeNull()
    expect(parseVideoEmbed('https://cdn.video.mage.ru/', DEFAULT_VIDEO_IFRAME_ORIGINS)).toBeNull()
  })

  it('субдомены разрешённого origin (не PeerTube-пути) — как есть', () => {
    expect(parseVideoEmbed('https://cdn.video.mage.ru/embed/9')).toEqual({
      embedUrl: 'https://cdn.video.mage.ru/embed/9',
      provider: 'corporate',
    })
  })

  it('не-видео и небезопасное — null (материал остаётся внешней ссылкой)', () => {
    expect(parseVideoEmbed('https://example.com/article')).toBeNull()
    expect(parseVideoEmbed('https://vimeo.evil.com/video/1')).toBeNull()
    expect(parseVideoEmbed('javascript:alert(1)')).toBeNull()
    expect(parseVideoEmbed('ftp://rutube.ru/video/abc123def0/')).toBeNull()
    expect(parseVideoEmbed('не ссылка')).toBeNull()
    expect(parseVideoEmbed('')).toBeNull()
  })

  it('гейт по настройке: убранный из списка провайдер → null', () => {
    const origins = ['https://video.mage.ru', 'https://rutube.ru']
    // rutube разрешён — встраиваем
    expect(parseVideoEmbed('https://rutube.ru/video/abc123def0/', origins)).not.toBeNull()
    // youtube разрешён только при youtube-nocookie в списке (embed-origin)
    expect(parseVideoEmbed('https://youtu.be/dQw4w9WgXcQ', origins)).toBeNull()
    // vk: нужен vkvideo.ru — embed- origin, не vk.com
    expect(parseVideoEmbed('https://vk.com/video-1_2', [...origins, 'https://vk.com'])).toBeNull()
    expect(parseVideoEmbed('https://vk.com/video-1_2', [...origins, 'https://vkvideo.ru'])).not.toBeNull()
  })

  it('пустой список настройки — встраивание полностью выключено', () => {
    expect(parseVideoEmbed('https://rutube.ru/video/abc123def0/', [])).toBeNull()
    expect(parseVideoEmbed('https://video.mage.ru/embed/9', [])).toBeNull()
  })

  it('корпоративный origin из настройки: субдомены разрешены, чужие — нет', () => {
    const origins = ['http://video.lan:8080']
    expect(parseVideoEmbed('http://video.lan:8080/watch/42', origins)).toEqual({
      embedUrl: 'http://video.lan:8080/watch/42',
      provider: 'corporate',
    })
    expect(parseVideoEmbed('http://cdn.video.lan:8080/watch/42', origins)).toEqual({
      embedUrl: 'http://cdn.video.lan:8080/watch/42',
      provider: 'corporate',
    })
    expect(parseVideoEmbed('https://video.lan:8080/watch/42', origins)).toBeNull()
    expect(parseVideoEmbed('http://video.lan/watch/42', origins)).toBeNull()
  })

  it('без явного списка используется дефолт (зеркало DEFAULT_VIDEO_IFRAME_ORIGINS)', () => {
    expect(parseVideoEmbed('https://video.mage.ru/embed/9', DEFAULT_VIDEO_IFRAME_ORIGINS)).toEqual(
      parseVideoEmbed('https://video.mage.ru/embed/9'),
    )
  })
})

describe('hostsFromOrigins', () => {
  it('origin → hostname (без порта, lowercase), дедупликация', () => {
    expect(
      hostsFromOrigins([
        'https://video.mage.ru',
        'http://VIDEO.Mage.ru:8443',
        'https://rutube.ru',
        'https://rutube.ru',
      ]),
    ).toEqual(['video.mage.ru', 'rutube.ru'])
  })

  it('невалидные записи пропускаются, пустой список → пусто', () => {
    expect(hostsFromOrigins(['не origin', ''])).toEqual([])
    expect(hostsFromOrigins([])).toEqual([])
  })
})

describe('VideoEmbed', () => {
  it('iframe рендерится сразу (как в новостях): embed-URL, sandbox, allowfullscreen', () => {
    const w = mount(VideoEmbed, {
      props: { url: 'https://vk.com/video-12345_67890', title: 'Инструкция' },
    })
    const iframe = w.find('iframe')
    expect(iframe.exists()).toBe(true)
    expect(iframe.attributes('src')).toBe('https://vkvideo.ru/video_ext.php?oid=-12345&id=67890')
    expect(iframe.attributes('sandbox')).toContain('allow-scripts')
    expect(iframe.attributes('allowfullscreen')).toBeDefined()
    expect(iframe.attributes('loading')).toBe('lazy')
    expect(iframe.attributes('title')).toBe('Инструкция')
  })

  it('peertube-ссылка: iframe с embed-URL, не watch-страницей', () => {
    const w = mount(VideoEmbed, {
      props: { url: 'https://video.mage.ru/videos/watch/44e4d865-ad2e-4702-b5cc-0d64f8dd1de3' },
    })
    expect(w.find('iframe').attributes('src')).toBe(
      'https://video.mage.ru/videos/embed/44e4d865-ad2e-4702-b5cc-0d64f8dd1de3',
    )
  })

  it('смена url подменяет src iframe', async () => {
    const w = mount(VideoEmbed, { props: { url: 'https://rutube.ru/video/abc123def0/' } })
    expect(w.find('iframe').attributes('src')).toBe('https://rutube.ru/play/embed/abc123def0')

    await w.setProps({ url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' })
    expect(w.find('iframe').attributes('src')).toBe('https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ')
  })

  it('неразрешённая ссылка — iframe не рендерится (страховка, карточка такое не пропускает)', () => {
    const w = mount(VideoEmbed, { props: { url: 'https://example.com/article' } })
    expect(w.find('iframe').exists()).toBe(false)
  })
})
