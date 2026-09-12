import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockApi = vi.fn()
const mockApiUpload = vi.fn()
const mockOfetch = vi.fn()

vi.mock('ofetch', () => ({ ofetch: mockOfetch }))

vi.mock('../../src/api/index', () => ({
  api: mockApi,
  apiUpload: mockApiUpload,
  BASE_URL: '/api/v1',
}))

describe('src/api/learning', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetchAdminCourses passes search params', async () => {
    const { fetchAdminCourses } = await import('../../src/api/learning')
    mockApi.mockResolvedValueOnce({ items: [], total: 0, limit: 20, offset: 0 })
    await fetchAdminCourses({ q: 'охрана', limit: 20, offset: 20 })
    expect(mockApi).toHaveBeenCalledWith('/learning/admin/courses', {
      query: { q: 'охрана', limit: 20, offset: 20 },
    })
  })

  it('category CRUD maps to /learning/admin/categories', async () => {
    const mod = await import('../../src/api/learning')
    mockApi.mockResolvedValueOnce([])
    await mod.fetchCategories()
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/categories')

    await mod.createCategory({ title: 'К' })
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/categories', {
      method: 'POST',
      body: { title: 'К' },
    })

    await mod.updateCategory('k1', { title: 'Н' })
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/categories/k1', {
      method: 'PATCH',
      body: { title: 'Н' },
    })

    await mod.reorderCategories({ ordered_ids: ['b', 'a'] })
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/categories/reorder', {
      method: 'POST',
      body: { ordered_ids: ['b', 'a'] },
    })

    await mod.deleteCategory('k1')
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/categories/k1', {
      method: 'DELETE',
    })
  })

  it('createCourse posts body', async () => {
    const { createCourse } = await import('../../src/api/learning')
    mockApi.mockResolvedValueOnce({ id: 'c1' })
    const body = { title: 'Курс', description: null, slug: null, for_all_staff: false }
    await createCourse(body)
    expect(mockApi).toHaveBeenCalledWith('/learning/admin/courses', { method: 'POST', body })
  })

  it('setCoursePublished picks publish/unpublish path', async () => {
    const { setCoursePublished } = await import('../../src/api/learning')
    mockApi.mockResolvedValue({ ok: true })
    await setCoursePublished('cid', true)
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/cid/publish', { method: 'POST' })
    await setCoursePublished('cid', false)
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/cid/unpublish', { method: 'POST' })
  })

  it('enrollParticipant posts XOR body', async () => {
    const { enrollParticipant } = await import('../../src/api/learning')
    mockApi.mockResolvedValueOnce({ ok: true, participant_id: 'p1' })
    await enrollParticipant('cid', { user_id: 'u1', learning_account_id: null })
    expect(mockApi).toHaveBeenCalledWith('/learning/admin/courses/cid/participants', {
      method: 'POST',
      body: { user_id: 'u1', learning_account_id: null },
    })
  })

  it('uploadMaterialFile posts FormData to item file endpoint', async () => {
    const { uploadMaterialFile } = await import('../../src/api/learning')
    mockApiUpload.mockResolvedValueOnce({ ok: true, file_path: '/data/x.pdf', mime: 'application/pdf' })
    const file = new File(['x'], 'a.pdf', { type: 'application/pdf' })
    await uploadMaterialFile('iid', file)
    expect(mockApiUpload).toHaveBeenCalledTimes(1)
    const [path, form] = mockApiUpload.mock.calls[0]
    expect(path).toBe('/learning/admin/courses/items/iid/file')
    expect(form.get('file')).toBe(file)
  })

  it('uploadCourseCover posts FormData to course cover endpoint', async () => {
    const { uploadCourseCover } = await import('../../src/api/learning')
    mockApiUpload.mockResolvedValueOnce({ id: 'cid', cover_url: '/x?v=1' })
    const file = new File(['x'], 'cover.png', { type: 'image/png' })
    await uploadCourseCover('cid', file)
    expect(mockApiUpload).toHaveBeenCalledTimes(1)
    const [path, form] = mockApiUpload.mock.calls[0]
    expect(path).toBe('/learning/admin/courses/cid/cover')
    expect(form.get('file')).toBe(file)
  })

  it('deleteCourseCover DELETE-ит course cover endpoint', async () => {
    const { deleteCourseCover } = await import('../../src/api/learning')
    mockApi.mockResolvedValueOnce({ id: 'cid', cover_url: null })
    await deleteCourseCover('cid')
    expect(mockApi).toHaveBeenCalledWith('/learning/admin/courses/cid/cover', { method: 'DELETE' })
  })

  it('bulkEnrollParticipants posts user_ids list', async () => {
    const { bulkEnrollParticipants } = await import('../../src/api/learning')
    mockApi.mockResolvedValueOnce({ enrolled: 2, skipped_duplicates: 1, errors: [] })
    await bulkEnrollParticipants('cid', ['u1', 'u2'])
    expect(mockApi).toHaveBeenCalledWith('/learning/admin/courses/cid/participants/bulk', {
      method: 'POST',
      body: { user_ids: ['u1', 'u2'] },
    })
  })

  it('question endpoints hit nested item paths', async () => {
    const { addQuestion, updateQuestion, deleteQuestion } = await import('../../src/api/learning')
    mockApi.mockResolvedValue({ ok: true })
    const body = { text: 'Q', multi: false, options: [{ text: 'a', is_correct: true }] }
    await addQuestion('iid', body)
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/items/iid/questions', {
      method: 'POST',
      body,
    })
    await updateQuestion('iid', 'qid', body)
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/items/iid/questions/qid', {
      method: 'PATCH',
      body,
    })
    await deleteQuestion('iid', 'qid')
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/items/iid/questions/qid', {
      method: 'DELETE',
    })
  })

  it('account mutations hit block/unblock/login-code endpoints', async () => {
    const { blockLearningAccount, unblockLearningAccount, issueLearningAccountLoginCode } =
      await import('../../src/api/learning')
    mockApi.mockResolvedValue({ ok: true })
    await blockLearningAccount('a1')
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/accounts/a1/block', { method: 'POST' })
    await unblockLearningAccount('a1')
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/accounts/a1/unblock', { method: 'POST' })
    // ручная выдача одноразового кода входа (passwordless, миграция 113)
    mockApi.mockResolvedValue({ code: '123456', expires_at: '2026-09-04T12:10:00Z' })
    await issueLearningAccountLoginCode('a1')
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/accounts/a1/login-code', {
      method: 'POST',
    })
  })

  it('imports xlsx as multipart and downloads template as blob', async () => {
    const { importLearningAccounts, downloadLearningAccountsTemplate } =
      await import('../../src/api/learning')
    const file = new File(['xlsx'], 'accounts.xlsx')
    mockApiUpload.mockResolvedValueOnce({ created: 1, skipped_duplicates: 0, error_count: 0, errors: [] })
    await importLearningAccounts(file)
    const [path, form] = mockApiUpload.mock.calls[0]
    expect(path).toBe('/learning/admin/accounts/import')
    expect(form.get('file')).toBe(file)

    const blob = new Blob(['template'])
    mockOfetch.mockResolvedValueOnce(blob)
    await expect(downloadLearningAccountsTemplate()).resolves.toBe(blob)
    expect(mockOfetch).toHaveBeenCalledWith('/learning/admin/accounts/template', {
      baseURL: '/api/v1',
      credentials: 'include',
      responseType: 'blob',
    })
  })

  it('question import: template blob + preview/import multipart', async () => {
    const { downloadQuestionsTemplate, previewQuestionsImport, importQuestions } =
      await import('../../src/api/learning')
    const file = new File(['xlsx'], 'questions.xlsx')

    const blob = new Blob(['tpl'])
    mockOfetch.mockResolvedValueOnce(blob)
    await expect(downloadQuestionsTemplate('iid')).resolves.toBe(blob)
    expect(mockOfetch).toHaveBeenCalledWith(
      '/learning/admin/courses/items/iid/questions/template',
      { baseURL: '/api/v1', credentials: 'include', responseType: 'blob' },
    )

    mockApiUpload.mockResolvedValueOnce({ questions: [], errors: [] })
    await previewQuestionsImport('iid', file)
    let [path, form] = mockApiUpload.mock.calls[0]
    expect(path).toBe('/learning/admin/courses/items/iid/questions/import/preview')
    expect(form.get('file')).toBe(file)

    mockApiUpload.mockResolvedValueOnce({ created: 1, errors: [] })
    await importQuestions('iid', file)
    ;[path, form] = mockApiUpload.mock.calls[1]
    expect(path).toBe('/learning/admin/courses/items/iid/questions/import')
    expect(form.get('file')).toBe(file)
  })

  it('fetchMyCourses reads learner endpoint', async () => {
    const { fetchMyCourses } = await import('../../src/api/learning')
    mockApi.mockResolvedValueOnce([])
    await fetchMyCourses()
    expect(mockApi).toHaveBeenCalledWith('/learning/me/courses')
  })
})

