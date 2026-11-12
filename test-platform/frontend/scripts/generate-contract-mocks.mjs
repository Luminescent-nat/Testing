#!/usr/bin/env node
/**
 * 确定性契约 mock 生成器（T-20）。
 *
 * 背景：当前环境没有 mock-api 工具，无法使用其生成 mock。本脚本作为
 * 已记录的偏差方案：从 docs/contracts/*.md 中已确认的 JSON 样例（请求/响应）
 * 确定性生成前端隔离开发/测试用 mock 数据。
 *
 * 约束：
 *  - 不含时间戳等易变信息，同样输入必然得到逐字节相同的输出；
 *  - 生成文件头部明确标注 GENERATED MOCK，仅隔离开发/测试，禁止用于生产/联调；
 *  - 只读取契约文档，不读取后端运行结果，不联网。
 *
 * 用法：在 test-platform/frontend 下执行 `npm run mock:generate`
 */

import { readdirSync, readFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const FRONTEND_ROOT = path.resolve(__dirname, '..')
const REPO_ROOT = path.resolve(FRONTEND_ROOT, '..', '..')
const CONTRACTS_DIR = path.join(REPO_ROOT, 'docs', 'contracts')
const OUTPUT_FILE = path.join(FRONTEND_ROOT, 'src', 'mocks', 'generated', 'contract-mocks.js')

const HEADING_RE = /^##\s+\d+\.\s+(GET|POST|PUT|PATCH|DELETE)\s+(\/api\/v1\/\S+)\s*$/
const ANY_H2_RE = /^##\s+/

/**
 * 从 Markdown 文本中解析出各接口章节的 JSON 样例。
 * @param {string} text 契约文档内容
 * @param {string} source 相对仓库根路径的文件名
 * @returns {Array<object>} 接口条目
 */
function parseContractDoc(text, source) {
  const lines = text.split(/\r?\n/)
  const sections = []
  let current = null

  const flush = () => {
    if (current) sections.push(current)
    current = null
  }

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    const heading = line.match(HEADING_RE)
    if (heading) {
      flush()
      current = { method: heading[1], path: heading[2], source, requests: [], responses: [] }
      continue
    }
    if (ANY_H2_RE.test(line)) {
      flush()
      continue
    }
    if (!current) continue

    if (/^```json\s*$/i.test(line)) {
      const blockLines = []
      let j = i + 1
      while (j < lines.length && !/^```/.test(lines[j])) {
        blockLines.push(lines[j])
        j += 1
      }
      i = j
      const rawJson = blockLines.join('\n').trim()
      let parsed
      try {
        parsed = JSON.parse(rawJson)
      } catch {
        continue
      }
      let beforeText = ''
      for (let k = i - blockLines.length - 2; k >= 0; k -= 1) {
        const candidate = (lines[k] || '').trim()
        if (candidate) {
          beforeText = candidate
          break
        }
      }
      const isRequest = /请求|正文|request/i.test(beforeText)
      const isResponse = /响应|response/i.test(beforeText)
      const hasCode =
        parsed && typeof parsed === 'object' && !Array.isArray(parsed) && 'code' in parsed
      if (hasCode) {
        // 契约中请求体从不含 code 字段，凡带 code 的一律是响应外层（成功或错误）。
        current.responses.push(parsed)
      } else if (isRequest && !isResponse) {
        current.requests.push(parsed)
      } else if (isResponse) {
        current.responses.push(parsed)
      } else {
        current.requests.push(parsed)
      }
    }
  }
  flush()
  return sections
}

/**
 * 序列化为带缩进的 JS 对象字面量片段。
 * @param {unknown} value 任意 JSON 值
 * @param {number} indent 每行前置空格数
 * @returns {string} JS 片段
 */
function toJsLiteral(value, indent) {
  const json = JSON.stringify(value, null, 2)
  const pad = ' '.repeat(indent)
  return json
    .split('\n')
    .map((line, index) => (index === 0 ? line : `${pad}${line}`))
    .join('\n')
}

