# 测试平台前端

基于 Vue3 + Element Plus + Pinia 的现代化前端界面，支持亮色/暗色双主题切换。

## 特性

- Vue 3 Composition API
- Element Plus 组件库
- Pinia 状态管理
- Vue Router 路由
- SCSS 样式预处理
- 亮色/暗色主题切换
- 响应式布局

## 项目结构

```
src/
├── api/                    # API接口封装
│   └── index.js
├── components/             # 公共组件
│   └── Breadcrumb.vue      # 面包屑组件
├── layouts/                # 布局组件
│   └── MainLayout.vue      # 主布局（侧边栏+顶部导航）
├── router/                 # 路由配置
│   └── index.js
├── store/                  # Pinia状态管理
│   ├── theme.js            # 主题状态
│   └── user.js             # 用户状态
├── styles/                 # 样式文件
│   ├── theme.scss          # 主题变量
│   └── index.scss          # 通用样式
├── utils/                  # 工具函数
│   └── request.js          # HTTP请求封装
├── views/                  # 页面视图
│   ├── login/              # 登录页
│   │   └── index.vue
│   ├── dashboard/          # 仪表盘
│   │   └── index.vue
│   ├── devices/            # 设备管理
│   │   └── index.vue
│   ├── tasks/              # 测试任务
│   │   ├── create.vue      # 创建任务
│   │   ├── monitor.vue     # 任务监控
│   │   └── index.vue       # 任务列表
│   ├── modules/            # 测试模块
│   │   └── index.vue
│   ├── reports/            # 测试报告
│   │   └── index.vue
│   └── admin/              # 管理员功能
│       └── users.vue       # 用户管理
├── App.vue
└── main.js
```

## 主题切换

项目实现了完善的双主题系统：

### 实现方式

1. **CSS变量** (`styles/theme.scss`)
   - 定义了两套颜色变量（亮色/暗色）
   - 使用 `:root` 和 `.dark` 类名切换

2. **Pinia状态管理** (`store/theme.js`)
   - 管理当前主题状态
   - 自动持久化到 localStorage
   - 提供 `toggleTheme()` 方法

3. **Element Plus适配**
   - 覆盖 Element Plus CSS 变量
   - 自动跟随主题变化

### 使用方法

```vue
<template>
  <!-- 切换按钮 -->
  <el-button 
    circle 
    :icon="themeStore.theme === 'light' ? Moon : Sunny"
    @click="themeStore.toggleTheme()"
  />
</template>

<script setup>
import { useThemeStore } from '@/store/theme'
const themeStore = useThemeStore()
</script>
```

### 主题变量

```scss
// 亮色主题（默认）
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f5f7fa;
  --text-primary: #303133;
  --text-secondary: #606266;
  --border-color: #dcdfe6;
  --shadow-color: rgba(0, 0, 0, 0.1);
}

// 暗色主题
.dark {
  --bg-primary: #141414;
  --bg-secondary: #1d1d1d;
  --text-primary: #e0e0e0;
  --text-secondary: #b0b0b0;
  --border-color: #434343;
  --shadow-color: rgba(0, 0, 0, 0.3);
}
```

## 页面功能

### 1. 登录页 (`/login`)
- 用户名/密码登录
- 用户注册功能
- 渐变背景设计

### 2. 仪表盘 (`/dashboard`)
- 统计数据卡片展示
- 在线设备列表
- 最近测试任务
- 快捷操作入口

### 3. 设备管理 (`/devices`)
- 设备卡片网格展示
- 搜索和筛选功能
- 刷新ADB设备
- 快速开始测试

### 4. 创建任务 (`/tasks/create`)
- 测试项选择（按模块分组）
- 设备选择
- 任务确认和创建

### 5. 其他页面
- 测试模块管理
- 任务列表和历史
- 测试报告查看
- 用户管理（管理员）

## 快速开始

```bash
# 安装依赖
npm install

# 开发模式启动
npm run dev

# 构建生产环境
npm run build
```

## 端到端测试 (E2E)

项目使用 [Playwright](https://playwright.dev/) 编写前端 E2E 测试，覆盖登录、侧边栏导航、关键按钮交互、任务创建、报告查看等核心流程。

### 目录结构

```
tests/e2e/
├── global-setup.mjs        # 全局前置：确保后端存在 e2e-admin 管理员账号
├── auth.setup.spec.js      # 登录态初始化并保存 storage state
├── navigation.spec.js      # 侧边栏各菜单进入与页面渲染
├── interactions.spec.js    # 主题切换、快捷按钮、设备刷新、用户管理操作按钮
└── task-workflow.spec.js   # 创建任务页交互、报告列表时间显示
```

### 环境要求

- 后端服务已启动：http://localhost:8000
- 前端开发服务已启动：http://localhost:3000
- 已安装 Chromium（执行 `npx playwright install chromium`）

### 运行测试

```bash
# 运行全部 E2E 测试
npm run test:e2e

# UI 模式调试
npm run test:e2e:ui

# 调试模式
npm run test:e2e:debug
```

### 覆盖范围

- 登录态初始化（`auth.setup.spec.js`）
- 侧边栏导航与页面渲染（`navigation.spec.js`）
- 关键按钮与交互（`interactions.spec.js`）：主题切换、仪表盘快捷入口、设备刷新、用户管理列表与操作按钮
- 任务与报告流程（`task-workflow.spec.js`）：创建任务页模块/测试项选择、报告列表时间显示

可通过环境变量自定义地址与账号：

```bash
set FRONTEND_URL=http://localhost:3000
set BACKEND_URL=http://localhost:8000
set E2E_ADMIN_USER=e2e-admin
set E2E_ADMIN_PASS=e2e-admin-pass
npm run test:e2e
```

## 主题预览

### 亮色主题
- 白色背景
- 深色文字
- 清晰的边框

### 暗色主题
- 深灰背景
- 浅色文字
- 柔和的边框

切换按钮位于顶部导航栏右侧，点击即可实时切换主题。
