#!/usr/bin/env python3
"""
Interfaz web local para transcribir_youtube.py.

    uv run app_web.py          → abre http://127.0.0.1:8765 en el navegador

Corre solo en tu PC (no se publica en internet). No necesita dependencias extra.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import threading
import uuid
import webbrowser
import zipfile
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import transcribir_youtube as ty

BASE = Path(__file__).resolve().parent
HTML = (BASE / "web" / "index.html").read_text(encoding="utf-8")
SALIDA = BASE / "transcripciones"

TRABAJOS: dict[str, dict] = {}
CANDADO = threading.Lock()   # un trabajo por vez, para no hacer enojar a YouTube


class LogEnVivo(io.TextIOBase):
    """Recibe lo que imprime el extractor y lo guarda en la lista del trabajo."""

    def __init__(self, trabajo: dict):
        self.trabajo, self.buffer_linea = trabajo, ""

    def write(self, s: str) -> int:
        self.buffer_linea += s
        while "\n" in self.buffer_linea:
            linea, self.buffer_linea = self.buffer_linea.split("\n", 1)
            self.trabajo["log"].append(linea)
        return len(s)


def correr_trabajo(tid: str, argv: list[str]) -> None:
    t = TRABAJOS[tid]
    try:
        args = ty.construir_parser().parse_args(argv)
        with CANDADO, redirect_stdout(LogEnVivo(t)):
            t["codigo"] = ty.procesar(args)
    except SystemExit as e:
        t["log"].append(f"✗ {e}")
        t["codigo"] = 2
    except Exception as e:
        t["log"].append(f"✗ Error inesperado: {type(e).__name__}: {e}")
        t["codigo"] = 1
    finally:
        t["terminado"] = True


def armar_argv(datos: dict) -> list[str]:
    argv = ["-o", str(SALIDA)]
    formatos = [f for f in datos.get("formatos", []) if f in ty.FORMATOS] or ["txt", "md"]
    argv += ["-f", *formatos]
    if datos.get("idiomas"):
        argv += ["-i", str(datos["idiomas"])]
    if datos.get("traducir"):
        argv += ["-t", str(datos["traducir"])]
    try:
        argv += ["--pausa", str(max(0.0, float(datos.get("pausa", 1.5))))]
    except ValueError:
        pass
    for clave, flag in [("unir", "--unir"), ("solo_video", "--solo-video"),
                        ("solo_manuales", "--solo-manuales"), ("sobrescribir", "--sobrescribir")]:
        if datos.get(clave):
            argv.append(flag)
    links = []
    for linea in str(datos.get("links", "")).splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#"):
            links += [x for x in linea.replace(",", " ").replace(";", " ").split() if x]
    return argv + ["--", *links]   # "--": un ID que empieza con "-" no se confunde con una opción


def listar_archivos() -> list[dict]:
    if not SALIDA.exists():
        return []
    grupos = []
    for carpeta in sorted(p for p in SALIDA.iterdir() if p.is_dir()):
        archivos = sorted(carpeta.iterdir(), key=lambda p: p.name)
        grupos.append({
            "grupo": carpeta.name,
            "archivos": [{"nombre": a.name, "ruta": str(a.relative_to(SALIDA)), "kb": round(a.stat().st_size / 1024, 1)}
                         for a in archivos if a.is_file()],
        })
    return grupos


def ruta_segura(rel: str) -> Path | None:
    p = (SALIDA / rel).resolve()
    return p if SALIDA.resolve() in p.parents or p == SALIDA.resolve() else None


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silenciar el log de cada request en la consola
        pass

    def responder(self, codigo: int, cuerpo: bytes, tipo: str, extra: dict | None = None):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(cuerpo)

    def json(self, obj, codigo=200):
        self.responder(codigo, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/":
            return self.responder(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
        if u.path.startswith("/api/trabajos/"):
            t = TRABAJOS.get(u.path.rsplit("/", 1)[-1])
            if not t:
                return self.json({"error": "no existe"}, 404)
            desde = int(q.get("desde", ["0"])[0])
            return self.json({"log": t["log"][desde:], "total": len(t["log"]),
                              "terminado": t["terminado"], "codigo": t["codigo"]})
        if u.path == "/api/archivos":
            return self.json(listar_archivos())
        if u.path == "/descargar":
            p = ruta_segura(q.get("ruta", [""])[0])
            if not p or not p.is_file():
                return self.json({"error": "archivo no encontrado"}, 404)
            nombre = p.name.encode("ascii", "ignore").decode() or "archivo"
            return self.responder(200, p.read_bytes(), "application/octet-stream", {
                "Content-Disposition": f"attachment; filename=\"{nombre}\"; filename*=UTF-8''{_quote(p.name)}"})
        if u.path == "/zip":
            p = ruta_segura(q.get("grupo", [""])[0])
            if not p or not p.is_dir():
                return self.json({"error": "carpeta no encontrada"}, 404)
            mem = io.BytesIO()
            with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
                for a in p.iterdir():
                    if a.is_file():
                        z.write(a, a.name)
            return self.responder(200, mem.getvalue(), "application/zip", {
                "Content-Disposition": f"attachment; filename=\"transcripciones.zip\"; filename*=UTF-8''{_quote(p.name)}.zip"})
        self.json({"error": "no encontrado"}, 404)

    def do_POST(self):
        largo = int(self.headers.get("Content-Length", 0))
        datos = json.loads(self.rfile.read(largo) or b"{}")
        if self.path == "/api/trabajos":
            argv = armar_argv(datos)
            if argv[-1] == "--":
                return self.json({"error": "Pegá al menos un link."}, 400)
            if CANDADO.locked():
                return self.json({"error": "Ya hay una transcripción en curso. Esperá a que termine."}, 409)
            tid = uuid.uuid4().hex[:8]
            TRABAJOS[tid] = {"log": [], "terminado": False, "codigo": None}
            threading.Thread(target=correr_trabajo, args=(tid, argv), daemon=True).start()
            return self.json({"id": tid})
        if self.path == "/api/abrir-carpeta":
            SALIDA.mkdir(exist_ok=True)
            destino = ruta_segura(datos.get("grupo", "")) or SALIDA
            abrir_en_explorador(destino)
            return self.json({"ok": True})
        self.json({"error": "no encontrado"}, 404)


def _quote(s: str) -> str:
    from urllib.parse import quote
    return quote(s)


def abrir_en_explorador(p: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(p)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Interfaz web del extractor de transcripciones")
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--no-abrir", action="store_true", help="no abrir el navegador automáticamente")
    a = ap.parse_args()
    servidor = ThreadingHTTPServer(("127.0.0.1", a.puerto), Manejador)
    url = f"http://127.0.0.1:{a.puerto}"
    print(f"🌐 Interfaz web en {url}   (cerrá esta ventana o Ctrl+C para apagarla)")
    if not a.no_abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nChau 👋")


if __name__ == "__main__":
    main()
