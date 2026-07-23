import { test, expect } from '@playwright/test'

test.describe('侧边栏导航与页面渲染', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.locator('.sidebar-title')).toHaveText('测试平台')
  })

  test('仪表盘页面关键元素渲染正常', async ({ page }) => {
    // 仪表盘使用 stat-card 统计卡片与 quick-actions 快捷操作
    await expect(page.locator('.stat-card').first()).toBeVisible()
    await expect(page.locator('.quick-actions')).toBeVisible()
    await expect(page.locator('.app-card').first()).toBeVisible()
  })

  test('点击“设备管理”进入设备列表且交互正常', async ({ page }) => {
    await page.locator('.el-menu-item', { hasText: '设备管理' }).click()
    await expect(page).toHaveURL(/\/devices/)
    // 页面主体应渲染设备卡片/列表容器
    await expect(page.locator('.devices-page, .device-list, .el-card').first()).toBeVisible()
  })

  test('点击“测试模块”进入模块管理页', async ({ page }) => {
    await page.locator('.el-menu-item', { hasText: '测试模块' }).click()
    await expect(page).toHaveURL(/\/modules/)
    await expect(page.locator('.modules-page, .module-list, .el-card').first()).toBeVisible()
  })

  test('点击“测试任务”进入任务列表', async ({ page }) => {
    await page.locator('.el-menu-item', { hasText: '测试任务' }).click()
    await expect(page).toHaveURL(/\/tasks$/)
    await expect(page.locator('.tasks-page, .task-list, .el-card').first()).toBeVisible()
  })

  test('点击“测试报告”进入报告页', async ({ page }) => {
    await page.locator('.el-menu-item', { hasText: '测试报告' }).click()
    await expect(page).toHaveURL(/\/reports/)
    await expect(page.locator('.reports-page, .report-list, .el-card').first()).toBeVisible()
  })

  test('管理员可展开系统管理并进入用户管理', async ({ page }) => {
    await page.locator('.el-sub-menu__title', { hasText: '系统管理' }).click()
    await page.locator('.el-menu-item', { hasText: '用户管理' }).click()
    await expect(page).toHaveURL(/\/admin\/users/)
    await expect(page.locator('.users-page, .user-list, .el-table').first()).toBeVisible()
  })

  test('顶部用户下拉可进入个人信息并返回', async ({ page }) => {
    await page.locator('.user-info').click()
    await page.locator('.el-dropdown-menu__item', { hasText: '个人信息' }).click()
    await expect(page).toHaveURL(/\/profile/)
    await expect(page.locator('.profile-page, .el-form, .el-card').first()).toBeVisible()
  })
})
