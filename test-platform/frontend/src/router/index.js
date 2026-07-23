import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/store/user'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { public: true }
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: { title: '仪表盘', icon: 'Odometer' }
      },
      {
        path: 'devices',
        name: 'Devices',
        component: () => import('@/views/devices/index.vue'),
        meta: { title: '设备管理', icon: 'Cellphone' }
      },
      {
        path: 'modules',
        name: 'Modules',
        component: () => import('@/views/modules/index.vue'),
        meta: { title: '测试模块', icon: 'Grid' }
      },
      {
        path: 'ai-test',
        name: 'AITest',
        component: () => import('@/views/ai-test/index.vue'),
        meta: { title: 'AI 测试', icon: 'MagicStick' }
      },
      {
        path: 'tasks',
        name: 'Tasks',
        component: () => import('@/views/tasks/index.vue'),
        meta: { title: '测试任务', icon: 'List' }
      },
      {
        path: 'tasks/create',
        name: 'TaskCreate',
        component: () => import('@/views/tasks/create.vue'),
        meta: { title: '创建任务', icon: 'CirclePlus', hideInMenu: true }
      },
      {
        path: 'tasks/monitor/:id',
        name: 'TaskMonitor',
        component: () => import('@/views/tasks/monitor.vue'),
        meta: { title: '任务监控', icon: 'VideoPlay', hideInMenu: true }
      },
      {
        path: 'reports',
        name: 'Reports',
        component: () => import('@/views/reports/index.vue'),
        meta: { title: '测试报告', icon: 'Document' }
      },
      {
        path: 'memory',
        name: 'Memory',
        component: () => import('@/views/memory/index.vue'),
        meta: { title: '基线知识库', icon: 'Collection' }
      },
      {
        path: 'knowledge',
        name: 'Knowledge',
        component: () => import('@/views/knowledge/index.vue'),
        meta: { title: '测试知识库', icon: 'Notebook' }
      },
      {
        path: 'admin/users',
        name: 'AdminUsers',
        component: () => import('@/views/admin/users.vue'),
        meta: { title: '用户管理', icon: 'UserFilled', requireAdmin: true }
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/profile/index.vue'),
        meta: { title: '个人信息', icon: 'User', hideInMenu: true }
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/error/404.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫
router.beforeEach(async (to, from, next) => {
  const userStore = useUserStore()
  
  // 公开页面直接放行
  if (to.meta.public) {
    next()
    return
  }
  
  // 检查登录状态
  if (!userStore.token) {
    next('/login')
    return
  }
  
  // 若已有 token 但用户信息未加载，先拉取用户信息
  if (!userStore.userInfo) {
    await userStore.fetchUserInfo()
  }
  
  // 检查管理员权限
  if (to.meta.requireAdmin && userStore.userInfo?.role !== 'admin') {
    next('/')
    return
  }
  
  next()
})

export default router