describe('queryKeys.learning', () => {
  it('builds stable hierarchical keys', async () => {
    const { queryKeys } = await import('../../src/queries/keys')
    expect(queryKeys.learning.myCourses()).toEqual(['learning', 'my-courses'])
    expect(queryKeys.learning.adminCourses({ q: 'x' })).toEqual(['learning', 'admin-courses', { q: 'x' }])
    expect(queryKeys.learning.adminCourse('c1')).toEqual(['learning', 'admin-course', 'c1'])
    expect(queryKeys.learning.adminProgress('c1')).toEqual(['learning', 'admin-progress', 'c1'])
    expect(queryKeys.learning.adminTest('i1')).toEqual(['learning', 'admin-test', 'i1'])
    expect(queryKeys.learning.adminAccounts({ q: 'a' })).toEqual(['learning', 'admin-accounts', { q: 'a' }])
  })
})

describe('src/api/learning — остальные эндпоинты', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockResolvedValue({ ok: true })
  })

  it('fetchAdminCourse / updateCourse / fetchCourseProgress', async () => {
    const { fetchAdminCourse, updateCourse, fetchCourseProgress } = await import('../../src/api/learning')
    await fetchAdminCourse('c1')
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/c1')
    await updateCourse('c1', { title: 'N' })
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/c1', {
      method: 'PATCH',
      body: { title: 'N' },
    })
    await fetchCourseProgress('c1')
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/c1/progress')
  })

  it('item update/delete hit items collection', async () => {
    const { updateCourseItem, deleteCourseItem } = await import('../../src/api/learning')
    await updateCourseItem('i1', { title: 'N' })
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/items/i1', {
      method: 'PATCH',
      body: { title: 'N' },
    })
    await deleteCourseItem('i1')
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/items/i1', { method: 'DELETE' })
  })

  it('reorder posts ordered_ids', async () => {
    const { reorderCourseItems } = await import('../../src/api/learning')
    await reorderCourseItems('c1', ['b', 'a'])
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/c1/items/reorder', {
      method: 'POST',
      body: { ordered_ids: ['b', 'a'] },
    })
  })

  it('test config get/patch', async () => {
    const { fetchTestConfig, updateTestSettings } = await import('../../src/api/learning')
    mockApi.mockResolvedValueOnce({ pass_score: 70, questions: [] })
    await fetchTestConfig('i1')
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/items/i1/test')
    await updateTestSettings('i1', { pass_score: 50 })
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/items/i1/test', {
      method: 'PATCH',
      body: { pass_score: 50 },
    })
  })

  it('unenroll DELETEs participant', async () => {
    const { unenrollParticipant } = await import('../../src/api/learning')
    await unenrollParticipant('c1', 'p1')
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/c1/participants/p1', {
      method: 'DELETE',
    })
  })

  it('participant items/reset/certificate hit admin participant paths', async () => {
    const { fetchParticipantItems, resetParticipantAttempts, fetchParticipantCertificateBlob } = await import('../../src/api/learning')
    mockApi.mockResolvedValueOnce({ participant_id: 'p1', items: [] })
    await fetchParticipantItems('c1', 'p1')
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/c1/participants/p1/items')

    mockApi.mockResolvedValueOnce({ ok: true, deleted_attempts: 2 })
    await resetParticipantAttempts('c1', 'p1', 'i1')
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/c1/participants/p1/items/i1/reset-attempts', {
      method: 'POST',
    })

    mockOfetch.mockResolvedValueOnce(new Blob(['pdf'], { type: 'application/pdf' }))
    await fetchParticipantCertificateBlob('c1', 'p1')
    expect(mockOfetch).toHaveBeenLastCalledWith('/learning/admin/courses/c1/participants/p1/certificate', {
      baseURL: '/api/v1',
      credentials: 'include',
      responseType: 'blob',
    })
  })

  it('fetchLearningAccounts passes filters', async () => {
    const { fetchLearningAccounts } = await import('../../src/api/learning')
    mockApi.mockResolvedValueOnce({ items: [], total: 0, limit: 10, offset: 0 })
    await fetchLearningAccounts({ q: 'иван', limit: 10, offset: 0 })
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/accounts', {
      query: { q: 'иван', limit: 10, offset: 0 },
    })
  })
})

