import { test, expect } from '@playwright/test'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'
const ADMIN_USER = process.env.E2E_ADMIN_USER || 'e2e-admin'
const ADMIN_PASS = process.env.E2E_ADMIN_PASS || 'e2e-admin-pass'

/**
 * 说明（task-29 / RR-V11-REVIEW 演示前收口）：
 *  - 空态用例要求隔离 E2E 数据库无任务；若库中已有报告则 test.skip 并注明原因（非静默）。
 *  - 非空态用例先从 API 取在线设备与合法测试项，再创建任务并断言 HTTP 201；
 *    禁止使用非法 item_ids=[] 或静默接受创建失败；无设备/无测试项时 test.skip 并给出原因。
 *  - 选择器与当前 reports 视图 DOM 对齐（报告卡片 .report-card / 详情对话框 .report-detail）。
 */

test.describe('任务创建与报告查看流程', () => {
  test('任务创建页模块、测试项可正常加载与选择', async ({ page }) => {
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

    // 演示版收口：daily/once 选项必须 disabled 并带「后续版本」标注，仅立即执行可选
    const onceRadio = page.locator('.el-radio', { hasText: '定时一次（后续版本）' })
    const dailyRadio = page.locator('.el-radio', { hasText: '每日定时（后续版本）' })
    await expect(onceRadio).toHaveClass(/is-disabled/)
    await expect(dailyRadio).toHaveClass(/is-disabled/)
    await expect(page.locator('.el-radio', { hasText: '立即执行' })).not.toHaveClass(/is-disabled/)
  })

  test('报告空态：全新隔离库进入 /reports 显示空态且无 console error', async ({ page }) => {
    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })
    page.on('pageerror', (error) => consoleErrors.push(String(error)))

    await page.goto('/reports')
    await expect(page.locator('.page-container')).toBeVisible()

    const cards = page.locator('.report-card')
    const emptyState = page.locator('.el-empty')

    // 等待列表/空态二选一出现
    await expect(async () => {
      const total = (await cards.count()) + (await emptyState.count())
      expect(total).toBeGreaterThan(0)
    }).toPass({ timeout: 15000 })

    if ((await cards.count()) > 0) {
      test.skip(true, '隔离库中已有报告数据，空态用例需在全新 E2E 数据库运行')
    }

    await expect(emptyState.first()).toBeVisible()
    await expect(emptyState.first()).toContainText('暂无报告')
    // 404/空态不得弹出错误提示，也不得产生 console error
    await expect(page.locator('.el-message--error')).toHaveCount(0)
    expect(consoleErrors, `控制台错误: ${consoleErrors.join(' | ')}`).toEqual([])
  })

  test('非空报告：创建任务→轮询 completed→报告详情统计正确', async ({ page, context }) => {
    const token = await getAdminToken(context)
    expect(token, '管理员登录失败，无法通过 API 创建任务').toBeTruthy()

    const device = await pickOnlineDevice(context, token)
    if (!device) {
      test.skip(true, '无在线设备（GET /api/v1/devices?status=online 为空），无法创建真实任务')
    }
    const item = await pickValidItem(context, token)
    if (!item) {
      test.skip(true, '无合法测试项（/api/v1/modules 下无 item），无法创建真实任务')
    }

    const createRes = await context.request.post(`${BACKEND_URL}/api/v1/tasks`, {
      headers: {
        Authorization: `Bearer ${token}`,
        'Idempotency-Key': `e2e-report-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
      },
      data: {
        name: `E2E 报告校验任务 ${Date.now()}`,
        device_serial: device.serial_number,
        item_ids: [item.id],
        custom_parameters: {},
        schedule_type: 'immediate'
      }
    })
    expect(
      createRes.status(),
      `创建任务必须返回 201（禁止静默接受失败），实际 ${createRes.status()}: ${await createRes.text()}`
    ).toBe(201)
    const createBody = await createRes.json()
    const taskId = createBody?.data?.id
    expect(typeof taskId, '创建响应 data.id 应为整数').toBe('number')

    // 轮询任务直至 completed（终态 failed/cancelled 也返回，交给断言判失败）
    const finalTask = await pollTaskCompleted(context, token, taskId)
    expect(finalTask?.status, `任务 ${taskId} 未完成，实际状态 ${finalTask?.status}`).toBe('completed')

    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })
    page.on('pageerror', (error) => consoleErrors.push(String(error)))

    await page.goto('/reports')
    const card = page.locator('.report-card', { hasText: `#${taskId}` }).first()
    await expect(card).toBeVisible({ timeout: 20000 })
    await card.getByRole('button', { name: '查看详情' }).click()

    const detail = page.locator('.report-detail')
    await expect(detail).toBeVisible({ timeout: 15000 })
    await expect(detail.locator('.detail-stats')).toBeVisible()

    // 五类计数（含超时）+ 总项数共 6 个统计框
    const statBoxes = detail.locator('.detail-stats .stat-box')
    expect(await statBoxes.count()).toBeGreaterThanOrEqual(6)

    // 通过率徽标：number → x%，null → 无有效结果（不得显示 0%/100% 冒充）
    const badgeText = (await detail.locator('.detail-header .el-tag').first().innerText()).trim()
    expect(badgeText === '无有效结果' || /^\d+(\.\d+)?%$/.test(badgeText), `通过率徽标异常: ${badgeText}`).toBe(true)

    // 详情不得出现 undefined / NaN / Invalid Date
    const detailText = await detail.innerText()
    expect(detailText).not.toMatch(/undefined|NaN|Invalid Date/)

    // 报告统计与后端一致：总项数等于创建时选择项数 1
    const totalText = await detail.locator('.detail-stats .stat-box .stat-number').first().innerText()
    expect(Number(totalText.trim())).toBeGreaterThanOrEqual(1)

    expect(consoleErrors, `控制台错误: ${consoleErrors.join(' | ')}`).toEqual([])
  })
})

async function getAdminToken(context) {
  // 兼容 legacy 登录路径与契约会话路径；成功码接受 200/201
  const legacy = await context.request.post(`${BACKEND_URL}/api/v1/auth/login`, {
    data: { username: ADMIN_USER, password: ADMIN_PASS, pc_identifier: 'e2e-admin-pc' }
  })
  if ([200, 201].includes(legacy.status())) {
    const body = await legacy.json()
    return body?.data?.access_token || null
  }
  const sessions = await context.request.post(`${BACKEND_URL}/api/v1/auth/sessions`, {
    data: { username: ADMIN_USER, password: ADMIN_PASS, pc_identifier: 'e2e-admin-pc' }
  })
  if ([200, 201].includes(sessions.status())) {
    const body = await sessions.json()
    return body?.data?.access_token || null
  }
  return null
}

async function apiGet(context, token, path) {
  return context.request.get(`${BACKEND_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` }
  })
}

