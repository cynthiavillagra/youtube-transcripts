#!/usr/bin/env python3
"""
Extractor de transcripciones de YouTube.

Acepta, en cualquier combinación:
  - uno o varios links (o IDs) de videos
  - links de playlists (se expanden a todos sus videos)
  - un archivo de texto con un link por línea (--lista)

Ejemplos:
  python transcribir_youtube.py https://youtu.be/dQw4w9WgXcQ
  python transcribir_youtube.py "https://www.youtube.com/playlist?list=PLxxxx"
  python transcribir_youtube.py --lista links.txt --formato txt md --unir
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api import (
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
        RequestBlocked,
        IpBlocked,
    )
except ImportError:  # pragma: no cover
    sys.exit("Falta instalar dependencias. Corré:  uv sync   (o  pip install -r requirements.txt)")

IDIOMAS_DEFAULT = ["es", "es-419", "es-ES", "es-AR", "es-MX", "en"]
FORMATOS = ["txt", "txt-tiempos", "srt", "md", "json"]
EXTENSION = {"txt": ".txt", "txt-tiempos": ".tiempos.txt", "srt": ".srt", "md": ".md", "json": ".json"}

ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


# --------------------------------------------------------------------------- #
#  Modelos
# --------------------------------------------------------------------------- #
@dataclass
class Video:
    video_id: str
    titulo: str = ""
    grupo: str = "videos"          # carpeta de salida (nombre de la playlist o "videos")
    posicion: int | None = None    # orden dentro de la playlist

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


@dataclass
class Resultado:
    video: Video
    ok: bool
    idioma: str = ""
    generada: bool | None = None
    archivos: list[str] = field(default_factory=list)
    error: str = ""


# --------------------------------------------------------------------------- #
#  Parseo de links
# --------------------------------------------------------------------------- #
def extraer_video_id(texto: str) -> str | None:
    """Devuelve el ID de 11 caracteres de un link de YouTube (o del ID suelto)."""
    texto = texto.strip()
    if ID_RE.match(texto):
        return texto
    try:
        u = urllib.parse.urlparse(texto if "://" in texto else "https://" + texto)
    except ValueError:
        return None
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        cand = u.path.lstrip("/").split("/")[0]
        return cand if ID_RE.match(cand) else None
    if host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
        qs = urllib.parse.parse_qs(u.query)
        if "v" in qs and ID_RE.match(qs["v"][0]):
            return qs["v"][0]
        partes = [p for p in u.path.split("/") if p]
        if len(partes) >= 2 and partes[0] in {"shorts", "embed", "live", "v", "e"}:
            return partes[1] if ID_RE.match(partes[1]) else None
    return None


def extraer_playlist_id(texto: str) -> str | None:
    """Devuelve el ID de playlist si el link tiene ?list=..., salvo los 'Mix' automáticos."""
    try:
        u = urllib.parse.urlparse(texto.strip() if "://" in texto else "https://" + texto.strip())
    except ValueError:
        return None
    lista = urllib.parse.parse_qs(u.query).get("list", [None])[0]
    # Las listas RD... son "Mix" generados por YouTube (infinitos): no se expanden.
    if lista and not lista.startswith("RD"):
        return lista
    return None


def leer_archivo_links(ruta: Path) -> list[str]:
    """Lee un .txt con un link por línea. Ignora líneas vacías y las que empiezan con #."""
    links = []
    for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#"):
            # permite varios links separados por espacios o comas en la misma línea
            links.extend(x for x in re.split(r"[\s,;]+", linea) if x)
    return links