function main() {
  const files = readdirSync(CONTRACTS_DIR)
    .filter((name) => name.endsWith('.md') && name !== 'README.md' && !name.includes('review'))
    .sort()

  const hash = createHash('sha256')
  const entries = []
  for (const file of files) {
    const fullPath = path.join(CONTRACTS_DIR, file)
    const text = readFileSync(fullPath, 'utf8')
    hash.update(file)
    hash.update(text)
    const relSource = `docs/contracts/${file}`
    entries.push(...parseContractDoc(text, relSource))
  }

  const coveredEntries = entries.filter(
    (entry) => entry.requests.length > 0 || entry.responses.length > 0
  )

  const sourceDigest = hash.digest('hex')
  const header = [
    '/**',
    ' * GENERATED MOCK - 仅隔离开发/测试，禁止用于生产/联调',
    ' *',
    ' * 本文件由 scripts/generate-contract-mocks.mjs 从 docs/contracts/*.md 的已确认 JSON 样例',
    ' * 确定性生成，请勿手工修改。当前环境无 mock-api 工具，此文件为已记录的偏差产物，',
    ' * 需用户确认后方可用于真实联调替代；正式联调必须切换到真实后端接口。',
    ' *',
    ` * source-digest: sha256:${sourceDigest}`,
    ` * entries: ${coveredEntries.length}`,
    ' */',
    ''
  ].join('\n')

  const entryBlocks = coveredEntries
    .map((entry) => {
      const requests = entry.requests
        .map((item) => `${' '.repeat(6)}${toJsLiteral(item, 6)}`)
        .join(',\n')
      const responses = entry.responses
        .map((item) => `${' '.repeat(6)}${toJsLiteral(item, 6)}`)
        .join(',\n')
      return [
        '  {',
        `    method: '${entry.method}',`,
        `    path: '${entry.path}',`,
        `    source: '${entry.source}',`,
        '    requests: [',
        requests,
        '    ],',
        '    responses: [',
        responses,
        '    ]',
        '  }'
      ]
        .filter((line) => line !== '')
        .join('\n')
    })
    .join(',\n')

  const body = [
    header,
    '/** @type {Array<{method: string, path: string, source: string, requests: Array<object>, responses: Array<object>}>} */',
    'export const CONTRACT_MOCK_ENTRIES = [',
    entryBlocks,
    ']',
    '',
    '/**',
    ' * 将契约模板路径（含 {param}）编译为精确路径匹配正则。',
    ' * @param {string} pattern 契约模板路径',
    ' * @returns {RegExp} 匹配实际路径的正则',
    ' */',
    'const compilePathPattern = (pattern) => {',
    '  const source = pattern',
    "    .split('/')",
    '    .map((segment) =>',
    '      /^\\{[a-zA-Z0-9_]+\\}$/.test(segment)',
    "        ? '[^/]+'",
    "        : segment.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&')",
    '    )',
    "    .join('/')",
    '  return new RegExp(`^${source}$`)',
    '}',
    '',
    '/**',
    ' * 归一化实际请求路径：去掉查询串，补全 /api/v1 前缀。',
    ' * @param {string} url 请求 URL（可含查询串）',
    ' * @returns {string} 归一化路径',
    ' */',
    'export const normalizeMockPath = (url) => {',
    "  const noQuery = String(url || '').split('?')[0]",
    "  if (noQuery.startsWith('/api/v1')) return noQuery",
    "  return `/api/v1${noQuery.startsWith('/') ? noQuery : `/${noQuery}`}`",
    '}',
    '',
    '/**',
    ' * 按方法与路径查找契约 mock 条目（仅隔离开发/测试使用）。',
    ' * @param {string} method HTTP 方法',
    ' * @param {string} url 请求 URL',
    ' * @returns {object|null} 命中的条目',
    ' */',
    'export const findContractMock = (method, url) => {',
    "  const upperMethod = String(method || 'get').toUpperCase()",
    '  const actualPath = normalizeMockPath(url)',
    '  return (',
    '    CONTRACT_MOCK_ENTRIES.find(',
    '      (entry) => entry.method === upperMethod && compilePathPattern(entry.path).test(actualPath)',
    '    ) || null',
    '  )',
    '}',
    '',
    '/**',
    ' * 取该接口的首个 2xx 响应样例；无 2xx 时回退首个响应样例。',
    ' * @param {string} method HTTP 方法',
    ' * @param {string} url 请求 URL',
    ' * @returns {object|null} 响应样例',
    ' */',
    'export const getContractMockResponse = (method, url) => {',
    '  const entry = findContractMock(method, url)',
    '  if (!entry || entry.responses.length === 0) return null',
    '  const success = entry.responses.find(',
    "    (item) => typeof item.code === 'number' && item.code >= 200 && item.code < 300",
    '  )',
    '  return success || entry.responses[0]',
    '}',
    '',
    '/**',
    ' * 生成 axios 自定义 adapter，供隔离开发/测试注入使用。',
    ' * 未命中样例时返回带 MOCK_NOT_FOUND 的 404 响应，便于发现契约覆盖缺口。',
    ' * @returns {(config: object) => Promise<object>} axios adapter',
    ' */',
    'export const createContractMockAdapter = () => {',
    '  return async (config) => {',
    '    const sample = getContractMockResponse(config.method, config.url)',
    '    if (sample) {',
    "      const status = typeof sample.code === 'number' ? sample.code : 200",
    '      return {',
    '        data: sample,',
    '        status,',
    "        statusText: 'OK',",
    '        headers: {},',
    '        config,',
    '        request: null',
    '      }',
    '    }',
    '    const notFound = {',
    "      code: 'MOCK_NOT_FOUND',",
    "      message: '契约 mock 未覆盖该请求',",
    "      details: { field: 'path', reason: normalizeMockPath(config.url) }",
    '    }',
    "    return { data: notFound, status: 404, statusText: 'Not Found', headers: {}, config, request: null }",
    '  }',
    '}',
    ''
  ].join('\n')

  mkdirSync(path.dirname(OUTPUT_FILE), { recursive: true })
  writeFileSync(OUTPUT_FILE, body, 'utf8')
  process.stdout.write(
    `[mock:generate] wrote ${path.relative(REPO_ROOT, OUTPUT_FILE)} (entries=${coveredEntries.length}, digest=${sourceDigest.slice(0, 12)})\n`
  )
}

main()
