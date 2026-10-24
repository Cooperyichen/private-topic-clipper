import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";

const clip = {
  id: "clip-1", kind: "TEXT", status: "INBOX", rawText: "Original", editableText: "Photonic interconnect insight", note: null, sourceUrl: null, sourceTitle: "Research paper", createdAt: "2026-10-18T12:00:00Z", extractionStatus: null, ocrMarkdown: null, ocrText: null, ocrLatex: null, tags: [], assets: [],
};

afterEach(() => vi.restoreAllMocks());

test("loads the inbox and exposes touch-friendly batch actions", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.includes("/clips/batch")) return response({ data: { updated: 1 } });
    if (url.includes("/clips?")) return response({ data: [clip], pagination: { totalItems: 1 } });
    if (url.endsWith("/tags")) return response({ data: [] });
    if (url.endsWith("/topics")) return response({ data: [] });
    throw new Error(`Unexpected request ${url} ${init?.method}`);
  });
  render(<App />);
  expect(await screen.findByText("Photonic interconnect insight")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("checkbox"));
  expect(screen.getByText("已选 1 条")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "归档" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/clips/batch", expect.objectContaining({ method: "POST" })));
});

test("opens immutable text by default and keeps the editable representation available", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/clips?")) return response({ data: [clip], pagination: { totalItems: 1 } });
    return response({ data: [] });
  });
  render(<App />);
  await userEvent.click(await screen.findByText("Photonic interconnect insight"));
  expect(screen.getByText("Original")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: "编辑稿" }));
  expect(screen.getByLabelText("可编辑正文")).toHaveValue("Photonic interconnect insight");
});

function response(body: unknown): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
}
