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
.venv/bin/pytest                      # 58 pruebas, no descargan modelos
.venv/bin/pytest -m slow              # las que separan audio de verdad
.venv/bin/pytest tests/test_core.py::test_stopwatch_records_the_stage
cp .env.example .env                  # una vez: fija puerto y token de desarrollo
.venv/bin/python -m mewsplit.api      # imprime MEWSPLIT_READY port=<n> token=<t>
.venv/bin/python cli.py cancion.mp3 [--6-stems] [--skip-chords] [--simple-chords]
.venv/bin/python bench.py cancion.mp3
.venv/bin/python bench_chords.py [variante ...]   # acordes contra GuitarSet

# Frontend
cd frontend
npm install && npm run dev            # lee backend/.env, no necesita .env.local
npm run typecheck && npm run build

# Contrato tipado: regenerar tras CUALQUIER cambio en los modelos de api.py
./scripts/gen-types.sh

# Paquete para usuarios (wheel con la interfaz dentro) y su instalador
./scripts/build-release.sh
MEWSPLIT_WHEEL="$(ls dist/*.whl)" MEWSPLIT_APP_DIR=/tmp/apps sh scripts/install.sh
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
  api.py          FastAPI: proyectos, análisis en segundo plano, token, puerto dinámico
  projects.py     los proyectos en disco: project.json, audio original, stems en FLAC
  app.py          el comando `mewsplit`: envuelve api, sirve la interfaz, abre la ventana
  web/            interfaz compilada, GENERADA por build-release.sh e ignorada por git
  bin/            ventana nativa compilada, GENERADA por build-release.sh e ignorada
native/macos/main.swift  la ventana nativa de macOS (Swift, WKWebView)
backend/cli.py    argparse sobre core
backend/bench.py  consume las funciones sueltas, no analyze(): necesita otro orden
backend/bench_chords.py  mide variantes de acordes contra GuitarSet (mir_eval)
frontend/lib/audio.ts   el mezclador (Web Audio API)
frontend/lib/api.ts     cliente HTTP, tipos importados de shared/types.ts
scripts/install.sh      instalador de una línea: uv, el wheel y el acceso directo
desktop/src-tauri/      Tauri, SUPERADO por native/macos (ver Distribución)
shared/types.ts         GENERADO, no editar a mano
```

Dos contratos que hay que respetar al tocar los extremos:

- **Arranque del sidecar**: `api.run()` imprime
  `MEWSPLIT_READY port=<n> token=<t>` como primera línea de stdout.
  `desktop/src-tauri/src/main.rs` la parsea. Cambiar el formato rompe el escritorio.
- **Configuración en el cliente**: `app.py` (y antes Tauri) inyecta
  `window.__MEWSPLIT__` en el `<head>` antes de que corra el JS de la página,
  con `api: ""` porque interfaz y API comparten origen; en `next dev` los
  valores salen de `NEXT_PUBLIC_MEWSPLIT_*`. Todo eso está en `lib/api.ts`.
- **Puerto y token en desarrollo**: `backend/.env` es la FUENTE ÚNICA. Lo leen
  `api.py` al arrancar y `frontend/next.config.ts` al levantar `next dev`.
  El entorno explícito gana sobre el archivo, y en la build estática de Tauri
  no se incrusta nada: el token llegaría dentro del binario distribuido.

La API nunca devuelve rutas del disco del servidor: los stems se piden por
nombre a `/projects/{id}/stems/{name}`.

## Decisiones ya tomadas

No las revisites sin razón nueva. Están medidas — los números viven en
`pipeline/salida_bench/bench.json` (M3, canción de 3:39, MPS).

**Separación: `htdemucs`, no `htdemucs_ft`.** El `_ft` es un ensamble de 4
modelos: 130.7s vs 32.2s (4.06x más lento, RTF 0.5951 vs 0.1466) y no aportó
diferencia útil. Medido, no supuesto.

**Acordes: `puar-playground/btc-chord`, en CPU, vocabulario de 170 clases**
(notación Harte). ~1 segundo por canción. No necesita GPU.

**Los acordes NO salen de `model.predict()`.** Ese método toma el argmax por
frame de 93 ms y tira las probabilidades: cada frame dudoso es un acorde
fantasma. `detect_chords()` hace su propia decodificación, medida con
`bench_chords.py` en GuitarSet (180 fragmentos; guitarristas 00-03 para
ajustar y 04-05 para validar). En validación, frente al `predict()` crudo:

| | root | majmin | sevenths | fantasmas/min | segmentos/min |
|---|---|---|---|---|---|
| `predict()` | 0.722 | 0.706 | 0.569 | 8.60 | 35.9 (ref 23.6) |
| actual | 0.737 | 0.716 | 0.612 | 0.16 | 23.7 |

Las piezas, en orden, y qué aporta cada una:
1. Ventanas de 10 s solapadas a medio bloque: la única que mejora la raíz
   (+1.1 pt). BTC no tiene contexto entre bloques.
2. Masa de las 170 clases sumada por familia: C, C7, Cmaj7 dejan de competir
   entre sí. Mayor y menor agrupan por tercera; aumentado y disminuido tienen
   familia propia (ver abajo).
3. Viterbi con `SELF_PROBABILITY = 0.99`: −98% de fantasmas. Da casi igual
   entre 0.9 y 0.995, no es un ajuste frágil.
4. Calidad por segmento con `QUALITY_MARGIN = 3`: una séptima se muestra solo
   si pesa 3× la tríada. Detecta el 45% de las séptimas reales e inventa
   séptimas en el 11% de las tríadas. Conservador a propósito: una séptima
   inventada choca al tocar encima, una omitida solo suena más simple. No
   elijas el margen por la métrica `sevenths`: sube sola al dejar de predecir
   séptimas.

**Aumentado y disminuido, familia propia.** Dentro de la mayor o la menor,
Viterbi nunca los separaba del acorde vecino: el `F#aug` de "Evidencias"
quedaba absorbido en un `F#` de 4 s. La familia disminuida lleva
`DIM_WEIGHT = 3` porque junta 3 calidades frente a las 6 de la mayor; el
aumentado va ×1 (con peso gana poca detección y pierde precisión). Medido en
6 canciones de McGill Billboard con voz y batería, frente a no separarlos:

