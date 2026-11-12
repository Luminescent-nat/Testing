#!/usr/bin/env node
/**
 * 设计 token 静态检查（T-21）。
 *
 * 校验：
 *  1. theme.scss / index.scss 中 token 块之外不存在 hex、rgb(a) 裸色；
 *  2. token 块之外 font-size 只能引用 var(--font-size-*)；
 *  3. token 块之外 margin/padding/gap 只允许 0/4/8/12/16/24/32/48；
 *  4. token 块之外 border-radius 只允许 0/4/8/999 或 var(--radius-*)；
 *  5. token 块之外 box-shadow 只允许 var(--shadow-*) 或 none；
 *  6. token 声明只能出现在 token 块内；
 *  7. token 清单完整且与 docs/design/ui-tokens.md v1.0 一致（无缺失/无表外）；
 *  8. 按 WCAG 相对亮度实测核心对比度并与 ui-tokens.md 第 7 节表对照。
 *
 * 用法：在 test-platform/frontend 下执行 `npm run check:tokens`
 * 退出码：0 通过；1 存在违规/缺失/对比度不达标。
 */

import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const FRONTEND_ROOT = path.resolve(__dirname, '..')
const THEME_FILE = path.join(FRONTEND_ROOT, 'src', 'styles', 'theme.scss')
const INDEX_FILE = path.join(FRONTEND_ROOT, 'src', 'styles', 'index.scss')

const EXPECTED = {
  colors: {
    'color-primary': ['#2563eb', '#60a5fa'],
    'color-text': ['#0f172a', '#f8fafc'],
    'color-text-secondary': ['#475569', '#cbd5e1'],
    'color-bg': ['#ffffff', '#0f172a'],
    'color-success': ['#15803d', '#4ade80'],
    'color-warning': ['#a16207', '#fcd34d'],
    'color-error': ['#b91c1c', '#fca5a5'],
    'color-bg-page': ['#f8fafc', '#020617'],
    'color-bg-elevated': ['#ffffff', '#1e293b'],
    'color-text-tertiary': ['#64748b', '#94a3b8'],
    'color-text-inverse': ['#ffffff', '#0f172a'],
    'color-border': ['#e2e8f0', '#334155'],
    'color-control-border': ['#64748b', '#94a3b8'],
    'color-bg-disabled': ['#f1f5f9', '#1e293b'],
    'color-text-disabled': ['#64748b', '#94a3b8']
  },
  fontSizes: {
    caption: 12,
    small: 14,
    body: 16,
    'title-sm': 20,
    'title-md': 24,
    display: 32
  },
  lineHeights: {
    caption: 18,
    small: 21,
    body: 24,
    'title-sm': 30,
    'title-md': 36,
    display: 48
  },
  spacing: { 1: 4, 2: 8, 3: 12, 4: 16, 6: 24, 8: 32, 12: 48 },
  radius: { none: 0, sm: 4, md: 8, full: 999 },
  shadows: {
    'shadow-sm': '0 1px 2px rgba(0, 0, 0, 0.08)',
    'shadow-md': '0 4px 8px rgba(0, 0, 0, 0.12)',
    'shadow-lg': '0 8px 24px rgba(0, 0, 0, 0.16)'
  },
  focusRing: '4px solid var(--color-primary)'
}

const ALLOWED_SPACING = new Set(Object.values(EXPECTED.spacing))
const ALLOWED_RADIUS = new Set(Object.values(EXPECTED.radius))

/**
 * 拆分为带有 token 块标记的行。
 * @param {string} content 文件内容
 * @returns {Array<{line: string, lineNo: number, inBlock: boolean, block: string}>} 行信息
 */
const collectLines = (content) => {
  const lines = content.split(/\r?\n/)
  let inBlock = false
  let block = ''
  return lines.map((line, index) => {
    const startMatch = line.match(/token-block:start\s+([a-z-]+)/)
    if (startMatch) {
      inBlock = true
      block = startMatch[1]
      return { line, lineNo: index + 1, inBlock: true, block }
    }
    if (/token-block:end/.test(line)) {
      inBlock = false
      block = ''
      return { line, lineNo: index + 1, inBlock: true, block: '' }
    }
    return { line, lineNo: index + 1, inBlock, block }
  })
}

/**
 * 解析 token 声明。
 * @param {Array<object>} lines 行信息
 * @returns {Map<string, {value: string, block: string, lineNo: number}>} 声明映射（同名取最后一次，附带按块分组）
 */
