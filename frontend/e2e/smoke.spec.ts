import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/projects', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            id: 'project-1',
            project_code: 'EP-VOL-V2',
            name: 'Electronic Pipette Validation',
            description: 'Volume setting vertical slice',
            product_type_id: 'pt-ep',
            product_type: {
              id: 'pt-ep',
              code: 'ELECTRONIC_PIPETTE',
              name: 'Electronic Pipette',
              display_name: '电子移液枪',
              status: 'Active',
            },
            knowledge_pack_id: 'kp-ep-1',
            knowledge_pack_version: '1.0',
            status: 'Active',
            revision: 1,
          },
        ],
        total: 1,
      }),
    })
  })
  await page.route('**/api/v1/product-types', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'pt-ep',
          code: 'ELECTRONIC_PIPETTE',
          name: 'Electronic Pipette',
          display_name: '电子移液枪',
          description: '液体处理、马达、吸头与配置持久化知识',
          status: 'Active',
        },
      ]),
    })
  })
})

test('shows the project workspace and starts the four-step wizard', async ({ page }) => {
  await page.goto('/projects')
  await expect(page.getByRole('heading', { name: '项目' })).toBeVisible()
  await expect(page.getByText('Electronic Pipette Validation')).toBeVisible()

  await page.getByRole('button', { name: '创建项目' }).first().click()
  await expect(page.getByRole('heading', { name: '创建项目' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '选择 Product Type' })).toBeVisible()
  await expect(page.getByRole('button', { name: /电子移液枪/ })).toBeVisible()
})