| | root | triads | aug detectado / acertado | dim detectado / acertado |
|---|---|---|---|---|
| Billboard antes | 0.744 | 0.654 | 0% / — | 5% / 50% |
| Billboard ahora | 0.740 | 0.665 | 25% / 71% | 35% / 67% |
| GuitarSet antes | 0.737 | 0.698 | — | 26% / 71% |
| GuitarSet ahora | 0.737 | 0.704 | — | 45% / 68% |

Coste: −0.3 pt de majmin y sevenths en GuitarSet. Límite conocido: solo salen
los aumentados sostenidos (~2 s); los de paso (0.6–1.3 s, Anita Baker, Alan
O'Day) los sigue absorbiendo Viterbi. Relajarlo solo en esas familias traería
de vuelta fantasmas; no se ha probado.

Las canciones de Billboard (anotaciones CC0, sin artistas del entrenamiento de
BTC) y el experimento viven en `/tests/billboard/`, ignorado por git: el audio
no se puede versionar. Rita Coolidge "Higher And Higher", George Harrison "All
Those Years Ago" (versión 3:47, no la remasterización de 3:22), Juice Newton
"Break It To Me Gently", Tina Turner "Private Dancer" (7:13), Anita Baker
"Caught Up In The Rapture" y Alan O'Day "Undercover Angel". Comprueba la
versión alineando por cuartos: si el acierto se desploma a mitad, es otra
edición.

Descartadas, con números en `bench_chords.py`: el checkpoint de 25 clases como
base temporal y el de 170 para la calidad (pierde majmin frente a sumar el de
170), el promedio de ambos modelos (no aporta) y la votación por beat (quita
fantasmas pero el beat tracker mete sus errores; con Viterbi encima empeora
todo). Lo que queda es la raíz equivocada (~26% en validación): errores
sostenidos en los que el modelo está convencido, que ningún suavizado arregla.

GuitarSet es guitarra sola y la referencia es la partitura ("instructed"):
parte de las "séptimas inventadas" pueden ser voicings reales.

Dos errores sostenidos que ya se vieron en canciones reales: los menores con
séptima se leen como su relativo mayor (`Ebm7` → `Gb`, el mismo caso que
`E:min`/`G` de arriba), y en hip-hop sobre sample el modelo dice "sin acorde"
el 74% del tiempo (De La Soul): no ve la armonía bajo rap y batería. Una idea
sin probar para ese caso es detectar sobre los stems sin batería ni voz.

**El conmutador simples/completos es de detalle, no de precisión.** Las raíces
y los tiempos son idénticos en las dos posiciones. La tríada se deduce en el
cliente (`toTriad` en `lib/chords.ts`): raíz + tercera, teoría musical que no
depende del algoritmo, así que no hizo falta otro campo en la API.

**Los acordes son independientes de la separación.** Se probó detectarlos sobre
el instrumental esperando mejor precisión: 20 de 22 tramos idénticos al audio
original. No esperes a los stems para calcular acordes. Queda una discrepancia
sin resolver a oído: en cinco puntos el original detecta `E:min` donde el
instrumental detecta `G` — comparten dos notas, la diferencia está en si la
tercera viene de la guitarra o de la melodía vocal.

**Una excepción: la quinta aumentada de paso sí espera a los stems.** BTC no
distingue D–A# (D con quinta aumentada, sin tercera) de A#–D (A# sin quinta):
siempre dice A#. En "Hold me baby" (THE DO DO DO's) la progresión D#5 – D(#5)
– C#5 – C5 salía D# – A# – C# – C. `refine_with_stems` mira el cromagrama de
los stems armónicos (guitarra + piano + other, sin voz ni batería) y marca
`X:(1,#5)` solo si el mayor tiene su tercera al frente, no tiene quinta Y está
a medio tono de sus dos vecinos. Sin la línea cromática, las mismas notas son
un mayor en primera inversión (`Bb:maj/3` en Billboard) y se dejan. Medido en
`tests/powerchords/`: 0 cambios en GuitarSet y en Billboard, y los dos D(#5)
de la canción en su proyecto de 6 stems. En el de 4 stems Viterbi ya lo había
absorbido en el D# vecino y no hay tramo que corregir. Los acordes tempranos
(`on_chords`) salen sin el repaso; ~1–3 s después de la separación.

**El bajo de los acordes invertidos sale del stem de bajo, y solo si es claro.**
El mismo repaso añade `/3`, `/b3` o `/5` (la interfaz lo muestra como `A#/D`)
cuando la nota del stem de bajo es la tercera o la quinta y suena en el 75%
del tramo (`BASS_SHARE`). La nota sale del CQT entre E1 y E4 y no del
cromagrama, donde los armónicos del bajo pesan como notas. Medido en
`tests/bass/` contra las inversiones de Billboard: muestra 49 s, acierta el
71% y encuentra el 15% de las reales; majmin_inv .710 → .729 y la raíz no
cambia. Conservador a propósito, como las séptimas. Descartado: tomar la nota
más grave de guitarra y piano cuando el bajo calla (inventa inversiones en
GuitarSet). Por eso la intro de "Hold me baby" no cambia: ahí no toca el bajo,
lo más grave es el piano (F, F#, G#, que confirma A#, F#, G#) y la línea
D# → D → C# → C que se oye es la guitarra en el registro medio. Las dos
lecturas son válidas; la de la guitarra necesitaría separar voces (Basic Pitch).

**Las quintas solas (power chords) NO se detectan, y no por falta de
intentarlo.** BTC no tiene la clase "5" y dice mayor. Mirar si la tercera
falta en el cromagrama de los stems no sirve: en GuitarSet las tríadas reales
tienen la tercera tan débil (una cuerda de seis) como los power chords
distorsionados (el armónico 5 de la raíz cae en la tercera). El umbral que
encontraba las quintas de la canción convertía el 25–40% de las tríadas de
GuitarSet y el 10% de las de Billboard. Hace falta transcripción de notas
(Basic Pitch) o un modelo con quintas en su vocabulario.

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

**`audio-separator` se niega a arrancar sin `ffmpeg` en el PATH**, y quien
instala mewsplit para tocar no tiene Homebrew. `separation.ensure_ffmpeg()`
usa el del sistema si lo hay y si no el que trae `imageio-ffmpeg`, enlazado
como `ffmpeg` en `~/.cache/mewsplit/bin` (el binario se llama
`ffmpeg-macos-aarch64-v7.1` y audio-separator busca el nombre literal). En
esta máquina todo funcionaba porque Homebrew lo tenía: pruébalo con
`PATH=/usr/bin:/bin`.

**`uv tool dir --bin` pinta la ruta de color aun capturada.** Sin
`--color never`, los códigos ANSI quedan pegados a la ruta y el instalador no
encontraba el ejecutable que acababa de instalar.

**Una app lanzada por LaunchServices no puede leer `~/Documents` sin
permiso.** Probando la ventana nativa con una instalación dentro del
repositorio, el servidor se quedaba colgado al arrancar, sin CPU, esperando
el permiso de privacidad. Prueba siempre con la instalación fuera de las
carpetas protegidas (`/tmp`); la real vive en `~/.local`, que no lo está. El
binario de pruebas se compila con `-D MEWSPLIT_AUTOTEST`: contesta los
diálogos solo y se cierra, y el de producción no lleva esos ganchos.

**Uvicorn relanza la señal de cierre** después de apagarse, así que un
`finally` alrededor de `server.run()` no llega a correr. Por eso
`instance.json` puede quedar obsoleto y `_running_instance` pregunta a
`/health` antes de fiarse.

**Una grabación desafinada destroza los acordes, y no es culpa del modelo.**
"The Man Who Sold The World" (Nirvana, +43 cents) salía con 11 acordes
distintos que se peleaban por pares: G#/A, C#/D, E/F, B/C. El `predict()`
crudo daba 24; no lo causó la decodificación. BTC calcula sus casillas de
frecuencia (cuarto de tono) contando con 440 Hz, y a ~45 cents cada nota cae
entre dos. Nirvana pasa a su progresión real medio tono abajo (C#m, E, G#,
B, G#7) corriendo el CQT esa cantidad.

**Cómo se elige la afinación: la que deja al modelo más seguro.** Primero hubo
un umbral fijo (compensar solo desde 20 cents), y falló con dos copias de la
misma canción: la de Spotify medía +20.0 y la de YouTube +2 (una fue cambiada de
tono sin cambiar el tempo), así que una se corregía y la otra no según un
redondeo. `analyze_chords` prueba ahora la estándar, la estimada y la estimada
±10 cents (`TUNING_SPREAD`) y se queda con la de mayor confianza media
(`most_confident`). Medido en `tests/tuning/experiment.py` frente a umbral,
compensar siempre y promediar: gana en todo (par Spotify/YouTube 73.8% → 77.2%
de coincidencia; GuitarSet majmin .716 → .722; Billboard raíz .740 → .746) y
Nirvana sigue bien. Cuesta 4 inferencias de acordes (~2–3 s), irrelevante
frente a la separación. Lo que queda de diferencia entre esas dos copias son
pasajes ambiguos entre acordes que comparten notas (D#/G#, D#/Cm). La
compresión no influye: recomprimir a 128 kbps deja el 99% igual.

La afinación estimada viaja al proyecto (`tuning_cents`) y la interfaz avisa
desde 20 cents, con el La al que afinar el instrumento para tocar encima.
El aviso va a todo el ancho bajo la cabecera hasta que se descarta (por
proyecto, en localStorage); en la cabecera sola no se veía. Sugiere comparar
con otra versión porque ese par lo demostró: ningún ajuste de afinación ni de
ecualización llevó la copia de Spotify más allá del 77% de coincidencia con la
de YouTube, que suena fiel. Una copia con el tono cambiado pierde información
que el análisis no recupera.

**`AutoModel.from_pretrained` se traga `large_voca`.** Lo guarda como atributo
de configuración y el `from_pretrained` propio de BTC nunca lo recibe: siempre
cargaba el de 170 clases y `--simple-chords` no hacía nada, sin error.
`chords._load` llama a la clase directamente; hay una prueba `slow` que lo
vigila.

**`audio-separator` carga el modelo de forma diferida**, así que el tiempo de
carga aparece dentro del de separación, no antes.

**Los checkpoints de Demucs caen en `/tmp/audio-separator-models/`** por
defecto, y macOS lo purga. `api.py` fija `~/.cache/mewsplit/models` vía
`model_cache_dir`; el CLI usa el default salvo que le pases `--model-dir`. Los
pesos de BTC van a `~/.cache/huggingface/`.

**Los proyectos se guardan en disco, y eso tiene reglas.** Viven en
`~/Library/Application Support/mewsplit/projects/<id>/` (`MEWSPLIT_PROJECTS_DIR`
para pruebas): `project.json`, `original.<ext>` y `stems/*.flac`. La separación
escribe WAV en una carpeta de trabajo temporal y al proyecto solo llegan los
FLAC (sin pérdida, ~40–50% del WAV; una canción en WAV son 200–350 MB). El
instrumental no se guarda: la interfaz no lo usa. Si la app se cierra a mitad,
al arrancar el proyecto aparece como interrumpido en vez de "procesando" para
siempre. Eliminar a mitad de un análisis no lo corta (no se puede): marca el
proyecto y `_process` lo borra al terminar. La página pide el detalle de un
proyecto solo al cambiar de estado, no en cada sondeo de la lista: un objeto
nuevo cada segundo haría que Studio recargara los stems.

**Dos separaciones a la vez tumban el servidor.** Subir varias canciones
seguidas lanzaba un análisis por cada una en paralelo, y dos separaciones sobre
la GPU (MPS) desde hilos distintos chocan dentro de Metal (`failed assertion
_status < MTLCommandBufferStatusCommitted`): macOS mata el proceso entero, sin
excepción que atrapar. `_analysis_slot` en `api.py` deja pasar un análisis a
la vez; los demás esperan en "queued". No lo quites para "ganar velocidad":
repartir la GPU tampoco es más rápido.

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

**El progreso de Demucs se engancha parcheando `apply_model` en DOS módulos.**
`audio-separator` pasa `set_progress_bar=None` fijo, así que `separation.py`
lo sustituye mientras dura la separación. `demucs_separator.py` hace
`from ...apply import apply_model` y guarda su propia referencia: parchear solo
`apply` no hace nada y la barra se queda en 0% sin ningún error. El avance
llega de 0.1 a 0.9 y `core` lo cierra en 1.0. El parche es global al proceso:
dos separaciones simultáneas se pisarían el callback. Si una versión nueva de
`audio-separator` mueve esos módulos, el `ImportError` desactiva el progreso en
silencio.

**La velocidad se cambia en las fuentes y el tono se corrige al final.** Todas
las pistas cambian `playbackRate` en el mismo instante del reloj (siguen en
fase, sin reprogramarse) y un solo `SoundTouchNode` (@soundtouchjs/audio-worklet,
MPL-2.0) tras el master compensa el tono. Corregir por pista exigiría un
procesador por stem y podría desfasarlas; usar `<audio preservesPitch>` por
pista rompe el reloj único. SoundTouch solo está en el camino si la velocidad
no es 1 (a 1 no hay ni su retardo ni su procesado), el `time` del mezclador
avanza `elapsed * rate`, y la mezcla exportada sale a velocidad original. La
librería se importa dinámicamente: define su clase extendiendo
`AudioWorkletNode` al cargarse y eso revienta el prerender de Next en Node. El
procesador lo copia `frontend/scripts/copy-worklet.mjs` a `public/` antes de
`dev` y `build`. Medido en WKWebView: a 80% la canción avanza 0.799 del reloj
y un La de 440 Hz sigue en 440 (sin corrección bajaría a 352).

**El mezclador se desincroniza si cada fuente arranca por su cuenta.** Las
cuatro pistas se programan con el MISMO instante absoluto y el bucle lo hace el
hilo de audio (`loop`/`loopStart`/`loopEnd`), no `requestAnimationFrame`. rAF
solo pinta. Está explicado en la cabecera de `frontend/lib/audio.ts`; si alguien
lo "simplifica", vuelve el desfase.

## Pendientes

- **Los proyectos viven en el disco local.** En escritorio es lo correcto; un
  despliegue web con varios usuarios o workers necesitaría otro almacén.
- **Reanalizar un proyecto.** El audio original se guarda justo para eso (por
  ejemplo, tras mejorar los acordes), pero todavía no hay botón ni endpoint.
- **La UI aún no pinta los acordes en cuanto llegan.** El backend ya los
  publica con `chords_ready` a los ~2s; `page.tsx` sigue esperando a `done`
  para montar el `<Studio>`.
- **Solo hay pre-releases.** `install.sh` busca la release "latest" y, como
  GitHub nunca marca así una pre-release, cae a la más nueva de la lista.
  Cuando haya una versión definitiva, las pre-releases posteriores dejarán de
  instalarse con el comando corto (solo con `MEWSPLIT_WHEEL`).
- **El acceso directo no tiene icono** (usa el genérico de macOS).

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

El backend está completo y medido: `core.py`, `api.py`, CLI, bench y 58
pruebas en verde. Probado de punta a punta con canciones reales, y el comando
`mewsplit` instalado con `install.sh` en una carpeta aislada, sin Homebrew.

**Ya resuelto, no rehacer**: la sincronización entre Web Audio API y la línea de
tiempo era el corazón técnico del frontend y está en `lib/audio.ts` con el
porqué escrito. El puerto dinámico y el token local también están hechos.

**En pausa**: `desktop/` (Tauri). Escrito, nunca compilado. Ver Distribución.

Fuera de alcance por ahora: transcripción a MIDI, detección de tempo y compás,
edición manual de acordes, cuentas de usuario.

## Licencia

**El código de mewsplit es PolyForm Noncommercial 1.0.0** (`LICENSE`, texto
oficial sin alterar más la línea `Required Notice`). Se eligió sobre MIT
porque el autor no quiere que se venda ni se meta en un producto cerrado; no
por obligación de BTC, cuyos pesos no se redistribuyen y viajan con su propia
licencia. Es reversible en un sentido: se puede pasar a una licencia abierta
para versiones futuras, pero lo publicado con MIT nunca podría cerrarse. No lo
describas como "open source" en la documentación: es código disponible.

**Los pesos de BTC.** El código de BTC es MIT, pero hay ambigüedad sobre los pesos: un tercero
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

**Un comando con uv, no un `.dmg`.** El público son músicos, no gente técnica.
Un binario sin firmar bajado con el navegador lleva la marca de cuarentena y
Gatekeeper lo bloquea; desde macOS Sequoia el clic derecho → Abrir ya no lo
salta (hay que ir a Configuración del Sistema), y ahí es donde la gente se
rinde. Lo que instala uv desde la terminal no lleva esa marca, y el
`mewsplit.app` que crea `install.sh` nace en la propia Mac, así que tampoco.

**La ventana es nativa y viaja por uv.** `native/macos/main.swift` (Swift,
WKWebView) se compila en `build-release.sh` con las Command Line Tools y va
dentro del wheel, etiquetado `macosx_12_0_arm64`. Lo que baja uv no lleva
cuarentena, así que tampoco ese binario: `install.sh` lo copia como ejecutable
de `mewsplit.app` y firma el paquete ad-hoc (`codesign --sign -`, viene con
macOS). Da ventana e icono propios en el Dock y en Cmd+Tab, sin mezclarse con
las ventanas del navegador del usuario.

Es lanzador y ventana a la vez: arranca el comando `mewsplit` (ruta en la
clave `MewsplitCommand` del Info.plist) con `MEWSPLIT_NATIVE=1`, espera la
línea `MEWSPLIT_APP_READY url=… owner=new|existing` y carga esa URL. Si el
servidor es suyo lo detiene al cerrarse (SIGTERM y, al segundo, SIGKILL: el
cierre ordenado esperaría al análisis en curso); si ya existía, no lo toca.
Abrirla otra vez solo la trae al frente. Además de la página, avisa ella
misma a `/health` cada minuto: WebKit pausa los temporizadores de una ventana
minimizada y el servidor se apagaría por inactividad. Sin ventana nativa en el
paquete, `install.sh` vuelve al acceso directo con script y navegador.

Puerto fijo preferido (47820): si cambiara, cambiaría el origen y se perdería
lo guardado en localStorage.

**Tauri, superado; PyInstaller, descartado.** Un `--onefile` con PyTorch pesa
1–2 GB y se descomprime en cada arranque, y la ventana nativa cubre lo que
aportaba Tauri sin Rust ni firma de Apple. La App Store no es viable: exige
sandboxing, que pelea con la descarga de modelos en tiempo de ejecución.
