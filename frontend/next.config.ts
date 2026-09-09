import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import type { NextConfig } from "next";

/**
 * Lee backend/.env — la MISMA fuente que usa el backend al arrancar.
 *
 * Tener el puerto y el token duplicados aquí y allá era la causa de que el
 * frontend acabara llamando a un puerto donde ya no había nadie: se reinicia
 * el backend, cambia el puerto, y nadie actualiza el archivo del frontend.
 */
function readBackendEnv(): Record<string, string> {
  const path = join(process.cwd(), "..", "backend", ".env");
  if (!existsSync(path)) return {};

  const values: Record<string, string> = {};
  for (const raw of readFileSync(path, "utf8").split("\n")) {
    const line = raw.trim().replace(/^export\s+/, "");
    if (!line || line.startsWith("#")) continue;

    const separator = line.indexOf("=");
    if (separator === -1) continue;

    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1).trim().replace(/^(["'])(.*)\1$/, "$2");
    values[key] = value;
  }
  return values;
}

const backend = readBackendEnv();

// Tauri sirve la app como archivos estáticos y ese bundle se distribuye.
// Nunca se le incrusta el token de desarrollo: en escritorio los valores
// llegan en tiempo de ejecución por window.__MEWSPLIT__.
const isStaticExport = process.env.MEWSPLIT_STATIC === "1";

const config: NextConfig = {
  reactStrictMode: true,
  output: isStaticExport ? "export" : undefined,
  images: { unoptimized: true },
  env: isStaticExport
    ? {}
    : {
        // El entorno explícito gana sobre el archivo, para poder apuntar a un
        // backend remoto sin tocar backend/.env.
        NEXT_PUBLIC_MEWSPLIT_API:
          process.env.NEXT_PUBLIC_MEWSPLIT_API ??
          `http://127.0.0.1:${backend.MEWSPLIT_PORT ?? "8000"}`,
        NEXT_PUBLIC_MEWSPLIT_TOKEN:
          process.env.NEXT_PUBLIC_MEWSPLIT_TOKEN ?? backend.MEWSPLIT_TOKEN ?? "",
      },
};

export default config;
