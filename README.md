# mewsplit

Separa una canción en sus instrumentos, detecta sus acordes y te deja
practicar encima. Aplicación de escritorio con opción de despliegue web.

Subes un archivo de audio y obtienes:

- **Stems separados**: voz, bajo, batería y el resto; opcionalmente también
  guitarra y piano.
- **Los acordes de la canción**, con sus tiempos, alineados con las formas de
  onda.
- **Un mezclador** para subir, bajar, silenciar o aislar cada instrumento
  mientras suena.
- **Backing tracks**: exporta la mezcla que armaste (sin voz, sin guitarra,
  solo la sección rítmica…) como un WAV para tocar encima.

Pensado para sacar canciones de oído, estudiar una línea de bajo, ensayar sin
el instrumento que tocas tú o hacer un karaoke.

## Instalación

Necesitas una Mac con Apple Silicon (M1 o posterior). Abre la app **Terminal**
(⌘ + espacio, escribe "Terminal"), pega esta línea y pulsa Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/JUrielC/mewsplit/master/scripts/install.sh | sh
```

Cuando termine, mewsplit queda en tu carpeta de Aplicaciones: ábrelo con
Spotlight (⌘ + espacio, "mewsplit") o con doble clic, como cualquier app. Se
abre en una ventana del navegador y se cierra solo unos minutos después de
cerrarla.

La primera instalación descarga alrededor de 1 GB y la primera canción baja
los modelos (~100 MB); después ya no hace falta volver a descargarlos.

### Si prefieres que te guíe un asistente de IA

Copia esto en ChatGPT, Claude, Gemini o el que uses:

> Quiero instalar mewsplit en mi Mac. Guíame paso a paso, como a alguien que
> nunca ha usado la Terminal: cómo abrir la aplicación Terminal, y luego que
> pegue exactamente este comando y pulse Enter:
> `curl -fsSL https://raw.githubusercontent.com/JUrielC/mewsplit/master/scripts/install.sh | sh`.
> No me propongas otros comandos ni pasos alternativos. Si aparece un error,
> pídeme que te pegue el mensaje completo y ayúdame a entenderlo.

### Actualizar o desinstalar

```bash
uv tool upgrade mewsplit                                               # actualizar
uv tool uninstall mewsplit && rm -rf ~/Applications/mewsplit.app ~/.cache/mewsplit   # desinstalar
```

### ¿Por qué un comando y no una app descargable?

macOS bloquea las apps descargadas con el navegador si no están firmadas y
notarizadas por Apple, y desde macOS Sequoia ya no basta con el clic derecho:
hay que ir a Configuración del Sistema. Lo que se instala desde la Terminal no
lleva esa marca de "descargado de internet", y el acceso directo lo crea el
instalador en tu propia Mac, así que se abre sin avisos.

## Qué puede hacer

### Separación de pistas

- **4 stems** (por defecto): voz, bajo, batería y otros.
- **6 stems** (opcional): añade guitarra y piano. Se elige al subir el audio.
  Cuesta algo de calidad en los 4 stems base, y el piano sale con artefactos;
  la guitarra sale bien.
- Un **instrumental** (todo menos la voz) se genera automáticamente.
- Barra de progreso real durante la separación. Una canción de 3:39 tarda
  unos 32 s en un MacBook M3, sin GPU dedicada.
- Formatos de entrada: WAV, MP3, FLAC, AIFF, M4A y OGG.

### Acordes

- Se detectan sobre el audio original, en paralelo con la separación: están
  listos en un par de segundos.
- Cada acorde es un bloque proporcional a su duración real, en el mismo eje
  que las formas de onda. Clic en un acorde para saltar a él.
- El acorde que está sonando se muestra en el transporte.
- **Dos niveles de detalle**, sin volver a procesar:
  - **simples**: solo mayores y menores.
  - **completos**: además séptimas, sextas, suspendidos, aumentados y
    disminuidos, cuando hay evidencia sostenida.
- Cifrado de siempre (`Gm`, `C7`, `Am7b5`), no notación técnica.

### Mezclador

- Volumen, mute y solo por pista. Todas las pistas suenan en fase: se
  programan con el mismo reloj de audio, no cada una por su cuenta.