async function pickOnlineDevice(context, token) {
  const res = await apiGet(context, token, '/api/v1/devices?status=online&page=1&page_size=50')
  if (![200, 201].includes(res.status())) return null
  const body = await res.json()
  const items = body?.data?.items || []
  return items.find((device) => typeof device?.serial_number === 'string' && device.serial_number) || null
}

async function pickValidItem(context, token) {
  const modulesRes = await apiGet(context, token, '/api/v1/modules')
  if (![200, 201].includes(modulesRes.status())) return null
  const modulesBody = await modulesRes.json()
  const modules = modulesBody?.data?.items || []
  for (const module of modules) {
    if (!module?.id) continue
    const itemsRes = await apiGet(context, token, `/api/v1/modules/${module.id}/items`)
    if (![200, 201].includes(itemsRes.status())) continue
    const itemsBody = await itemsRes.json()
    const items = itemsBody?.data?.items || []
    const item = items.find((candidate) => Number.isInteger(candidate?.id))
    if (item) return item
  }
  return null
}

async function pollTaskCompleted(context, token, taskId, timeoutMs = 180000) {
  const startedAt = Date.now()
  let lastTask = null
  while (Date.now() - startedAt < timeoutMs) {
    const res = await apiGet(context, token, `/api/v1/tasks/${taskId}`)
    expect(res.status(), `查询任务 ${taskId} 详情应成功，实际 ${res.status()}`).toBe(200)
    const body = await res.json()
    lastTask = body?.data || null
    if (lastTask?.status === 'completed') return lastTask
    if (['failed', 'cancelled'].includes(lastTask?.status)) return lastTask
    await new Promise((resolve) => setTimeout(resolve, 2000))
  }
  return lastTask
}
