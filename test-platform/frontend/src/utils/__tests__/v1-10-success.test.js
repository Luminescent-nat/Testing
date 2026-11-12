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
  createSubmitGuard,
  isSuccessResponse,
  withPcIdentifier
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

beforeEach(() => {
  vi.stubGlobal('localStorage', createLocalStorageMock())
  capture.config = null
  logoutMock.mockClear()
  userState.token = null
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('isSuccessResponse：统一 2xx 成功判定', () => {
  it('200/201/204 成功外层均判定为成功', () => {
    expect(isSuccessResponse({ code: 200, message: 'ok', data: {} })).toBe(true)
    expect(isSuccessResponse({ code: 201, message: 'created', data: {} })).toBe(true)
    expect(isSuccessResponse({ code: 204, message: 'no content', data: {} })).toBe(true)
  })

  it('错误外层（字符串码/非 2xx 整数）判定为失败', () => {
    expect(isSuccessResponse({ code: 'VALIDATION_ERROR', message: 'x', details: {} })).toBe(false)
    expect(isSuccessResponse({ code: 400, message: 'x' })).toBe(false)
    expect(isSuccessResponse({ code: 401, message: 'x' })).toBe(false)
    expect(isSuccessResponse({ code: 500, message: 'x' })).toBe(false)
  })

  it('无 code 的裸响应体判定为失败', () => {
    expect(isSuccessResponse({})).toBe(false)
    expect(isSuccessResponse(null)).toBe(false)
    expect(isSuccessResponse('raw')).toBe(false)
    expect(isSuccessResponse([1, 2, 3])).toBe(false)
  })
})

describe('V1-10 端到端语义（client 拦截器）', () => {
  it('201 成功响应保留 data 中的 0/false/""/null', async () => {
    const body = {
      code: 201,
      message: '创建成功',
      data: { zero: 0, no: false, empty: '', nil: null }
    }
    const res = await client.post('/tasks', {}, { adapter: jsonAdapter(201, body) })
    expect(isSuccessResponse(res)).toBe(true)
    expect(res.data.zero).toBe(0)
    expect(res.data.no).toBe(false)
    expect(res.data.empty).toBe('')
    expect(res.data.nil).toBeNull()
  })

  it('200 成功响应同样保留 falsy 值', async () => {
    const body = { code: 200, message: 'ok', data: { pass_rate: 0, archived: false, note: '', next: null } }
    const res = await client.get('/tasks/1', { adapter: jsonAdapter(200, body) })
    expect(isSuccessResponse(res)).toBe(true)
    expect(res.data).toEqual({ pass_rate: 0, archived: false, note: '', next: null })
  })

  it('错误外层被拒绝并归一化（code/message/details 可读）', async () => {
    await expect(
      client.post(
        '/tasks',
        {},
        {
          adapter: jsonAdapter(400, {
            code: 'VALIDATION_ERROR',
            message: '任务参数不合法',
            details: { field: 'custom_parameters.12.count' }
          })
        }
      )
    ).rejects.toMatchObject({
      code: 'VALIDATION_ERROR',
      details: { field: 'custom_parameters.12.count' }
    })
  })
})

describe('withPcIdentifier：登录/注册契约字段', () => {
  it('为请求体附加当前 PC 标识且不改入参', () => {
    localStorage.setItem('pc_identifier', 'pc-test-01')
    const payload = { username: 'operator', password: 'user-pass' }
    const sent = withPcIdentifier(payload)
    expect(sent).toEqual({
      username: 'operator',
      password: 'user-pass',
      pc_identifier: 'pc-test-01'
    })
    expect(payload).toEqual({ username: 'operator', password: 'user-pass' })
  })

  it('无已有标识时自动生成合法 pc_identifier', () => {
    const sent = withPcIdentifier({ username: 'first-admin' })
    expect(typeof sent.pc_identifier).toBe('string')
    expect(sent.pc_identifier.length).toBeGreaterThan(0)
    expect(localStorage.getItem('pc_identifier')).toBe(sent.pc_identifier)
  })
})

describe('createSubmitGuard：重复提交只发起一次请求', () => {
  it('提交进行中时重复触发被忽略，结束后可再次提交', async () => {
    const guard = createSubmitGuard()
    let calls = 0
    const task = () =>
      new Promise((resolve) => {
        calls += 1
        setTimeout(() => resolve('done'), 10)
      })

    const [first, second, third] = await Promise.all([
      guard.run(task),
      guard.run(task),
      guard.run(task)
    ])
    expect(calls).toBe(1)
    expect(first).toBe('done')
    expect(second).toBeUndefined()
    expect(third).toBeUndefined()
    expect(guard.isPending()).toBe(false)

    // 上一轮结束后可正常再次提交
    await guard.run(task)
    expect(calls).toBe(2)
  })

  it('异常时复位 pending，不永久锁死按钮', async () => {
    const guard = createSubmitGuard()
    await expect(
      guard.run(async () => {
        throw new Error('boom')
      })
    ).rejects.toThrow('boom')
    expect(guard.isPending()).toBe(false)
    const result = await guard.run(async () => 'ok')
    expect(result).toBe('ok')
  })
})