# --------------------------------------------------------------------------- #
#  Metadatos (títulos y playlists)
# --------------------------------------------------------------------------- #
def expandir_playlist(playlist_id: str) -> tuple[str, list[Video]]:
    """Usa yt-dlp (sin descargar nada) para listar los videos de una playlist."""
    try:
        import yt_dlp
    except ImportError:
        sys.exit("Para playlists hace falta yt-dlp. Corré:  uv sync   (o  pip install yt-dlp)")
    opciones = {"extract_flat": "in_playlist", "quiet": True, "skip_download": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(opciones) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/playlist?list={playlist_id}", download=False)
    nombre = info.get("title") or playlist_id
    videos = []
    for i, e in enumerate(info.get("entries") or [], start=1):
        if not e or not e.get("id"):
            continue
        titulo = e.get("title") or ""
        if titulo in {"[Private video]", "[Deleted video]"}:
            continue
        videos.append(Video(e["id"], titulo, grupo=nombre, posicion=i))
    return nombre, videos


def obtener_titulo(video_id: str) -> str:
    """Título vía oEmbed (rápido, sin API key). Si falla, devuelve ''."""
    url = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(
        f"https://www.youtube.com/watch?v={video_id}", safe=""
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode("utf-8")).get("title", "")
    except Exception:
        return ""


def resolver_fuentes(fuentes: list[str], solo_video: bool, nombre_grupo: str) -> list[Video]:
    """Convierte la mezcla de links/IDs/playlists en una lista de Video sin duplicados."""
    videos: list[Video] = []
    vistos: set[str] = set()
    for f in fuentes:
        vid = extraer_video_id(f)
        pl = extraer_playlist_id(f)
        if pl and not (solo_video and vid):
            print(f"📃 Leyendo playlist {pl} ...")
            try:
                nombre, lista = expandir_playlist(pl)
            except Exception as e:
                print(f"   ✗ No se pudo leer la playlist: {e}")
                continue
            print(f"   → «{nombre}»: {len(lista)} videos")
            for v in lista:
                if v.video_id not in vistos:
                    vistos.add(v.video_id)
                    videos.append(v)
        elif vid:
            if vid not in vistos:
                vistos.add(vid)
                videos.append(Video(vid, grupo=nombre_grupo))
        else:
            print(f"⚠ No reconozco esto como link de YouTube, lo salteo: {f}")
    return videos


# --------------------------------------------------------------------------- #
#  Transcripción
# --------------------------------------------------------------------------- #
def crear_api(proxy: str | None) -> YouTubeTranscriptApi:
    if proxy:
        from youtube_transcript_api.proxies import GenericProxyConfig
        return YouTubeTranscriptApi(proxy_config=GenericProxyConfig(http_url=proxy, https_url=proxy))
    return YouTubeTranscriptApi()


def obtener_transcripcion(api, video_id: str, idiomas: list[str], traducir: str | None,
                          solo_manuales: bool):
    """
    Devuelve (snippets, codigo_idioma, es_generada).
    Prioridad: manual en idiomas pedidos > automática en idiomas pedidos >
               traducción al idioma de --traducir > cualquier otra disponible.
    """
    lista = api.list(video_id)
    t = None
    try:
        t = lista.find_manually_created_transcript(idiomas)
    except NoTranscriptFound:
        if not solo_manuales:
            try:
                t = lista.find_generated_transcript(idiomas)
            except NoTranscriptFound:
                pass
    if t is None:
        disponibles = [x for x in lista if not (solo_manuales and x.is_generated)]
        if not disponibles:
            raise NoTranscriptFound(video_id, idiomas, lista)
        base = sorted(disponibles, key=lambda x: x.is_generated)[0]  # manuales primero
        if traducir and base.is_translatable and base.language_code != traducir:
            datos = base.translate(traducir).fetch()
            return datos.snippets, f"{traducir} (traducida de {base.language_code})", base.is_generated
        t = base
    datos = t.fetch()
    return datos.snippets, t.language_code, t.is_generated


# --------------------------------------------------------------------------- #
#  Formatos de salida
# --------------------------------------------------------------------------- #
def ts(segundos: float, srt: bool = False) -> str:
    total_ms = int(round(segundos * 1000))
    h, resto = divmod(total_ms, 3_600_000)
    m, resto = divmod(resto, 60_000)
    s, ms = divmod(resto, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}" if srt else f"{h:02d}:{m:02d}:{s:02d}"


def limpiar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto.replace("\n", " ")).strip()


