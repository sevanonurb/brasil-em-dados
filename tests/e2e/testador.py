"""End-to-end tester for the brasil_em_dados panel (live demo by default).

Every step has an ORACLE — an expected result that is checked — not just "no crash":

  1  load           console/page errors, failed requests, LCP/CLS, bytes
  2  discovery      every visible control; click each button, re-inventory, test what appeared (state exploration)
  3  exhaustive     all indicator x year pairs: right data file requested, legend changed, map coloured
  4  partitions     27 states + "all", 5 view levels, sex / race / cause filters
  5  boundaries     age-range slider ends; search with 1 char, accents, no match, very long, markup
  6  cross-oracle   hover/click features and compare the number shown with the data file
  7  accessibility  axe-core (WCAG 2.x A/AA tags)
  8  responsive     390x844 phone and 1920x1080: horizontal overflow, what is covered
  9  monkey         N random clicks/keys with a fixed seed, errors watched
 10  links          every external link answers

Each check ends as OK, FALHA (defect), or ACHADO (works, but a UX/content problem worth a human look).
Output: tests/e2e/relatorio/{relatorio.json, relatorio.html, shots/}.

    python3 tests/e2e/testador.py [URL] [--rapido]
"""
import io, json, math, random, re, sys, time, urllib.request
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

URL = next((a for a in sys.argv[1:] if a.startswith("http")), "https://sevanonurb.github.io/brasil-em-dados/")
RAPIDO = "--rapido" in sys.argv
SAIDA = Path(__file__).parent / "relatorio"
SHOTS = SAIDA / "shots"
GPU = ["--use-angle=vulkan", "--enable-features=Vulkan", "--ignore-gpu-blocklist"]
AXE = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
LIMIAR_COR = 0.03          # fração mínima de pixels coloridos para "o mapa pintou"

resultados = []


def registrar(etapa, tecnica, caso, esperado, obtido, estado, evidencia=None):
    resultados.append(dict(etapa=etapa, tecnica=tecnica, caso=caso, esperado=esperado,
                           obtido=obtido, estado=estado, evidencia=evidencia))
    marca = {"OK": "  ok ", "FALHA": "FALHA", "ACHADO": "ACHAD"}[estado]
    print(f"[{marca}] {etapa:>2} {caso[:70]:70} {obtido[:60] if isinstance(obtido, str) else obtido}", flush=True)


def numero(txt):
    """'595,6/100k' → 595.6 ; 'R$ 12.345' → 12345 ; '12,3%' → 12.3"""
    m = re.search(r"-?[\d.]+(?:,\d+)?", txt.replace("\u00a0", " "))
    if not m:
        return None, 0
    s = m.group(0)
    dec = len(s.split(",")[1]) if "," in s else 0
    return float(s.replace(".", "").replace(",", ".")), dec


