import vinext from "vinext";
import { defineConfig, loadEnv } from "vite";
import hostingConfig from "./.openai/hosting.json";
import { sites } from "./build/sites-vite-plugin";

const SITE_CREATOR_PLACEHOLDER_DATABASE_ID =
  "00000000-0000-4000-8000-000000000000";

const { d1, r2 } = hostingConfig;

// macOS Seatbelt blocks FSEvents, so Codex previews need polling for HMR.
const isCodexSeatbeltSandbox = process.env.CODEX_SANDBOX === "seatbelt";

export default defineConfig(async ({ mode, command }) => {
  const fileEnv = loadEnv(mode, process.cwd(), "");
  const localModeEnabled = command === "serve" && mode !== "production" &&
    (process.env.LOCAL_MODE === "true" || fileEnv.LOCAL_MODE === "true");
  const localBindingConfig = {
    main: "./worker/index.ts",
    compatibility_flags: ["nodejs_compat"],
    d1_databases: d1
      ? [
          {
            binding: d1,
            database_name: "site-creator-d1",
            database_id: SITE_CREATOR_PLACEHOLDER_DATABASE_ID,
          },
        ]
      : [],
    r2_buckets: r2
      ? [
          {
            binding: r2,
            bucket_name: "site-creator-r2",
          },
        ]
      : [],
    ...(localModeEnabled
      ? { vars: {
          APP_ENV: "development",
          LOCAL_MODE: "true",
          LOCAL_OWNER_EMAIL: fileEnv.LOCAL_OWNER_EMAIL || "local@stance-shift.test",
          LOCAL_OWNER_NAME: fileEnv.LOCAL_OWNER_NAME || "本機研究者",
          OLLAMA_BASE_URL: fileEnv.OLLAMA_BASE_URL || "http://127.0.0.1:11434",
          OLLAMA_MODEL: fileEnv.OLLAMA_MODEL || "gemma3:4b",
          OWNER_KEY_PEPPER: fileEnv.OWNER_KEY_PEPPER || "stance-shift-local-development-v1",
        } }
      : {}),
  };

  // Keep Wrangler and Miniflare state project-local. These are non-secret tool
  // settings; application environment belongs in ignored `.env*` files.
  process.env.WRANGLER_WRITE_LOGS ??= "false";
  process.env.WRANGLER_LOG_PATH ??= ".wrangler/logs";
  process.env.MINIFLARE_REGISTRY_PATH ??= ".wrangler/registry";

  // Wrangler snapshots its log path while the Cloudflare plugin is imported.
  const { cloudflare } = await import("@cloudflare/vite-plugin");

  return {
    server: {
      host: "localhost",
      port: 3000,
      strictPort: true,
      ...(isCodexSeatbeltSandbox ? { watch: { useFsEvents: false, usePolling: true } } : {}),
    },
    plugins: [
      vinext(),
      sites(),
      cloudflare({
        viteEnvironment: { name: "rsc", childEnvironments: ["ssr"] },
        config: localBindingConfig,
      }),
    ],
  };
});
