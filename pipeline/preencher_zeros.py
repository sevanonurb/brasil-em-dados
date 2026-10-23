"""Preenche com ZERO os municípios sem linha nas métricas em que ausência significa "nenhuma
ocorrência" — sem baixar nada de novo. Idempotente (só insere onde falta).

Só entram métricas em que o zero foi verificado no CÓDIGO do loader, não suposto:
  load_sinan.py  incidências: a taxa vinha só dos municípios com notificação (groupby de casos)
  load_sih.py    internações: `if total > 0` / `if n > 0` descartavam o zero explicitamente
Os loaders já foram corrigidos para gravar o zero; este script conserta o que já está no banco.
  SIDRA 9884   pop_favelas_pct: o universo da tabela são as FAVELAS ("…segundo as Favelas e
                Comunidades Urbanas"); município sem favela não existe nela (nem com "-"). Zero por definição.
NÃO entram: media_permanencia_sus (0/0 é indefinido) e as tabelas do IBGE/SIDRA, onde a ausência
pode ser "-" (zero) ou "X" (suprimido) — essas agora saem certas na carga (pipeline/sidra.py).
Também NÃO entra taxa_divorcialidade: o divórcio é registrado na sede da COMARCA, não onde o casal
mora; município sem comarca não tem zero divórcios, tem divórcios contados em outro lugar.

    python3 pipeline/preencher_zeros.py          (POSTGRES_* no ambiente)
"""
import os
import psycopg2

ZERO_POR_CONSTRUCAO = [
    "incidencia_dengue", "incidencia_tuberculose", "incidencia_hanseniase", "incidencia_leishmaniose",
    "taxa_internacao_sus", "taxa_internacao_cardiovascular", "taxa_internacao_respiratoria", "taxa_internacao_mental",
    "pop_favelas_pct",
]


def main():
    conn = psycopg2.connect(host=os.environ.get("POSTGRES_HOST", "127.0.0.1"), dbname=os.environ["POSTGRES_DB"],
                            user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"])
    with conn, conn.cursor() as cur:
        for m in ZERO_POR_CONSTRUCAO:
            # anos com carga real da métrica; município entra se tem população (mesma regra dos loaders)
            cur.execute("""
                INSERT INTO api.metricas_municipio (cod_municipio, metrica, ano, valor)
                SELECT gm.cod_ibge_7, %(m)s, a.ano, 0
                FROM (SELECT DISTINCT ano FROM api.metricas_municipio WHERE metrica = %(m)s) a
                CROSS JOIN geo.municipios gm
                WHERE gm.populacao_2022 > 0
                  AND NOT EXISTS (SELECT 1 FROM api.metricas_municipio x
                                  WHERE x.metrica = %(m)s AND x.ano = a.ano AND x.cod_municipio = gm.cod_ibge_7)""",
                        {"m": m})
            print(f"  {m}: +{cur.rowcount} zeros", flush=True)


if __name__ == "__main__":
    main()
