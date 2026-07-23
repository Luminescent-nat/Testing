import { execSync } from 'child_process'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

export default async function globalSetup() {
  // 确保后端存在已知密码的 E2E 管理员账号
  const backendDir = join(__dirname, '..', '..', '..', 'backend')
  const scriptPath = join(backendDir, 'scripts', 'ensure_e2e_admin.py')
  execSync(`python "${scriptPath}"`, { stdio: 'inherit', cwd: backendDir })
}
