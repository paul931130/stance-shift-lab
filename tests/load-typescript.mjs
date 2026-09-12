import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const root = fileURLToPath(new URL("../", import.meta.url));
const nativeRequire = createRequire(import.meta.url);

// Execute the actual server sources, replacing only platform bindings in tests.
export function loadTypeScript(entry, overrides = {}) {
  const cache = new Map();
  function load(file) {
    if (cache.has(file)) return cache.get(file).exports;
    const loaded = { exports: {} };
    cache.set(file, loaded);
    const source = ts.transpileModule(readFileSync(file, "utf8"), {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true },
    }).outputText;
    function require(specifier) {
      if (Object.hasOwn(overrides, specifier)) return overrides[specifier];
      if (specifier.startsWith(".") || specifier.startsWith("@/")) {
        let target = specifier.startsWith("@/") ? resolve(root, specifier.slice(2)) : resolve(dirname(file), specifier);
        if (!extname(target)) target += specifier === "@/db" ? "/index.ts" : ".ts";
        return load(target);
      }
      return nativeRequire(specifier);
    }
    new Function("require", "module", "exports", source)(require, loaded, loaded.exports);
    return loaded.exports;
  }
  return load(resolve(root, entry));
}
