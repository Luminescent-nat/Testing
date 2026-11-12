# T-21 验证记录：双主题设计 token 映射与静态检查

## 1. 任务
把 `docs/design/ui-tokens.md` v1.0 全量映射到 `theme.scss` 与 `index.scss` 的 CSS 变量（七色 + 8 扩展色 + 6 字号/行高 + 7 间距 + 4 圆角 + 3 阴影 + 焦点环），完成 Element Plus 变量映射，保留现有视图引用的 `--tp-*` 兼容别名；移除共享样式中的表外裸值；新增静态 token 检查脚本并输出 token 差异清单与核心对比度实测。

## 2. 变更文件
| 文件 | 类型 | 说明 |
|---|---|---|
| `test-platform/frontend/src/styles/theme.scss` | 重写 | 完整 token 定义（token-block 包裹）+ Element Plus 映射 + `--tp-*` 兼容别名 + 基础样式改用 token |
| `test-platform/frontend/src/styles/index.scss` | 重写 | 共享样式裸颜色/字号/12px 圆角/10·15·20px 间距全部替换为 token |
| `test-platform/frontend/scripts/check-tokens.mjs` | 新增 | 静态检查 + WCAG 对比度实测（`npm run check:tokens`） |
| `test-platform/frontend/package.json` | 修改 | 新增脚本 `check:tokens`（与 T-20 共用） |

未修改任何视图文件（`views/**`、`layouts/**`）与业务逻辑；视图引用的 `--tp-*` 名称全部通过别名保留。

## 3. 环境
- OS：Windows（工作目录 `D:\MCTEST\test-platform\frontend`）
- Node：v24.15.0；npm：11.6.4
- token 规范：docs/design/ui-tokens.md v1.0（2026-11-12 确认）

## 4. 命令与退出码
| 命令 | 开始 | 结束 | 退出码 | 原始日志 |
|---|---|---|---|---|
| `npm run check:tokens` | 2026-11-12 11:47:53.254 | 2026-11-12 11:47:53.509 | 0 | `check-tokens.log` |
| `npm test` | 2026-11-12 11:57:46.623 | 2026-11-12 11:57:48.059 | 0 | `npm-test.log` |
| `npm run lint` | 2026-11-12 11:57:48.079 | 2026-11-12 11:57:49.332 | 0 | `npm-lint.log` |
| `npm run build` | 2026-11-12 11:57:49.334 | 2026-11-12 11:57:55.997 | 0 | `npm-build.log` |

## 5. DoD 逐条证据
- **七色、六字号、间距、圆角、阴影及扩展 token 均来自确认表**
  - `check-tokens.log`「token 清单」：颜色 15 个（7 核心 + 8 扩展），字号/行高 6 对，间距 7，圆角 4，阴影 3，焦点环 1。
  - 「token 差异清单」：`无差异：token 完整且与 ui-tokens.md v1.0 一致`（脚本逐一比对浅色/暗色 hex 与字号、间距、圆角、阴影、焦点环值，缺失或表外均计为差异）。
- **亮暗主题无表外魔法值，间距均 4 倍数**
  - 脚本将 theme/index 中 `token-block` 之外的一切 hex、`rgb/rgba`、非 `var(--font-size-*)` 字号、非 `0/4/8/12/16/24/32/48` 间距、非 `0/4/8/999` 圆角、非 `var(--shadow-*)` 阴影、以及块外 token 声明列为违规；结果「裸值违规 0 项」。
  - 圆角仅 `--radius-none/sm/md/full = 0/4/8/999`；间距仅 7 档 4 的倍数；阴影仅三档，无发光阴影；焦点环 `4px solid var(--color-primary)`，偏移 4px。
- **Element Plus 变量映射**：`--el-color-primary/success/warning/danger/error`、`--el-bg-color*`、`--el-text-color-*`、`--el-border-color*`、`--el-disabled-*` 等由 token 派生，并用 `:root, html.light, html.dark` 组覆盖 element-plus 暗色默认值。
- **`--tp-*` 兼容别名**：`tp-var-compat.txt` 显示视图/共享样式引用的 16 个 `--tp-*` 名称全部有定义（缺 0），另保留 `--tp-primary-dark/--tp-bg/--tp-bg-overlay/--tp-divider/--tp-success/--tp-warning/--tp-danger/--tp-text-inverse` 等既有别名共 24 个；别名值均引用已确认 token（半透明用 `color-mix(... var(--color-*) ...)` 派生，不新增裸色）。
- **核心对比度实测（WCAG 相对亮度，阈值对照 ui-tokens.md 第 7 节）**：18 组全部通过且与文档值偏差 ≤0.05，例如
  - 浅色 text/bg 17.85:1、text-secondary/bg 7.58:1、primary/bg 5.17:1、success/bg 5.02:1、warning/bg 4.92:1、error/bg 6.47:1、text-tertiary/bg 4.76:1、control-border/bg 4.76:1；
  - 暗色 text/bg 17.06:1、text-secondary/bg 12.02:1、primary/bg 7.02:1、success/bg 10.25:1、warning/bg 12.38:1、error/bg 9.41:1、text-tertiary/bg 6.96:1、control-border/bg-elevated 5.71:1。
  - 完整表格见 `check-tokens.log`「核心对比度实测」段。
- **构建可用**：`npm run build` 退出码 0，Sass 正常编译 `color-mix()`，无新增编译错误。

## 6. 既有告警与新增告警对比
- **ESLint**：基线 1037 warnings / 0 errors → 改动后 1037 warnings / 0 errors（逐文件无变化；本任务未新增/修改 .js 业务文件，故无新增告警）。
- **Build**：`legacy-js-api` 弃用告警 15 条、chunk>500kB 1 条，与改动前基线一致（历史告警，T-35 处理范围）；无 CJS 错误、无 Sass 编译错误。退出码 0。
- **样式构建**：theme/index 均为 SCSS 且经 Vite 正常编译，无新增 ESLint/Sass/build 告警。
- 未通过关闭规则、排除文件或降低检查标准达标。

## 7. 未验证项
- 未做浏览器亮/暗主题逐页截图与走查（360/767/768/1024/1025/1440px 断点、Element Plus 实际渲染状态、透明度叠加后的真实对比度、焦点环实际可见性）——属 T-22+ 页面/组件验收范围，`ui-tokens.md` 第 7 节亦要求“实施后须在亮暗主题下重新测量”。
- 未在真实后端与浏览器运行时验证主题切换效果（环境无后端、未启动前端服务）。
- 图表（ECharts）内联 `var(--tp-*)` 颜色与 canvas 渲染未做真机截图核对。

## 8. 回退说明
- 用原始版本还原 `src/styles/theme.scss`、`src/styles/index.scss` 即可恢复旧主题变量与共享样式；视图无需改动。
- 删除 `scripts/check-tokens.mjs` 并移除 `package.json` 的 `check:tokens` 脚本。
- 回退不影响视图业务逻辑；`--tp-*` 旧引用在回退后仍可工作。

## 9. 证据文件
- `check-tokens.log`、`npm-test.log`、`npm-lint.log`、`npm-build.log`
- `tp-var-compat.txt`、`eslint-baseline.json`、`eslint-after.json`、`lint-diff-summary.txt`
