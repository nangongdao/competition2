import { test, expect, type Page } from '@playwright/test'

/**
 * E2E 关键用户流程测试（TD-7 补强）。
 *
 * 通过 page.route 拦截 API 请求，用桩数据驱动，无需真实后端 / ASR / NMT，
 * 可本地与 CI 稳定运行。
 */

// —— 测试辅助 ——

/** 拦截本地设置等 API，返回可用的桩响应，避免 404 噪声。 */
async function stubApi(page: Page): Promise<void> {
  await page.route('**/api/v1/settings/local*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    })
  })
  await page.route('**/api/v1/translation-memory*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total_entries: 0, hits: 0, misses: 0 }),
    })
  })
  await page.route('**/api/v1/session-history*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ sessions: [] }),
    })
  })
}

// —— 测试用例 ——

test.describe('应用加载与控制面板', () => {
  test('应用渲染并显示控制面板', async ({ page }) => {
    await stubApi(page)
    await page.goto('/')

    // 应用品牌名可见
    await expect(page.getByText('AI 同声传译助手').first()).toBeVisible()
    // 控制面板 aria-label
    await expect(page.getByRole('complementary', { name: '实时翻译控制' })).toBeVisible()
    // 关键控件存在
    await expect(page.getByLabel('源语言')).toBeVisible()
    await expect(page.getByLabel('目标语言')).toBeVisible()
    // 开始翻译按钮
    await expect(page.getByRole('button', { name: '开始翻译' })).toBeVisible()
  })

  test('切换源/目标语言与翻译风格', async ({ page }) => {
    await stubApi(page)
    await page.goto('/')

    const source = page.getByLabel('源语言')
    await source.selectOption({ label: '英语' })
    await expect(source).toHaveValue('en')

    const target = page.getByLabel('目标语言')
    await target.selectOption({ label: '日语' })
    await expect(target).toHaveValue('ja')

    const style = page.getByLabel('翻译风格')
    await style.selectOption({ label: '忠实' })
    await expect(style).toHaveValue('faithful')
  })

  test('切换音频输入源为标签页/窗口', async ({ page }) => {
    await stubApi(page)
    await page.goto('/')

    const audioSource = page.getByLabel('音频输入')
    await audioSource.selectOption({ label: '标签页/窗口' })
    await expect(audioSource).toHaveValue('tab')
  })
})

test.describe('面板开关（懒加载模块）', () => {
  test('打开设置面板', async ({ page }) => {
    await stubApi(page)
    await page.goto('/')

    await page.getByRole('button', { name: '设置', exact: true }).click()
    // 设置 modal 出现
    await expect(page.locator('.settings-modal-title')).toBeVisible()
  })

  test('打开字幕历史与导出面板', async ({ page }) => {
    await stubApi(page)
    await page.goto('/')

    await page.getByRole('button', { name: /历史与导出/ }).click()
    // 历史面板懒加载渲染出标题
    await expect(page.getByText('字幕历史').first()).toBeVisible()
  })

  test('打开字幕样式面板', async ({ page }) => {
    await stubApi(page)
    await page.goto('/')

    await page.getByRole('button', { name: '字幕样式' }).click()
    await expect(page.getByRole('heading', { name: '字幕样式' })).toBeVisible()
  })
})

test.describe('字幕渲染（mock WebSocket）', () => {
  test('收到 asr_final 与 translation_token 后渲染字幕', async ({ page }) => {
    await stubApi(page)
    // 无头环境无真实麦克风：mock getUserMedia 返回一个含 audio track 的流，
    // 满足 AudioCapture 校验（getAudioTracks 非空），且 URL 匹配后端带会话路径。
    await page.addInitScript(() => {
      const fakeTrack = {
        stop: () => {},
        getSettings: () => ({}),
        kind: 'audio',
        label: 'fake mic',
      } as unknown as MediaStreamTrack
      const fakeStream = {
        getTracks: () => [fakeTrack],
        getAudioTracks: () => [fakeTrack],
        addTrack: () => {},
        removeTrack: () => {},
      } as unknown as MediaStream
      if (navigator.mediaDevices) {
        navigator.mediaDevices.getUserMedia = async () => fakeStream
        navigator.mediaDevices.getDisplayMedia = async () => fakeStream
      }
    })
    // mock 翻译 WebSocket：模拟后端推送识别与译文消息。
    await page.routeWebSocket('**/api/v1/ws/translate**', (ws) => {
      ws.onMessage(() => {
        // 先推送源识别。
        ws.send(
          JSON.stringify({
            type: 'asr_final',
            segment_id: 'seg-1',
            segment_index: 0,
            text: 'Hello world',
            confidence: 0.98,
          }),
        )
        // 译文 token 分两次：先累积文本（is_final=false），再标记完成。
        setTimeout(() => {
          ws.send(
            JSON.stringify({
              type: 'translation_token',
              segment_id: 'seg-1',
              segment_index: 0,
              token: '你好，世界',
              is_final: false,
            }),
          )
          setTimeout(() => {
            ws.send(
              JSON.stringify({
                type: 'translation_token',
                segment_id: 'seg-1',
                segment_index: 0,
                token: '',
                is_final: true,
              }),
            )
          }, 50)
        }, 50)
      })
    })

    await page.goto('/')
    // 点击开始翻译建立 WS 连接并收到桩字幕。
    await page.getByRole('button', { name: '开始翻译' }).click()

    // 源字幕渲染
    await expect(page.locator('.subtitle-source').first()).toContainText('Hello world', {
      timeout: 10_000,
    })
    // 译文字幕渲染
    await expect(page.locator('.subtitle-translated').first()).toContainText('你好，世界', {
      timeout: 10_000,
    })
  })
})
