"""Tests sin internet: parseo de links, formatos y flujo completo con YouTube simulado.
Correr con:  python -m unittest discover tests
"""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import transcribir_youtube as ty  # noqa: E402
from youtube_transcript_api import NoTranscriptFound  # noqa: E402


def snip(start, dur, text):
    return SimpleNamespace(start=start, duration=dur, text=text)


SNIPPETS = [snip(i * 5.0, 5.0, f"frase número {i}.") for i in range(30)]


class TestLinks(unittest.TestCase):
    def test_ids(self):
        casos = {
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ": "dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ?si=abc": "dQw4w9WgXcQ",
            "youtube.com/shorts/dQw4w9WgXcQ": "dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=30s": "dQw4w9WgXcQ",
            "https://www.youtube.com/embed/dQw4w9WgXcQ": "dQw4w9WgXcQ",
            "https://www.youtube.com/live/dQw4w9WgXcQ": "dQw4w9WgXcQ",
            "dQw4w9WgXcQ": "dQw4w9WgXcQ",
            "https://www.youtube.com/playlist?list=PL123": None,
            "https://google.com": None,
        }
        for link, esperado in casos.items():
            self.assertEqual(ty.extraer_video_id(link), esperado, link)

    def test_playlist(self):
        self.assertEqual(ty.extraer_playlist_id("https://www.youtube.com/playlist?list=PLabc"), "PLabc")
        self.assertEqual(ty.extraer_playlist_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLabc"), "PLabc")
        self.assertIsNone(ty.extraer_playlist_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=RDdQw4w9WgXcQ"))
        self.assertIsNone(ty.extraer_playlist_id("https://youtu.be/dQw4w9WgXcQ"))

    def test_archivo_links(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "links.txt"
            p.write_text("# comentario\nhttps://youtu.be/dQw4w9WgXcQ\n\nabcdefghijk, https://youtu.be/AAAAAAAAAAA\n",
                         encoding="utf-8")
            self.assertEqual(ty.leer_archivo_links(p),
                             ["https://youtu.be/dQw4w9WgXcQ", "abcdefghijk", "https://youtu.be/AAAAAAAAAAA"])

    def test_resolver_sin_duplicados_y_solo_video(self):
        with mock.patch.object(ty, "expandir_playlist",
                               return_value=("Mi lista", [ty.Video("AAAAAAAAAAA", "a", "Mi lista", 1),
                                                          ty.Video("dQw4w9WgXcQ", "b", "Mi lista", 2)])):
            vs = ty.resolver_fuentes(["dQw4w9WgXcQ", "https://www.youtube.com/playlist?list=PLx"], False, "videos")
            self.assertEqual([v.video_id for v in vs], ["dQw4w9WgXcQ", "AAAAAAAAAAA"])
            vs = ty.resolver_fuentes(["https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLx"], True, "videos")
            self.assertEqual([(v.video_id, v.grupo) for v in vs], [("dQw4w9WgXcQ", "videos")])


class TestFormatos(unittest.TestCase):
    v = ty.Video("dQw4w9WgXcQ", 'Clase 1: "Intro" / IA?', "videos")

    def test_ts(self):
        self.assertEqual(ty.ts(3725.5), "01:02:05")
        self.assertEqual(ty.ts(3725.5, srt=True), "01:02:05,500")

    def test_srt(self):
        out = ty.a_srt(SNIPPETS[:2])
        self.assertIn("1\n00:00:00,000 --> 00:00:05,000\nfrase número 0.", out)
        self.assertIn("2\n00:00:05,000 --> 00:00:10,000", out)

    def test_txt_parrafos(self):
        out = ty.a_txt(SNIPPETS)
        self.assertGreater(out.count("\n\n"), 1)        # se agrupó en varios párrafos
        self.assertIn("frase número 29.", out)

    def test_md(self):
        out = ty.a_md(SNIPPETS, video=self.v, idioma="es", generada=True)
        self.assertTrue(out.startswith('# Clase 1: "Intro" / IA?'))
        self.assertIn("(automática)", out)
        self.assertIn("https://youtu.be/dQw4w9WgXcQ?t=0", out)

    def test_nombre_seguro_windows(self):
        self.assertEqual(ty.base_archivo(self.v), "Clase 1 Intro IA [dQw4w9WgXcQ]")


class FakeTranscript:
    def __init__(self, code, generated, translatable=True):
        self.language_code, self.is_generated, self.is_translatable = code, generated, translatable

    def fetch(self):
        return SimpleNamespace(snippets=SNIPPETS)

    def translate(self, code):
        return FakeTranscript(code, self.is_generated)


class FakeList(list):
    def find_manually_created_transcript(self, langs):
        for t in self:
            if not t.is_generated and t.language_code in langs:
                return t
        raise NoTranscriptFound("x", langs, self)

    def find_generated_transcript(self, langs):
        for t in self:
            if t.is_generated and t.language_code in langs:
                return t
        raise NoTranscriptFound("x", langs, self)


class TestFlujo(unittest.TestCase):
    def test_prioridades(self):
        api = mock.Mock()
        api.list.return_value = FakeList([FakeTranscript("es", True), FakeTranscript("en", False)])
        _, idioma, gen = ty.obtener_transcripcion(api, "x", ["es", "en"], None, False)
        self.assertEqual((idioma, gen), ("en", False))  # manual en idioma pedido gana a automática
        _, idioma, _ = ty.obtener_transcripcion(api, "x", ["es"], None, False)
        self.assertEqual(idioma, "es")
        api.list.return_value = FakeList([FakeTranscript("fr", False)])
        _, idioma, _ = ty.obtener_transcripcion(api, "x", ["es"], "es", False)
        self.assertEqual(idioma, "es (traducida de fr)")

    def test_cli_completo(self):
        api = mock.Mock()
        api.list.return_value = FakeList([FakeTranscript("es", True)])
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(ty, "crear_api", return_value=api), \
                mock.patch.object(ty, "obtener_titulo", return_value="Video de prueba"), \
                mock.patch.object(ty, "expandir_playlist",
                                  return_value=("Curso X", [ty.Video("AAAAAAAAAAA", "Uno", "Curso X", 1),
                                                            ty.Video("BBBBBBBBBBB", "Dos", "Curso X", 2)])):
            rc = ty.main(["dQw4w9WgXcQ", "https://www.youtube.com/playlist?list=PLx",
                          "-o", d, "-f", "txt", "md", "srt", "--unir", "--pausa", "0"])
            self.assertEqual(rc, 0)
            archivos = sorted(str(p.relative_to(d)) for p in Path(d).rglob("*") if p.is_file())
            self.assertIn("videos/Video de prueba [dQw4w9WgXcQ].md", archivos)
            self.assertIn("Curso X/001 - Uno [AAAAAAAAAAA].srt", archivos)
            self.assertIn("Curso X/_TODO - Curso X.md", archivos)
            self.assertIn("resumen.csv", archivos)
            # segunda corrida: saltea lo ya bajado
            api.list.reset_mock()
            ty.main(["dQw4w9WgXcQ", "-o", d, "-f", "txt", "md", "srt", "--pausa", "0"])
            api.list.assert_not_called()


if __name__ == "__main__":
    unittest.main()
