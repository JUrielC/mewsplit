# mewsplit

Separador de pistas de audio con detección de acordes. Aplicación de escritorio
con opción de despliegue web.

Recibe un archivo de audio y devuelve:

1. **Stems separados** — voz, bajo, batería y otros, como archivos independientes.
2. **Progresión de acordes** con marcas de tiempo, en vocabulario amplio
   (séptimas, sus, disminuidos), no solo mayor/menor.
3. **Mezclador** con volúmenes independientes por stem, para aislar o silenciar
   partes mientras se escucha.

El caso de uso: sacar de oído una canción, aislar el bajo para estudiarlo, o
hacer una pista de acompañamiento quitando un instrumento.

## Estado

El backend funciona y está medido. El frontend compila y tiene el mezclador
resuelto, pero aún no se ha probado de punta a punta contra una canción real.
`desktop/` está escrito y sin compilar: falta Rust.

## Puesta en marcha

Requiere macOS con Apple Silicon, Python 3.11+ y Node 20+.

```bash
# Backend
cd backend
uv venv .venv --python 3.11 && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest                                   # 27 pruebas, sin descargar modelos
python -m mewsplit.api                   # imprime puerto y token

# Frontend, en otra terminal
cd frontend
npm install
cp .env.example .env.local               # pega ahí el puerto y el token
npm run dev
```

Los checkpoints se descargan en la primera ejecución (Demucs pesa 84 MB) y
van a `~/.cache/mewsplit/models`.

### Desde la terminal, sin interfaz

```bash
cd backend
python cli.py cancion.mp3                # stems + acordes en ./output
python cli.py cancion.mp3 --6-stems      # añade guitarra y piano
python cli.py cancion.mp3 --skip-chords
python bench.py cancion.mp3              # comparativa de modelos
```

## Arquitectura

```
backend/mewsplit/core.py   lógica pura: recibe rutas, devuelve datos
backend/mewsplit/api.py    FastAPI encima de core
frontend/                  Next.js — la misma build sirve a web y a escritorio
desktop/                   Tauri: arranca el backend como sidecar
shared/types.ts            generado desde OpenAPI
```

**La regla**: `core.py` no sabe dónde corre. Ni Gradio, ni Modal, ni HF Spaces,
ni Vercel, ni Tauri. Todo lo demás es envoltorio y todo envoltorio es
reemplazable. Eso es lo que hace que el mismo código sirva para escritorio y
para web, y que cambiar de proveedor de nube sea reescribir un archivo.

La comunicación es HTTP en ambos destinos: en escritorio contra `localhost`,
en web contra un servidor remoto. El frontend solo cambia la URL base.

## Decisiones, con los datos que las respaldan

### Separación: Demucs v4 estándar

`htdemucs` sobre `audio-separator`. Descartado `htdemucs_ft` (ensamble de 4
modelos): tarda 4.06x más y no aportó diferencia útil.

Medición en MacBook M3, canción de 3:39:

| Modelo        | Tiempo | Factor tiempo real |
|---------------|--------|--------------------|
| `htdemucs`    | 32 s   | 6.8x               |
| `htdemucs_ft` | 131 s  | 1.7x               |

6.8x tiempo real en una laptop sin GPU dedicada hace que la versión de
escritorio sea viable como producto principal, no como plan B.

### Acordes: BTC, independiente de la separación

`puar-playground/btc-chord`, vocabulario de 170 clases, notación Harte. Corre
en CPU en ~1 segundo por canción.

Se probó la hipótesis de que detectar acordes sobre el instrumental (sin voz)
mejoraría la precisión. **No se confirmó**: 20 de 22 tramos coincidieron con la
detección sobre el audio original. Por eso las dos etapas corren en paralelo y
los acordes no esperan a los stems.

Queda una discrepancia por resolver a oído: en cinco puntos recurrentes el
original detecta `E:min` donde el instrumental detecta `G`. Comparten dos notas;
la diferencia está en si la tercera viene de la guitarra o de la melodía vocal.

## Alcance de la v1

Dentro: separación en 4 stems, acordes con marcas de tiempo, mezclador con
volúmenes, exportar stems, empaquetado de escritorio para macOS.

Fuera por ahora: transcripción a MIDI, detección de tempo y compás, edición de
los acordes detectados, cuentas de usuario, historial.

## Distribución

GitHub Releases con binario sin firmar. La primera vez hay que abrirlo con clic
derecho para saltar Gatekeeper. Es una decisión, no una omisión: la App Store
exige sandboxing, que pelea con el sidecar de Python y con la descarga de
checkpoints en runtime, y la exención de cuota de Apple es solo para
organizaciones.

## Licencia y atribución

La detección de acordes usa **BTC** (Bi-directional Transformer for Chord
recognition), de Jonggwon Park, Kyoyun Choi, Sungwook Jeon, Dokyun Kim y
Jonghun Park — *"A Bi-Directional Transformer for Musical Chord Recognition"*
(ISMIR 2019). Código original: [jayg996/BTC-ISMIR19](https://github.com/jayg996/BTC-ISMIR19).
Los pesos se toman de [puar-playground/btc-chord](https://huggingface.co/puar-playground/btc-chord).

El código de BTC es MIT, pero hay ambigüedad sobre los pesos: un tercero
sostiene que heredan restricciones no comerciales de los datasets con que se
entrenaron (Isophonics, Robbie Williams, UsPop2002), aunque los autores
originales nunca hicieron esa distinción. En MIR es práctica común licenciar
código y pesos por separado —madmom lo hace explícitamente— así que el
argumento no es frívolo.

Para uso no comercial no hay problema bajo ninguna interpretación. Por eso los
pesos **no se empaquetan ni se redistribuyen**: se descargan de Hugging Face en
tiempo de ejecución. Si el proyecto se monetizara, hay que aclararlo con los
autores o migrar a Basic Pitch de Spotify (Apache 2.0 para código y pesos).

La separación usa **Demucs v4** (Alexandre Défossez et al.) vía
[audio-separator](https://github.com/nomadkaraoke/python-audio-separator).
