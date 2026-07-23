import { test, expect } from '@playwright/test'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

test.describe('任务创建与报告查看流程', () => {
  test('创建任务页模块、测试项可正常加载与选择', async ({ page }) => {
    await page.goto('/tasks/create')
    await expect(page.locator('.page-container')).toBeVisible()

    // 等待模块列表加载
    await page.waitForSelector('.module-section', { timeout: 10000 })
    const moduleCount = await page.locator('.module-section').count()
    expect(moduleCount).toBeGreaterThan(0)

    // 找到第一个包含测试项的模块并选择第一个测试项
    const modules = page.locator('.module-section')
    let itemClicked = false
    for (let i = 0; i < moduleCount; i++) {
      const module = modules.nth(i)
      const item = module.locator('.test-item').first()
      if (await item.isVisible().catch(() => false)) {
        await item.click()
        itemClicked = true
        break
      }
    }
    expect(itemClicked).toBe(true)

    // 已选数量应更新
    await expect(page.locator('.summary-item .value').first()).toContainText('1 项')

    // 若存在在线设备，则选择设备并验证“开始测试”按钮可点击
    const emptyText = page.locator('.empty-text')
    const hasDevice = await emptyText.isHidden().catch(() => false)
    if (hasDevice) {
      await page.locator('.device-option').first().click()
      await expect(page.locator('button:has-text("开始测试")')).toBeEnabled()
    } else {
      // 无设备时按钮应禁用，并给出提示
      await expect(page.locator('button:has-text("开始测试")')).toBeDisabled()
      await expect(emptyText).toHaveText('暂无可用设备，请先连接设备')
    }
  })

  test('报告列表页时间显示正常且可进入详情', async ({ page, context }) => {
    // 先通过 API 创建一个已完成的任务，确保报告列表有数据
    const token = await getAdminToken(context)

    // 注入一个已完成任务（如果报告页依赖任务数据）
    const taskRes = await context.request.post(`${BACKEND_URL}/api/v1/tasks`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        name: 'E2E 报告时间校验任务',
        device_serial: 'e2e-test-device',
        item_ids: [],
      },
    })

    let taskId = null
    if (taskRes.status() === 200 || taskRes.status() === 201) {
      const body = await taskRes.json()
      taskId = body.data?.id
    }

    await page.goto('/reports')
    await expect(page.locator('.reports-page, .report-list, .el-card').first()).toBeVisible()

    // 报告页应正确渲染，不出现时间 NaN/Invalid Date 等异常文本
    const pageText = await page.locator('body').innerText()
    expect(pageText).not.toMatch(/Invalid Date|NaN|null/)

    if (taskId) {
      // 可点击报告卡片/行进入详情
      const detailLink = page.locator(`a[href*="/reports/${taskId}"], .report-item`).first()
      if (await detailLink.isVisible().catch(() => false)) {
        await detailLink.click()
        await expect(page).toHaveURL(new RegExp(`/reports/${taskId}`))
      }
    }
  })
})

async function getAdminToken(context) {
  const ADMIN_USER = process.env.E2E_ADMIN_USER || 'e2e-admin'
  const ADMIN_PASS = process.env.E2E_ADMIN_PASS || 'e2e-admin-pass'
  const res = await context.request.post(`${BACKEND_URL}/api/v1/auth/login`, {
    data: { username: ADMIN_USER, password: ADMIN_PASS },
  })
  const body = await res.json()
  return body.data?.access_token
}
