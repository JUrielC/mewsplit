# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es

`mewsplit` — separador de pistas de audio con detección de acordes.
Aplicación de escritorio (destino principal) con opción de despliegue web.

Entrada: un archivo de audio. Salida: stems separados, progresión de acordes
con marcas de tiempo, y un mezclador para escuchar con volúmenes por pista.

## Comandos

```bash
# Backend
cd backend
uv venv .venv --python 3.11 && uv pip install -e ".[dev]"
.venv/bin/pytest                      # 27 pruebas, no descargan modelos
.venv/bin/pytest -m slow              # las que separan audio de verdad
.venv/bin/pytest tests/test_core.py::test_stopwatch_records_the_stage
cp .env.example .env                  # una vez: fija puerto y token de desarrollo
.venv/bin/python -m mewsplit.api      # imprime MEWSPLIT_READY port=<n> token=<t>
.venv/bin/python cli.py cancion.mp3 [--6-stems] [--skip-chords] [--simple-chords]
.venv/bin/python bench.py cancion.mp3

# Frontend
cd frontend
npm install && npm run dev            # lee backend/.env, no necesita .env.local
npm run typecheck && npm run build

# Contrato tipado: regenerar tras CUALQUIER cambio en los modelos de api.py
./scripts/gen-types.sh
```

`pipeline/` y `design/` son las pruebas originales de las que salió esto.
Ya no son la fuente de verdad; el código vive en `backend/`.

## La regla que no se rompe

**`backend/mewsplit/core.py` no sabe dónde corre.**

Sin imports de FastAPI, Gradio, Modal, Tauri ni nada de plataforma. Recibe
rutas de archivo, devuelve datos. `api.py` depende de `core.py`, nunca al
revés — y `separation.py` y `chords.py` no importan `core` tampoco: reciben el
cronómetro como parámetro para no crear el ciclo.

Todo lo demás es envoltorio y todo envoltorio es reemplazable. Esto es lo que
permite que el mismo código sirva para escritorio y para web, y que cambiar de
proveedor de nube sea reescribir un archivo.

Si una tarea parece requerir que `core.py` importe algo de plataforma, la
solución está mal planteada — pregunta antes de hacerlo.

## Estructura

```
backend/mewsplit/
  core.py         orquestación pura: Stopwatch, Analysis, analyze()
  separation.py   audio-separator; separate() y build_instrumental()
  chords.py       BTC; detect_chords(), cachea el modelo por vocabulario
  api.py          FastAPI: trabajos en segundo plano, token, puerto dinámico
backend/cli.py    argparse sobre core
backend/bench.py  consume las funciones sueltas, no analyze(): necesita otro orden
frontend/lib/audio.ts   el mezclador (Web Audio API)
frontend/lib/api.ts     cliente HTTP, tipos importados de shared/types.ts
desktop/src-tauri/      cáscara; tauri.conf.json va DENTRO de src-tauri/
shared/types.ts         GENERADO, no editar a mano
```

Dos contratos que hay que respetar al tocar los extremos:

- **Arranque del sidecar**: `api.run()` imprime
  `MEWSPLIT_READY port=<n> token=<t>` como primera línea de stdout.
  `desktop/src-tauri/src/main.rs` la parsea. Cambiar el formato rompe el escritorio.
- **Configuración en el cliente**: Tauri inyecta `window.__MEWSPLIT__` como
  script de inicialización antes de que corra el JS de la página; en web los
  valores salen de `NEXT_PUBLIC_MEWSPLIT_*`. Todo eso está en `lib/api.ts`.
- **Puerto y token en desarrollo**: `backend/.env` es la FUENTE ÚNICA. Lo leen
  `api.py` al arrancar y `frontend/next.config.ts` al levantar `next dev`.
  El entorno explícito gana sobre el archivo, y en la build estática de Tauri
  no se incrusta nada: el token llegaría dentro del binario distribuido.

La API nunca devuelve rutas del disco del servidor: los stems se piden por
nombre a `/jobs/{id}/stems/{name}`.

## Decisiones ya tomadas

No las revisites sin razón nueva. Están medidas — los números viven en
`pipeline/salida_bench/bench.json` (M3, canción de 3:39, MPS).

**Separación: `htdemucs`, no `htdemucs_ft`.** El `_ft` es un ensamble de 4
modelos: 130.7s vs 32.2s (4.06x más lento, RTF 0.5951 vs 0.1466) y no aportó
diferencia útil. Medido, no supuesto.

**Acordes: `puar-playground/btc-chord`, en CPU, vocabulario de 170 clases**
(notación Harte). ~1 segundo por canción. No necesita GPU.

**Los acordes son independientes de la separación.** Se probó detectarlos sobre
el instrumental esperando mejor precisión: 20 de 22 tramos idénticos al audio
original. No esperes a los stems para calcular acordes. Queda una discrepancia
sin resolver a oído: en cinco puntos el original detecta `E:min` donde el
instrumental detecta `G` — comparten dos notas, la diferencia está en si la
tercera viene de la guitarra o de la melodía vocal.

