# 前端路由页面组件契约

- 版本：v1.0-review
- 日期：2026-11-12
- 状态：待用户确认；确认前不得按本契约改造页面
- 说明：路由页面无父传props时仍显式记录；API数据不复制成可由props推导的状态

## MainLayout

职责：提供导航、主题和响应式内容框架；请求接口：无，不缓存业务数据。

### props
| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| 无 | 无 | 否 | 无 | 布局不使用props |
### state
| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| navCollapsed | boolean | false | >1024用户折叠侧栏 |
| mobileDrawerOpen | boolean | false | <768打开/关闭抽屉，路由变化自动关闭 |
### events
| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 布局不向上发事件 |
### 插槽
| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| default | 无 | 渲染router-view；无匹配子路由由404处理 |

## LoginPage

职责：处理首管理员/登录和凭据错误；请求 `/auth/registrations`、`/auth/sessions`，不缓存密码。

### props
| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| 无 | 无 | 否 | 无 | 路由页面 |
### state
| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| mode | 'login' \| 'bootstrap' | 'login' | 服务返回系统初始化状态 |
| form | {username:string,password:string,pcIdentifier:string} | 均为'' | 用户输入 |
| requestState | 'idle' \| 'loading' \| 'error' | 'idle' | 提交及响应 |
| errorMessage | string \| null | null | 契约错误响应 |
### events
| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 登录成功仅导航 |
### 插槽
| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| 无 | 无 | 页面无插槽 |

## DashboardPage

职责：展示任务与设备统计；请求dashboard/trend/by-module，仅在进入页和用户明确刷新时更新。

### props
| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| 无 | 无 | 否 | 无 | 路由页面 |
### state
| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| days | number | 30 | 用户选择1～365趋势范围 |
| requestState | 'loading' \| 'ready' \| 'error' | 'loading' | 三个统计请求状态汇总 |
| errorMessage | string \| null | null | 任一请求失败 |
### events
| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 页面无父事件 |
### 插槽
| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| 无 | 无 | 页面无插槽 |

## DevicesPage

职责：展示授权设备、手动发现和改派；请求devices/device-discoveries/PATCH devices，不在首屏自动扫描。

### props
| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| 无 | 无 | 否 | 无 | 路由页面 |
### state
| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| statusFilter | DeviceStatus \| null | null | 用户筛选 |
| page / pageSize | number / number | 1 / 20 | 分页操作 |
| requestState | 'loading' \| 'ready' \| 'error' | 'loading' | 列表请求 |
| discovering | boolean | false | 明确刷新发现开始/结束 |
| activeDialog | 'detail' \| 'assign' \| null | null | 用户打开/关闭 |
### events
| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 页面无父事件 |
### 插槽
| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| 无 | 无 | 页面无插槽 |

## ModulesPage

职责：管理模块和测试项展示；请求现有modules/items API，按页缓存当前筛选， mutations后失效刷新。

### props
| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| 无 | 无 | 否 | 无 | 路由页面 |
### state
| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| activeModuleId | number \| null | null | 用户选择模块 |
| dialogMode | 'create' \| 'edit' \| null | null | 用户打开/关闭表单 |
| requestState | 'loading' \| 'ready' \| 'error' | 'loading' | 列表/详情请求 |
| submitting | boolean | false | 写操作开始/结束 |
### events
| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 页面无父事件 |
### 插槽
| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| 无 | 无 | 页面无插槽 |

## AITestPage

职责：提交自然语言并展示真实任务结果；请求legacy AI入口，必须委托同一任务创建服务，不缓存敏感输入。

### props
| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| 无 | 无 | 否 | 无 | 路由页面 |
### state
| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| inputText | string | '' | 用户输入 |
| requestState | 'idle' \| 'loading' \| 'error' | 'idle' | 提交/响应 |
| degradationMessage | string \| null | null | 无LLM或规划降级响应 |
### events
| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 创建成功导航任务 |
### 插槽
| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| 无 | 无 | 页面无插槽 |

## TasksPage

职责：展示任务/模板并执行取消、重跑和软删除；请求tasks/reruns/cancellations/DELETE，操作后刷新当前页。

### props
| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| 无 | 无 | 否 | 无 | 路由页面 |
### state
| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| filters | {status:TaskStatus\|null,search:string,taskKind:'instance'\|'daily_template'\|'all'} | null/''/'instance' | 用户筛选 |
| page / pageSize | number / number | 1 / 20 | 分页操作 |
| requestState | 'loading' \| 'ready' \| 'error' | 'loading' | 列表请求 |
| pendingActionTaskId | number \| null | null | 写操作开始/结束 |
### events
| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 页面无父事件 |
### 插槽
| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| 无 | 无 | 页面无插槽 |

## TaskCreatePage

职责：创建immediate/once/daily任务；请求devices/modules/tasks，参数默认值来自选中测试项，不持久化敏感参数。

### props
| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| 无 | 无 | 否 | 无 | 路由页面 |
### state
| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| currentStep | number | 0 | 用户上一步/下一步 |
| submitting | boolean | false | 创建开始/结束 |
| fieldErrors | Record<string,string> | {} | 客户端校验或服务端details |
| requestState | 'loading' \| 'ready' \| 'error' | 'loading' | 设备/模块请求 |
### events
| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 创建成功导航任务 |
### 插槽
| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| 无 | 无 | 页面无插槽 |

