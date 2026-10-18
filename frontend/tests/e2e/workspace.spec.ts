import { expect, test } from "@playwright/test";

const clip = {
  id: "clip-1",
  kind: "IMAGE",
  status: "INBOX",
  rawText: null,
  editableText: "A handwritten insight about optical interconnects",
  note: "Use in the architecture section",
  sourceUrl: null,
  sourceTitle: "Whiteboard note",
  createdAt: "2026-10-18T12:00:00Z",
  extractionStatus: "COMPLETED",
  ocrMarkdown: "A handwritten insight about optical interconnects",
  ocrText: "A handwritten insight about optical interconnects",
  ocrLatex: "E = mc^2",
  tags: [{ id: "tag-1", name: "Photonics" }],
  assets: [{ id: "asset-1", originalName: "note.png", mediaType: "image/png", byteSize: 100, checksumSha256: "abc", relativePath: "ab/abc.png" }],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/v1/clips") {
      await route.fulfill({ json: { data: [clip], pagination: { totalItems: 1 } } });
    } else if (url.pathname === "/api/v1/tags") {
      await route.fulfill({ json: { data: clip.tags } });
    } else if (url.pathname === "/api/v1/topics") {
      await route.fulfill({ json: { data: [{ id: "topic-1", title: "Optical compute", description: "Evidence", clipCount: 1 }] } });
    } else if (url.pathname === "/api/v1/topics/topic-1") {
      await route.fulfill({ json: { data: { id: "topic-1", title: "Optical compute", description: "Evidence", clips: [{ position: 0, annotation: null, representation: "EDITED", clip }] } } });
    } else {
      await route.fulfill({ json: { data: {} } });
    }
  });
});

test("responsive inbox works without browser errors", async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on("console", (message) => { if (message.type() === "error" || message.type() === "warning") errors.push(message.text()); });
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "收件箱", exact: true })).toBeVisible();
  await expect(page.getByLabel("类型筛选")).toBeVisible();
  await expect(page.getByLabel("标签筛选")).toBeVisible();
  await expect(page.getByLabel("新标签名称")).toBeVisible();
  await expect(page.getByText("A handwritten insight about optical interconnects")).toBeVisible();
  await page.getByRole("checkbox").check();
  await expect(page.getByText("已选 1 条")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("inbox.png"), fullPage: true });

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
  expect(errors).toEqual([]);
});

test("topic navigation exposes touch ordering workspace", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "主题" }).click();
  await expect(page.getByRole("heading", { name: "主题", exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Optical compute/ }).click();
  await expect(page.getByRole("button", { name: "预览导出" })).toBeVisible();
});
