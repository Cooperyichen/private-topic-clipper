import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { ClipEditor } from "./ClipEditor";
import type { Clip, ClipKind, ClipStatus, Tag, Topic } from "./types";

type View = "inbox" | "topics";

export function App() {
  const [view, setView] = useState<View>("inbox");
  const [clips, setClips] = useState<Clip[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [activeClip, setActiveClip] = useState<Clip | null>(null);
  const [activeTopic, setActiveTopic] = useState<Topic | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<ClipStatus | "ALL">("INBOX");
  const [kind, setKind] = useState<ClipKind | "ALL">("ALL");
  const [tagFilter, setTagFilter] = useState("ALL");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [nextClips, nextTags, nextTopics] = await Promise.all([
        api.clips(search, status, kind, tagFilter),
        api.tags(),
        api.topics(),
      ]);
      setClips(nextClips);
      setTags(nextTags);
      setTopics(nextTopics);
      setSelectedIds((current) => new Set([...current].filter((id) => nextClips.some((clip) => clip.id === id))));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }, [search, status, kind, tagFilter]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const selectedClips = useMemo(
    () => clips.filter((clip) => selectedIds.has(clip.id)),
    [clips, selectedIds],
  );

  async function run(action: () => Promise<void>, success: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(success);
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  function toggleSelected(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function openTopic(id: string) {
    setBusy(true);
    try {
      setActiveTopic(await api.topic(id));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">C</span>
          <div><strong>Clippings</strong><span>私人主题剪贴板</span></div>
        </div>
        <nav aria-label="主要页面">
          <button className={view === "inbox" ? "nav-active" : ""} onClick={() => setView("inbox")}>收件箱</button>
          <button className={view === "topics" ? "nav-active" : ""} onClick={() => setView("topics")}>主题</button>
        </nav>
        <span className={`sync-dot ${busy ? "syncing" : ""}`}>{busy ? "同步中" : "已连接"}</span>
      </header>

      {(message || error) && (
        <div className={`notice ${error ? "notice-error" : ""}`} role="status">
          {error ?? message}<button aria-label="关闭通知" onClick={() => { setError(null); setMessage(null); }}>×</button>
        </div>
      )}

      {view === "inbox" ? (
        <main className="workspace">
          <aside className="capture-rail">
            <QuickCapture onSaved={() => run(async () => undefined, "摘录已进入收件箱")} refresh={refresh} />
            <TagCreator tags={tags} onCreated={refresh} />
            <div className="rail-note">
              <span>快捷入口</span>
              <p>在 iPhone 或 iPad 的分享菜单中运行 Quick Clip；需要备注时运行 Detailed Clip。</p>
            </div>
          </aside>

          <section className="inbox-panel" aria-labelledby="inbox-heading">
            <div className="panel-heading">
              <div><p className="eyebrow">CAPTURE STREAM</p><h1 id="inbox-heading">收件箱</h1></div>
              <span className="count-pill">{clips.length} 条</span>
            </div>
            <div className="filters">
              <label className="search-field"><span aria-hidden="true">⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索正文、备注或来源" /></label>
              <select aria-label="状态筛选" value={status} onChange={(event) => setStatus(event.target.value as ClipStatus | "ALL")}>
                <option value="INBOX">待整理</option><option value="ARCHIVED">已归档</option><option value="ALL">全部</option>
              </select>
              <select aria-label="类型筛选" value={kind} onChange={(event) => setKind(event.target.value as ClipKind | "ALL")}>
                <option value="ALL">全部类型</option><option value="TEXT">文本</option><option value="LINK">链接</option><option value="CODE">代码</option><option value="FORMULA">公式</option><option value="IMAGE">图片</option><option value="PDF">PDF</option><option value="VIDEO">视频</option>
              </select>
              <select aria-label="标签筛选" value={tagFilter} onChange={(event) => setTagFilter(event.target.value)}>
                <option value="ALL">全部标签</option>{tags.map((tag) => <option key={tag.id} value={tag.id}>{tag.name}</option>)}
              </select>
            </div>

            {selectedIds.size > 0 && (
              <BatchBar
                count={selectedIds.size}
                tags={tags}
                topics={topics}
                onArchive={() => run(() => api.batch([...selectedIds], "ARCHIVED"), "已归档")}
                onTag={(tagId) => run(() => api.batch([...selectedIds], undefined, [tagId]), "标签已添加")}
                onTopic={(topicId) => run(async () => { for (const clip of selectedClips) await api.addToTopic(topicId, clip.id); }, "已加入主题")}
                onClear={() => setSelectedIds(new Set())}
              />
            )}

            <div className="clip-list">
              {!busy && clips.length === 0 && <EmptyState />}
              {clips.map((clip) => (
                <ClipCard key={clip.id} clip={clip} selected={selectedIds.has(clip.id)} onToggle={() => toggleSelected(clip.id)} onOpen={() => setActiveClip(clip)} />
              ))}
            </div>
          </section>

          <aside className={`detail-panel ${activeClip ? "detail-open" : ""}`}>
            {activeClip ? <ClipEditor clip={activeClip} onClose={() => setActiveClip(null)} onSaved={(clip) => { setActiveClip(clip); void refresh(); }} /> : <div className="detail-placeholder"><span>↗</span><p>选择一条摘录，修正正文、备注或 MinerU 识别结果。</p></div>}
          </aside>
        </main>
      ) : (
        <TopicWorkspace topics={topics} activeTopic={activeTopic} selectedClipIds={[...selectedIds]} onOpen={openTopic} onOpenClip={setActiveClip} onChanged={async (topic) => { setActiveTopic(topic); await refresh(); }} onCreate={(title, description) => run(async () => { const topic = await api.createTopic(title, description); await openTopic(topic.id); }, "主题已创建")} />
      )}
      {view === "topics" && activeClip && (
        <aside className="detail-panel topic-detail-panel detail-open">
          <ClipEditor
            clip={activeClip}
            onClose={() => setActiveClip(null)}
            onSaved={(clip) => {
              setActiveClip(clip);
              if (activeTopic) void openTopic(activeTopic.id);
            }}
          />
        </aside>
      )}
    </div>
  );
}

function QuickCapture({ refresh, onSaved }: { refresh: () => Promise<void>; onSaved: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [source, setSource] = useState("");
  const [saving, setSaving] = useState(false);
  async function save() {
    if (!text.trim() && !source.trim()) return;
    setSaving(true);
    try { await api.captureText(text, note, source); setText(""); setNote(""); setSource(""); setExpanded(false); await refresh(); onSaved(); }
    finally { setSaving(false); }
  }
  async function upload(file?: File) {
    if (!file) return;
    setSaving(true);
    try { await api.captureFile(file); await refresh(); onSaved(); }
    finally { setSaving(false); }
  }
  return <div className="capture-card">
    <p className="eyebrow">QUICK CAPTURE</p><h2>随手放进来</h2>
    <textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="粘贴文本、代码或公式…" rows={expanded ? 6 : 3} />
    {expanded && <><input value={source} onChange={(event) => setSource(event.target.value)} placeholder="来源链接（可选）" /><textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="为什么值得保留？" rows={3} /></>}
    <div className="capture-actions">
      <label className="file-button">图片 / PDF<input type="file" accept="image/*,application/pdf" onChange={(event) => void upload(event.target.files?.[0])} /></label>
      <button className="text-button" onClick={() => setExpanded(!expanded)}>{expanded ? "收起" : "详细"}</button>
      <button className="primary-button" disabled={saving || (!text.trim() && !source.trim())} onClick={() => void save()}>{saving ? "保存中" : "保存"}</button>
    </div>
  </div>;
}

function TagCreator({ tags, onCreated }: { tags: Tag[]; onCreated: () => Promise<void> }) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  async function create() {
    if (!name.trim()) return;
    setSaving(true);
    try { await api.createTag(name.trim()); setName(""); await onCreated(); }
    finally { setSaving(false); }
  }
  return <div className="tag-creator"><p className="eyebrow">TAGS</p><div><input aria-label="新标签名称" value={name} onChange={(event) => setName(event.target.value)} placeholder="新建标签" /><button disabled={saving || !name.trim()} onClick={() => void create()}>＋</button></div><p>{tags.length ? tags.map((tag) => `#${tag.name}`).join("  ") : "尚无标签"}</p></div>;
}

function ClipCard({ clip, selected, onToggle, onOpen }: { clip: Clip; selected: boolean; onToggle: () => void; onOpen: () => void }) {
  const content = clip.editableText || clip.ocrMarkdown || clip.sourceTitle || clip.sourceUrl || clip.assets[0]?.originalName || "无文字内容";
  return <article className={`clip-card ${selected ? "clip-selected" : ""}`}>
    <label className="check"><input type="checkbox" checked={selected} onChange={onToggle} /><span /></label>
    <button className="clip-body" onClick={onOpen}>
      <div className="clip-meta"><span className={`kind kind-${clip.kind.toLowerCase()}`}>{kindLabel(clip.kind)}</span><time>{formatDate(clip.createdAt)}</time>{clip.extractionStatus && <span className={`extract extract-${clip.extractionStatus.toLowerCase()}`}>{extractionLabel(clip.extractionStatus)}</span>}</div>
      <p>{content}</p>
      <div className="tag-row">{clip.tags.map((tag) => <span key={tag.id}>#{tag.name}</span>)}{clip.sourceTitle && <span className="source">↗ {clip.sourceTitle}</span>}</div>
    </button>
  </article>;
}

function BatchBar({ count, tags, topics, onArchive, onTag, onTopic, onClear }: { count: number; tags: Tag[]; topics: Topic[]; onArchive: () => void; onTag: (id: string) => void; onTopic: (id: string) => void; onClear: () => void }) {
  return <div className="batch-bar"><strong>已选 {count} 条</strong><button onClick={onArchive}>归档</button><select aria-label="批量添加标签" defaultValue="" onChange={(event) => { if (event.target.value) onTag(event.target.value); event.target.value = ""; }}><option value="">添加标签…</option>{tags.map((tag) => <option key={tag.id} value={tag.id}>{tag.name}</option>)}</select><select aria-label="加入主题" defaultValue="" onChange={(event) => { if (event.target.value) onTopic(event.target.value); event.target.value = ""; }}><option value="">加入主题…</option>{topics.map((topic) => <option key={topic.id} value={topic.id}>{topic.title}</option>)}</select><button className="batch-close" onClick={onClear}>取消</button></div>;
}

function TopicWorkspace({ topics, activeTopic, selectedClipIds, onOpen, onOpenClip, onChanged, onCreate }: { topics: Topic[]; activeTopic: Topic | null; selectedClipIds: string[]; onOpen: (id: string) => void; onOpenClip: (clip: Clip) => void; onChanged: (topic: Topic) => Promise<void>; onCreate: (title: string, description: string) => void }) {
  const [title, setTitle] = useState(""); const [description, setDescription] = useState(""); const [preview, setPreview] = useState<string | null>(null); const [conflict, setConflict] = useState(false);
  async function move(index: number, delta: number) { if (!activeTopic?.clips) return; const ids = activeTopic.clips.map((item) => item.clip.id); const target = index + delta; if (target < 0 || target >= ids.length) return; [ids[index], ids[target]] = [ids[target], ids[index]]; await onChanged(await api.reorderTopic(activeTopic.id, ids)); }
  async function showPreview() { if (!activeTopic) return; const result = await api.previewExport(activeTopic.id); setPreview(result.markdown); setConflict(result.conflict); }
  async function exportNow() { if (!activeTopic) return; await api.exportTopic(activeTopic.id, conflict); setPreview(null); setConflict(false); }
  return <main className="topics-workspace"><aside className="topic-list"><div className="panel-heading"><div><p className="eyebrow">COLLECTIONS</p><h1>主题</h1></div></div><form onSubmit={(event) => { event.preventDefault(); if (title.trim()) { onCreate(title, description); setTitle(""); setDescription(""); } }}><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="新主题名称" /><textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={2} placeholder="主题说明（可选）" /><button className="primary-button">创建主题</button></form><div>{topics.map((topic) => <button key={topic.id} className={`topic-row ${activeTopic?.id === topic.id ? "active" : ""}`} onClick={() => void onOpen(topic.id)}><span>{topic.title}</span><small>{topic.clipCount ?? 0} 条</small></button>)}</div></aside><section className="topic-canvas">{activeTopic ? <><div className="topic-title"><div><p className="eyebrow">TOPIC BOARD</p><h2>{activeTopic.title}</h2><p>{activeTopic.description}</p></div><button onClick={() => void showPreview()}>预览导出</button></div>{selectedClipIds.length > 0 && <button className="add-selection" onClick={async () => { for (const id of selectedClipIds) await api.addToTopic(activeTopic.id, id); await onChanged(await api.topic(activeTopic.id)); }}>加入收件箱中已选的 {selectedClipIds.length} 条</button>}<div className="topic-stack">{activeTopic.clips?.map((item, index) => <article key={item.clip.id} className="topic-item"><span className="order-number">{String(index + 1).padStart(2, "0")}</span><div><strong>{item.clip.sourceTitle || kindLabel(item.clip.kind)}</strong><p>{item.clip.editableText || item.clip.ocrMarkdown || item.clip.assets[0]?.originalName}</p>{item.annotation && <small>{item.annotation}</small>}<button className="topic-preview-button" onClick={() => onOpenClip(item.clip)}>查看原件与详情</button></div><div className="order-actions"><button aria-label="上移" disabled={index === 0} onClick={() => void move(index, -1)}>↑</button><button aria-label="下移" disabled={index === (activeTopic.clips?.length ?? 0) - 1} onClick={() => void move(index, 1)}>↓</button></div></article>)}</div></> : <div className="topic-empty"><span>◫</span><h2>把零散摘录编成主题</h2><p>从左侧创建或选择主题，然后在收件箱勾选摘录。</p></div>}</section>{preview !== null && <div className="preview-backdrop"><section className="preview-dialog"><div><h2>Obsidian 导出预览</h2><button aria-label="关闭预览" onClick={() => setPreview(null)}>×</button></div>{conflict && <p className="conflict">检测到 Obsidian 中的手工修改。继续会先保存应用历史版本，再覆盖目标文件。</p>}<pre>{preview}</pre><button className="primary-button" onClick={() => void exportNow()}>{conflict ? "确认覆盖并导出" : "导出到 Clippings"}</button></section></div>}</main>;
}

function EmptyState() { return <div className="empty-state"><span>✦</span><h2>收件箱是空的</h2><p>粘贴一段文字，或从 Apple 分享菜单发送第一条摘录。</p></div>; }
function errorMessage(value: unknown) { return value instanceof Error ? value.message : "发生未知错误"; }
function formatDate(value: string) { return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value)); }
function kindLabel(kind: Clip["kind"]) { return ({ TEXT: "文本", RICH_TEXT: "富文本", CODE: "代码", FORMULA: "公式", LINK: "链接", VIDEO: "视频", IMAGE: "图片", PDF: "PDF" })[kind]; }
function extractionLabel(status: NonNullable<Clip["extractionStatus"]>) { return ({ PENDING: "等待识别", PROCESSING: "识别中", COMPLETED: "已识别", FAILED: "识别失败" })[status]; }