describe('src/api/learning — delete/create прямые вызовы', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.mockResolvedValue({ ok: true })
  })

  it('deleteCourse DELETEs by id', async () => {
    const { deleteCourse } = await import('../../src/api/learning')
    await deleteCourse('c1')
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/c1', { method: 'DELETE' })
  })

  it('addCourseItem posts type+title', async () => {
    const { addCourseItem } = await import('../../src/api/learning')
    mockApi.mockResolvedValueOnce({ id: 'i9', sort_order: 3 })
    await addCourseItem('c1', { type: 'test', title: 'Т' })
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/courses/c1/items', {
      method: 'POST',
      body: { type: 'test', title: 'Т' },
    })
  })

  it('createLearningAccount posts body', async () => {
    const { createLearningAccount } = await import('../../src/api/learning')
    mockApi.mockResolvedValueOnce({ id: 'a9' })
    await createLearningAccount({ email: 'a@b', full_name: 'A' })
    expect(mockApi).toHaveBeenLastCalledWith('/learning/admin/accounts', {
      method: 'POST',
      body: { email: 'a@b', full_name: 'A' },
    })
  })

  it('fetchLearningAdmins GETs the collection', async () => {
    const { fetchLearningAdmins } = await import('../../src/api/learning')
    mockApi.mockResolvedValueOnce([])
    await fetchLearningAdmins()
    expect(mockApi).toHaveBeenCalledWith('/learning/admins')
  })

  it('assignLearningAdmin posts user_id', async () => {
    const { assignLearningAdmin } = await import('../../src/api/learning')
    mockApi.mockResolvedValueOnce({ ok: true, user_id: 'u1' })
    await assignLearningAdmin({ user_id: 'u1' })
    expect(mockApi).toHaveBeenCalledWith('/learning/admins', { method: 'POST', body: { user_id: 'u1' } })
  })

  it('revokeLearningAdmin DELETEs by user_id', async () => {
    const { revokeLearningAdmin } = await import('../../src/api/learning')
    mockApi.mockResolvedValueOnce({ ok: true })
    await revokeLearningAdmin('u1')
    expect(mockApi).toHaveBeenCalledWith('/learning/admins/u1', { method: 'DELETE' })
  })
})

describe('URL-билдеры (ревью 2026-08-30)', () => {
  it('certificateFileUrl строит ссылку стриминга сертификата', async () => {
    const { certificateFileUrl } = await import('../../src/api/learning')
    expect(certificateFileUrl('kurs-1')).toBe('/api/v1/learning/me/courses/kurs-1/certificate')
  })
})