class Sessao:
    def __init__(self, p, largura=1400, altura=850):
        self.b = p.chromium.launch(channel="chrome", headless=True, args=GPU)
        self.pg = self.b.new_page(viewport={"width": largura, "height": altura})
        self.erros, self.falhas, self.pedidos = [], [], []
        self.pg.on("console", lambda m: m.type == "error" and self.erros.append(f"{m.text[:160]} @ {(m.location or {}).get('url', '')[-60:]}"))
        self.pg.on("pageerror", lambda e: self.erros.append("pageerror: " + str(e)[:200]))
        # o mapa cancela tiles fora da vista ao se mover: ERR_ABORTED é rotina, não defeito
        self.pg.on("requestfailed", lambda r: None if "ERR_ABORTED" in (r.failure or "")
                   else self.falhas.append(f"{r.url[-80:]} {r.failure}"))
        self.pg.on("response", self._resp)
        self.pg.add_init_script("""
          window.__lcp=0; window.__cls=0;
          new PerformanceObserver(l=>{for(const e of l.getEntries()) window.__lcp=e.startTime}).observe({type:'largest-contentful-paint',buffered:true});
          new PerformanceObserver(l=>{for(const e of l.getEntries()) if(!e.hadRecentInput) window.__cls+=e.value}).observe({type:'layout-shift',buffered:true});
        """)

    def _resp(self, r):
        self.pedidos.append(r.url)
        if r.status >= 400:
            self.falhas.append(f"{r.status} {r.url[-80:]}")

    def abrir(self):
        self.pg.goto(URL, wait_until="networkidle")
        self.pg.wait_for_timeout(2500)

    def limpar(self):
        e, f = self.erros[:], self.falhas[:]
        self.erros.clear(); self.falhas.clear(); self.pedidos.clear()
        return e, f

    def foto(self, nome):
        caminho = SHOTS / f"{nome}.png"
        self.pg.screenshot(path=str(caminho))
        return str(caminho.relative_to(SAIDA))

    def fracao_colorida(self):
        """oráculo visual: fração de pixels saturados na área do mapa (sem os painéis)"""
        vw = self.pg.viewport_size
        img = Image.open(io.BytesIO(self.pg.screenshot())).convert("HSV")
        a = np.asarray(img)[:, : int(vw["width"] * 0.55)]
        return float(((a[..., 1] > 90) & (a[..., 2] > 60)).mean())

    def tom_dominante(self):
        """fração dos pixels coloridos do mapa que têm o mesmo tom (escala estourada → um tom só)"""
        vw = self.pg.viewport_size
        a = np.asarray(Image.open(io.BytesIO(self.pg.screenshot())).convert("HSV"))[:, : int(vw["width"] * 0.55)]
        cor = (a[..., 1] > 90) & (a[..., 2] > 60)
        if cor.sum() < 500:
            return 0.0
        hist = np.bincount((a[..., 0][cor] // 8).astype(int), minlength=32)
        return float(hist.max() / hist.sum())

    def quadro(self, mapa=False):
        img = Image.open(io.BytesIO(self.pg.screenshot())).convert("L")
        if mapa:                                   # só a área do mapa: sem painéis, que mudam sozinhos ao clicar
            img = img.crop((0, 0, int(img.width * 0.55), img.height))
        return np.asarray(img.resize((350, 212)), dtype=np.int16)

    @staticmethod
    def diferenca(a, b):
        """fração de pixels que mudaram de forma visível (> 12 níveis de cinza)"""
        return float((np.abs(a - b) > 12).mean())

    def texto(self, js):
        return self.pg.evaluate(js)

    def zoom(self):
        return self.texto("[...document.querySelectorAll('span')].map(s=>s.innerText).find(t=>/^zoom/.test(t))||''")

    def legenda(self):
        return self.texto("""(()=>{const c=[...document.querySelectorAll('div')].filter(d=>getComputedStyle(d).position==='absolute'
          && /maior risco|melhor|pior|↑|↓/.test(d.innerText||'') && d.innerText.length<160);return c.length?c[c.length-1].innerText.replace(/\\n/g,' | '):''})()""")

    def fechar(self):
        self.b.close()


def selecionar(s, indice_select, valor):
    s.pg.locator("select").nth(indice_select).select_option(valor)
    s.pg.wait_for_load_state("networkidle")
    s.pg.wait_for_timeout(900)


# ── etapas ─────────────────────────────────────────────────────────────────────────────────

def e1_carga(p):
    s = Sessao(p); t = time.time(); s.abrir(); dur = time.time() - t
    erros, falhas = s.limpar()
    lcp, cls = s.texto("window.__lcp"), s.texto("window.__cls")
    bytes_ = s.texto("performance.getEntriesByType('resource').reduce((a,r)=>a+(r.transferSize||0),0)")
    ev = s.foto("01-carga")
    registrar(1, "monitoramento", "abre sem erro de console", "0 erros, 0 pedidos falhos",
              f"{len(erros)} erros, {len(falhas)} falhas {erros[:1]}{falhas[:1]}", "OK" if not erros and not falhas else "FALHA", ev)
    registrar(1, "desempenho", "LCP (Core Web Vitals: bom ≤ 2,5 s)", "≤ 2500 ms", f"{lcp:.0f} ms", "OK" if lcp <= 2500 else "ACHADO")
    registrar(1, "desempenho", "CLS (bom ≤ 0,1)", "≤ 0.1", f"{cls:.3f}", "OK" if cls <= 0.1 else "ACHADO")
    registrar(1, "desempenho", "bytes na primeira carga", "informativo", f"{bytes_/1e6:.1f} MB em {dur:.1f} s", "OK")
    f = s.fracao_colorida()
    registrar(1, "visual", "mapa pinta na abertura", f"> {LIMIAR_COR:.0%} de pixels coloridos", f"{f:.1%}", "OK" if f > LIMIAR_COR else "FALHA", ev)
    s.fechar()


INVENTARIO_JS = """(()=>{window.__tid=window.__tid||0;const vis=e=>{const r=e.getBoundingClientRect(),c=getComputedStyle(e);return r.width>0&&r.height>0&&c.visibility!=='hidden'&&c.display!=='none'&&r.x<innerWidth&&r.y<innerHeight};
 const nome=e=>(e.getAttribute('aria-label')||e.title||e.innerText||e.placeholder||e.tagName).trim().replace(/\\s+/g,' ').slice(0,40);
 return [...document.querySelectorAll('button,select,input,a[href],[role=button],[tabindex]:not([tabindex="-1"])')].filter(vis).map(e=>{if(!e.dataset.tid)e.dataset.tid=++window.__tid;return e.tagName.toLowerCase()+':'+nome(e)+'#'+e.dataset.tid})})()"""


def _clicar_tid(s, tid):
    s.pg.locator(f"[data-tid='{tid}']").first.click(timeout=3000)


def e2_descoberta(p):
    s = Sessao(p); s.abrir(); s.limpar()
    base = s.texto(INVENTARIO_JS)
    registrar(2, "inventário", "controles visíveis na abertura", "lista", f"{len(base)} controles", "OK")
    botoes = [c for c in base if c.startswith("button:")]
    for i, item in enumerate(botoes):
        nome, tid = item.split(":", 1)[1].rsplit("#", 1)
        s.abrir(); s.limpar(); antes = {c.rsplit("#", 1)[0] for c in s.texto(INVENTARIO_JS)}
        q0 = s.quadro()
        # depois do reload os ids mudam: reencontra pelo nome
        alvo = next((c for c in s.texto(INVENTARIO_JS) if c.startswith("button:") and c.split(":", 1)[1].rsplit("#", 1)[0] == nome), None)
        if not alvo:
            registrar(2, "transição de estados", f"botão «{nome}»", "existe após recarregar", "sumiu", "ACHADO"); continue
        try:
            _clicar_tid(s, alvo.rsplit("#", 1)[1]); s.pg.wait_for_timeout(1500)
        except Exception as ex:
            registrar(2, "transição de estados", f"botão «{nome}»", "clicável", str(ex).splitlines()[0][:80], "FALHA"); continue
        depois_l = s.texto(INVENTARIO_JS); depois = {c.rsplit("#", 1)[0] for c in depois_l}
        novos = [c for c in depois_l if c.rsplit("#", 1)[0] not in antes]
        dif = s.diferenca(q0, s.quadro()); erros, _ = s.limpar(); ev = s.foto(f"02-botao-{i:02d}")
        reagiu = bool(novos or (antes - depois) or dif > 0.005)
        registrar(2, "transição de estados", f"botão «{nome}»", "reage visivelmente, 0 erros",
                  f"tela mudou {dif:.1%}; +{len(novos)} −{len(antes - depois)} controles; erros {len(erros)} {erros[:1]}",
                  "FALHA" if erros else ("OK" if reagiu else "ACHADO"), ev)
        for j, n in enumerate([c for c in novos if c.startswith(("button:", "select:", "input:"))][:15]):
            rot = n.split(":", 1)[1].rsplit("#", 1)[0]
            # estado limpo: recarrega, reabre o pai, reencontra o filho pelo nome (o anterior não contamina este)
            s.abrir(); pai = next(c for c in s.texto(INVENTARIO_JS) if c.startswith("button:") and c.split(":", 1)[1].rsplit("#", 1)[0] == nome)
            _clicar_tid(s, pai.rsplit("#", 1)[1]); s.pg.wait_for_timeout(1200); s.limpar()
            filho = next((c for c in s.texto(INVENTARIO_JS) if c.rsplit("#", 1)[0] == n.rsplit("#", 1)[0]), None)
            if not filho:
                registrar(2, "transição de estados", f"   └ em «{nome}»: «{rot}»", "reaparece ao reabrir", "não reapareceu", "ACHADO"); continue
            ntid = filho.rsplit("#", 1)[1]; q1 = s.quadro()
            try:
                el = s.pg.locator(f"[data-tid='{ntid}']").first
                if n.startswith("select:"):
                    opts = el.evaluate("e=>[...e.options].map(o=>o.value)"); el.select_option(opts[-1])
                elif n.startswith("input:"):
                    tipo = el.get_attribute("type") or "text"
                    el.check() if tipo in ("checkbox", "radio") else (el.fill("teste") if tipo == "text" else el.click())
                else:
                    el.click(timeout=3000)
                s.pg.wait_for_timeout(1000)
                er, _ = s.limpar(); d2 = s.diferenca(q1, s.quadro())
                registrar(2, "transição de estados", f"   └ em «{nome}»: «{rot}»", "reage, 0 erros", f"tela mudou {d2:.1%}; erros {len(er)} {er[:1]}",
                          "FALHA" if er else ("OK" if d2 > 0.002 else "ACHADO"), s.foto(f"02-botao-{i:02d}-{j:02d}"))
            except Exception as ex:
                registrar(2, "transição de estados", f"   └ em «{nome}»: «{rot}»", "clicável", str(ex).splitlines()[0][:80], "FALHA")
    s.fechar()


def e3_exaustivo(p):
    s = Sessao(p); s.abrir(); s.limpar()
    sel = s.pg.locator("select")
    metricas = sel.nth(0).evaluate("e=>[...e.options].map(o=>[o.value,o.text])")
    if RAPIDO:
        metricas = metricas[::12]
    anos_site = json.loads(urllib.request.urlopen(URL + "demo/anos.json").read())
    total, falhas = 0, 0
    for k, (m, rotulo) in enumerate(metricas):
        selecionar(s, 0, m)
        anos_ui = sel.nth(1).evaluate("e=>[...e.options].map(o=>o.value)")
        esperado_anos = [str(a) for a in anos_site.get(m, [])]
        if sorted(anos_ui) != sorted(esperado_anos):
            registrar(3, "domínio exaustivo", f"{rotulo}: anos no seletor", str(esperado_anos), str(anos_ui), "FALHA")
        leg0 = None
        for a in anos_ui:
            s.limpar(); selecionar(s, 1, a)
            pedido = any(f"/dados/{m}/{a}.json" in u for u in s.pedidos) or any(f"metrica={m}" in u and f"ano={a}" in u for u in s.pedidos)
            erros, fal = s.limpar()
            f = s.fracao_colorida(); leg = s.legenda(); leg0 = leg0 or leg; dom = s.tom_dominante()
            if dom > 0.85:
                registrar(3, "domínio exaustivo", f"{rotulo} · {a}: escala", "cores distribuídas", f"{dom:.0%} num tom só", "ACHADO", s.foto(f"03-sat-{m}-{a}"))
            ok = (not erros) and (not fal) and f > LIMIAR_COR and leg
            total += 1; falhas += 0 if ok else 1
            if not ok or a == anos_ui[0]:
                registrar(3, "domínio exaustivo", f"{rotulo} · {a}", "pedido certo, legenda, mapa colorido, 0 erros",
                          f"pedido={'sim' if pedido else 'não'} cor={f:.1%} legenda='{leg[:40]}' erros={len(erros)+len(fal)}",
                          "OK" if ok else "FALHA", s.foto(f"03-{m}-{a}"))
    registrar(3, "domínio exaustivo", "RESUMO indicador × ano", "todos OK", f"{total-falhas}/{total} OK", "OK" if not falhas else "FALHA")
    s.fechar()


def ausente(s, etapa, tecnica, caso, foto):
    """Controle que a página não oferece: aceitável só se ela disser por quê (aviso visível)."""
    aviso = s.pg.get_by_text(re.compile("só existem no painel completo|need the full stack")).count() > 0
    registrar(etapa, tecnica, caso, "oferecido, ou ausente com aviso visível",
              "não oferecido; aviso na tela" if aviso else "não oferecido e sem aviso", "OK" if aviso else "ACHADO", s.foto(foto))


def e4_particoes(p):
    s = Sessao(p); s.abrir(); s.limpar()
    ufs = s.pg.locator("select").nth(2).evaluate("e=>[...e.options].map(o=>[o.value,o.text])")
    q_todos = s.quadro(mapa=True)
    for v, t in ufs:
        z0 = s.zoom(); selecionar(s, 2, v); s.pg.wait_for_timeout(1500)
        try: s.pg.wait_for_load_state("networkidle", timeout=10000)
        except Exception: pass
        s.pg.wait_for_timeout(500)
        erros, fal = s.limpar(); f = s.fracao_colorida(); d = s.diferenca(q_todos, s.quadro(mapa=True))
        estado = "FALHA" if erros or f <= LIMIAR_COR else ("OK" if (d > 0.01 or not v) else "ACHADO")
        registrar(4, "partição (UF)", f"Estado: {t}", "o mapa destaca/aproxima o estado (tela muda), 0 erros",
                  f"tela mudou {d:.1%} vs 'todos'; cor={f:.1%}; zoom {z0}→{s.zoom()}" + (f"; erros {erros[:2]}" if erros else ""), estado, s.foto(f"04-uf-{v or 'todos'}"))
    selecionar(s, 2, ufs[0][0])
    for nivel in ["Auto", "Estadual", "Municipal", "Setores", "Endereços"]:
        botao = s.pg.locator("button").filter(has_text=nivel)
        if not botao.count(): ausente(s, 4, "partição (nível)", f"nível «{nivel}»", f"04-nivel-{nivel}"); continue
        s.limpar(); botao.first.click(); s.pg.wait_for_timeout(3500)
        erros, _ = s.limpar(); f = s.fracao_colorida()
        estado = "FALHA" if erros else ("OK" if f > LIMIAR_COR else "ACHADO")
        registrar(4, "partição (nível)", f"nível «{nivel}»", "mapa com conteúdo (ou aviso de indisponível)", f"cor={f:.1%} erros={len(erros)}",
                  estado, s.foto(f"04-nivel-{nivel}"))
    s.pg.locator("button").filter(has_text="Auto").first.click(); s.pg.wait_for_timeout(1500)
    ref = s.fracao_colorida(); q_ref = s.quadro(mapa=True)
    for grupo in [["Masculino", "Feminino", "Todos"], ["Branca", "Preta", "Parda", "Indígena", "Todas"]]:
        for b in grupo:
            botao = s.pg.locator("button").filter(has_text=re.compile(f"^{b}$"))
            if not botao.count(): ausente(s, 4, "partição (filtro)", f"filtro «{b}»", f"04-filtro-{b}"); continue
            s.limpar(); botao.first.click(); s.pg.wait_for_timeout(1500)
            erros, _ = s.limpar(); f = s.fracao_colorida(); mudou = s.diferenca(q_ref, s.quadro(mapa=True)) > 0.01
            estado = "FALHA" if erros else ("OK" if mudou or b in ("Todos", "Todas") else "ACHADO")
            registrar(4, "partição (filtro)", f"filtro «{b}»", "mapa muda, ou o controle avisa que não vale na demo",
                      f"cor={f:.1%} (ref {ref:.1%}) mudou={'sim' if mudou else 'não'}", estado, s.foto(f"04-filtro-{b}"))
    if s.pg.locator("select").count() < 4:
        ausente(s, 4, "partição (causa)", "seletor de causa (CID-10)", "04-causa-ausente"); s.fechar(); return
    causas = s.pg.locator("select").nth(3).evaluate("e=>[...e.options].map(o=>[o.value,o.text])")
    for v, t in causas[1:]:
        s.limpar(); selecionar(s, 3, v)
        dado_novo = any(("/dados/" in u) or ("cid10_capitulo=" in u and "/demo/" not in u) for u in s.pedidos)
        erros, _ = s.limpar(); f = s.fracao_colorida(); mudou = s.diferenca(q_ref, s.quadro(mapa=True)) > 0.01; dom = s.tom_dominante()
        if erros: estado, nota = "FALHA", f"erros {erros[:1]}"
        elif dom > 0.85: estado, nota = "FALHA", f"mapa saturado: {dom:.0%} dos pixels num tom só (escala não corresponde ao dado)"
        elif mudou and not dado_novo: estado, nota = "FALHA", "a tela mudou mas nenhum dado novo foi pedido: só a escala mudou"
        elif not mudou: estado, nota = "ACHADO", "filtro sem efeito"
        else: estado, nota = "OK", "dado novo e mapa mudou"
        registrar(4, "partição (causa)", f"causa «{t[:40]}»", "dado novo pedido e mapa coerente, ou aviso de indisponível",
                  f"{nota} · cor={f:.1%} tom dominante={dom:.0%}", estado, s.foto(f"04-causa-{v}"))
    s.fechar()


def e5_limites(p):
    s = Sessao(p); s.abrir(); s.limpar()
    for i, faixa in enumerate(s.pg.locator("input[type=range]").all()):
        mn, mx = faixa.get_attribute("min"), faixa.get_attribute("max")
        for alvo in (mn, mx):
            faixa.evaluate("(e,v)=>{const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;set.call(e,v);e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}))}", alvo)
            s.pg.wait_for_timeout(1200); erros, _ = s.limpar()
            registrar(5, "valor-limite", f"faixa etária #{i} no {'mínimo' if alvo == mn else 'máximo'} ({alvo})", "0 erros",
                      f"erros={len(erros)} {erros[:1]}", "FALHA" if erros else "OK", s.foto(f"05-faixa-{i}-{alvo}"))
    busca = s.pg.get_by_placeholder("Buscar município")
    casos = [("C", "1 letra: não lista"), ("Campinas", "acha Campinas/SP"), ("sao paulo", "sem acento acha São Paulo"),
             ("SÃO PAULO", "maiúsculas acha"), ("Xyzwq", "inexistente: lista vazia/aviso"), ("a" * 300, "texto enorme não quebra"),
             ("<img src=x onerror=alert(1)>", "marcação não executa")]
    for texto, esperado in casos:
        dialogo = []
        s.pg.once("dialog", lambda d: (dialogo.append(d.message), d.dismiss()))
        busca.fill(""); busca.fill(texto); s.pg.wait_for_timeout(700)
        lista = s.texto("(()=>{const i=document.querySelector('input[placeholder*=Buscar]');const c=i.closest('div').parentElement;return c.innerText.split('\\n').filter(t=>t&&t!=='🔍'&&t!=='×')})()")
        erros, _ = s.limpar()
        if texto == "C": ok = len(lista) == 0
        elif texto in ("Campinas",): ok = any(t.startswith("Campinas") for t in lista)
        elif texto.lower() == "sao paulo" or texto == "SÃO PAULO": ok = any("São Paulo" in t for t in lista)
        elif texto == "Xyzwq": ok = len(lista) <= 1
        else: ok = not dialogo and not erros
        registrar(5, "valor-limite (busca)", f"busca «{texto[:30]}»", esperado, f"{len(lista)} itens {lista[:3]} diálogo={bool(dialogo)} erros={len(erros)}",
                  "OK" if ok else ("FALHA" if dialogo or erros else "ACHADO"), s.foto(f"05-busca-{abs(hash(texto)) % 10**6}"))
    busca.fill("Campinas"); s.pg.wait_for_timeout(700); z0 = s.zoom()
    try:
        s.pg.get_by_text(re.compile(r"^Campinas$")).first.click(timeout=3000); s.pg.wait_for_timeout(3500)
        registrar(5, "transição de estados", "clicar no resultado «Campinas»", "o mapa vai até Campinas (zoom muda)",
                  f"zoom {z0} → {s.zoom()}", "OK" if s.zoom() != z0 else "FALHA", s.foto("05-busca-voo"))
    except Exception as ex:
        registrar(5, "transição de estados", "clicar no resultado «Campinas»", "clicável", str(ex)[:80], "FALHA")
    s.fechar()


def e6_oraculo_cruzado(p):
    s = Sessao(p); s.abrir(); s.limpar()
    dados = json.loads(urllib.request.urlopen(URL + "demo/dados/taxa_mortalidade/2023.json").read())
    vw = s.pg.viewport_size; rnd = random.Random(7); conferidos = 0
    for k in range(12):
        x, y = rnd.randint(150, int(vw["width"] * 0.55)), rnd.randint(120, vw["height"] - 150)
        s.pg.mouse.click(x, y); s.pg.wait_for_timeout(1200)
        painel = s.texto("[...document.querySelectorAll('div')].map(d=>d.innerText||'').find(t=>/cod \\d+/.test(t)&&t.length<600)||''")
        m = re.search(r"cod (\d+)", painel)
        if not m:
            continue
        cod = m.group(1); tabela = dados["u"] if len(cod) <= 2 else dados["m"]
        mv = re.search(r"MORTALIDADE[^\n]*\n([^\n]+)", painel)
        mostrado, dec = numero(mv.group(1)) if mv else (None, 0)
        esperado = tabela.get(cod)
        tol = 0.5 * 10 ** -dec + 1e-6
        ok = mostrado is not None and esperado is not None and abs(mostrado - esperado) <= tol
        conferidos += 1
        registrar(6, "oráculo cruzado", f"clique ({x},{y}) → cod {cod}", f"painel mostra {esperado}", f"mostrou {mostrado}",
                  "OK" if ok else "FALHA", s.foto(f"06-clique-{k}"))
        vazias = s.texto("""(()=>{const t=[...document.querySelectorAll('div')].map(d=>d.innerText||'').find(t=>/cod \\d+/.test(t)&&t.length<600)||'';
          const l=t.split('\\n');return l.filter((x,i)=>/^[A-ZÇÃÕÉÍÓÚ ]{4,}$/.test(x)&&(i+1>=l.length||/^[A-ZÇÃÕÉÍÓÚ ]{4,}$/.test(l[i+1])||/^UF:|cod \\d/.test(l[i+1])))})()""")
        if vazias:
            registrar(6, "conteúdo", f"painel de detalhes cod {cod}", "toda seção tem conteúdo", f"seções vazias: {vazias}", "ACHADO")
    registrar(6, "oráculo cruzado", "RESUMO", "≥ 3 feições conferidas", f"{conferidos} conferidas", "OK" if conferidos >= 3 else "ACHADO")
    s.fechar()


def e7_acessibilidade(p):
    s = Sessao(p); s.abrir()
    s.pg.add_script_tag(url=AXE)
    r = s.pg.evaluate("axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}}).then(r=>r.violations.map(v=>({id:v.id,impact:v.impact,n:v.nodes.length,help:v.help})))")
    for v in r:
        registrar(7, "acessibilidade (axe)", f"{v['id']} ({v['impact']})", "0 violações", f"{v['n']}× {v['help'][:60]}",
                  "FALHA" if v["impact"] in ("critical", "serious") else "ACHADO")
    if not r:
        registrar(7, "acessibilidade (axe)", "varredura WCAG A/AA", "0 violações", "0", "OK")
    registrar(7, "acessibilidade", "limite do método", "—", "axe pega ~57% dos problemas; teclado e leitor de tela exigem teste manual", "ACHADO")
    s.fechar()


def e8_responsivo(p):
    for l, a, nome in [(390, 844, "celular"), (1920, 1080, "tela grande")]:
        s = Sessao(p, l, a); s.abrir()
        transborda = s.texto("document.documentElement.scrollWidth > innerWidth + 1")
        coberto = s.texto("""(()=>{let area=0;for(const d of document.querySelectorAll('div')){const c=getComputedStyle(d),r=d.getBoundingClientRect();
          if((c.position==='absolute'||c.position==='fixed')&&parseFloat(c.opacity)>0.5&&c.backgroundColor!=='rgba(0, 0, 0, 0)'&&r.width<innerWidth*0.99)area+=Math.max(0,Math.min(r.right,innerWidth)-Math.max(r.left,0))*Math.max(0,Math.min(r.bottom,innerHeight)-Math.max(r.top,0))}
          return area/(innerWidth*innerHeight)})()""")
        erros, _ = s.limpar(); ev = s.foto(f"08-{nome}")
        registrar(8, "responsivo", f"{nome} {l}×{a}: rolagem horizontal", "não transborda", "transborda" if transborda else "ok",
                  "FALHA" if transborda else "OK", ev)
        registrar(8, "responsivo", f"{nome}: área coberta por painéis", "mapa visível (< 60%)", f"{coberto:.0%}", "OK" if coberto < 0.6 else "ACHADO", ev)
        s.fechar()


def e9_macaco(p, n=300, semente=42):
    s = Sessao(p); s.abrir(); s.limpar(); rnd = random.Random(semente); vw = s.pg.viewport_size; erros_tot = []
    for i in range(n):
        acao = rnd.random()
        try:
            if acao < 0.55: s.pg.mouse.click(rnd.randint(0, vw["width"] - 1), rnd.randint(0, vw["height"] - 1))
            elif acao < 0.75: s.pg.mouse.wheel(0, rnd.choice([-300, 300]))
            elif acao < 0.9: s.pg.keyboard.press(rnd.choice(["Tab", "Enter", "Escape", "ArrowUp", "ArrowDown", "Space"]))
            else:
                els = s.pg.locator("select"); k = rnd.randrange(els.count())
                opts = els.nth(k).evaluate("e=>[...e.options].map(o=>o.value)"); els.nth(k).select_option(rnd.choice(opts))
        except Exception:
            pass
        s.pg.wait_for_timeout(60)
        e, _ = s.limpar(); erros_tot += [f"ação {i}: {x}" for x in e]
    registrar(9, "macaco (semente 42)", f"{n} ações aleatórias", "0 erros", f"{len(erros_tot)} erros {erros_tot[:2]}",
              "OK" if not erros_tot else "FALHA", s.foto("09-macaco-fim"))
    s.fechar()


def e10_links(p):
    s = Sessao(p); s.abrir()
    for href in set(s.texto("[...document.querySelectorAll('a[href]')].map(a=>a.href)")):
        try:
            cod = urllib.request.urlopen(urllib.request.Request(href, method="GET", headers={"User-Agent": "Mozilla/5.0"}), timeout=15).status
        except Exception as ex:
            cod = str(ex)[:40]
        registrar(10, "links", href[:60], "200", str(cod), "OK" if cod == 200 else "FALHA")
    s.fechar()


def relatorio():
    SAIDA.mkdir(exist_ok=True)
    (SAIDA / "relatorio.json").write_text(json.dumps(dict(url=URL, quando=time.strftime("%F %T"), resultados=resultados), ensure_ascii=False, indent=1))
    cont = {k: sum(r["estado"] == k for r in resultados) for k in ("OK", "FALHA", "ACHADO")}
    cor = {"OK": "#2a7a46", "FALHA": "#b42318", "ACHADO": "#b54708"}
    linhas = "".join(
        f"<tr><td>{r['etapa']}</td><td>{r['tecnica']}</td><td>{r['caso']}</td><td>{r['esperado']}</td><td>{r['obtido']}</td>"
        f"<td style='color:{cor[r['estado']]};font-weight:600'>{r['estado']}</td>"
        f"<td>{f'<a href=\"{r['evidencia']}\"><img src=\"{r['evidencia']}\" width=160></a>' if r['evidencia'] else ''}</td></tr>"
        for r in sorted(resultados, key=lambda r: ({'FALHA': 0, 'ACHADO': 1, 'OK': 2}[r['estado']], r['etapa'])))
    (SAIDA / "relatorio.html").write_text(f"""<!doctype html><meta charset=utf-8><title>Teste — brasil_em_dados</title>
<style>body{{font:14px system-ui;margin:24px;max-width:1500px}}td,th{{border-bottom:1px solid #ddd;padding:6px;vertical-align:top;text-align:left}}table{{border-collapse:collapse}}</style>
<h1>Teste de ponta a ponta</h1><p>{URL} · {time.strftime('%F %T')} · <b>{cont['OK']} OK · {cont['FALHA']} FALHA · {cont['ACHADO']} ACHADO</b></p>
<table><tr><th>#</th><th>técnica</th><th>caso</th><th>esperado</th><th>obtido</th><th>estado</th><th>evidência</th></tr>{linhas}</table>""")
    return cont


if __name__ == "__main__":
    SHOTS.mkdir(parents=True, exist_ok=True)
    etapas = [e1_carga, e2_descoberta, e3_exaustivo, e4_particoes, e5_limites, e6_oraculo_cruzado, e7_acessibilidade, e8_responsivo, e9_macaco, e10_links]
    so = [a for a in sys.argv[1:] if a.isdigit()]
    with sync_playwright() as p:
        for i, etapa in enumerate(etapas, 1):
            if so and str(i) not in so:
                continue
            try:
                etapa(p)
            except Exception as ex:
                registrar(i, "execução", f"etapa {etapa.__name__} quebrou", "roda até o fim", f"{type(ex).__name__}: {str(ex)[:120]}", "FALHA")
    c = relatorio()
    print(f"\nRESULTADO: {c['OK']} OK · {c['FALHA']} FALHA · {c['ACHADO']} ACHADO  →  {SAIDA/'relatorio.html'}")
