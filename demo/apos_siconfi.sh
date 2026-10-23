#!/usr/bin/env bash
# Depois de pipeline/recarregar_siconfi.py: reextrai as 3 métricas de finanças, testa e publica
# SÓ se o testador der 0 FALHA. Uso: systemd-run --user ... bash demo/apos_siconfi.sh
set -u
cd "$(dirname "$0")/.."
while systemctl --user is-active -q siconfi-recarga; do sleep 120; done
echo "== siconfi terminou: $(journalctl --user -u siconfi-recarga --no-pager -o cat | grep -c GRAVADO) anos gravados"
journalctl --user -u siconfi-recarga --no-pager -o cat | grep -E "GRAVADO|NÃO gravado"
if journalctl --user -u siconfi-recarga --no-pager -o cat | grep -q "NÃO gravado"; then
  echo "== há ano com erro de rede: NÃO publico. Rode de novo pipeline/recarregar_siconfi.py (retoma)"; exit 1
fi
mkdir -p demo/dados-antes-siconfi
for m in receita_per_capita despesa_saude_per_capita despesa_educacao_per_capita; do
  rm -rf demo/dados-antes-siconfi/$m; mv demo/dados/$m demo/dados-antes-siconfi/ 2>/dev/null
done
python3 demo/extrair_catalogo.py | grep -E "ERRO|FIM"
(cd frontend && VITE_DEMO=1 VITE_MARTIN_URL=/martin VITE_API_URL= npx vite build --base=/brasil-em-dados/ --outDir ../demo/dist --emptyOutDir 2>&1 | grep -E "error|built in")
mkdir -p demo/dist/demo && cp demo/web/* demo/dist/demo/ && rm -rf demo/dist/demo/dados && cp -r demo/dados demo/dist/demo/dados && cp -r demo/cubo demo/dist/demo/cubo; touch demo/dist/.nojekyll
mv tests/e2e/relatorio "tests/e2e/relatorio-pre-siconfi-$(date +%H%M)" 2>/dev/null
R=$(python3 tests/e2e/testador.py http://127.0.0.1:8392/brasil-em-dados/ 1 3 6 2>&1 | tee /dev/stderr | grep RESULTADO)
echo "== LOCAL: $R"
case "$R" in *" 0 FALHA"*) ;; *) echo "== testador com falha: NÃO publico"; exit 1;; esac
(cd demo/dist && git add -A && git commit -qm "deploy: municipal finances (RREO Simplificado, spending by function)" && \
  for t in 1 2 3; do git push -q origin gh-pages && break; sleep 60; done)
echo "== publicado: $(cd demo/dist && git ls-remote origin gh-pages)"
