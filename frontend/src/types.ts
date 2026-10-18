export type ClipStatus = "INBOX" | "ARCHIVED";
export type ClipKind = "TEXT" | "RICH_TEXT" | "CODE" | "FORMULA" | "LINK" | "VIDEO" | "IMAGE" | "PDF";

export interface Tag {
  id: string;
  name: string;
}

export interface Asset {
  id: string;
  originalName: string;
  mediaType: string;
  byteSize: number;
  checksumSha256: string;
  relativePath: string;
}

export interface Clip {
  id: string;
  kind: ClipKind;
  status: ClipStatus;
  rawText: string | null;
  editableText: string | null;
  note: string | null;
  sourceUrl: string | null;
  sourceTitle: string | null;
  createdAt: string;
  extractionStatus: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED" | null;
  ocrMarkdown: string | null;
  ocrText: string | null;
  ocrLatex: string | null;
  tags: Tag[];
  assets: Asset[];
}

export interface TopicClip {
  position: number;
  annotation: string | null;
  representation: "ORIGINAL" | "EDITED" | "OCR";
  clip: Clip;
}

export interface Topic {
  id: string;
  title: string;
  description: string | null;
  clipCount?: number;
  clips?: TopicClip[];
}

export interface ApiErrorBody {
  error?: { code?: string; message?: string };
}
