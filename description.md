# mewsplit

Separador de pistas de audio con detección de acordes. Aplicación de escritorio
con opción de despliegue web.

## Qué hace

Recibe un archivo de audio y devuelve:

1. **Stems separados** — voz, bajo, batería y otros, como archivos independientes.
2. **Progresión de acordes** — con marcas de tiempo, en vocabulario amplio
   (séptimas, sus, disminuidos), no solo mayor/menor.
3. **Mezclador interactivo** — volúmenes independientes por stem en el navegador,
   para aislar o silenciar partes mientras se escucha.

El caso de uso: sacar de oído una canción, aislar el bajo para estudiarlo,
o hacer una pista de acompañamiento quitando un instrumento.

## Decisiones tomadas, con los datos que las respaldan

### Separación: Demucs v4 estándar

`htdemucs` sobre `audio-separator`. Descartado `htdemucs_ft` (la variante
fine-tuned, que es un ensamble de 4 modelos): tarda 4.06x más y no aportó
diferencia útil en los acordes.

Medición en MacBook M3, canción de 3:39:

| Modelo        | Tiempo | Factor tiempo real |
|---------------|--------|--------------------|
| `htdemucs`    | 32 s   | 6.8x               |
| `htdemucs_ft` | 131 s  | 1.7x               |

**Consecuencia**: 6.8x tiempo real en una laptop sin GPU dedicada hace que
la versión de escritorio sea viable como producto principal, no como plan B.

### Acordes: BTC, independiente de la separación

Modelo `puar-playground/btc-chord`, vocabulario de 170 clases, notación Harte.
Corre en CPU en ~1 segundo por canción. No necesita GPU.

Se probó la hipótesis de que detectar acordes sobre el instrumental (sin voz)
mejoraría la precisión. **No se confirmó**: 20 de 22 tramos coincidieron con
la detección sobre el audio original.

**Consecuencia**: las dos funciones son independientes. Los acordes no esperan
a la separación, y un demo web de solo acordes no necesitaría GPU en absoluto.

Queda una discrepancia por resolver a oído: en cinco puntos recurrentes el
original detecta `E:min` donde el instrumental detecta `G`. Comparten dos notas;
la diferencia está en si la tercera viene de la guitarra o de la melodía vocal.

### Comunicación: HTTP en ambos destinos

El backend de Python expone HTTP. En escritorio corre en `localhost`; en web
corre remoto. El frontend solo cambia la URL base.

Se descartó IPC nativo para escritorio: obligaría a mantener dos caminos de
comunicación para la misma funcionalidad. El overhead de HTTP sobre loopback
es irrelevante frente a una operación de 30 segundos.

## Arquitectura

Monorepo con dos paquetes y una regla que los separa:

```
frontend/   Next.js — UI, mezclador con Web Audio API, cliente HTTP
backend/
  core.py   lógica pura: recibe rutas, devuelve datos.
            CERO referencias a plataforma.
  api.py    FastAPI encima de core.py
```

**La regla**: `core.py` no sabe dónde corre. Ni Gradio, ni Modal, ni HF Spaces,
ni Vercel, ni Tauri. Todo lo demás es envoltorio y todo envoltorio es
reemplazable.

Eso es lo que hace que el mismo código sirva para escritorio y para web, y lo
que hace que cambiar de proveedor de nube sea reescribir un archivo.

### Escritorio (destino principal)

Tauri empaqueta el frontend y arranca el backend de Python como sidecar.
Sin límites de duración, sin cuotas, sin dependencia de terceros.

### Web (escaparate)

Frontend en Vercel. Backend en Hugging Face Spaces con ZeroGPU: el navegador
llama al Space directamente, sin proxy, para que cada visitante consuma su
propia cuota anónima en lugar de la del dueño del Space.

Limitaciones aceptadas: tope de duración por llamada, cola de prioridad baja,
y el Space se duerme a las 48 horas.

Su función es que alguien pruebe el proyecto en diez segundos sin instalar nada,
y de ahí descargue la versión completa.

## Alcance de la v1

Dentro: separación en 4 stems, acordes con marcas de tiempo, mezclador con
volúmenes, exportar stems, empaquetado de escritorio para macOS.

Fuera por ahora: transcripción a MIDI, detección de tempo y compás, edición de
los acordes detectados, cuentas de usuario, historial.

## Pendientes por resolver

- **Empaquetado**: juntar Python, PyTorch y los checkpoints de Demucs en un
  instalador es la parte más ingrata. No abordarlo hasta tener el flujo completo
  corriendo con `next dev` contra el FastAPI local.
- **Puerto dinámico**: fijar un puerto revienta si el usuario lo tiene ocupado.
  El backend debe tomar uno libre y comunicárselo al frontend.
- **Token local**: cualquier proceso en la máquina puede hablarle a un servidor
  en localhost. Token aleatorio al arrancar, exigido en cada petición.
- **Contrato tipado**: FastAPI genera OpenAPI; generar tipos de TypeScript desde
  ahí para no mantener las interfaces a mano en dos lenguajes.
- **Descarga de checkpoints**: en primera ejecución o incluidos en el instalador.

## Nota de licencia

El código de BTC es MIT, pero hay ambigüedad sobre los pesos: un tercero sostiene
que heredan restricciones no comerciales de los datasets con que se entrenaron
(Isophonics, Robbie Williams, UsPop2002), aunque los autores originales nunca
hicieron esa distinción. En el campo es práctica común licenciar código y pesos
por separado —madmom lo hace explícitamente— así que el argumento no es frívolo.

Para uso no comercial no hay problema bajo ninguna interpretación. Si el proyecto
se monetizara, hay que aclararlo con los autores o cambiar a pesos de procedencia
limpia. Basic Pitch de Spotify es Apache 2.0 para código y pesos, y sería la ruta
alternativa.

Atribución a Park et al. y al repositorio original en el README.
