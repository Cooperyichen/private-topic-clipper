import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { AssetPreview } from "./AssetPreview";
import type { Clip } from "./types";
import { formatVideoTimeRange } from "./videoTime";

type EditorTab = "original" | "edit" | "ocr";

export function ClipEditor({
  clip,
  onClose,
  onSaved,
}: {
  clip: Clip;
  onClose: () => void;
  onSaved: (clip: Clip) => void;
}) {
  const [editable, setEditable] = useState(clip.editableText ?? "");
  const [note, setNote] = useState(clip.note ?? "");
  const [ocrMarkdown, setOcrMarkdown] = useState(clip.ocrMarkdown ?? "");
  const [ocrText, setOcrText] = useState(clip.ocrText ?? "");
  const [ocrLatex, setOcrLatex] = useState(clip.ocrLatex ?? "");
  const [tab, setTab] = useState<EditorTab>("original");
  const [selectedAssetId, setSelectedAssetId] = useState(clip.assets[0]?.id ?? null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setEditable(clip.editableText ?? "");
    setNote(clip.note ?? "");
    setOcrMarkdown(clip.ocrMarkdown ?? "");
    setOcrText(clip.ocrText ?? "");
    setOcrLatex(clip.ocrLatex ?? "");
    setSelectedAssetId(clip.assets[0]?.id ?? null);
    setTab("original");
  }, [clip]);

  const selectedAsset = useMemo(
    () => clip.assets.find((asset) => asset.id === selectedAssetId) ?? clip.assets[0] ?? null,
    [clip.assets, selectedAssetId],
  );
  const videoTime = clip.kind === "VIDEO"
    ? formatVideoTimeRange(clip.videoStartSeconds, clip.videoEndSeconds)
    : null;

  async function save() {
    setSaving(true);
    try {
      const updated =
        tab === "edit"
          ? await api.updateClip(clip.id, editable, note)
          : await api.updateExtraction(clip.id, ocrMarkdown, ocrText, ocrLatex);
      onSaved(updated);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="editor">
      <div className="editor-head">
        <div>
          <p className="eyebrow">CLIP DETAIL</p>
          <h2>{clip.sourceTitle || kindLabel(clip.kind)}</h2>
          {videoTime && <p className="video-time video-time-detail">视频片段 {videoTime}</p>}
        </div>
        <button aria-label="关闭编辑器" onClick={onClose}>×</button>
      </div>
      <div className="editor-tabs" role="tablist" aria-label="摘录内容表示">
        <TabButton active={tab === "original"} id="original" onSelect={setTab}>原件</TabButton>
        <TabButton active={tab === "edit"} id="edit" onSelect={setTab}>编辑稿</TabButton>
        <TabButton active={tab === "ocr"} id="ocr" onSelect={setTab}>MinerU</TabButton>
      </div>

      {tab === "original" && (
        <section role="tabpanel" aria-label="原件" className="original-panel">
          {selectedAsset ? (
            <>
              {clip.assets.length > 1 && (
                <div className="asset-list" aria-label="附件列表">
                  {clip.assets.map((asset, index) => (
                    <button
                      key={asset.id}
                      aria-pressed={asset.id === selectedAsset.id}
                      onClick={() => setSelectedAssetId(asset.id)}
                    >
                      <span>{index + 1}</span>
                      <span>{asset.originalName}</span>
                    </button>
                  ))}
                </div>
              )}
              <AssetPreview asset={selectedAsset} />
            </>
          ) : (
            <pre className="raw-original">{clip.rawText || "这条摘录没有可显示的原始文本。"}</pre>
          )}
        </section>
      )}

      {tab === "edit" && (
        <section role="tabpanel" aria-label="编辑稿">
          <label>可编辑正文<textarea rows={12} value={editable} onChange={(event) => setEditable(event.target.value)} /></label>
          <label>个人说明<textarea rows={5} value={note} onChange={(event) => setNote(event.target.value)} /></label>
        </section>
      )}

      {tab === "ocr" && (
        <section role="tabpanel" aria-label="MinerU">
          <label>Markdown<textarea rows={10} value={ocrMarkdown} onChange={(event) => setOcrMarkdown(event.target.value)} /></label>
          <label>纯文字<textarea rows={5} value={ocrText} onChange={(event) => setOcrText(event.target.value)} /></label>
          <label>LaTeX<textarea rows={4} value={ocrLatex} onChange={(event) => setOcrLatex(event.target.value)} /></label>
        </section>
      )}

      {tab !== "original" && (
        <button className="primary-button editor-save" disabled={saving} onClick={() => void save()}>
          {saving ? "保存中" : "保存修改"}
        </button>
      )}
    </div>
  );
}

function TabButton({
  active,
  children,
  id,
  onSelect,
}: {
  active: boolean;
  children: string;
  id: EditorTab;
  onSelect: (tab: EditorTab) => void;
}) {
  return (
    <button role="tab" aria-selected={active} className={active ? "active" : ""} onClick={() => onSelect(id)}>
      {children}
    </button>
  );
}

function kindLabel(kind: Clip["kind"]) {
  return ({ TEXT: "文本", RICH_TEXT: "富文本", CODE: "代码", FORMULA: "公式", LINK: "链接", VIDEO: "视频", IMAGE: "图片", PDF: "PDF" })[kind];
}
