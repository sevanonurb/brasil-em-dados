#!/usr/bin/env bash
# Depois de uma recarga longa (unidade systemd): reextrai as métricas dela, testa e publica SÓ se o
# testador der 0 FALHA. Uso: systemd-run --user ... bash demo/apos_siconfi.sh [unidade métrica...]
# (padrão: siconfi-recarga e as 3 métricas de finanças do RREO)
set -u
UNIDADE=${1:-siconfi-recarga}; shift || true
METRICAS=${*:-receita_per_capita despesa_saude_per_capita despesa_educacao_per_capita}
cd "$(dirname "$0")/.."
# só o journal DESTA execução: o da unidade acumula as anteriores (um "NÃO gravado" velho bloquearia tudo)
DESDE=$(date -d "-10 min" "+%F %T")
log() { journalctl --user -u $UNIDADE --since "$DESDE" --no-pager -o cat; }
while systemctl --user is-active -q $UNIDADE; do sleep 120; done
echo "== $UNIDADE terminou: $(log | grep -c GRAVADO) anos gravados"
log | grep -E "GRAVADO|NÃO gravado"
if log | grep -q "NÃO gravado"; then
  echo "== há ano com erro de rede: NÃO publico. Rode a recarga de novo (retoma)"; exit 1
fi
mkdir -p demo/dados-antes-siconfi
for m in $METRICAS; do
  rm -rf demo/dados-antes-siconfi/$m; mv demo/dados/$m demo/dados-antes-siconfi/ 2>/dev/null
done
# o catálogo (anos por métrica) vem do banco: sem isto os anos novos não aparecem no painel
python3 - <<'PY'
import json, importlib.util
s = importlib.util.spec_from_file_location("server", "api/server.py"); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
json.dump(m.query_anos(), open("demo/anos.json", "w"), default=int)
PY
cp demo/anos.json demo/web/anos.json
python3 demo/extrair_catalogo.py | grep -E "ERRO|FIM"
for m in $METRICAS; do   # extração vazia (ex.: sem POSTGRES_* no ambiente) não pode chegar ao testador
  [ -n "$(ls demo/dados/$m 2>/dev/null)" ] || { echo "== $m sem dados extraídos: NÃO publico"; exit 1; }
done
(cd frontend && VITE_DEMO=1 VITE_MARTIN_URL=/martin VITE_API_URL= npx vite build --base=/brasil-em-dados/ --outDir ../demo/dist --emptyOutDir 2>&1 | grep -E "error|built in")
mkdir -p demo/dist/demo && cp demo/web/* demo/dist/demo/ && rm -rf demo/dist/demo/dados && cp -r demo/dados demo/dist/demo/dados && cp -r demo/cubo demo/dist/demo/cubo; touch demo/dist/.nojekyll
mv tests/e2e/relatorio "tests/e2e/relatorio-pre-siconfi-$(date +%H%M)" 2>/dev/null
# o testador precisa do servidor local; se ele não está no ar, sobe só para este teste
if ! curl -sf -o /dev/null http://127.0.0.1:8392/brasil-em-dados/; then
  python3 demo/servir.py 8392 >/dev/null 2>&1 & SERV=$!; trap 'kill $SERV 2>/dev/null' EXIT
  for i in $(seq 30); do curl -sf -o /dev/null http://127.0.0.1:8392/brasil-em-dados/ && break; sleep 0.5; done
fi
R=$(python3 tests/e2e/testador.py http://127.0.0.1:8392/brasil-em-dados/ 1 3 6 2>&1 | tee /dev/stderr | grep RESULTADO)
echo "== LOCAL: $R"
case "$R" in *" 0 FALHA"*) ;; *) echo "== testador com falha: NÃO publico"; exit 1;; esac
(cd demo/dist && git add -A && git commit -qm "deploy: $UNIDADE ($METRICAS)" && \
  for t in 1 2 3; do git push -q origin gh-pages && break; sleep 60; done)
echo "== publicado: $(cd demo/dist && git ls-remote origin gh-pages)"