def agrupar_parrafos(snippets, segundos: float = 60.0):
    """Agrupa fragmentos en párrafos de ~N segundos. Devuelve [(inicio, texto)]."""
    parrafos, actual, inicio = [], [], None
    for s in snippets:
        txt = limpiar(s.text)
        if not txt or txt in {"[Música]", "[Music]", "[Aplausos]", "[Applause]"}:
            continue
        if inicio is None:
            inicio = s.start
        actual.append(txt)
        if s.start + s.duration - inicio >= segundos and txt[-1:] in ".?!…" or \
           s.start + s.duration - inicio >= segundos * 1.5:
            parrafos.append((inicio, " ".join(actual)))
            actual, inicio = [], None
    if actual:
        parrafos.append((inicio, " ".join(actual)))
    return parrafos


def a_txt(snippets, **_) -> str:
    return "\n\n".join(t for _, t in agrupar_parrafos(snippets)) + "\n"


def a_txt_tiempos(snippets, **_) -> str:
    return "\n".join(f"[{ts(s.start)}] {limpiar(s.text)}" for s in snippets if limpiar(s.text)) + "\n"


def a_srt(snippets, **_) -> str:
    bloques = []
    n = 0
    for s in snippets:
        txt = s.text.strip()
        if not txt:
            continue
        n += 1
        bloques.append(f"{n}\n{ts(s.start, True)} --> {ts(s.start + s.duration, True)}\n{txt}\n")
    return "\n".join(bloques)


def a_md(snippets, video: Video, idioma: str, generada: bool | None, **_) -> str:
    tipo = "automática" if generada else "manual"
    cab = [
        f"# {video.titulo or video.video_id}",
        "",
        f"- **Link:** {video.url}",
        f"- **Idioma:** {idioma} ({tipo})",
    ]
    if video.grupo != "videos":
        cab.append(f"- **Playlist:** {video.grupo}" + (f" (video {video.posicion})" if video.posicion else ""))
    cab += ["", "---", ""]
    cuerpo = []
    for inicio, texto in agrupar_parrafos(snippets):
        seg = int(inicio)
        cuerpo.append(f"**[{ts(inicio)}](https://youtu.be/{video.video_id}?t={seg})** {texto}\n")
    return "\n".join(cab) + "\n".join(cuerpo)


def a_json(snippets, video: Video, idioma: str, generada: bool | None, **_) -> str:
    return json.dumps({
        "video_id": video.video_id,
        "titulo": video.titulo,
        "url": video.url,
        "playlist": None if video.grupo == "videos" else video.grupo,
        "posicion": video.posicion,
        "idioma": idioma,
        "generada_automaticamente": generada,
        "fragmentos": [{"inicio": s.start, "duracion": s.duration, "texto": s.text} for s in snippets],
    }, ensure_ascii=False, indent=2)


CONVERSORES = {"txt": a_txt, "txt-tiempos": a_txt_tiempos, "srt": a_srt, "md": a_md, "json": a_json}


def nombre_seguro(texto: str, maximo: int = 90) -> str:
    texto = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", texto)   # caracteres prohibidos en Windows
    texto = re.sub(r"\s+", " ", texto).strip(" .")
    return texto[:maximo].rstrip(" .") or "sin-titulo"


def base_archivo(video: Video) -> str:
    pref = f"{video.posicion:03d} - " if video.posicion else ""
    return f"{pref}{nombre_seguro(video.titulo or video.video_id)} [{video.video_id}]"


