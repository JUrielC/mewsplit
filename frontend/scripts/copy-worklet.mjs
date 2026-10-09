// Copia el procesador de SoundTouch (AudioWorklet) a public/ para que se sirva
// junto a la interfaz: el hilo de audio lo carga por URL, no por import.
// Corre antes de `next dev` y `next build`; la copia está ignorada por git para
// que siempre coincida con la versión instalada del paquete (licencia MPL-2.0).
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const source = require.resolve("@soundtouchjs/audio-worklet/processor");
mkdirSync("public", { recursive: true });
copyFileSync(source, "public/soundtouch-processor.js");
