import { describe, it, expectTypeOf } from 'vitest'
import type {
  PhotoFolderTreeNode,
  PhotoFolderTree,
  PhotoFolder,
  Photo,
  PhotoList,
  PhotoPermission,
  UploadResult,
  ShareLink,
  PhotoTag,
  BulkActionResponse,
  ZipJob,
} from '../../src/api/photos'
import type {
  KbSection,
  KbArticle,
  KbArticleListItem,
  KbArticleList,
  KbTag,
  KbComment,
  KbVersion,
  SearchResponse,
  FeedbackStats,
} from '../../src/api/kb'

describe('api/photos.ts — типы из OpenAPI схемы', () => {
  it('PhotoFolderTreeNode имеет обязательное поле children', () => {
    expectTypeOf<PhotoFolderTreeNode>().toHaveProperty('children')
    expectTypeOf<PhotoFolderTreeNode['children']>().toEqualTypeOf<PhotoFolderTreeNode[]>()
  })

  it('PhotoFolderTree.items содержит PhotoFolderTreeNode[]', () => {
    expectTypeOf<PhotoFolderTree['items']>().toEqualTypeOf<PhotoFolderTreeNode[]>()
  })

  it('PhotoFolder имеет обязательные поля id и name', () => {
    expectTypeOf<PhotoFolder>().toHaveProperty('id')
    expectTypeOf<PhotoFolder>().toHaveProperty('name')
    expectTypeOf<PhotoFolder['id']>().toBeString()
    expectTypeOf<PhotoFolder['name']>().toBeString()
  })

  it('Photo имеет обязательные поля id и original_name', () => {
    expectTypeOf<Photo>().toHaveProperty('id')
    expectTypeOf<Photo>().toHaveProperty('original_name')
  })

  it('PhotoList.items содержит Photo[]', () => {
    expectTypeOf<PhotoList['items']>().toEqualTypeOf<Photo[]>()
  })

  it('PhotoPermission имеет поле permission', () => {
    expectTypeOf<PhotoPermission>().toHaveProperty('permission')
  })

  it('UploadResult.items существует', () => {
    expectTypeOf<UploadResult>().toHaveProperty('items')
  })

  it('ShareLink имеет поле token', () => {
    expectTypeOf<ShareLink>().toHaveProperty('token')
    expectTypeOf<ShareLink['token']>().toBeString()
  })

  it('PhotoTag имеет поля id и name', () => {
    expectTypeOf<PhotoTag>().toHaveProperty('id')
    expectTypeOf<PhotoTag>().toHaveProperty('name')
  })

  it('BulkActionResponse имеет поле affected', () => {
    expectTypeOf<BulkActionResponse>().toHaveProperty('affected')
    expectTypeOf<BulkActionResponse['affected']>().toBeNumber()
  })

  it('ZipJob имеет поле status', () => {
    expectTypeOf<ZipJob>().toHaveProperty('status')
  })
})

describe('api/kb.ts — типы из OpenAPI схемы', () => {
  it('KbSection имеет обязательное поле children', () => {
    expectTypeOf<KbSection>().toHaveProperty('children')
    expectTypeOf<KbSection['children']>().toEqualTypeOf<KbSection[]>()
  })

  it('KbSection имеет обязательные поля id и title', () => {
    expectTypeOf<KbSection['id']>().toBeString()
    expectTypeOf<KbSection['title']>().toBeString()
  })

  it('KbArticle имеет строго типизированный статус', () => {
    expectTypeOf<KbArticle['status']>().toEqualTypeOf<'draft' | 'published' | 'archived'>()
  })

  it('KbArticle.tags обязательно (не undefined)', () => {
    expectTypeOf<KbArticle['tags']>().toEqualTypeOf<KbTag[]>()
  })

  it('KbArticleListItem.tags обязательно (не undefined)', () => {
    expectTypeOf<KbArticleListItem['tags']>().toEqualTypeOf<KbTag[]>()
  })

  it('KbArticleList.items содержит KbArticleListItem[]', () => {
    expectTypeOf<KbArticleList['items']>().toEqualTypeOf<KbArticleListItem[]>()
  })

  it('KbArticleList имеет поля total, limit, offset', () => {
    expectTypeOf<KbArticleList['total']>().toBeNumber()
    expectTypeOf<KbArticleList['limit']>().toBeNumber()
    expectTypeOf<KbArticleList['offset']>().toBeNumber()
  })

  it('KbTag имеет поля id, name, slug', () => {
    expectTypeOf<KbTag>().toHaveProperty('id')
    expectTypeOf<KbTag>().toHaveProperty('name')
    expectTypeOf<KbTag>().toHaveProperty('slug')
  })

  it('KbComment имеет поле body', () => {
    expectTypeOf<KbComment>().toHaveProperty('body')
    expectTypeOf<KbComment['body']>().toBeString()
  })

  it('KbVersion имеет поле version_number', () => {
    expectTypeOf<KbVersion>().toHaveProperty('version_number')
  })

  it('SearchResponse имеет поле items', () => {
    expectTypeOf<SearchResponse>().toHaveProperty('items')
  })

  it('FeedbackStats имеет числовые счётчики', () => {
    expectTypeOf<FeedbackStats>().toHaveProperty('helpful_count')
    expectTypeOf<FeedbackStats>().toHaveProperty('not_helpful_count')
  })
})
