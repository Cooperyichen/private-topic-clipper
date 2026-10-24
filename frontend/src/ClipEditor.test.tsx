import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ClipEditor } from "./ClipEditor";
import type { Clip } from "./types";

const baseClip: Clip = {
  id: "clip-1",
  kind: "IMAGE",
  status: "INBOX",
  rawText: null,
  editableText: "Editable text",
  note: "Personal note",
  sourceUrl: null,
  sourceTitle: null,
  createdAt: "2026-10-18T12:00:00Z",
  extractionStatus: "COMPLETED",
  ocrMarkdown: "# OCR markdown",
  ocrText: "OCR text",
  ocrLatex: "x = y",
  tags: [],
  assets: [
    {
      id: "asset-image",
      originalName: "sql-notes.png",
      mediaType: "image/png",
      byteSize: 128,
      checksumSha256: "abc",
      relativePath: "ab/abc.png",
    },
  ],
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("previews an image original and exposes open and download actions", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 206 }));

  renderEditor(baseClip);

  expect(screen.getByRole("status")).toHaveTextContent("正在载入原件");
  const image = await screen.findByRole("img", { name: "原件：sql-notes.png" });
  expect(image).toHaveAttribute("src", "/api/v1/assets/asset-image/content");
  expect(screen.getByRole("link", { name: "在新窗口打开" })).toHaveAttribute(
    "href",
    "/api/v1/assets/asset-image/content",
  );
  expect(screen.getByRole("link", { name: "下载原件" })).toHaveAttribute(
    "download",
    "sql-notes.png",
  );
});

test("previews a PDF with an embedded reader and fallback message", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 206 }));
  const pdfClip = {
    ...baseClip,
    kind: "PDF" as const,
    assets: [{ ...baseClip.assets[0], id: "asset-pdf", originalName: "paper.pdf", mediaType: "application/pdf" }],
  };

  renderEditor(pdfClip);

  const reader = await screen.findByTitle("PDF 原件：paper.pdf");
  expect(reader).toHaveAttribute("src", "/api/v1/assets/asset-pdf/content");
  expect(screen.getByText(/如果浏览器无法显示 PDF/)).toBeInTheDocument();
});

test("switches between multiple original attachments", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 206 }));
  const multiClip = {
    ...baseClip,
    assets: [
      baseClip.assets[0],
      { ...baseClip.assets[0], id: "asset-pdf", originalName: "appendix.pdf", mediaType: "application/pdf" },
    ],
  };
  renderEditor(multiClip);
  await screen.findByRole("img", { name: "原件：sql-notes.png" });

  await userEvent.click(screen.getByRole("button", { name: /appendix.pdf/ }));

  expect(await screen.findByTitle("PDF 原件：appendix.pdf")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /appendix.pdf/ })).toHaveAttribute("aria-pressed", "true");
});

test("shows immutable raw text when a clip has no attachments", () => {
  renderEditor({ ...baseClip, kind: "TEXT", rawText: "Immutable source text", assets: [] });

  expect(screen.getByText("Immutable source text")).toBeInTheDocument();
  expect(screen.queryByText("正在载入原件")).not.toBeInTheDocument();
});

test("shows a useful load error and retries the selected asset", async () => {
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(null, { status: 404 }))
    .mockResolvedValueOnce(new Response(null, { status: 206 }));
  renderEditor(baseClip);

  expect(await screen.findByText("原件加载失败，请检查连接后重试。")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "重试" }));

  expect(await screen.findByRole("img", { name: "原件：sql-notes.png" })).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("keeps editable and MinerU representations saveable", async () => {
  const updated = { ...baseClip, editableText: "Revised", note: "Why it matters" };
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.includes("/assets/")) return new Response(null, { status: 206 });
    if (url.endsWith("/clips/clip-1")) return jsonResponse({ data: updated });
    if (url.endsWith("/clips/clip-1/extraction")) return jsonResponse({ data: updated });
    throw new Error(`Unexpected request ${url} ${init?.method}`);
  });
  renderEditor(baseClip);

  await userEvent.click(screen.getByRole("tab", { name: "编辑稿" }));
  await userEvent.clear(screen.getByLabelText("可编辑正文"));
  await userEvent.type(screen.getByLabelText("可编辑正文"), "Revised");
  await userEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/clips/clip-1",
      expect.objectContaining({ method: "PATCH" }),
    ),
  );

  await userEvent.click(screen.getByRole("tab", { name: "MinerU" }));
  expect(screen.getByLabelText("Markdown")).toHaveValue("# OCR markdown");
  expect(screen.getByLabelText("纯文字")).toHaveValue("OCR text");
  expect(screen.getByLabelText("LaTeX")).toHaveValue("x = y");
  await userEvent.click(screen.getByRole("button", { name: "保存修改" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/clips/clip-1/extraction",
      expect.objectContaining({ method: "PATCH" }),
    ),
  );
});

function renderEditor(clip: Clip) {
  render(<ClipEditor clip={clip} onClose={vi.fn()} onSaved={vi.fn()} />);
}

function jsonResponse(body: unknown): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}
