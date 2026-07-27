import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

// user store 会连带引入 vue-router（依赖浏览器 history），node 环境下 mock 掉，
// getPcIdentifier 本身不依赖 store。
vi.mock('@/store/user', () => ({
  useUserStore: () => ({ token: null, logout: vi.fn() })
}))

// request.js 会引入 axios/element-plus，仅使用其导出的 getPcIdentifier，
// 拦截器内的 useUserStore 在导入期不会执行，node 环境下可安全导入。
import { getPcIdentifier } from '../request'

// 最小 localStorage mock（Map 实现）
const createLocalStorageMock = () => {
  const store = new Map()
  return {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
    clear: () => store.clear(),
  }
}

describe('getPcIdentifier', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createLocalStorageMock())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('首次调用生成 UUID 并持久化，后续调用复用同一标识', () => {
    const first = getPcIdentifier()
    expect(first).toBeTruthy()
    // node 20 的 crypto.randomUUID 格式
    expect(first).toMatch(/^[0-9a-f-]{36}$/)
    expect(localStorage.getItem('pc_identifier')).toBe(first)

    const second = getPcIdentifier()
    expect(second).toBe(first)
  })

  it('localStorage 已有标识时直接返回，不重新生成', () => {
    localStorage.setItem('pc_identifier', 'existing-pc-id')
    expect(getPcIdentifier()).toBe('existing-pc-id')
  })

  it('crypto.randomUUID 不可用时回退为 pc- 前缀的随机串', () => {
    vi.stubGlobal('crypto', { randomUUID: undefined })
    const id = getPcIdentifier()
    expect(id).toMatch(/^pc-\d+-[a-z0-9]+$/)
    expect(localStorage.getItem('pc_identifier')).toBe(id)
  })
})