const parseDeclarations = (lines) => {
  const declarations = new Map()
  for (const item of lines) {
    if (!item.inBlock) continue
    const match = item.line.match(/--([a-z0-9-]+)\s*:\s*([^;]+);/)
    if (!match) continue
    declarations.set(`--${match[1]}`, {
      value: match[2].trim(),
      block: item.block,
      lineNo: item.lineNo
    })
    // 记录按块归属，供颜色双主题校验
    if (!declarations.has(`${item.block}::--${match[1]}`)) {
      declarations.set(`${item.block}::--${match[1]}`, {
        value: match[2].trim(),
        block: item.block,
        lineNo: item.lineNo
      })
    }
  }
  return declarations
}

const violations = []
const addViolation = (file, lineNo, message) => {
  violations.push(`${file}:${lineNo} ${message}`)
}

/**
 * 检查 token 块之外的裸值。
 * @param {string} fileLabel 文件名标签
 * @param {string} content 内容
 */
const checkRawValues = (fileLabel, content) => {
  const lines = collectLines(content)
  let sawTokenStart = false
  let sawTokenEnd = false
  for (const item of lines) {
    if (item.inBlock) {
      if (/token-block:start/.test(item.line)) sawTokenStart = true
      if (/token-block:end/.test(item.line)) sawTokenEnd = true
      continue
    }
    const line = item.line
    if (!line.trim() || line.trim().startsWith('//')) continue

    if (/#[0-9a-fA-F]{3,8}\b/.test(line)) {
      addViolation(fileLabel, item.lineNo, `token 块外出现裸 hex 颜色: ${line.trim()}`)
    }
    if (/\brgba?\(\s*\d/.test(line)) {
      addViolation(fileLabel, item.lineNo, `token 块外出现裸 rgb/rgba 颜色: ${line.trim()}`)
    }
    if (/^\s*--[a-z0-9-]+\s*:/.test(line)) {
      addViolation(fileLabel, item.lineNo, `token 声明出现在 token 块之外: ${line.trim()}`)
    }

    const fontSize = line.match(/font-size\s*:\s*([^;]+)/)
    if (fontSize && !/^var\(--font-size-[a-z-]+\)$/.test(fontSize[1].trim())) {
      addViolation(fileLabel, item.lineNo, `非表内/未引用 token 的 font-size: ${fontSize[1].trim()}`)
    }

    const spacing = line.match(/^\s*(margin|padding|gap)(-[a-z]+)?\s*:\s*([^;]+)/)
    if (spacing && !spacing[3].includes('var(')) {
      const pxValues = [...spacing[3].matchAll(/(-?\d*\.?\d+)px/g)].map((m) => Number(m[1]))
      for (const value of pxValues) {
        if (!ALLOWED_SPACING.has(value)) {
          addViolation(fileLabel, item.lineNo, `非表内间距 ${value}px: ${line.trim()}`)
        }
      }
      if (/-\d/.test(spacing[3]) && !spacing[3].includes('var(')) {
        addViolation(fileLabel, item.lineNo, `出现负间距: ${line.trim()}`)
      }
    }

    const radius = line.match(/border-radius\s*:\s*([^;]+)/)
    if (radius) {
      const parts = radius[1].trim().split(/\s+/)
      for (const part of parts) {
        if (part === '0') continue
        if (/^var\(--radius-[a-z]+\)$/.test(part)) continue
        const px = part.match(/^(-?\d*\.?\d+)px$/)
        if (!px || !ALLOWED_RADIUS.has(Number(px[1]))) {
          addViolation(fileLabel, item.lineNo, `非表内圆角 ${part}: ${line.trim()}`)
        }
      }
    }

    const shadow = line.match(/box-shadow\s*:\s*([^;]+)/)
    if (shadow) {
      const value = shadow[1].trim()
      if (value !== 'none' && !/^var\(--shadow-(sm|md|lg)\)$/.test(value)) {
        addViolation(fileLabel, item.lineNo, `非表内阴影: ${value}`)
      }
    }
  }
  if (sawTokenStart && !sawTokenEnd) {
    addViolation(fileLabel, 1, 'token-block 缺少结束标记')
  }
}

const normalize = (value) => value.replace(/\s+/g, ' ').trim()

const fileReport = []
const tokenDiff = []

/**
 * 校验颜色双主题清单。
 * @param {Map<string, object>} declarations 声明表
 */
const checkColors = (declarations) => {
  for (const [name, [light, dark]] of Object.entries(EXPECTED.colors)) {
    const lightDecl = declarations.get(`colors-light::--${name}`)
    const darkDecl = declarations.get(`colors-dark::--${name}`)
    if (!lightDecl) tokenDiff.push(`缺少浅色 token --${name}`)
    if (!darkDecl) tokenDiff.push(`缺少暗色 token --${name}`)
    if (lightDecl && lightDecl.value.toLowerCase() !== light) {
      tokenDiff.push(`--${name} 浅色值 ${lightDecl.value} ≠ 期望 ${light}`)
    }
    if (darkDecl && darkDecl.value.toLowerCase() !== dark) {
      tokenDiff.push(`--${name} 暗色值 ${darkDecl.value} ≠ 期望 ${dark}`)
    }
  }
  // 表外颜色 token
  const foundColorNames = new Set(
    [...declarations.keys()]
      .filter((key) => key.startsWith('colors-light::--color-'))
      .map((key) => key.replace('colors-light::--', ''))
  )
  for (const name of foundColorNames) {
    if (!(name in EXPECTED.colors)) tokenDiff.push(`表外颜色 token --${name}`)
  }
  fileReport.push(`  颜色 token：期望 ${Object.keys(EXPECTED.colors).length} 个，浅色块实际 ${foundColorNames.size} 个`)
}

const checkScale = (declarations) => {
  const keyMap = [
    ['font-size', EXPECTED.fontSizes, (v) => Number(v.replace('px', ''))],
    ['space', EXPECTED.spacing, (v) => Number(v.replace('px', ''))],
    ['radius', EXPECTED.radius, (v) => Number(v.replace('px', ''))],
    ['line-height', EXPECTED.lineHeights, (v) => Number(v.replace('px', ''))]
  ]
  for (const [prefix, expectedMap, toNumber] of keyMap) {
    for (const [name, expectedValue] of Object.entries(expectedMap)) {
      const decl = declarations.get(`--${prefix}-${name}`)
      if (!decl) {
        tokenDiff.push(`缺少 token --${prefix}-${name}`)
      } else if (toNumber(decl.value) !== expectedValue) {
        tokenDiff.push(`--${prefix}-${name} 值 ${decl.value} ≠ 期望 ${expectedValue}px`)
      }
    }
    const found = [...declarations.keys()].filter((key) => key.startsWith(`--${prefix}-`) && !key.includes('::'))
    for (const key of found) {
      const name = key.slice(prefix.length + 3)
      if (!(name in expectedMap)) tokenDiff.push(`表外 token ${key}`)
    }
  }
  for (const [name, expectedValue] of Object.entries(EXPECTED.shadows)) {
    const decl = declarations.get(`--${name}`)
    if (!decl) {
      tokenDiff.push(`缺少 token --${name}`)
    } else if (normalize(decl.value) !== expectedValue) {
      tokenDiff.push(`--${name} 值 "${decl.value}" ≠ 期望 "${expectedValue}"`)
    }
  }
  const focus = declarations.get('--focus-ring')
  if (!focus) {
    tokenDiff.push('缺少 token --focus-ring')
  } else if (normalize(focus.value) !== EXPECTED.focusRing) {
    tokenDiff.push(`--focus-ring 值 "${focus.value}" ≠ 期望 "${EXPECTED.focusRing}"`)
  }
  fileReport.push(
    `  字号/行高：期望 ${Object.keys(EXPECTED.fontSizes).length} 对；间距：${Object.keys(EXPECTED.spacing).length}；圆角：${Object.keys(EXPECTED.radius).length}；阴影：${Object.keys(EXPECTED.shadows).length}；焦点环：1`
  )
}

// ==================== WCAG 对比度实测 ====================

const hexToRgb = (hex) => {
  let value = hex.replace('#', '')
  if (value.length === 3) {
    value = value
      .split('')
      .map((c) => c + c)
      .join('')
  }
  return [parseInt(value.slice(0, 2), 16), parseInt(value.slice(2, 4), 16), parseInt(value.slice(4, 6), 16)]
}

const relativeLuminance = (hex) => {
  const [r, g, b] = hexToRgb(hex).map((channel) => {
    const c = channel / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

const contrastRatio = (foreground, background) => {
  const l1 = relativeLuminance(foreground)
  const l2 = relativeLuminance(background)
  const lighter = Math.max(l1, l2)
  const darker = Math.min(l1, l2)
  return (lighter + 0.05) / (darker + 0.05)
}

const getColor = (declarations, block, name) => {
  const decl = declarations.get(`${block}::--${name}`)
  return decl ? decl.value.toLowerCase() : EXPECTED.colors[name][block === 'colors-light' ? 0 : 1]
}

const CONTRAST_CASES = [
  ['浅色 text / bg', 'colors-light', 'color-text', 'color-bg', 4.5, 17.85],
  ['浅色 text-secondary / bg', 'colors-light', 'color-text-secondary', 'color-bg', 4.5, 7.58],
  ['浅色 primary / bg', 'colors-light', 'color-primary', 'color-bg', 4.5, 5.17],
  ['浅色 text-inverse / primary', 'colors-light', 'color-text-inverse', 'color-primary', 4.5, 5.17],
  ['浅色 success / bg', 'colors-light', 'color-success', 'color-bg', 4.5, 5.02],
  ['浅色 warning / bg', 'colors-light', 'color-warning', 'color-bg', 4.5, 4.92],
  ['浅色 error / bg', 'colors-light', 'color-error', 'color-bg', 4.5, 6.47],
  ['浅色 text-tertiary / bg', 'colors-light', 'color-text-tertiary', 'color-bg', 4.5, 4.76],
  ['浅色 control-border / bg', 'colors-light', 'color-control-border', 'color-bg', 3, 4.76],
  ['暗色 text / bg', 'colors-dark', 'color-text', 'color-bg', 4.5, 17.06],
  ['暗色 text-secondary / bg', 'colors-dark', 'color-text-secondary', 'color-bg', 4.5, 12.02],
  ['暗色 primary / bg', 'colors-dark', 'color-primary', 'color-bg', 4.5, 7.02],
  ['暗色 text-inverse / primary', 'colors-dark', 'color-text-inverse', 'color-primary', 4.5, 7.02],
  ['暗色 success / bg', 'colors-dark', 'color-success', 'color-bg', 4.5, 10.25],
  ['暗色 warning / bg', 'colors-dark', 'color-warning', 'color-bg', 4.5, 12.38],
  ['暗色 error / bg', 'colors-dark', 'color-error', 'color-bg', 4.5, 9.41],
  ['暗色 text-tertiary / bg', 'colors-dark', 'color-text-tertiary', 'color-bg', 4.5, 6.96],
  ['暗色 control-border / bg-elevated', 'colors-dark', 'color-control-border', 'color-bg-elevated', 3, 5.71]
]

const main = () => {
  const themeContent = readFileSync(THEME_FILE, 'utf8')
  const indexContent = readFileSync(INDEX_FILE, 'utf8')

  checkRawValues('src/styles/theme.scss', themeContent)
  checkRawValues('src/styles/index.scss', indexContent)

  const themeLines = collectLines(themeContent)
  const declarations = parseDeclarations(themeLines)
  checkColors(declarations)
  checkScale(declarations)

  const contrastRows = []
  let contrastFailed = 0
  for (const [label, block, fgName, bgName, threshold, expected] of CONTRAST_CASES) {
    const fg = getColor(declarations, block, fgName)
    const bg = getColor(declarations, block, bgName)
    const ratio = contrastRatio(fg, bg)
    const pass = ratio >= threshold
    const drift = Math.abs(ratio - expected)
    const consistent = drift <= 0.05
    if (!pass || !consistent) contrastFailed += 1
    contrastRows.push(
      `${label}: ${ratio.toFixed(2)}:1 (门槛 ${threshold}:1, 文档 ${expected.toFixed(2)}:1) ${
        pass ? '通过' : '不通过'
      }${consistent ? '' : ` [与文档偏差 ${drift.toFixed(2)}]`}`
    )
  }

  process.stdout.write('=== 设计 token 静态检查（T-21） ===\n')
  process.stdout.write('文件：src/styles/theme.scss, src/styles/index.scss\n\n')
  process.stdout.write('[token 清单]\n')
  fileReport.forEach((line) => process.stdout.write(`${line}\n`))
  process.stdout.write('\n[token 差异清单]\n')
  if (tokenDiff.length === 0) {
    process.stdout.write('  无差异：token 完整且与 ui-tokens.md v1.0 一致\n')
  } else {
    tokenDiff.forEach((item) => process.stdout.write(`  - ${item}\n`))
  }
  process.stdout.write('\n[裸值违规]\n')
  if (violations.length === 0) {
    process.stdout.write('  无：token 块外未发现裸 hex/rgb、表外字号/间距/圆角/阴影\n')
  } else {
    violations.forEach((item) => process.stdout.write(`  - ${item}\n`))
  }
  process.stdout.write('\n[核心对比度实测（WCAG 相对亮度）]\n')
  contrastRows.forEach((row) => process.stdout.write(`  ${row}\n`))

  const summary = `\n[结论] 裸值违规 ${violations.length} 项；token 差异 ${tokenDiff.length} 项；对比度不达标/偏差 ${contrastFailed} 项\n`
  process.stdout.write(summary)

  const failed = violations.length > 0 || tokenDiff.length > 0 || contrastFailed > 0
  process.exit(failed ? 1 : 0)
}

main()
