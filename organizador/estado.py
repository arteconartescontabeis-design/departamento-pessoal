"""Registro local (SQLite) de relatórios, aprovações e execuções.

Ciclo de um relatório:
  analisando -> pendente -> executando -> executado | executado_com_erros
             -> erro                   (falha na análise)
  pendente   -> descartado             (reprovado no painel)
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

_ESQUEMA = """
create table if not exists relatorios(
  id integer primary key autoincrement,
  situacao text not null,
  criado_em text not null,
  params text not null,
  resumo text,
  status text not null default 'analisando',
  aprovado_em text,
  executado_em text,
  erro text);
create table if not exists itens(
  id integer primary key autoincrement,
  relatorio_id integer not null references relatorios(id),
  acao text not null,
  origem text,
  destino text,
  tamanho integer,
  detalhe text,
  status text not null default 'planejado',
  erro text);
create index if not exists itens_rel on itens(relatorio_id);
"""


def _agora():
    return datetime.now().isoformat(timespec="seconds")


class Estado:
    def __init__(self, arquivo: Path):
        Path(arquivo).parent.mkdir(parents=True, exist_ok=True)
        self._arquivo = str(arquivo)
        with self._con() as c:
            c.executescript(_ESQUEMA)

    def _con(self):
        c = sqlite3.connect(self._arquivo, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def marcar_interrompidos(self):
        """Relatórios que ficaram em analisando/executando de uma execução
        anterior do aplicativo não vão mais andar — marca como erro."""
        with self._con() as c:
            c.execute("update relatorios set status='erro', "
                      "erro='interrompido — o aplicativo foi reiniciado durante a análise/execução' "
                      "where status in ('analisando','executando')")

    def novo_relatorio(self, situacao, params):
        with self._con() as c:
            cur = c.execute(
                "insert into relatorios(situacao, criado_em, params) values(?,?,?)",
                (situacao, _agora(), json.dumps(params, ensure_ascii=False)))
            return cur.lastrowid

    def concluir_analise(self, rid, resumo, itens):
        with self._con() as c:
            c.executemany(
                "insert into itens(relatorio_id, acao, origem, destino, tamanho, detalhe) "
                "values(?,?,?,?,?,?)",
                [(rid, i["acao"], i.get("origem"), i.get("destino"),
                  i.get("tamanho"), i.get("detalhe")) for i in itens])
            c.execute("update relatorios set resumo=?, status='pendente' where id=?",
                      (json.dumps(resumo, ensure_ascii=False), rid))

    def falhar(self, rid, erro):
        with self._con() as c:
            c.execute("update relatorios set status='erro', erro=? where id=?", (str(erro)[:2000], rid))

    def aprovar(self, rid):
        with self._con() as c:
            cur = c.execute(
                "update relatorios set status='executando', aprovado_em=? "
                "where id=? and status='pendente'", (_agora(), rid))
            return cur.rowcount == 1

    def cancelar_registro(self, rid):
        with self._con() as c:
            c.execute("update relatorios set status='cancelado' where id=?", (rid,))

    def descartar(self, rid):
        with self._con() as c:
            cur = c.execute(
                "update relatorios set status='descartado' where id=? and status='pendente'", (rid,))
            return cur.rowcount == 1

    def atualizar_item(self, item_id, status, erro=None):
        with self._con() as c:
            c.execute("update itens set status=?, erro=? where id=?",
                      (status, erro and str(erro)[:2000], item_id))

    def concluir_execucao(self, rid, erros):
        status = "executado_com_erros" if erros else "executado"
        with self._con() as c:
            c.execute("update relatorios set status=?, executado_em=? where id=?",
                      (status, _agora(), rid))

    def listar_relatorios(self, limite=50):
        with self._con() as c:
            linhas = c.execute(
                "select id, situacao, criado_em, status, resumo, aprovado_em, executado_em, erro "
                "from relatorios order by id desc limit ?", (limite,)).fetchall()
        saida = []
        for l in linhas:
            d = dict(l)
            d["resumo"] = json.loads(d["resumo"]) if d["resumo"] else None
            saida.append(d)
        return saida

    def obter(self, rid):
        with self._con() as c:
            rel = c.execute("select * from relatorios where id=?", (rid,)).fetchone()
            if not rel:
                return None
            itens = c.execute(
                "select * from itens where relatorio_id=? order by acao, origem", (rid,)).fetchall()
        d = dict(rel)
        d["params"] = json.loads(d["params"])
        d["resumo"] = json.loads(d["resumo"]) if d["resumo"] else None
        d["itens"] = [dict(i) for i in itens]
        return d
