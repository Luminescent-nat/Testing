import { createRequire } from 'node:module'
import { writeFileSync } from 'node:fs'

const require = createRequire('D:/MCTEST/test-platform/frontend/package.json')
const { chromium, expect } = require('@playwright/test')
const baseURL = 'http://127.0.0.1:8770'
const outputPath = 'D:/MCTEST/docs/verification/reviews/evidence/v1-demo-final-review-20261113/browser-monitor.log'
const screenshotPath = 'D:/MCTEST/docs/verification/reviews/evidence/v1-demo-final-review-20261113/browser-monitor.png'

const browser = await chromium.launch({ headless: true })
const context = await browser.newContext()
const page = await context.newPage()
const consoleErrors = []
const pageErrors = []
const serverErrors = []
page.on('console', message => {
  if (message.type() === 'error') consoleErrors.push(message.text())
})
page.on('pageerror', error => pageErrors.push(String(error)))
page.on('response', response => {
  if (response.status() >= 500) serverErrors.push(`${response.status()} ${response.url()}`)
})

try {
  const login = await context.request.post(`${baseURL}/api/v1/auth/login`, {
    data: { username: 'e2e-admin', password: 'e2e-admin-pass', pc_identifier: 'independent-monitor-review' }
  })
  expect(login.status()).toBe(200)
  const loginBody = await login.json()
  const token = loginBody?.data?.access_token
  expect(token).toBeTruthy()

  const tasksResponse = await context.request.get(`${baseURL}/api/v1/tasks?page=1&page_size=50`, {
    headers: { Authorization: `Bearer ${token}` }
  })
  expect(tasksResponse.status()).toBe(200)
  const tasksBody = await tasksResponse.json()
  const task = (tasksBody?.data?.items || []).find(candidate => candidate?.name?.startsWith('E2E 报告校验任务'))
  expect(task?.id, '必须找到本轮非空报告 E2E 创建的任务').toBeGreaterThan(0)

  await page.goto(`${baseURL}/login`)
  await page.locator('input[type="text"]').fill('e2e-admin')
  await page.locator('input[type="password"]').first().fill('e2e-admin-pass')
  await page.locator('button.submit-btn').click()
  await expect(page).toHaveURL(/\/dashboard/)

  await page.goto(`${baseURL}/tasks/monitor/${task.id}`)
  await expect(page.locator('.page-container')).toBeVisible()
  await expect(page.locator('.node-name', { hasText: '容量校验' }).first()).toBeVisible()
  await expect(page.locator('.item-name', { hasText: '容量校验' }).first()).toBeVisible()

  const bodyText = await page.locator('body').innerText()
  expect(bodyText).not.toMatch(/undefined|NaN|Invalid Date/)

  const clickableNode = page.locator('.timeline-node.clickable').first()
  await expect(clickableNode).toBeVisible()
  await clickableNode.click()
  const dialog = page.locator('.el-dialog').last()
  await expect(dialog).toBeVisible()
  await expect(dialog.locator('.el-descriptions')).toBeVisible({ timeout: 10000 })
  await expect(dialog.locator('.log-output')).toContainText('MemTotal', { timeout: 10000 })
  const dialogText = await dialog.innerText()
  expect(dialogText).toContain('容量校验')
  expect(dialogText).not.toMatch(/undefined|NaN|Invalid Date/)

  const logPanelText = await page.locator('.log-panel').innerText().catch(() => '')
  expect(logPanelText).not.toMatch(/undefined|NaN|Invalid Date/)
  expect(consoleErrors, `console errors: ${consoleErrors.join(' | ')}`).toEqual([])
  expect(pageErrors, `page errors: ${pageErrors.join(' | ')}`).toEqual([])
  expect(serverErrors, `HTTP 5xx: ${serverErrors.join(' | ')}`).toEqual([])

  await page.screenshot({ path: screenshotPath, fullPage: true })
  const result = {
    task_id: task.id,
    task_name: task.name,
    item_name_visible: true,
    log_dialog_item_name_visible: true,
    undefined_present: false,
    console_errors: consoleErrors,
    page_errors: pageErrors,
    http_5xx: serverErrors,
    result: 'PASS'
  }
  writeFileSync(outputPath, JSON.stringify(result, null, 2), 'utf8')
  console.log(JSON.stringify(result))
} catch (error) {
  const failure = { result: 'FAIL', error: String(error), consoleErrors, pageErrors, serverErrors }
  writeFileSync(outputPath, JSON.stringify(failure, null, 2), 'utf8')
  throw error
} finally {
  await browser.close()
}
