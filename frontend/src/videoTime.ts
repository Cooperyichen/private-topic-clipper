export function formatVideoTimeRange(startSeconds: number | null, endSeconds: number | null) {
  const start = validSeconds(startSeconds);
  const end = validSeconds(endSeconds);

  if (start === null && end === null) return null;
  if (start !== null && end !== null) {
    if (start === end) return formatTimestamp(start);
    return `${formatTimestamp(start)}–${formatTimestamp(end)}`;
  }
  if (start !== null) return formatTimestamp(start);
  return `截至 ${formatTimestamp(end!)}`;
}

function validSeconds(value: number | null) {
  return value !== null && Number.isFinite(value) && value >= 0 ? value : null;
}

function formatTimestamp(value: number) {
  const totalHundredths = Math.round(value * 100);
  const wholeSeconds = Math.floor(totalHundredths / 100);
  const hundredths = totalHundredths % 100;
  const hours = Math.floor(wholeSeconds / 3600);
  const minutes = Math.floor((wholeSeconds % 3600) / 60);
  const seconds = wholeSeconds % 60;
  const fraction = hundredths === 0 ? "" : `.${String(hundredths).padStart(2, "0").replace(/0+$/, "")}`;
  const secondPart = `${String(seconds).padStart(2, "0")}${fraction}`;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${secondPart}`
    : `${String(minutes).padStart(2, "0")}:${secondPart}`;
}
