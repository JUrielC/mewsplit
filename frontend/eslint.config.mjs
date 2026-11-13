import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTypescript,
  {
    // Con "detect", eslint-plugin-react 7.37 llama a context.getFilename(), que ESLint 10 ya no tiene.
    settings: { react: { version: "19.2" } },
  },
  // public/ lleva el procesador de SoundTouch copiado de node_modules (scripts/copy-worklet.mjs).
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "public/**"]),
]);
