import { loadEnv } from "vite";

const env = { ...loadEnv("development", process.cwd(), ""), ...process.env };
const [major, minor] = process.versions.node.split(".").map(Number);
if (major < 22 || (major === 22 && minor < 13)) {
  console.error(`Node.js ${process.versions.node} 不支援，請使用 22.13 以上版本。`);
  process.exit(1);
}
console.log(`Node.js ${process.versions.node}：可用`);
const model = env.OLLAMA_MODEL?.trim() || "gemma3:4b";
try {
  const base = new URL(env.OLLAMA_BASE_URL?.trim() || "http://127.0.0.1:11434");
  if (base.protocol !== "http:" || !["localhost", "127.0.0.1", "[::1]"].includes(base.hostname) || base.username || base.password || base.search || base.hash) {
    throw new Error("OLLAMA_BASE_URL 只接受沒有憑證的本機 HTTP 位址。");
  }
  const response = await fetch(`${base.href.replace(/\/+$/, "")}/api/tags`, { signal: AbortSignal.timeout(5000) });
  if (!response.ok) throw new Error(`Ollama 回傳 HTTP ${response.status}`);
  const body = await response.json();
  if (!body.models?.some((item) => item.name === model || item.model === model)) {
    throw new Error(`尚未安裝 ${model}。請執行 ollama pull ${model}`);
  }
  console.log(`Ollama ${model}：已安裝且服務可連線`);
  console.log("資料：本機 .wrangler；內建證據與價格為合成示範資料。");
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  console.error("請開啟 Ollama 後重試；仍可手動使用網站的固定示範模式。");
  process.exitCode = 1;
}
