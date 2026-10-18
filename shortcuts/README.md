# Apple Shortcuts

The Shortcuts app signs exported shortcut files against an Apple account, so this repository stores reproducible action specifications instead of an unsigned binary. Build each shortcut once on an iPhone, iPad, or Mac, then let iCloud synchronize it to the other devices.

## Shared setup

1. Copy `config.example.json` to a private location and replace `baseUrl` with the HTTPS address shown by `tailscale serve status`.
2. Ensure the device is connected to the same tailnet.
3. Create each shortcut with **Show in Share Sheet** enabled. Accept text, rich text, URLs, images, and PDF files. If there is no input, request clipboard contents.
4. For every request, generate a fresh UUID and send it as the `Idempotency-Key` header. Keep the same UUID when retrying the same request.
5. Treat any response outside the successful status range as a visible failure. Show the error message returned in `error.message`.

## Quick Clip

Build the following action sequence:

1. Receive Share Sheet input, falling back to the clipboard.
2. Use **Get Type** to branch on files versus text or URLs.
3. For an image or PDF, use **Get Contents of URL** with `POST`, the endpoint `/api/v1/captures/files`, and a **File** request body. Set `Content-Type`, `Content-Disposition`, and `Idempotency-Key`.
4. For a URL, send JSON to `/api/v1/captures` with `kind` set to `LINK` and `sourceUrl` set to the shared URL.
5. For text or rich text, convert rich text to Markdown when available and send JSON with `kind` set to `TEXT` or `RICH_TEXT`, plus `rawText`.
6. Show a compact success notification containing the returned clip identifier.

## Detailed Clip

Duplicate Quick Clip and insert these actions before the request:

1. Ask for a multiline personal note.
2. Ask for an optional source title when the input does not supply one.
3. When the input is a video URL, choose `VIDEO` and ask for optional start and end values in seconds. Send them as `videoStartSeconds` and `videoEndSeconds`.
4. Add `note`, `sourceTitle`, and the video location fields to the JSON request. File captures can be created first, followed by `PATCH /api/v1/clips/{clipId}` with the note and source metadata.

## Device acceptance checklist

- Safari selected text creates one inbox item.
- Photos and a screenshot create image items and return before MinerU finishes.
- A PDF from Files remains below the configured file limit and enters the extraction queue.
- Repeating an interrupted request with the same idempotency key does not create a duplicate.
- A video link preserves the optional start or end position.
