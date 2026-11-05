"""Prueba la interfaz web de punta a punta con YouTube simulado."""
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app_web  # noqa: E402
import transcribir_youtube as ty  # noqa: E402
from test_basico import FakeList, FakeTranscript  # noqa: E402


class TestWeb(unittest.TestCase):
    def test_flujo_web(self):
        api = mock.Mock()
        api.list.return_value = FakeList([FakeTranscript("es", False)])
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(app_web, "SALIDA", Path(d)), \
                mock.patch.object(ty, "crear_api", return_value=api), \
                mock.patch.object(ty, "obtener_titulo", return_value="Clase uno"):
            srv = ThreadingHTTPServer(("127.0.0.1", 0), app_web.Manejador)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{srv.server_port}"
            try:
                self.assertIn("Transcripciones de YouTube", urllib.request.urlopen(base).read().decode())
                req = urllib.request.Request(base + "/api/trabajos", method="POST", data=json.dumps({
                    "links": "https://youtu.be/dQw4w9WgXcQ\n# comentario\n-AbCdEfGhIj",
                    "formatos": ["txt", "md"], "unir": True, "pausa": 0}).encode())
                tid = json.load(urllib.request.urlopen(req))["id"]
                for _ in range(50):
                    e = json.load(urllib.request.urlopen(f"{base}/api/trabajos/{tid}"))
                    if e["terminado"]:
                        break
                    time.sleep(0.1)
                self.assertEqual(e["codigo"], 0, e["log"])
                grupos = json.load(urllib.request.urlopen(base + "/api/archivos"))
                nombres = [a["nombre"] for a in grupos[0]["archivos"]]
                self.assertIn("Clase uno [dQw4w9WgXcQ].md", nombres)
                self.assertIn("Clase uno [-AbCdEfGhIj].txt", nombres)   # ID que empieza con "-"
                ruta = urllib.request.quote(grupos[0]["archivos"][0]["ruta"])
                self.assertTrue(urllib.request.urlopen(f"{base}/descargar?ruta={ruta}").read())
                self.assertEqual(urllib.request.urlopen(f"{base}/zip?grupo=videos").read()[:2], b"PK")
                with self.assertRaises(urllib.error.HTTPError):   # no deja salir de la carpeta
                    urllib.request.urlopen(f"{base}/descargar?ruta=../../etc/passwd")
            finally:
                srv.shutdown()


if __name__ == "__main__":
    unittest.main()
