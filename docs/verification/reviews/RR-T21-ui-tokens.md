# RR-T21：双主题 UI token 映射与静态检查

- 评审编号：RR-T21
- 评审对象/任务编号：T-21 映射已确认 UI token（双主题 token v1.0 → 主题变量）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/design/ui-tokens.md` v1.0（确认日期 2026-11-12）、`docs/verification/verification-rules-v1.0.md` v1.0 §7、`docs/plan/task-board-v1.0.md` T-21
- 环境与 commit/变更集：Windows 10，Node v24.15.0 / npm 11.6.4；git HEAD `d0b415d` + 工作区未提交变更。被评审变更：
  - 重写 `test-platform/frontend/src/styles/theme.scss`
  - 重写 `test-platform/frontend/src/styles/index.scss`
  - 新增 `test-platform/frontend/scripts/check-tokens.mjs`
  - 修改 `test-platform/frontend/package.json`（脚本 `check:tokens`）
  - 未修改任何 views/layouts 与业务逻辑
- 证据路径：
  - 开发证据：`docs/verification/tasks/T-21/`（result.md、check-tokens.log、npm-test.log、npm-lint.log、npm-build.log、tp-var-compat.txt、eslint-baseline/after.json、lint-diff-summary.txt）
  - 评审方独立重跑：`docs/verification/reviews/evidence/test-rerun-20261112/`（check-tokens-direct.log、npm-test.log、npm-lint.log、npm-build.log）

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | 只改声明 scope | `git status`/`git diff HEAD` | 仅 theme.scss、index.scss、scripts/check-tokens.mjs、package.json；views/layouts 0 改动 | 通过 |
| 2 | 七核心色 + 8 扩展色与确认表逐值一致 | 逐行比对 ui-tokens.md §1-2 与 theme.scss:10-49 | 15 个颜色浅/暗双值全部一致（十六进制大小写差异，值相同） | 通过 |
| 3 | 六字号/行高一致 | 比对 ui-tokens.md §3 与 theme.scss:56-67 | 12/14/16/20/24/32px，行高 18/21/24/30/36/48px 全部一致 | 通过 |
| 4 | 间距 7 档一致 | 比对 ui-tokens.md §4 与 theme.scss:70-76 | 4/8/12/16/24/32/48px 一致，均 4 倍数 | 通过 |
| 5 | 圆角 4 档一致 | 比对 ui-tokens.md §5 与 theme.scss:79-82 | 0/4/8/999px 一致 | 通过 |
| 6 | 阴影 3 档一致 | 比对 ui-tokens.md §6 与 theme.scss:85-87 | 三档 rgba 值完全一致 | 通过 |
| 7 | 焦点环 | ui-tokens.md §6 末 + theme.scss:90-91 | `4px solid var(--color-primary)`，offset 4px | 通过 |
| 8 | 亮暗主题无表外裸值 | 独立运行 check-tokens 脚本 + 人工读 index.scss | 脚本「裸值违规 0 项」；index.scss 全部引用 var token；theme.scss 颜色仅出现在 token-block 内 | 通过 |
| 9 | 间距均 4 倍数 | 脚本 + 人工读 index.scss 的 margin/padding/gap | 均 var(--space-*)；无表外 px | 通过（见 L1 非间距类 60px/1px 说明） |
| 10 | Element Plus 变量映射 | theme.scss:98-123 | `--el-color-* / --el-bg-* / --el-text-* / --el-border-* / --el-disabled-* / --el-mask-color` 由 token 派生 | 通过 |
| 11 | `--tp-*` 兼容别名保留 | theme.scss:129-159；tp-var-compat.txt | 24 个别名全部有定义，值引用 token；视图引用名称未缺 | 通过（值收敛见 P-T21-1） |
| 12 | 核心对比度实测 | 独立运行 `node scripts/check-tokens.mjs` | 18 组全部通过且与文档值偏差 0.00 | 通过 |
| 13 | 独立重跑 check:tokens | `npm run check:tokens` / `node scripts/check-tokens.mjs` | 退出码 0；token 差异 0；裸值违规 0；对比度不达标/偏差 0 | 通过 |
| 14 | 独立重跑 build（Sass 编译 color-mix） | `npm run build` | 退出码 0；无新增 Sass 编译错误；15×legacy-js-api +1×chunk（历史） | 通过 |
| 15 | 未放宽检查标准 | 读 check-tokens.mjs 全文 | 硬编码 EXPECTED 与 ui-tokens.md 一致；逐条校验缺失/表外/裸值/对比度，违规即 exit 1 | 通过 |

补充：check-tokens.mjs 的 EXPECTED 常量（colors/fontSizes/lineHeights/spacing/radius/shadows/focusRing）经与 ui-tokens.md 逐条核对完全一致，脚本非"只报通过"的空壳。

## 2. 问题与风险等级

| # | 问题 | 依据（文件:行/日志） | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-T21-1 | 部分 `--tp-*` 兼容别名值被收敛为单一 token：`--tp-primary-light`、`--tp-primary-dark` 均指向 `--color-primary`（原为 #3b82f6/#1d4ed8）；`--tp-info` 指向 `--color-primary`（原为灰系）；`--tp-shadow-glow` 指向 `--shadow-lg`；`.stat-card` 渐变两端同为 `--color-primary`（退化为纯色） | theme.scss:130-159；index.scss:27-29 | 名称兼容、引用不断，但依赖 light/dark/info 差异的既有视图将出现轻微视觉变化（亮度层次、信息色）。符合 token 治理"禁止表外裸值"方向，非功能缺陷 | 低 | T-21 记录；页面视觉走查时（T-22+）复核观感 |
| P-T21-2 | 非间距类表外像素值仍存在（`min-height: calc(100vh - 60px)` 的 60px、`border: 1px solid`、`translateX(±16px)`、`transition 0.3s`、`opacity 0.9`） | index.scss:6,14,74,82,86,127,131,135,166,172,182,186,190 | 这些不属于 ui-tokens.md 的 spacing/radius/shadow/color token 范畴（间距约束仅限 margin/padding/gap），不构成 token 违规；仅为历史布局常量 | 低 | 记录性（如未来扩展布局 token 再收口） |

## 3. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 浏览器亮/暗主题逐页截图、透明度叠加后真实对比度、Element Plus 实际渲染、焦点环可见性、图表 canvas 颜色 | 属页面/组件验收（T-22+）；ui-tokens.md §7 明确要求实施后在亮暗主题下重新测量 | 静态 token 与 CSS 变量层面通过；页面级视觉/可访问性本轮"无法核验"，留待 T-22+ |
| L2 | 主题运行时切换（无后端/未启动前端服务） | 环境限制 | 运行时行为未验证 |

## 4. 待用户确认项

无新增需用户确认项（token 表已于 2026-11-12 确认；本轮仅映射）。P-T21-1 视觉收敛是否可接受建议在 T-22+ 页面走查时由用户一并确认观感。

## 5. 独立重跑记录

| 命令 | 结果 | 退出码 | 独立日志 |
|---|---|---:|---|
| `node scripts/check-tokens.mjs`（= `npm run check:tokens`） | token 差异 0；裸值违规 0；18 组对比度全部通过且偏差 0.00 | 0 | `evidence/test-rerun-20261112/check-tokens-direct.log` |
| `npm test` | 3 文件 / 29 用例通过 | 0 | `evidence/test-rerun-20261112/npm-test.log` |
| `npm run lint` | 1037 warnings / 0 errors | 0 | `evidence/test-rerun-20261112/npm-lint.log` |
| `npm run build` | 构建成功 6.25s，color-mix 正常编译 | 0 | `evidence/test-rerun-20261112/npm-build.log` |

## 6. 最终结论

**通过（静态 token 映射范围）。** 七色、六字号、间距、圆角、阴影、扩展 token 与 `ui-tokens.md` v1.0 逐值一致；亮暗主题共享样式无表外裸值、间距均 4 倍数；`--tp-*` 兼容别名保留；核心 18 组对比度实测全部达标；独立重跑 check:tokens/build/test/lint 全部退出码 0。P-T21-1/P-T21-2 为低风险记录项。浏览器级视觉/对比度与主题切换（L1/L2）属 T-22+ 范围，本轮标"无法核验"，不影响本任务静态范围结论。

## 7. 签名

reviewer，2026-11-12；本记录基于原始 SCSS 全文、静态检查脚本源码与独立重跑日志作出，未代开发修改任何代码。