- **Modos de práctica** de un clic: mezcla completa, aislar bajo, sin voz y
  sección rítmica (bajo + batería). Se calculan sobre los stems que existen,
  así que funcionan igual con 4 que con 6.

### Backing tracks

**save mix** renderiza la mezcla actual (respetando volúmenes, mutes y solos)
a un WAV de 16 bits. El nombre del archivo lista las pistas que suenan:
`Canción - bass+drums.wav`, o `Canción - full mix.wav` si suenan todas.
Algunos usos:

- **Karaoke**: modo "sin voz" y guardar.
- **Pista para bajista**: silenciar `bass`.
- **Pista para guitarrista**: silenciar `other` (o `guitar` con 6 stems).
- **Base rítmica**: modo "sección rítmica" (bajo + batería).
- **Estudiar un instrumento**: dejarlo en solo y guardar.

### Navegación

- Formas de onda por pista, con zoom de 1× a 128×. El ancho de la pantalla es
  la resolución temporal: a más zoom, más detalle del compás.
- El scroll sigue al cursor de reproducción; clic en cualquier punto para
  saltar ahí.
- Atajos de teclado:

  | tecla | acción |
  |---|---|
  | espacio | reproducir / pausar |
  | ← → | mover 1 s |
  | ⇧ ← → | mover 5 s |
  | 0 – 9 | saltar al 0 %–90 % de la canción |

### Desde la terminal

Todo lo anterior salvo el mezclador, sin interfaz:

```bash
cd backend
.venv/bin/python cli.py cancion.mp3                  # stems + instrumental + acordes en ./output
.venv/bin/python cli.py cancion.mp3 --6-stems        # añade guitarra y piano
.venv/bin/python cli.py cancion.mp3 --simple-chords  # acordes solo mayores y menores
.venv/bin/python cli.py cancion.mp3 --skip-chords    # solo separar
.venv/bin/python cli.py cancion.mp3 --out stems/ --model-dir ~/.cache/mewsplit/models
```

## Estado

Funciona de punta a punta en `next dev`: se sube una canción, se separa, se
ven los acordes bajo las formas de onda y las pistas suenan en fase. Probado
con canciones reales.

Pendiente:

- **Ventana propia**: se abre en el navegador (en modo app si tienes Chrome).
  `desktop/` (Tauri) está en pausa: sin firma de Apple, un `.dmg` descargado
  es justo lo que macOS bloquea.
- **Bucle de una sección**: el motor de audio ya lo soporta, pero aún no hay
  control en la interfaz.
- **Acordes al instante**: el backend los publica a los ~2 s, pero la interfaz
  espera a que terminen los stems para mostrarlos.

## Desarrollo