# --------------------------------------------------------------------------- #
#  Programa principal
# --------------------------------------------------------------------------- #
def procesar(args) -> int:
    fuentes = list(args.links)
    for ruta in args.lista or []:
        p = Path(ruta)
        if not p.exists():
            print(f"✗ No encuentro el archivo {p}")
            return 2
        fuentes += leer_archivo_links(p)
    if not fuentes:
        print("No pasaste ningún link. Mirá  python transcribir_youtube.py --help")
        return 2

    videos = resolver_fuentes(fuentes, args.solo_video, args.carpeta_grupo)
    if not videos:
        print("No quedó ningún video para procesar.")
        return 1

    salida = Path(args.salida)
    api = crear_api(args.proxy)
    idiomas = [x.strip() for x in args.idiomas.split(",") if x.strip()]
    formatos = args.formato
    resultados: list[Resultado] = []

    print(f"\n🎬 {len(videos)} video(s) para transcribir → {salida.resolve()}\n")
    for i, v in enumerate(videos, start=1):
        if not v.titulo:
            v.titulo = obtener_titulo(v.video_id)
        carpeta = salida / nombre_seguro(v.grupo)
        base = base_archivo(v)
        destinos = {f: carpeta / (base + EXTENSION[f]) for f in formatos}
        etiqueta = f"[{i}/{len(videos)}] {v.titulo or v.video_id}"

        if not args.sobrescribir and all(d.exists() for d in destinos.values()):
            print(f"{etiqueta}  ↷ ya existe, lo salteo")
            resultados.append(Resultado(v, True, archivos=[str(d) for d in destinos.values()], error="ya existía"))
            continue

        try:
            snippets, idioma, generada = obtener_transcripcion(
                api, v.video_id, idiomas, args.traducir, args.solo_manuales)
            carpeta.mkdir(parents=True, exist_ok=True)
            for f, destino in destinos.items():
                destino.write_text(
                    CONVERSORES[f](snippets, video=v, idioma=idioma, generada=generada),
                    encoding="utf-8")
            tipo = "auto" if generada else "manual"
            print(f"{etiqueta}  ✓ {idioma} ({tipo})")
            resultados.append(Resultado(v, True, idioma, generada, [str(d) for d in destinos.values()]))
        except TranscriptsDisabled:
            print(f"{etiqueta}  ✗ el video tiene los subtítulos desactivados")
            resultados.append(Resultado(v, False, error="subtítulos desactivados"))
        except NoTranscriptFound:
            print(f"{etiqueta}  ✗ no hay transcripción en {', '.join(idiomas)} (probá --traducir es)")
            resultados.append(Resultado(v, False, error="sin transcripción en esos idiomas"))
        except VideoUnavailable:
            print(f"{etiqueta}  ✗ video no disponible (privado o borrado)")
            resultados.append(Resultado(v, False, error="video no disponible"))
        except (RequestBlocked, IpBlocked):
            print(f"{etiqueta}  ✗ YouTube bloqueó temporalmente las consultas desde tu IP.")
            print("     Esperá un rato, subí --pausa o usá --proxy. Corto acá.")
            resultados.append(Resultado(v, False, error="IP bloqueada por YouTube"))
            break
        except Exception as e:  # cualquier otro error: seguimos con el próximo
            print(f"{etiqueta}  ✗ error: {type(e).__name__}: {e}")
            resultados.append(Resultado(v, False, error=f"{type(e).__name__}: {e}"))

        if i < len(videos):
            time.sleep(args.pausa)

    if args.unir:
        unir_resultados(resultados, salida, formatos)
    guardar_resumen(resultados, salida)

    ok = sum(r.ok for r in resultados)
    print(f"\n✅ Listo: {ok} ok, {len(resultados) - ok} con problemas. Resumen en {salida / 'resumen.csv'}")
    return 0 if ok else 1


