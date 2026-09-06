import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // Tauri sirve la app como archivos estáticos; en web se despliega igual.
  // La URL del backend llega por variable de entorno, nunca cableada.
  output: process.env.MEWSPLIT_STATIC === "1" ? "export" : undefined,
  images: { unoptimized: true },
};

export default config;