Requiere macOS con Apple Silicon, Python 3.11+, [uv](https://docs.astral.sh/uv/)
y Node 20+.

```bash
# Backend
cd backend
uv venv .venv --python 3.11 && uv pip install -e ".[dev]"
cp .env.example .env                  # una sola vez: fija puerto y token
.venv/bin/pytest                      # 58 pruebas, sin descargar modelos
.venv/bin/python -m mewsplit.api      # imprime MEWSPLIT_READY port=<n> token=<t>

# Frontend, en otra terminal
cd frontend
npm install && npm run dev            # lee el puerto y el token de backend/.env
```

`backend/.env` es la única fuente de puerto y token: el frontend lo lee al
arrancar, así que no hace falta configurar nada más. `frontend/.env.local`
solo se usa para apuntar a un backend remoto.

La primera ejecución descarga los modelos: Demucs (84 MB) a
`~/.cache/mewsplit/models` y BTC a `~/.cache/huggingface/`. Nada de eso va al
repositorio.

### Publicar una versión

```bash
scripts/build-release.sh    # interfaz estática + wheel en dist/
```

El wheel lleva la interfaz ya compilada, así que instalarlo no requiere Node.
Se sube como asset de una GitHub Release; `scripts/install.sh` instala siempre
el de la última. Para probar el instalador sin publicar nada:

```bash
MEWSPLIT_WHEEL=dist/mewsplit-0.1.0-py3-none-any.whl MEWSPLIT_APP_DIR=/tmp/apps sh scripts/install.sh
```

## Arquitectura

```
backend/mewsplit/core.py         orquestación pura: recibe rutas, devuelve datos
backend/mewsplit/separation.py   Demucs vía audio-separator
backend/mewsplit/chords.py       BTC + decodificación propia de acordes
backend/mewsplit/api.py          FastAPI: trabajos en segundo plano, token, puerto
backend/mewsplit/app.py          el comando `mewsplit`: API + interfaz + ventana
backend/cli.py                   la misma lógica desde la terminal
frontend/                        Next.js: la misma build sirve a web y al comando
frontend/lib/audio.ts            el mezclador (Web Audio API)
scripts/install.sh               instalador de una línea para usuarios
desktop/                         Tauri, en pausa (ver Distribución)
shared/types.ts                  tipos del contrato, generados desde OpenAPI
```

**La regla**: `core.py` no sabe dónde corre. Ni FastAPI, ni Tauri, ni ningún
proveedor de nube. Todo lo demás es envoltorio y todo envoltorio es
reemplazable: por eso el mismo código sirve a escritorio y a web, y cambiar de
proveedor es reescribir un archivo.

La comunicación es HTTP en los dos destinos: en escritorio contra `localhost`,
en web contra un servidor remoto. El frontend solo cambia la URL base.

## Decisiones, con los datos que las respaldan

### Separación: Demucs v4 estándar

`htdemucs` sobre `audio-separator`. Se descartó `htdemucs_ft`, un ensamble de
4 modelos: tarda 4 veces más y no aportó diferencia útil.

Medición en MacBook M3, canción de 3:39:

| Modelo        | Tiempo | Factor tiempo real |
|---------------|--------|--------------------|
| `htdemucs`    | 32 s   | 6.8×               |
| `htdemucs_ft` | 131 s  | 1.7×               |

6.8× tiempo real en una laptop sin GPU dedicada hace viable la versión de
escritorio como producto principal, no como plan B.

### Acordes: BTC con decodificación propia

El modelo es BTC (`puar-playground/btc-chord`), vocabulario de 170 clases,
en CPU. Pero sus acordes no se usan tal cual: el modelo decide frame a frame
(cada 93 ms) y cada frame dudoso se convertía en un acorde "fantasma" de una
fracción de segundo. mewsplit toma sus probabilidades y las decodifica:

1. Ventanas solapadas, para que ningún frame quede en el borde de un bloque.
2. La probabilidad de las 170 clases se suma por familia: `C`, `C7` y `Cmaj7`
   dejan de competir entre sí. Aumentados y disminuidos tienen familia propia
   para no quedar absorbidos por el acorde vecino.
3. Viterbi: cambiar de acorde "cuesta", así que un frame dudoso no alcanza a
   crear un acorde nuevo.
4. La calidad (séptima, sus…) se decide por segmento, y solo se muestra si
   pesa 3 veces más que la tríada. Una séptima inventada choca al tocar
   encima; una omitida solo suena más simple.

Medido en [GuitarSet](https://zenodo.org/records/3371780) (guitarristas que
no se usaron para ajustar) y en 6 canciones de
[McGill Billboard](https://ddmal.music.mcgill.ca/research/The_McGill_Billboard_Project_(Chord_Analysis_Dataset))
con voz y batería, de artistas que no están en el entrenamiento de BTC:

| | antes | ahora |
|---|---|---|
| acordes fantasma por minuto (GuitarSet) | 8.6 | 0.16 |
| raíz correcta (GuitarSet) | 72.2 % | 73.7 % |
| mayor/menor correcto (GuitarSet) | 70.6 % | 71.6 % |
| disminuidos detectados (Billboard) | 5 % | 35 % |
| aumentados detectados (Billboard) | 0 % | 25 % |

El script de medición es `backend/bench_chords.py`; los datos y el audio se
quedan fuera del repositorio.

Límites conocidos: los aumentados de paso (menos de ~1 s) no se detectan; un
menor con séptima a veces se lee como su relativo mayor (`E♭m7` → `G♭`); y en
hip-hop construido sobre un sample el modelo a menudo no encuentra armonía.

**Los acordes son independientes de la separación.** Se probó detectarlos
sobre el instrumental, esperando más precisión, y no la hubo: 20 de 22 tramos
coincidieron con la detección sobre el audio original. Por eso las dos etapas
corren en paralelo y los acordes no esperan a los stems.

## Alcance

Dentro: separación en 4 o 6 stems, acordes con tiempos, mezclador, modos de
práctica, exportación de mezclas, instalación de un comando en macOS.

Fuera por ahora: transcripción a MIDI, detección de tempo y compás, edición de
los acordes detectados, cuentas de usuario, historial.

## Distribución

Un comando de instalación con uv, no un `.dmg`. Un binario sin firmar bajado
con el navegador lleva la marca de cuarentena y macOS lo bloquea; desde
Sequoia ni siquiera vale el clic derecho, y el público de mewsplit no tiene
por qué saber saltárselo. Lo instalado con uv desde la terminal no lleva esa
marca, y el acceso directo `mewsplit.app` lo genera el instalador en la propia
Mac, así que tampoco.

Firmar y notarizar un `.dmg` requiere la cuenta de desarrollador de Apple
(99 USD al año). Si algún día se paga, `desktop/` (Tauri) sirve con un cambio:
lanzar el comando `mewsplit` en vez de un binario empaquetado. La App Store no
es viable: exige sandboxing, que choca con la descarga de modelos en tiempo de
ejecución.

## Licencia y atribución

El código de mewsplit se publica bajo la
[PolyForm Noncommercial 1.0.0](LICENSE): es código disponible, no código
abierto en el sentido oficial. En lenguaje llano:

- **Puedes** usarlo gratis para tocar, estudiar, enseñar o investigar,
  modificarlo y compartirlo, siempre sin fines de lucro.
- **No puedes** venderlo ni incluirlo en un producto o servicio comercial.
- Las escuelas, ONG e instituciones públicas pueden usarlo aunque reciban
  financiamiento.

Si te interesa un uso comercial, escríbeme por GitHub.

### Uso bajo tu propio riesgo

mewsplit se entrega tal cual, sin garantías de ningún tipo. Quien lo usa lo
hace bajo su propia responsabilidad, y el autor no responde por daños
derivados de su uso. En particular:

- **Los derechos del audio que proceses son tu responsabilidad.** Separar una
  canción no te da derechos sobre ella ni sobre sus stems.
- **Los modelos tienen sus propias licencias**, que se detallan a
  continuación. mewsplit no los incluye: los descarga cada usuario al usarlo.
- Los acordes y los stems son estimaciones automáticas y pueden contener
  errores.

Este resumen es orientativo; lo que vale legalmente es el texto de
[LICENSE](LICENSE).

### Modelos y datos de terceros

La detección de acordes usa **BTC** (Bi-directional Transformer for Chord
recognition), de Jonggwon Park, Kyoyun Choi, Sungwook Jeon, Dokyun Kim y
Jonghun Park — *"A Bi-Directional Transformer for Musical Chord Recognition"*
(ISMIR 2019). Código original:
[jayg996/BTC-ISMIR19](https://github.com/jayg996/BTC-ISMIR19). Los pesos se
toman de [puar-playground/btc-chord](https://huggingface.co/puar-playground/btc-chord).

El código de BTC es MIT, pero hay ambigüedad sobre los pesos: un tercero
sostiene que heredan restricciones no comerciales de los datasets con que se
entrenaron (Isophonics, Robbie Williams, UsPop2002), aunque los autores
originales nunca hicieron esa distinción. En MIR es práctica común licenciar
código y pesos por separado (madmom lo hace explícitamente), así que el
argumento no es frívolo.

Para uso no comercial no hay problema bajo ninguna interpretación. Por eso los
pesos **no se empaquetan ni se redistribuyen**: se descargan de Hugging Face
en tiempo de ejecución. Si el proyecto se monetizara, habría que aclararlo con
los autores o migrar a Basic Pitch de Spotify (Apache 2.0 para código y
pesos).

La separación usa **Demucs v4** (Alexandre Défossez et al.) vía
[audio-separator](https://github.com/nomadkaraoke/python-audio-separator).

Las mediciones de acordes usan **GuitarSet** (Xi et al., ISMIR 2018, CC BY
4.0) y las anotaciones de **McGill Billboard** (Burgoyne et al., ISMIR 2011,
CC0). Ninguno de los dos se redistribuye aquí.
