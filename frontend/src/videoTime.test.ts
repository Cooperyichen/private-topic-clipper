import { expect, test } from "vitest";
import { formatVideoTimeRange } from "./videoTime";

test("formats a single video time point", () => {
  expect(formatVideoTimeRange(125, null)).toBe("02:05");
});

test("formats a video time range, including hour-long videos", () => {
  expect(formatVideoTimeRange(3661, 3725)).toBe("1:01:01–1:02:05");
});

test("hides missing or invalid video times", () => {
  expect(formatVideoTimeRange(null, null)).toBeNull();
  expect(formatVideoTimeRange(-1, null)).toBeNull();
});
