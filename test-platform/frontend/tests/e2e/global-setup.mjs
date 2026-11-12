import { execFileSync } from 'child_process'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

export default async function globalSetup() {
  // 只允许向显式指定的隔离 E2E 数据库写入固定管理员，避免污染正式库。
  const e2eDatabaseUrl = process.env.E2E_DATABASE_URL
  if (!e2eDatabaseUrl) {
    throw new Error('运行 E2E 前必须设置 E2E_DATABASE_URL 为一次性隔离数据库')
  }

  const backendDir = join(__dirname, '..', '..', '..', 'backend')
  const scriptPath = join(backendDir, 'scripts', 'ensure_e2e_admin.py')
  execFileSync('python', [scriptPath], {
    stdio: 'inherit',
    cwd: backendDir,
    env: {
      ...process.env,
      E2E_TEST_MODE: '1',
      DATABASE_URL: e2eDatabaseUrl,
    },
  })
}
