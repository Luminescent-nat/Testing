import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const { logoutMock, userState } = vi.hoisted(() => ({
  logoutMock: vi.fn(),
  userState: { token: null }
}))

vi.mock('@/store/user', () => ({
  useUserStore: () => ({ token: userState.token, logout: logoutMock })
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn() }
}))

import client, {
  ApiError,
  generateIdempotencyKey,
  getPcIdentifier,
  isSuccessEnvelope,
  isValidIdempotencyKey,
  normalizeErrorPayload,
  resolveIdempotencyKey,
  shouldAttachIdempotencyKey
} from '@/api/client'

const createLocalStorageMock = () => {
  const store = new Map()
  return {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
    clear: () => store.clear()
  }
}

const capture = { config: null }

const jsonAdapter = (status, data) => async (config) => {
  capture.config = config
  const response = { data, status, statusText: '', headers: {}, config, request: {} }
  if (status >= 300) {
    const error = new Error(`Request failed with status code ${status}`)
    error.response = response
    error.config = config
    error.isAxiosError = true
    throw error
  }
  return response
}

const readHeader = (config, name) => {
  const headers = config?.headers || {}
  if (typeof headers.get === 'function') return headers.get(name)
  return headers[name]
}

beforeEach(() => {
  vi.stubGlobal('localStorage', createLocalStorageMock())
  capture.config = null
  logoutMock.mockClear()
  userState.token = null
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('generateIdempotencyKey / isValidIdempotencyKey', () => {
  it('生成的键为 8～128 位可打印 ASCII 且不重复', () => {
    const a = generateIdempotencyKey()
    const b = generateIdempotencyKey()
    expect(a.length).toBeGreaterThanOrEqual(8)
    expect(a.length).toBeLessThanOrEqual(128)
    expect(a).toMatch(/^[\x20-\x7e]+$/)
    expect(a).not.toBe(b)
  })

  it('校验长度与字符集边界', () => {
    expect(isValidIdempotencyKey('12345678')).toBe(true)
    expect(isValidIdempotencyKey('1234567')).toBe(false)
    expect(isValidIdempotencyKey('x'.repeat(128))).toBe(true)
    expect(isValidIdempotencyKey('x'.repeat(129))).toBe(false)
    expect(isValidIdempotencyKey('bad\nkey-123')).toBe(false)
    expect(isValidIdempotencyKey('中文-key-123')).toBe(false)
    expect(isValidIdempotencyKey(undefined)).toBe(false)
  })
})

describe('shouldAttachIdempotencyKey', () => {
  it('仅 POST 任务创建/重跑需要幂等键', () => {
    expect(shouldAttachIdempotencyKey({ method: 'post', url: '/tasks' })).toBe(true)
    expect(shouldAttachIdempotencyKey({ method: 'POST', url: '/tasks/9/reruns' })).toBe(true)
    expect(shouldAttachIdempotencyKey({ method: 'POST', url: '/tasks/9/rerun-failed' })).toBe(true)
    expect(shouldAttachIdempotencyKey({ method: 'POST', url: '/api/v1/tasks?x=1' })).toBe(true)
  })

  it('其他写操作/查询不附加幂等键', () => {
    expect(shouldAttachIdempotencyKey({ method: 'POST', url: '/devices/refresh' })).toBe(false)
    expect(shouldAttachIdempotencyKey({ method: 'POST', url: '/tasks/9/cancel' })).toBe(false)
    expect(shouldAttachIdempotencyKey({ method: 'GET', url: '/tasks' })).toBe(false)
    expect(shouldAttachIdempotencyKey({ method: 'PUT', url: '/tasks/9' })).toBe(false)
  })
})

describe('resolveIdempotencyKey', () => {
  it('任务创建立即生成合法键', () => {
    const key = resolveIdempotencyKey({ method: 'post', url: '/tasks', headers: {} })
    expect(isValidIdempotencyKey(key)).toBe(true)
  })

  it('调用方传入合法键时优先使用', () => {
    const key = resolveIdempotencyKey({
      method: 'post',
      url: '/tasks',
      headers: {},
      idempotencyKey: 'caller-key-123'
    })
    expect(key).toBe('caller-key-123')
  })

  it('调用方传入非法键时抛出可追溯错误', () => {
    expect(() =>
      resolveIdempotencyKey({ method: 'post', url: '/tasks', headers: {}, idempotencyKey: 'short' })
    ).toThrowError(ApiError)
    try {
      resolveIdempotencyKey({ method: 'post', url: '/tasks', headers: {}, idempotencyKey: 'short' })
    } catch (error) {
      expect(error.code).toBe('CLIENT_INVALID_IDEMPOTENCY_KEY')
    }
  })

  it('非幂等端点返回 null', () => {
    expect(resolveIdempotencyKey({ method: 'get', url: '/tasks', headers: {} })).toBeNull()
  })
})

describe('normalizeErrorPayload', () => {
  it('新契约错误外层解析 code/message/details', () => {
    const normalized = normalizeErrorPayload(
      { code: 'VALIDATION_ERROR', message: '任务参数不合法', details: { field: 'x.y' } },
      400
    )
    expect(normalized).toMatchObject({
      code: 'VALIDATION_ERROR',
      rawMessage: '任务参数不合法',
      details: { field: 'x.y' },
      httpStatus: 400,
      legacy: false
    })
  })

  it('legacy {detail:string} 解析并标记 legacy', () => {
    const normalized = normalizeErrorPayload({ detail: '设备不存在' }, 404)
    expect(normalized.code).toBe('NOT_FOUND')
    expect(normalized.rawMessage).toBe('设备不存在')
    expect(normalized.legacy).toBe(true)
  })

  it('legacy DRF detail 数组解析字段路径与消息', () => {
    const normalized = normalizeErrorPayload(
      { detail: [{ loc: ['body', 'name'], msg: '不能为空' }] },
      422
    )
    expect(normalized.rawMessage).toContain('name: 不能为空')
    expect(normalized.code).toBe('VALIDATION_ERROR')
    expect(normalized.details.errors).toHaveLength(1)
  })

  it('legacy {errors:object} 归入 details.errors', () => {
    const normalized = normalizeErrorPayload({ errors: { name: ['必填'] } }, 400)
    expect(normalized.details).toEqual({ errors: { name: ['必填'] } })
    expect(normalized.legacy).toBe(true)
  })

  it('legacy 数字 code 映射为契约码', () => {
    const normalized = normalizeErrorPayload({ code: 403, message: '需要管理员权限' }, 200)
    expect(normalized.code).toBe('FORBIDDEN')
    expect(normalized.legacy).toBe(true)
  })

  it('无错误体时按 HTTP 状态映射', () => {
    expect(normalizeErrorPayload(null, 503).code).toBe('SERVICE_UNAVAILABLE')
    expect(normalizeErrorPayload(undefined, 500).code).toBe('INTERNAL_ERROR')
  })
})

describe('isSuccessEnvelope', () => {
  it('识别成功与错误外层', () => {
    expect(isSuccessEnvelope({ code: 200, data: {} })).toBe(true)
    expect(isSuccessEnvelope({ code: 201, data: {} })).toBe(true)
    expect(isSuccessEnvelope({ code: 400, message: 'x' })).toBe(false)
    expect(isSuccessEnvelope({ code: 'VALIDATION_ERROR' })).toBe(false)
  })

  it('无 code 的裸响应体按旧实现语义视为异常', () => {
    expect(isSuccessEnvelope({})).toBe(false)
    expect(isSuccessEnvelope(null)).toBe(false)
    expect(isSuccessEnvelope('raw')).toBe(false)
    expect(isSuccessEnvelope([1, 2, 3])).toBe(false)
  })
})

describe('client 响应/请求拦截器', () => {
  it('成功响应保留 data 中的 0/false/""/null/[]', async () => {
    const body = {
      code: 200,
      message: 'ok',
      data: { zero: 0, no: false, empty: '', nil: null, list: [], nested: { count: 0 } }
    }
    const res = await client.get('/dashboard/stats', { adapter: jsonAdapter(200, body) })
    expect(res).toEqual(body)
    expect(res.data.zero).toBe(0)
    expect(res.data.no).toBe(false)
    expect(res.data.empty).toBe('')
    expect(res.data.nil).toBeNull()
    expect(res.data.list).toEqual([])
    expect(res.data.nested.count).toBe(0)
  })

  it('新契约错误外层被归一化为 ApiError 并展示提示', async () => {
    const errorBody = {
      code: 'VALIDATION_ERROR',
      message: '任务参数不合法',
      details: { field: 'custom_parameters.12.count', reason: '不允许嵌套对象' }
    }
    await expect(
      client.post('/tasks', {}, { adapter: jsonAdapter(400, errorBody) })
    ).rejects.toMatchObject({
      name: 'ApiError',
      code: 'VALIDATION_ERROR',
      httpStatus: 400,
      details: { field: 'custom_parameters.12.count', reason: '不允许嵌套对象' }
    })
  })

  it('legacy {detail} 错误被兼容归一化', async () => {
    await expect(
      client.get('/devices', { adapter: jsonAdapter(404, { detail: '设备不存在' }) })
    ).rejects.toMatchObject({ code: 'NOT_FOUND', rawMessage: '设备不存在', legacy: true })
  })

  it('ApiError 携带与 httpStatus 一致的 response 兼容字段（error.response.status）', async () => {
    const errorBody = { code: 'NOT_FOUND', message: '任务不存在', details: {} }
    await expect(
      client.get('/reports/999', { adapter: jsonAdapter(404, errorBody) })
    ).rejects.toMatchObject({
      code: 'NOT_FOUND',
      httpStatus: 404,
      response: { status: 404, data: errorBody }
    })
  })

  it('HTTP 200 + legacy 数字错误码时 response.status 与 httpStatus 一致', async () => {
    await expect(
      client.get('/dashboard/stats', {
        adapter: jsonAdapter(200, { code: 400, message: '查询参数不合法' })
      })
    ).rejects.toMatchObject({
      code: 'VALIDATION_ERROR',
      httpStatus: 200,
      response: { status: 200 }
    })
  })

  it('无 response 的网络错误保留 response=null 兼容字段', async () => {
    await expect(
      client.get('/tasks', {
        adapter: async (config) => {
          throw Object.assign(new Error('Network Error'), { config })
        }
      })
    ).rejects.toMatchObject({ response: null, httpStatus: null })
  })

  it('POST /tasks 自动附加合法 Idempotency-Key', async () => {
    await client.post('/tasks', { name: 'x' }, { adapter: jsonAdapter(201, { code: 201, data: {} }) })
    const key = readHeader(capture.config, 'Idempotency-Key')
    expect(isValidIdempotencyKey(key)).toBe(true)
  })

  it('调用方传入的 Idempotency-Key 被原样使用', async () => {
    await client.post(
      '/tasks',
      { name: 'x' },
      { adapter: jsonAdapter(201, { code: 201, data: {} }), headers: { 'Idempotency-Key': 'caller-key-999' } }
    )
    expect(readHeader(capture.config, 'Idempotency-Key')).toBe('caller-key-999')
  })

  it('非幂等请求不附加 Idempotency-Key', async () => {
    await client.post('/devices/refresh', {}, { adapter: jsonAdapter(200, { code: 200, data: {} }) })
    expect(readHeader(capture.config, 'Idempotency-Key')).toBeUndefined()
    await client.get('/tasks', { adapter: jsonAdapter(200, { code: 200, data: {} }) })
    expect(readHeader(capture.config, 'Idempotency-Key')).toBeUndefined()
  })

  it('注入 Bearer token 与 X-PC-Identifier', async () => {
    userState.token = 'jwt-abc'
    await client.get('/tasks', { adapter: jsonAdapter(200, { code: 200, data: {} }) })
    expect(readHeader(capture.config, 'Authorization')).toBe('Bearer jwt-abc')
    expect(readHeader(capture.config, 'X-PC-Identifier')).toBe(getPcIdentifier())
  })

  it('401 触发登出', async () => {
    userState.token = 'expired'
    await expect(
      client.get('/tasks', {
        adapter: jsonAdapter(401, { code: 'UNAUTHENTICATED', message: '认证凭据无效', details: {} })
      })
    ).rejects.toMatchObject({ code: 'UNAUTHENTICATED', httpStatus: 401 })
    expect(logoutMock).toHaveBeenCalledTimes(1)
  })
})
