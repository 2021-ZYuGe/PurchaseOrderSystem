import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/order' },
  {
    path: '/order',
    name: 'order',
    component: () => import('./pages/OrderPage.vue'),
    meta: { title: '下单' },
  },
  {
    path: '/contract',
    name: 'contract',
    component: () => import('./pages/ContractPage.vue'),
    meta: { title: '主合同' },
  },
  {
    path: '/import',
    name: 'import',
    component: () => import('./pages/ImportPage.vue'),
    meta: { title: '导入合同' },
  },
  {
    path: '/welcome',
    name: 'welcome',
    component: () => import('./pages/WelcomePage.vue'),
    meta: { title: '欢迎使用' },
  },
  {
    path: '/system',
    name: 'system',
    component: () => import('./pages/SystemPage.vue'),
    meta: { title: '系统状态' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/order' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  document.title = (to.meta.title ? to.meta.title + ' - ' : '') + '采购下单系统'
})

export default router