def unir_resultados(resultados: list[Resultado], salida: Path, formatos: list[str]) -> None:
    """Junta todas las transcripciones de cada grupo en un solo archivo (útil para NotebookLM)."""
    fmt = "md" if "md" in formatos else ("txt" if "txt" in formatos else None)
    if not fmt:
        print("ℹ --unir necesita el formato txt o md; lo salteo.")
        return
    por_grupo: dict[str, list[Resultado]] = {}
    for r in resultados:
        if r.ok:
            por_grupo.setdefault(r.video.grupo, []).append(r)
    for grupo, rs in por_grupo.items():
        partes = []
        for r in rs:
            archivo = next((a for a in r.archivos if a.endswith(EXTENSION[fmt]) and not a.endswith(".tiempos.txt")), None)
            if not archivo:
                continue
            contenido = Path(archivo).read_text(encoding="utf-8")
            if fmt == "txt":
                contenido = f"===== {r.video.titulo or r.video.video_id} =====\n{r.video.url}\n\n{contenido}"
            partes.append(contenido.strip())
        separador = "\n\n---\n\n" if fmt == "md" else "\n\n\n"
        destino = salida / nombre_seguro(grupo) / f"_TODO - {nombre_seguro(grupo)}{EXTENSION[fmt]}"
        destino.write_text(separador.join(partes) + "\n", encoding="utf-8")
        print(f"📚 Archivo unificado: {destino}")


def guardar_resumen(resultados: list[Resultado], salida: Path) -> None:
    salida.mkdir(parents=True, exist_ok=True)
    ruta = salida / "resumen.csv"
    nuevo = not ruta.exists()
    with ruta.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["fecha", "grupo", "posicion", "video_id", "titulo", "url", "ok", "idioma",
                        "automatica", "error"])
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
        for r in resultados:
            w.writerow([ahora, r.video.grupo, r.video.posicion or "", r.video.video_id, r.video.titulo,
                        r.video.url, "sí" if r.ok else "no", r.idioma,
                        "" if r.generada is None else ("sí" if r.generada else "no"), r.error])


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Extrae transcripciones de videos y playlists de YouTube.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Ejemplos:")[1] if "Ejemplos:" in __doc__ else "",
    )
    p.add_argument("links", nargs="*", help="links o IDs de videos y/o playlists")
    p.add_argument("-l", "--lista", action="append", metavar="ARCHIVO",
                   help="archivo .txt con un link por línea (se puede repetir)")
    p.add_argument("-f", "--formato", nargs="+", choices=FORMATOS, default=["txt", "md"],
                   help="formatos de salida (default: txt md)")
    p.add_argument("-i", "--idiomas", default=",".join(IDIOMAS_DEFAULT),
                   help="idiomas preferidos en orden, separados por coma (default: %(default)s)")
    p.add_argument("-t", "--traducir", metavar="IDIOMA",
                   help="si no hay en los idiomas pedidos, traducir a este idioma (ej: es)")
    p.add_argument("-o", "--salida", default="transcripciones", help="carpeta de salida (default: %(default)s)")
    p.add_argument("--carpeta-grupo", default="videos",
                   help="subcarpeta para videos sueltos (default: %(default)s)")
    p.add_argument("--unir", action="store_true",
                   help="además, junta todo en un solo archivo por playlist/grupo")
    p.add_argument("--solo-video", action="store_true",
                   help="si el link es watch?v=...&list=..., bajar solo ese video y no toda la playlist")
    p.add_argument("--solo-manuales", action="store_true",
                   help="ignorar subtítulos generados automáticamente")
    p.add_argument("--sobrescribir", action="store_true", help="volver a bajar aunque el archivo ya exista")
    p.add_argument("--pausa", type=float, default=1.5,
                   help="segundos de espera entre videos, para que YouTube no bloquee (default: %(default)s)")
    p.add_argument("--proxy", help="proxy http(s)://usuario:clave@host:puerto (opcional)")
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # emojis en la consola de Windows
    args = construir_parser().parse_args(argv)
    return procesar(args)


if __name__ == "__main__":
    sys.exit(main())
