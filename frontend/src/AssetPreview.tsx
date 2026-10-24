import { useEffect, useState } from "react";
import type { Asset } from "./types";

type LoadState = "loading" | "ready" | "error";

export function AssetPreview({ asset }: { asset: Asset }) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [retryKey, setRetryKey] = useState(0);
  const url = assetContentUrl(asset.id);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    setLoadState("loading");
    void fetch(url, {
      headers: { Range: "bytes=0-0" },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Asset request failed with ${response.status}`);
        await response.body?.cancel();
        if (!cancelled) setLoadState("ready");
      })
      .catch((error: unknown) => {
        if (!cancelled && !(error instanceof DOMException && error.name === "AbortError")) {
          setLoadState("error");
        }
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [retryKey, url]);

  return (
    <div className="asset-preview">
      <div className="asset-toolbar">
        <div>
          <strong>{asset.originalName}</strong>
          <small>{formatBytes(asset.byteSize)}</small>
        </div>
        <div>
          <a href={url} target="_blank" rel="noreferrer">在新窗口打开</a>
          <a href={url} download={asset.originalName}>下载原件</a>
        </div>
      </div>

      {loadState === "loading" && <div className="asset-loading" role="status">正在载入原件…</div>}
      {loadState === "error" && (
        <div className="asset-error" role="alert">
          <p>原件加载失败，请检查连接后重试。</p>
          <button onClick={() => setRetryKey((value) => value + 1)}>重试</button>
        </div>
      )}
      {loadState === "ready" && asset.mediaType.startsWith("image/") && (
        <img src={url} alt={`原件：${asset.originalName}`} onError={() => setLoadState("error")} />
      )}
      {loadState === "ready" && asset.mediaType === "application/pdf" && (
        <div className="pdf-preview">
          <iframe src={url} title={`PDF 原件：${asset.originalName}`} />
          <p>如果浏览器无法显示 PDF，请使用“在新窗口打开”或“下载原件”。</p>
        </div>
      )}
      {loadState === "ready" && !asset.mediaType.startsWith("image/") && asset.mediaType !== "application/pdf" && (
        <div className="asset-error"><p>此文件类型暂不支持网页内预览。</p></div>
      )}
    </div>
  );
}

function assetContentUrl(assetId: string) {
  return `/api/v1/assets/${encodeURIComponent(assetId)}/content`;
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}