## TaskMonitorPage

职责：读取任务/记录并管理一个WS生命周期；请求tasks/records和WS，卸载不保留缓存连接。

### props
| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| 无 | 无 | 否 | 无 | taskId来自路由正整数参数 |
### state
| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| requestState | 'loading' \| 'ready' \| 'error' | 'loading' | 初始任务请求 |
| connectionState | 'connecting' \| 'open' \| 'closed' \| 'error' | 'closed' | WS生命周期 |
| reconnectAttempt | number | 0 | 实际重连/成功重置/卸载归零 |
| logPaused | boolean | false | 用户暂停/继续日志视图，不停止后端任务 |
### events
| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 页面无父事件 |
### 插槽
| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| 无 | 无 | 页面无插槽 |

## ReportsPage

职责：展示、对比和导出报告；请求reports/report-exports，按task_id+格式缓存只读结果，任务变化后失效。

### props
| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| 无 | 无 | 否 | 无 | 路由页面 |
### state
| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| selectedTaskId | number \| null | null | 用户选择主报告 |
| comparisonTaskId | number \| null | null | 用户选择对比任务 |
| exportFormat | ExportFormat | 'html' | 用户选择格式 |
| requestState | 'loading' \| 'ready' \| 'error' | 'loading' | 报告请求 |
| exporting | boolean | false | 导出开始/结束 |
### events
| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 页面无父事件 |
### 插槽
| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| 无 | 无 | 页面无插槽 |

## MemoryPage

职责：展示失败模式、基线和黄金案例；请求现有memory API，筛选变化即失效当前缓存。

### props
| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| 无 | 无 | 否 | 无 | 路由页面 |
### state
| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| activeTab | 'failure-patterns' \| 'baselines' \| 'golden-cases' | 'failure-patterns' | 用户切换 |
| query | string | '' | 用户输入筛选 |
| page / pageSize | number / number | 1 / 20 | 分页操作 |
| requestState | 'loading' \| 'ready' \| 'error' | 'loading' | 当前tab请求 |
### events
| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 页面无父事件 |
### 插槽
| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| 无 | 无 | 页面无插槽 |

## KnowledgePage

职责：管理知识条目和规则预览转换；请求knowledge/conversion-previews/conversions，转换后失效列表缓存。

### props
| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| 无 | 无 | 否 | 无 | 路由页面 |
### state
| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| filters | {query:string,entryType:string\|null,status:string\|null} | ''/null/null | 用户筛选 |
| page / pageSize | number / number | 1 / 20 | 分页操作 |
| requestState | 'loading' \| 'ready' \| 'error' | 'loading' | 列表/详情请求 |
| previewOpen | boolean | false | 用户打开/关闭预览 |
| converting | boolean | false | 转换开始/结束 |
### events
| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 页面无父事件 |
### 插槽
| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| 无 | 无 | 页面无插槽 |

## AdminUsersPage

职责：管理员建号和状态管理；请求users列表/POST/PATCH，写后刷新当前页，不缓存密码。

### props
| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| 无 | 无 | 否 | 无 | 路由页面 |
### state
| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| filters | {username:string,role:UserRole\|null,status:UserStatus\|null} | ''/null/null | 用户筛选 |
| page / pageSize | number / number | 1 / 20 | 分页操作 |
| requestState | 'loading' \| 'ready' \| 'error' | 'loading' | 列表请求 |
| createDialogOpen | boolean | false | 用户打开/关闭建号 |
| pendingUserId | number \| null | null | 用户写操作开始/结束 |
### events
| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 页面无父事件 |
### 插槽
| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| 无 | 无 | 页面无插槽 |

## ProfilePage

职责：展示本人资料并修改密码；请求现有auth/me/change-password，不缓存密码。

### props
| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| 无 | 无 | 否 | 无 | 路由页面 |
### state
| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| requestState | 'loading' \| 'ready' \| 'error' | 'loading' | 本人资料请求 |
| passwordDialogOpen | boolean | false | 用户打开/关闭 |
| submitting | boolean | false | 修改开始/结束 |
| errorMessage | string \| null | null | 契约错误响应 |
### events
| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 页面无父事件 |
### 插槽
| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| 无 | 无 | 页面无插槽 |

## NotFoundPage

职责：说明路由不存在并提供可键盘操作的返回；请求接口与缓存：无。

### props
| 名称 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| 无 | 无 | 否 | 无 | 路由页面 |
### state
| 名称 | 类型 | 初始值 | 变更触发 |
|---|---|---|---|
| 无 | 无 | 无 | 纯展示与导航 |
### events
| 事件名 | 载荷类型 | 触发时机 |
|---|---|---|
| 无 | 无 | 仅路由导航 |
### 插槽
| 名称 | 作用域参数 | 空内容兜底 |
|---|---|---|
| 无 | 无 | 页面无插槽 |

## 页面通用约束

表单业务字段可以由页面表单对象维护，但API响应、筛选后列表、五类统计和通过率不得重复维护可推导state。所有写按钮在loading/disabled/readonly时不得发请求；错误只显示契约安全摘要。实际组件文件名使用对应PascalCase，路由可继续现有懒加载路径。
