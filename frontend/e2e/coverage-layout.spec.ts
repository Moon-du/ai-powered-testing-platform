import { expect, test } from '@playwright/test'

test('coverage labels stay below the percentage and inside each card', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/v1/projects/project-coverage') {
      await route.fulfill({
        json: {
          id: 'project-coverage',
          project_code: 'EP-DEMO',
          name: 'Electronic Pipette Demo',
          description: 'Coverage layout validation',
          product_type_id: 'pt-ep',
          knowledge_pack_id: 'kp-ep-1',
          knowledge_pack_version: '1.0',
          status: 'ACTIVE',
        },
      })
      return
    }
    if (path === '/api/v1/projects/project-coverage/coverage') {
      await route.fulfill({
        json: {
          requirements: { total: 10, analyzed: 8, percentage: 80 },
          assertion_coverage: { total: 20, covered: 15, percentage: 75 },
          risk_coverage: { total: 12, covered: 9, percentage: 75 },
          scenario: { total: 18, approved: 12, percentage: 67 },
          test_cases: { total: 24, approved: 16, percentage: 67 },
          issues: {
            requirement_gaps: 1,
            undefined_expected_behaviors: 2,
            stale_assets: 0,
          },
        },
      })
      return
    }
    if (path === '/api/v1/projects') {
      await route.fulfill({ json: { items: [] } })
      return
    }
    await route.fulfill({ status: 404, json: { detail: 'Not mocked' } })
  })

  await page.goto('/projects/project-coverage/coverage')

  const cards = page.locator('.coverage-card')
  await expect(cards).toHaveCount(5)
  await expect(page.getByText('Approved Test Cases', { exact: true })).toBeVisible()

  const firstCardBox = await cards.first().boundingBox()
  expect(firstCardBox).not.toBeNull()

  for (let index = 0; index < 5; index += 1) {
    const card = cards.nth(index)
    const progress = card.locator('.ant-progress')
    const meta = card.locator('.coverage-card__meta')
    const [cardBox, progressBox, metaBox] = await Promise.all([
      card.boundingBox(),
      progress.boundingBox(),
      meta.boundingBox(),
    ])

    expect(cardBox).not.toBeNull()
    expect(progressBox).not.toBeNull()
    expect(metaBox).not.toBeNull()
    expect(metaBox!.y).toBeGreaterThanOrEqual(progressBox!.y + progressBox!.height - 1)
    expect(metaBox!.x).toBeGreaterThanOrEqual(cardBox!.x)
    expect(metaBox!.x + metaBox!.width).toBeLessThanOrEqual(cardBox!.x + cardBox!.width + 1)
    expect(cardBox!.y).toBeCloseTo(firstCardBox!.y, 0)
    expect(cardBox!.height).toBeCloseTo(firstCardBox!.height, 0)
  }

  const menu = page.locator('.app-menu')
  await expect(menu.getByText('项目', { exact: true })).toHaveCount(0)
  await expect(menu.getByText('项目概览', { exact: true })).toBeVisible()
  await expect(menu.getByText('需求与测试资产', { exact: true })).toBeVisible()
  await expect(menu.getByText('覆盖率', { exact: true })).toBeVisible()
  await expect(page.locator('.app-breadcrumb')).toContainText('主页面')
  await expect(page.locator('.app-breadcrumb')).toContainText('Electronic Pipette Demo')

  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  )
  expect(hasHorizontalOverflow).toBe(false)

  await page.locator('.app-breadcrumb__link').filter({ hasText: '主页面' }).click()
  await expect(page).toHaveURL(/\/projects$/)
  await expect(page.locator('.app-menu').getByText('项目', { exact: true })).toBeVisible()

  const [collapseButtonBox, homeButtonBox] = await Promise.all([
    page.locator('.collapse-button').boundingBox(),
    page.locator('.app-breadcrumb__link').filter({ hasText: '主页面' }).boundingBox(),
  ])
  expect(collapseButtonBox).not.toBeNull()
  expect(homeButtonBox).not.toBeNull()
  const collapseCenterY = collapseButtonBox!.y + collapseButtonBox!.height / 2
  const homeCenterY = homeButtonBox!.y + homeButtonBox!.height / 2
  expect(Math.abs(collapseCenterY - homeCenterY)).toBeLessThanOrEqual(1)

  await page.locator('.collapse-button').click()
  const collapsedSider = page.locator('.app-sider.ant-layout-sider-collapsed')
  await expect(collapsedSider).toBeVisible()
  await expect(collapsedSider).toHaveCSS('width', '72px')
  const [siderBox, selectedIconBox] = await Promise.all([
    collapsedSider.boundingBox(),
    collapsedSider.locator('.ant-menu-item-selected .ant-menu-item-icon').boundingBox(),
  ])
  expect(siderBox).not.toBeNull()
  expect(selectedIconBox).not.toBeNull()
  const siderCenterX = siderBox!.x + siderBox!.width / 2
  const iconCenterX = selectedIconBox!.x + selectedIconBox!.width / 2
  expect(Math.abs(siderCenterX - iconCenterX)).toBeLessThanOrEqual(1)
})
