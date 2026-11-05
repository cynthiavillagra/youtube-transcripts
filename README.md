# youtube-transcripts

Extrae las transcripciones (subtítulos) de YouTube a texto, sin API key y sin descargar los videos.

Funciona con:

- **un video** → `python transcribir_youtube.py https://youtu.be/ID`
- **varios videos** → pasás varios links seguidos, o un archivo con un link por línea
- **una playlist entera** → pasás el link de la playlist

Se pueden mezclar las tres cosas en una misma corrida.

## Instalación (una sola vez por PC)

Necesitás [uv](https://docs.astral.sh/uv/) (o Python 3.11+ con pip) y git.

```powershell
git clone https://github.com/cynthiavillagra/youtube-transcripts.git
cd youtube-transcripts
uv sync
```

Sin uv: `pip install -r requirements.txt` y reemplazás `uv run` por `python` en los ejemplos.

## Uso

### La forma rápida (Windows, doble clic)

1. Doble clic en **`transcribir.bat`**. La primera vez crea `links.txt` y lo abre en el Bloc de notas.
2. Pegá los links (uno por línea: videos, shorts o playlists), guardá y cerrá.
3. Doble clic de nuevo en `transcribir.bat`. Las transcripciones quedan en la carpeta `transcripciones/`.

### Desde la terminal

```powershell
# Un video
uv run transcribir_youtube.py https://www.youtube.com/watch?v=VIDEO_ID

# Varios videos
uv run transcribir_youtube.py https://youtu.be/ID1 https://youtu.be/ID2 https://youtu.be/ID3

# Lista de links en un archivo
uv run transcribir_youtube.py --lista links.txt

# Playlist completa, y además todo junto en un solo archivo (ideal para NotebookLM)
uv run transcribir_youtube.py "https://www.youtube.com/playlist?list=PLxxxx" --unir
```

> En PowerShell, poné entre comillas los links que tengan `&`.

### Opciones útiles

| Opción | Qué hace |
|---|---|
| `-f txt md srt json txt-tiempos` | Formatos de salida (por defecto `txt` y `md`) |
| `-i es,en` | Idiomas preferidos, en orden (por defecto español y luego inglés) |
| `-t es` | Si no hay subtítulos en esos idiomas, traduce al español con la traducción de YouTube |
| `--unir` | Además, junta todas las transcripciones de cada playlist en un solo archivo `_TODO - ….md` |
| `--solo-video` | Con un link `watch?v=…&list=…`, baja solo ese video y no la playlist entera |
| `--solo-manuales` | Ignora los subtítulos automáticos |
| `-o carpeta` | Carpeta de salida (por defecto `transcripciones`) |
| `--pausa 3` | Segundos entre videos (subilo si YouTube bloquea) |
| `--sobrescribir` | Vuelve a bajar aunque ya exista el archivo |

`uv run transcribir_youtube.py --help` muestra todas.

### Formatos

- **txt**: texto corrido, en párrafos de ~1 minuto.
- **md**: título, link, idioma y párrafos con marca de tiempo clickeable (abre el video en ese minuto).
- **txt-tiempos**: una línea por fragmento con `[hh:mm:ss]`.
- **srt**: subtítulos estándar (sirven para VLC, editores de video, etc.).
- **json**: todos los datos crudos, para procesar con código.

## Qué genera

```
transcripciones/
├── resumen.csv                  ← registro de cada corrida: qué salió bien, idioma, errores
├── videos/                      ← videos sueltos
│   └── Título del video [ID].md
└── Nombre de la playlist/
    ├── 001 - Primer video [ID].md
    ├── 002 - Segundo video [ID].md
    └── _TODO - Nombre de la playlist.md   (con --unir)
```

Si volvés a correr con la misma lista, **saltea los videos que ya están** bajados; así podés retomar una playlist larga si se cortó.

La carpeta `transcripciones/` no se sube a GitHub (está en `.gitignore`): queda en cada PC.

## Problemas comunes

- **"subtítulos desactivados"**: el video no tiene transcripción. Para esos casos sirve transcribir el audio con Whisper.
- **"no hay transcripción en es, en…"**: probá con `-t es` para usar la traducción automática.
- **"YouTube bloqueó las consultas desde tu IP"**: pasa con muchas consultas seguidas. Esperá un rato y corré de nuevo con `--pausa 5` (retoma donde quedó). En casos persistentes se puede usar `--proxy`.
- **Una playlist privada no se lee**: tiene que ser pública o "no listada".
- Si una playlist deja de leerse después de un tiempo, actualizá: `uv sync --upgrade` (YouTube cambia seguido y yt-dlp se actualiza para seguirle el ritmo).

## Tests

```powershell
uv run python -m unittest discover tests
```

Funcionan sin internet (simulan YouTube).

## No usa credenciales

Este proyecto no necesita tokens ni claves. Si en algún momento usás `--proxy` con usuario y contraseña, no lo guardes en el repo.