**`htdemucs_6s` (6 stems, con guitarra y piano) es opcional, no default.**
Los 4 stems base pierden algo de calidad cuando el modelo también predice
guitarra y piano. El piano sale con muchos artefactos; la guitarra sale bien.
La elección de 4 o 6 stems se hace al cargar el audio, no como preset de mezcla.

**HTTP en escritorio, no IPC nativo.** Mantener dos caminos de comunicación
para la misma funcionalidad no vale la pena. El overhead sobre loopback es
irrelevante frente a una operación de 30 segundos.

## Cosas que ya nos mordieron

**El retorno de `separator.separate()` cambia entre versiones** de
`audio-separator` — a veces rutas absolutas, a veces solo nombres. `separate()`
normaliza ambos casos y mapea por subcadena en el nombre del archivo; si cambia
el patrón de nombres del modelo, ese mapeo se rompe en silencio.

**Los nombres de modelo cambian entre releases.** Confirma con
`audio-separator --list_models` antes de fijar uno.

**`audio-separator` carga el modelo de forma diferida**, así que el tiempo de
carga aparece dentro del de separación, no antes.

**Los checkpoints de Demucs caen en `/tmp/audio-separator-models/`** por
defecto, y macOS lo purga. `api.py` fija `~/.cache/mewsplit/models` vía
`model_cache_dir`; el CLI usa el default salvo que le pases `--model-dir`. Los
pesos de BTC van a `~/.cache/huggingface/`.

**Los modos de práctica se calculan sobre los stems que existen.** "Sin voz"
tenía escrita la lista `["bass","drums","other"]`: con 4 stems acertaba por
casualidad y con `--6-stems` silenciaba también guitarra y piano. Defínelos
por lo que excluyen (`names.filter(n => n !== "vocals")`), no por lo que
incluyen.

**Puerto y token duplicados en dos archivos se desincronizan solos.** Cuando
`backend/.env` y `frontend/.env.local` eran archivos distintos, cualquier
reinicio del backend sin variables tomaba un puerto aleatorio y el frontend
seguía llamando al viejo: "failed to fetch" sin más pista. Ahora `next.config.ts`
lee `backend/.env`. No vuelvas a crear `frontend/.env.local` salvo para apuntar
a un backend remoto.

**Un solo campo de progreso no puede describir dos ramas paralelas.** `stage`
y `progress` los compartían separación y acordes: como los acordes acaban en
~2s, dejaban la barra en "chords 100%" durante los ~25s restantes. Por eso
`on_progress(avance)` ya no recibe el nombre de la etapa y mide solo la
separación (~92% del tiempo), y los acordes se anuncian aparte con
`on_chords`. Si vuelves a meter un identificador de etapa ahí, vuelve el bug.

**El mezclador se desincroniza si cada fuente arranca por su cuenta.** Las
cuatro pistas se programan con el MISMO instante absoluto y el bucle lo hace el
hilo de audio (`loop`/`loopStart`/`loopEnd`), no `requestAnimationFrame`. rAF
solo pinta. Está explicado en la cabecera de `frontend/lib/audio.ts`; si alguien
lo "simplifica", vuelve el desfase.

## Pendientes

- **El almacén de trabajos de `api.py` está en memoria.** En escritorio da igual
  (el proceso muere con la app); un despliegue web con varios workers necesita
  otra cosa.
- **El frontend no se ha probado contra una canción real de punta a punta.**
  Compila y el mezclador está resuelto, pero nadie ha subido un MP3 todavía.
- **`progress` solo vale 0.0 o 1.0.** Es honesto (no finge avance) pero la
  barra no se mueve durante la separación. Para granularidad real hay que
  enganchar el progreso de `audio-separator`, que hoy solo sale por tqdm.
- **La UI aún no pinta los acordes en cuanto llegan.** El backend ya los
  publica con `chords_ready` a los ~2s; `page.tsx` sigue esperando a `done`
  para montar el `<Studio>`.
- **`desktop/` no se ha compilado nunca**: falta Rust en la máquina. Además hay
  que generar los iconos (`npx tauri icon`) antes de la primera build.
- **Empaquetado**: `scripts/build-sidecar.sh` está escrito pero sin ejecutar.
  Juntar Python, PyTorch y los checkpoints es la parte más ingrata y no aporta
  información hasta que todo lo demás funcione.

## Convenciones

- **Español** en UI, comentarios, docstrings y mensajes de commit.
- Comentarios solo donde el porqué no sea obvio. No narrar lo que el código dice.
- `shared/types.ts` se genera con `scripts/gen-types.sh`. Nunca editarlo a
  mano; se desincroniza. El script importa la app en vez de levantar el
  servidor, así que no hace falta ni puerto ni token.
