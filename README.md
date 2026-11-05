# youtube-transcripts

Extrae las transcripciones (subtítulos) de YouTube a texto, sin API key y sin descargar los videos.

Sirve para:

- **un video**
- **varios videos** (una lista de links)
- **una playlist entera**

Se pueden mezclar las tres cosas en una misma corrida. Se usa desde una **interfaz web** en el navegador o desde la terminal.

---

## Instalación (una sola vez por PC)

### 1. Instalar las herramientas

Hacen falta dos programas. Si ya los tenés en esa PC, salteá este paso.

**Git** (para bajar y sincronizar el repo): https://git-scm.com/download/win → instalar con las opciones por defecto.

**uv** (administra Python y el entorno virtual). Abrí **PowerShell** y pegá:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Cerrá PowerShell y abrilo de nuevo para que reconozca el comando. Para verificar:

```powershell
git --version
uv --version
```

> No hace falta instalar Python aparte: uv baja la versión correcta solo.

### 2. Bajar el repo

Elegí dónde querés tenerlo (por ejemplo, Documentos) y cloná:

```powershell
cd $HOME\Documents
git clone https://github.com/cynthiavillagra/youtube-transcripts.git
cd youtube-transcripts
```

### 3. Crear el entorno virtual e instalar dependencias

```powershell
uv sync
```

Esto hace tres cosas:

1. Baja Python 3.11 o superior si no lo tenés.
2. Crea el **entorno virtual** en la carpeta `.venv/` dentro del proyecto. Es una instalación de Python aislada solo para este proyecto, así las librerías no se mezclan con las de otros proyectos.
3. Instala ahí las dos librerías que usa (`youtube-transcript-api` y `yt-dlp`), en las versiones exactas anotadas en `uv.lock`.

La carpeta `.venv/` **no se sube a GitHub** (está en `.gitignore`): cada PC crea la suya con `uv sync`.

**No hace falta "activar" el entorno.** Todos los comandos se corren con `uv run …`, que usa el `.venv` automáticamente. Los `.bat` también lo hacen.

<details>
<summary>Si preferís activarlo a mano (opcional)</summary>

```powershell
.venv\Scripts\Activate.ps1
python transcribir_youtube.py --help
deactivate
```

Si PowerShell dice que la ejecución de scripts está deshabilitada, corré una vez:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
</details>

<details>
<summary>Sin uv, con Python y pip clásicos</summary>

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Y en los ejemplos de abajo reemplazás `uv run` por `python`.
</details>

---

## Uso

### Interfaz web (lo más cómodo)

Doble clic en **`abrir_web.bat`**, o en la terminal:

```powershell
uv run app_web.py
```

Se abre el navegador en http://127.0.0.1:8765. Ahí:

1. Pegás los links (uno por línea) o arrastrás un `.txt` con links.
2. Elegís formatos y opciones.
3. Tocás **Transcribir** y ves el avance en vivo.
4. Abajo aparecen las transcripciones guardadas: podés bajarlas una por una, en `.zip`, o abrir la carpeta.

La interfaz corre **solo en tu PC** (no se publica en internet). Para apagarla, cerrá la ventana negra de la consola.
Los links que pegaste quedan recordados en ese navegador para la próxima vez.

### Doble clic sin interfaz

**`transcribir.bat`**: la primera vez crea `links.txt` y lo abre en el Bloc de notas; pegás los links, guardás, y con el segundo doble clic transcribe todo.

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

#### Opciones

| Opción | Qué hace |
|---|---|
| `-f txt md srt json txt-tiempos` | Formatos de salida (por defecto `txt` y `md`) |
| `-i es,en` | Idiomas preferidos, en orden (por defecto español y luego inglés) |
| `-t es` | Si no hay subtítulos en esos idiomas, usa la traducción automática de YouTube al español |
| `--unir` | Además, junta las transcripciones de cada playlist en un solo archivo `_TODO - ….md` |
| `--solo-video` | Con un link `watch?v=…&list=…`, baja solo ese video y no la playlist entera |
| `--solo-manuales` | Ignora los subtítulos automáticos |
| `-o carpeta` | Carpeta de salida (por defecto `transcripciones`) |
| `--pausa 3` | Segundos entre videos (subilo si YouTube bloquea) |
| `--sobrescribir` | Vuelve a bajar aunque el archivo ya exista |
| `--proxy URL` | Usa un proxy (solo si YouTube te bloquea seguido) |

`uv run transcribir_youtube.py --help` las muestra todas.

### Formatos

- **txt**: texto corrido, en párrafos de ~1 minuto.
- **md**: título, link, idioma y párrafos con marca de tiempo clickeable (abre el video en ese minuto).
- **txt-tiempos**: una línea por fragmento con `[hh:mm:ss]`.
- **srt**: subtítulos estándar (VLC, editores de video, etc.).
- **json**: datos crudos, para procesar con código.

### Qué genera

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

Si volvés a correr con los mismos links, **saltea los videos que ya están**; así podés retomar una playlist larga si se cortó.

La carpeta `transcripciones/` queda en cada PC y no se sube a GitHub.

---

## Usarlo desde otra PC / mantenerlo actualizado

En una PC nueva: pasos 1 a 3 de la instalación.

En una PC donde ya está instalado, antes de usarlo:

```powershell
cd $HOME\Documents\youtube-transcripts
git pull
uv sync
```

`git pull` trae los cambios del código y `uv sync` ajusta el entorno virtual si cambiaron las dependencias.

Si una playlist deja de leerse con el tiempo (YouTube cambia seguido), actualizá las librerías: `uv sync --upgrade`.

---

## Problemas comunes

- **"subtítulos desactivados"**: el video no tiene transcripción. Para esos casos sirve transcribir el audio con Whisper.
- **"no hay transcripción en es, en…"**: activá *traducir a es* (o `-t es` en la terminal).
- **"YouTube bloqueó las consultas desde tu IP"**: pasa con muchas consultas seguidas. Esperá un rato y corré de nuevo con una pausa mayor (retoma donde quedó).
- **Una playlist no se lee**: tiene que ser pública o "no listada".
- **`uv` no se reconoce como comando**: cerrá y abrí PowerShell después de instalarlo.
- **El puerto 8765 está ocupado**: `uv run app_web.py --puerto 8800`.

## Tests

```powershell
uv run python -m unittest discover tests
```

Funcionan sin internet (simulan YouTube).

## Credenciales

No usa tokens ni claves. Si algún día usás `--proxy` con usuario y contraseña, no lo guardes en el repo.

## Estructura

| Archivo | Para qué |
|---|---|
| `transcribir_youtube.py` | El extractor (se puede usar solo, desde la terminal) |
| `app_web.py` + `web/index.html` | La interfaz web |
| `abrir_web.bat` / `transcribir.bat` | Accesos de doble clic para Windows |
| `links.ejemplo.txt` | Modelo de lista de links |
| `pyproject.toml` + `uv.lock` | Dependencias y versiones exactas |
| `requirements.txt` | Lo mismo, para quien use pip |
| `tests/` | Pruebas automáticas |
