import { test as setup, expect } from '@playwright/test'

const adminFile = 'tests/e2e/.auth/admin-state.json'
const ADMIN_USER = process.env.E2E_ADMIN_USER || 'e2e-admin'
const ADMIN_PASS = process.env.E2E_ADMIN_PASS || 'e2e-admin-pass'
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

setup('初始化管理员账号并登录', async ({ page, context }) => {
  // 1. 尝试直接登录，若账号不存在则先注册（首个注册用户自动成为 admin）
  const loginRes = await context.request.post(`${BACKEND_URL}/api/v1/auth/login`, {
    data: { username: ADMIN_USER, password: ADMIN_PASS },
  })

  if (loginRes.status() === 401) {
    const registerRes = await context.request.post(`${BACKEND_URL}/api/v1/auth/register`, {
      data: { username: ADMIN_USER, password: ADMIN_PASS },
    })
    expect(registerRes.status()).toBe(200)
    const registerBody = await registerRes.json()
    expect(registerBody.code).toBe(200)
    expect(registerBody.data.role).toBe('admin')
  } else {
    expect(loginRes.status()).toBe(200)
  }

  // 2. 通过前端页面登录，验证交互链路
  await page.goto('/login')
  await expect(page).toHaveTitle(/测试平台|Test Platform/)

  await page.locator('input[type="text"]').fill(ADMIN_USER)
  await page.locator('input[type="password"]').first().fill(ADMIN_PASS)
  await page.locator('button.submit-btn').click()

  // 登录成功后跳转仪表盘
  await expect(page).toHaveURL(/\/dashboard/)
  await expect(page.locator('.sidebar-title')).toHaveText('测试平台')

  // 3. 保存登录态，供后续用例复用
  await page.context().storageState({ path: adminFile })
})
