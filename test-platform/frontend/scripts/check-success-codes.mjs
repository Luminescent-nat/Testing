#!/usr/bin/env node
/**
 * 成功判定静态检查（V1-10）。
 *
 * 校验 src/（排除 src/api/client.js 的注释与定义、src/mocks/generated/）中不再散落
 * 仅判 200 的成功判定（`code === 200` / `code == 200` / `code!== 200` 等），
 * 并统计 isSuccessResponse 使用情况，输出改动点清单与残留计数。
 *
 * 用法：node scripts/check-success-codes.mjs
 * 退出码：0 无残留；1 存在散落判定。
 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const FRONTEND_ROOT = path.resolve(__dirname, '..')
const SRC_DIR = path.join(FRONTEND_ROOT, 'src')

/** 散落判定正则（匹配 `.code === 200` 一类写法） */
const SCATTERED_RE = /\.code\s*={2,3}\s*200\b|\.code\s*!=\s*200\b|\.code\s*!==\s*200\b/
/** 统一判定使用正则 */
const UNIFIED_RE = /isSuccessResponse\(/

/**
 * 递归收集 .js/.vue 文件。
 * @param {string} dir 目录
 * @returns {string[]} 文件路径列表
 */
const collectFiles = (dir) => {
  const result = []
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name)
    const stat = statSync(full)
    if (stat.isDirectory()) {
      result.push(...collectFiles(full))
    } else if (/\.(js|vue)$/.test(name)) {
      result.push(full)
    }
  }
  return result
}

const files = collectFiles(SRC_DIR).sort()
const scattered = []
const unified = []

for (const file of files) {
  const rel = path.relative(FRONTEND_ROOT, file).replace(/\\/g, '/')
  if (rel === 'src/api/client.js' || rel.startsWith('src/mocks/generated/')) continue
  const lines = readFileSync(file, 'utf8').split(/\r?\n/)
  lines.forEach((line, index) => {
    if (SCATTERED_RE.test(line)) {
      scattered.push(`${rel}:${index + 1} ${line.trim()}`)
    }
    if (UNIFIED_RE.test(line)) {
      unified.push(`${rel}:${index + 1}`)
    }
  })
}

process.stdout.write('=== 成功判定静态检查（V1-10） ===\n')
process.stdout.write(`扫描范围：src/**/*.{js,vue}（排除 src/api/client.js、src/mocks/generated/）\n\n`)
process.stdout.write(`[统一判定 isSuccessResponse 使用点] 共 ${unified.length} 处\n`)
unified.forEach((item) => process.stdout.write(`  ${item}\n`))
process.stdout.write(`\n[残留散落判定（code ===/== 200 等）] 共 ${scattered.length} 处\n`)
if (scattered.length === 0) {
  process.stdout.write('  无残留：所有成功判定均走 isSuccessResponse\n')
} else {
  scattered.forEach((item) => process.stdout.write(`  ${item}\n`))
}

const failed = scattered.length > 0
process.stdout.write(`\n[结论] 残留计数 ${scattered.length}；统一判定使用 ${unified.length} 处\n`)
process.exit(failed ? 1 : 0)
