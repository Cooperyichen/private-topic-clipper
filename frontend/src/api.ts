import type { ApiErrorBody, Clip, ClipKind, ClipStatus, Tag, Topic } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const body = (await response.json()) as T & ApiErrorBody;
  if (!response.ok) {
    throw new Error(body.error?.message ?? `请求失败（${response.status}）`);
  }
  return body;
}

const jsonHeaders = { "Content-Type": "application/json" };

export const api = {
  async clips(
    search = "",
    status: ClipStatus | "ALL" = "INBOX",
    kind: ClipKind | "ALL" = "ALL",
    tagId = "ALL",
  ): Promise<Clip[]> {
    const params = new URLSearchParams({ pageSize: "100" });
    if (search.trim()) params.set("q", search.trim());
    if (status !== "ALL") params.set("status", status);
    if (kind !== "ALL") params.set("kind", kind);
    if (tagId !== "ALL") params.set("tagId", tagId);
    return (await request<{ data: Clip[] }>(`/api/v1/clips?${params}`)).data;
  },
  async tags(): Promise<Tag[]> {
    return (await request<{ data: Tag[] }>("/api/v1/tags")).data;
  },
  async topics(): Promise<Topic[]> {
    return (await request<{ data: Topic[] }>("/api/v1/topics")).data;
  },
  async topic(id: string): Promise<Topic> {
    return (await request<{ data: Topic }>(`/api/v1/topics/${id}`)).data;
  },
  async captureText(rawText: string, note: string, sourceUrl: string): Promise<Clip> {
    return (
      await request<{ data: Clip }>("/api/v1/captures", {
        method: "POST",
        headers: { ...jsonHeaders, "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ kind: sourceUrl ? "LINK" : "TEXT", rawText: rawText || undefined, note: note || undefined, sourceUrl: sourceUrl || undefined }),
      })
    ).data;
  },
  async captureFile(file: File): Promise<Clip> {
    return (
      await request<{ data: Clip }>("/api/v1/captures/files", {
        method: "POST",
        headers: {
          "Content-Type": file.type,
          "Content-Disposition": `attachment; filename="${file.name.replaceAll('"', "_")}"`,
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: file,
      })
    ).data;
  },
  async updateClip(id: string, editableText: string, note: string): Promise<Clip> {
    return (
      await request<{ data: Clip }>(`/api/v1/clips/${id}`, {
        method: "PATCH",
        headers: jsonHeaders,
        body: JSON.stringify({ editableText, note }),
      })
    ).data;
  },
  async updateExtraction(id: string, markdown: string, text: string, latex: string): Promise<Clip> {
    return (
      await request<{ data: Clip }>(`/api/v1/clips/${id}/extraction`, {
        method: "PATCH",
        headers: jsonHeaders,
        body: JSON.stringify({ ocrMarkdown: markdown, ocrText: text, ocrLatex: latex }),
      })
    ).data;
  },
  async batch(ids: string[], status?: ClipStatus, addTagIds: string[] = []): Promise<void> {
    await request("/api/v1/clips/batch", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ clipIds: ids, status, addTagIds }),
    });
  },
  async deleteClips(ids: string[]): Promise<void> {
    await request("/api/v1/clips/batch-delete", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ clipIds: ids, confirm: true }),
    });
  },
  async createTag(name: string): Promise<Tag> {
    return (await request<{ data: Tag }>("/api/v1/tags", { method: "POST", headers: jsonHeaders, body: JSON.stringify({ name }) })).data;
  },
  async createTopic(title: string, description: string): Promise<Topic> {
    return (await request<{ data: Topic }>("/api/v1/topics", { method: "POST", headers: jsonHeaders, body: JSON.stringify({ title, description }) })).data;
  },
  async addToTopic(topicId: string, clipId: string): Promise<void> {
    await request(`/api/v1/topics/${topicId}/clips`, { method: "POST", headers: jsonHeaders, body: JSON.stringify({ clipId, representation: "EDITED" }) });
  },
  async reorderTopic(topicId: string, clipIds: string[]): Promise<Topic> {
    return (await request<{ data: Topic }>(`/api/v1/topics/${topicId}/clips/order`, { method: "PUT", headers: jsonHeaders, body: JSON.stringify({ clipIds }) })).data;
  },
  async previewExport(topicId: string): Promise<{ conflict: boolean; markdown: string }> {
    return (await request<{ data: { conflict: boolean; markdown: string } }>(`/api/v1/topics/${topicId}/exports/preview`, { method: "POST" })).data;
  },
  async exportTopic(topicId: string, confirmOverwrite: boolean): Promise<void> {
    await request(`/api/v1/topics/${topicId}/exports`, { method: "POST", headers: jsonHeaders, body: JSON.stringify({ confirmOverwrite }) });
  },
};
