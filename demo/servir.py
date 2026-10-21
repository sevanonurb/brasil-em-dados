"""Serve demo/dist locally the way GitHub Pages does — including HTTP Range, which PMTiles needs
(python -m http.server has no Range support, and the map stays empty with it).

    python3 demo/servir.py 8392   →   http://127.0.0.1:8392/brasil-em-dados/
"""
import http.server, os, re, sys, tempfile

class Handler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        faixa = self.headers.get("Range")
        caminho = self.translate_path(self.path)
        if not faixa or not os.path.isfile(caminho):
            return super().send_head()
        m = re.match(r"bytes=(\d+)-(\d*)", faixa)
        tamanho = os.path.getsize(caminho)
        ini = int(m.group(1))
        fim = min(int(m.group(2)) if m.group(2) else tamanho - 1, tamanho - 1)
        f = open(caminho, "rb")
        f.seek(ini)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(caminho))
        self.send_header("Content-Range", f"bytes {ini}-{fim}/{tamanho}")
        self.send_header("Content-Length", str(fim - ini + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self._restante = fim - ini + 1
        return f

    def copyfile(self, origem, destino):
        n = getattr(self, "_restante", None)
        if n is None:
            return super().copyfile(origem, destino)
        destino.write(origem.read(n))
        self._restante = None

if __name__ == "__main__":
    raiz = tempfile.mkdtemp()
    os.symlink(os.path.abspath(os.path.join(os.path.dirname(__file__), "dist")), os.path.join(raiz, "brasil-em-dados"))
    os.chdir(raiz)
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8392
    print(f"http://127.0.0.1:{porta}/brasil-em-dados/")
    http.server.ThreadingHTTPServer(("127.0.0.1", porta), Handler).serve_forever()
