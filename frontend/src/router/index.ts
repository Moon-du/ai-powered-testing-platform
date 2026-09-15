import { createRouter, createWebHistory } from 'vue-router'

import AppShell from '@/components/layout/AppShell.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    {
      path: '/',
      component: AppShell,
      children: [
        { path: '', redirect: '/projects' },
        {
          path: 'projects',
          name: 'projects',
          component: () => import('@/views/ProjectsListView.vue'),
          meta: { title: '项目' },
        },
        {
          path: 'projects/new',
          name: 'project-create',
          component: () => import('@/views/ProjectCreateView.vue'),
          meta: { title: '创建项目' },
        },
        {
          path: 'projects/:projectId',
          name: 'project-overview',
          component: () => import('@/views/ProjectOverviewView.vue'),
          meta: { title: '项目概览' },
        },
        {
          path: 'projects/:projectId/requirements',
          name: 'project-requirements',
          component: () => import('@/views/RequirementsListView.vue'),
          meta: { title: '需求管理' },
        },
        {
          path: 'projects/:projectId/requirements/:requirementId',
          name: 'requirement-workspace',
          component: () => import('@/views/RequirementWorkspaceView.vue'),
          meta: { title: '需求工作台' },
        },
        {
          path: 'projects/:projectId/coverage',
          name: 'project-coverage',
          component: () => import('@/views/CoverageView.vue'),
          meta: { title: '覆盖率' },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
    },
  ],
})

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : '工作台'
  document.title = `${title} · AI 测试工程平台`
})

export default router