- Los checkpoints de modelos van a caché del usuario, **nunca al repositorio**.
  Se descargan en primera ejecución (Demucs pesa 84 MB, y hay una razón de
  licencia — ver abajo).
- Las salidas (`output/`, `bench_output/`, cualquier audio) nunca se versionan.
- **Identificadores en inglés, prosa en español.** Nombres de archivo,
  variables, funciones, clases, rutas HTTP, clases y variables CSS, claves de
  JSON y nombres de prueba en inglés. Comentarios, docstrings, textos de la UI
  y mensajes de error en español.
- Sin dependencias nativas que compliquen la instalación en macOS ARM.

## Diseño

Minimalismo editorial en modo oscuro. Referencias: Teenage Engineering,
Dieter Rams, vista de arreglo de Ableton Live. La maqueta en
`design/maqueta-preliminar/` es la referencia viva; sus tokens CSS son la
fuente de verdad para el frontend.

- Sin esquinas redondeadas, sombras, gradientes, glow ni neón.
- Sin cajas: la separación entre elementos son líneas de 0.5px
  (`rgba(255,255,255,0.12)`).
- Color **solo** para estado (acorde sonando, clip, selección). Un solo acento,
  `#ff4d00`, en menos del 5% de la pantalla. Si hay varios elementos con el
  acento encendido a la vez, es un bug.
- Etiquetas en `Inter` 11-13px con `letter-spacing: 0.14em`.
  Datos (tiempos, dB, acordes) en `JetBrains Mono`.
- La jerarquía viene del espaciado, no del tamaño ni del peso.
- Atajos de teclado en `lib/useTransportKeys.ts`: espacio reproduce/pausa,
  flechas mueven 1s (5s con Shift). `resolveShortcut` está separada y es pura
  para poder probar los casos raros sin navegador. El `preventDefault` no es
  opcional: sin él el espacio hace scroll de página Y activa el botón que
  tenga el foco, alternando dos veces.
- Ancho completo: en una herramienta multipista el ancho horizontal **es** la
  resolución temporal. No aplicar `max-width` de contenedor de lectura.
- La línea de acordes comparte eje exacto con las formas de onda. Cada acorde
  es un bloque proporcional a su duración real. **Enunciarlo no basta**: la
  garantía es estructural — acordes, ondas y playhead viven dentro del mismo
  `.canvas` de `studio.module.css`, así que comparten scroll y ancho por
  construcción. Cuando estaban en contenedores distintos el desfase era de
  112px al principio y 272px al final. No los separes.
- Los controles del canal quedan fuera del contenedor desplazable: el scroll
  horizontal mueve el tiempo, nunca el mezclador.

## Estado y prioridades

El backend está completo y medido: `core.py`, `api.py`, CLI, bench y 27
pruebas en verde. El frontend compila y el mezclador está resuelto.

**Lo siguiente**: probarlo de punta a punta con una canción real. Subir un MP3
desde `next dev`, ver las formas de onda con los acordes debajo, comprobar que
las cuatro pistas suenan en fase. Feo pero completo.

**Ya resuelto, no rehacer**: la sincronización entre Web Audio API y la línea de
tiempo era el corazón técnico del frontend y está en `lib/audio.ts` con el
porqué escrito. El puerto dinámico y el token local también están hechos.

**Dejar para el final**: el empaquetado con Tauri. `desktop/` está escrito pero
sin compilar, y así puede seguir semanas.

Fuera de alcance por ahora: transcripción a MIDI, detección de tempo y compás,
edición manual de acordes, cuentas de usuario, historial.

## Licencia

El código de BTC es MIT, pero hay ambigüedad sobre los pesos: un tercero
sostiene que heredan restricciones no comerciales de los datasets de
entrenamiento (Isophonics, Robbie Williams, UsPop2002). Los autores originales
nunca hicieron esa distinción. En MIR es práctica común licenciar código y pesos
por separado — madmom lo hace explícitamente.

Para uso no comercial no hay problema bajo ninguna interpretación. Por eso los
pesos **no se empaquetan ni se redistribuyen**: se descargan de Hugging Face en
tiempo de ejecución.

Atribución a Park et al. y al repositorio original en el README.

Si el proyecto se monetizara, hay que aclararlo con los autores o migrar a
Basic Pitch de Spotify (Apache 2.0 para código y pesos), que además daría
vocabulario ilimitado e inversiones reales desde el stem de bajo.

## Distribución

GitHub Releases con binario sin firmar. El usuario abre con clic derecho la
primera vez para saltar Gatekeeper; documentarlo en el README como decisión,
no como omisión.

La App Store no es viable: exige sandboxing, que pelea con el sidecar de Python
y con la descarga de checkpoints en runtime. La exención de cuota de Apple es
solo para organizaciones, no para individuos.
