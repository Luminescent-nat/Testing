import { test, expect } from '@playwright/test'

test.describe('关键按钮与交互', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard')
  })

  test('主题切换按钮可正常切换亮/暗色', async ({ page }) => {
    const themeBtn = page.locator('.theme-btn').first()
    await expect(themeBtn).toBeVisible()

    const htmlBefore = await page.evaluate(() => document.documentElement.className)
    await themeBtn.click()
    await page.waitForTimeout(300)
    const htmlAfter = await page.evaluate(() => document.documentElement.className)

    // 主题类名应发生变化（dark 类切换）
    expect(htmlBefore.includes('dark')).not.toBe(htmlAfter.includes('dark'))
  })

  test('仪表盘“开始新测试”快捷按钮可进入创建任务页', async ({ page }) => {
    await page.locator('.quick-actions button', { hasText: '开始新测试' }).click()
    await expect(page).toHaveURL(/\/tasks\/create/)
  })

  test('设备页刷新设备按钮可点击且不报错', async ({ page }) => {
    await page.goto('/devices')
    await expect(page.locator('.search-bar')).toBeVisible()

    const refreshBtn = page.locator('.search-bar button', { hasText: '刷新设备' })
    await expect(refreshBtn).toBeVisible()
    await refreshBtn.click()

    // 刷新后页面不应出现错误提示，且设备列表/空状态正常渲染
    await expect(page.locator('.device-card, .empty-container').first()).toBeVisible()
  })

  test('用户管理页可加载用户列表并展示操作按钮', async ({ page }) => {
    await page.goto('/admin/users')
    await expect(page.locator('.app-table')).toBeVisible()

    // 表格中应至少包含当前登录管理员账号
    await expect(page.locator('.el-table__row').first()).toBeVisible()

    // 操作列应展示“重置密码 / 禁用 / 删除”按钮
    const firstRow = page.locator('.el-table__row').first()
    await expect(firstRow.locator('button', { hasText: '重置密码' })).toBeVisible()
    await expect(firstRow.locator('button', { hasText: /禁用|启用/ })).toBeVisible()
    await expect(firstRow.locator('button', { hasText: '删除' })).toBeVisible()
  })
})
