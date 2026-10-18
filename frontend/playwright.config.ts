import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: "./test-results",
  reporter: "line",
  webServer: {
    command: "npm run dev -- --host 0.0.0.0",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: false,
  },
  use: {
    baseURL: "http://127.0.0.1:5173",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "iPad", use: { ...devices["iPad (gen 7) landscape"] } },
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
  ],
});
