import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";

const clip = {
  id: "clip-1", kind: "TEXT", status: "INBOX", rawText: "Original", editableText: "Photonic interconnect insight", note: "Worth revisiting", sourceUrl: null, sourceTitle: "Research paper", videoStartSeconds: null, videoEndSeconds: null, createdAt: "2026-10-18T12:00:00Z", extractionStatus: null, ocrMarkdown: null, ocrText: null, ocrLatex: null, tags: [], assets: [],
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("loads the inbox and exposes touch-friendly batch actions", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url === "/api/v1/clips/batch") return response({ data: { updated: 1 } });
    if (url.includes("/clips?")) return response({ data: [clip], pagination: { totalItems: 1 } });
    if (url.endsWith("/tags")) return response({ data: [] });
    if (url.endsWith("/topics")) return response({ data: [] });
    throw new Error(`Unexpected request ${url} ${init?.method}`);
  });
  render(<App />);
  expect(await screen.findByText("Research paper")).toBeInTheDocument();
  expect(screen.getByText("Worth revisiting")).toBeInTheDocument();
  expect(screen.queryByText("Photonic interconnect insight")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("checkbox"));
  expect(screen.getByText("已选 1 条")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "归档" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/clips/batch", expect.objectContaining({ method: "POST" })));
});

test("requires confirmation before permanently deleting selected clips", async () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url === "/api/v1/clips/batch-delete") return response({ data: { deleted: 1 } });
    if (url.includes("/clips?")) return response({ data: [clip], pagination: { totalItems: 1 } });
    if (url.endsWith("/tags") || url.endsWith("/topics")) return response({ data: [] });
    throw new Error(`Unexpected request ${url}`);
  });
  render(<App />);
  await userEvent.click(await screen.findByRole("checkbox"));

  await userEvent.click(screen.getByRole("button", { name: "永久删除" }));
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(fetchMock).not.toHaveBeenCalledWith("/api/v1/clips/batch-delete", expect.anything());

  await userEvent.click(screen.getByRole("button", { name: "永久删除" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/clips/batch-delete",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ clipIds: ["clip-1"], confirm: true }),
    }),
  ));
});

test("opens immutable text by default and keeps the editable representation available", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/clips?")) return response({ data: [clip], pagination: { totalItems: 1 } });
    return response({ data: [] });
  });
  render(<App />);
  await userEvent.click(await screen.findByText("Research paper"));
  expect(screen.getByText("Original")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: "编辑稿" }));
  expect(screen.getByLabelText("可编辑正文")).toHaveValue("Photonic interconnect insight");
});

test("shows a saved video time range on the card and in clip details", async () => {
  const videoClip = {
    ...clip,
    id: "video-1",
    kind: "VIDEO" as const,
    sourceTitle: "清月",
    videoStartSeconds: 10,
    videoEndSeconds: 20,
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/clips?")) return response({ data: [videoClip], pagination: { totalItems: 1 } });
    return response({ data: [] });
  });

  render(<App />);
  expect(await screen.findByText("视频片段 00:10–00:20")).toBeInTheDocument();
  await userEvent.click(screen.getByText("清月"));
  expect(screen.getAllByText("视频片段 00:10–00:20")).toHaveLength(2);
});

test("shows only clip titles in a topic board", async () => {
  const topic = {
    id: "topic-1",
    title: "PPO及其变体对比",
    description: null,
    clipCount: 1,
    clips: [{ position: 0, annotation: "Local annotation", representation: "EDITED", clip }],
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url === "/api/v1/topics/topic-1") return response({ data: topic });
    if (url.includes("/clips?")) return response({ data: [clip], pagination: { totalItems: 1 } });
    if (url.endsWith("/tags")) return response({ data: [] });
    if (url.endsWith("/topics")) return response({ data: [{ ...topic, clips: undefined }] });
    throw new Error(`Unexpected request ${url}`);
  });

  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "主题" }));
  await userEvent.click(await screen.findByRole("button", { name: /PPO及其变体对比/ }));

  expect(await screen.findByText("Research paper")).toBeInTheDocument();
  expect(screen.queryByText("Photonic interconnect insight")).not.toBeInTheDocument();
  expect(screen.queryByText("Local annotation")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "查看原件与详情" })).toBeInTheDocument();
});

function response(body: unknown): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
}
