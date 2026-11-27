"""Organizador de Documentos — painel local (http://localhost:8765).

Regras fixas: analisar é sempre só-leitura; executar só acontece depois do
botão Aprovar no painel; nada é apagado nem sobrescrito, nunca.
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import estado as estado_mod
import graph as graph_mod
import situacoes

VERSAO = "0.4.0"

AQUI = Path(__file__).resolve().parent
PASTA_DADOS = AQUI / "dados"

PADRAO = {
    "client_id": "",
    "tenant": "organizations",
    "porta": 8765,
    "transferencias_paralelas": 8,
    "envio": {"pasta_local": "F:\\Artecon Recibo\\RESTORE",
              "pasta_onedrive": "Artecon Recibo/RESTORE",
              "conferir_conteudo": True},
    "comparacao": {"pasta_a": "", "pasta_b": "", "direcao": "ambas",
                   "conferir_conteudo": True},
    "notas": {"origem": "", "destino": "", "anos": 6,
              "formato_destino": "{ano}/{mes:02d}"},
}


def carregar_config():
    arquivo = AQUI / "config.json"
    config = json.loads(json.dumps(PADRAO))
    if arquivo.exists():
        lido = json.loads(arquivo.read_text(encoding="utf-8"))
        for chave, valor in lido.items():
            if isinstance(valor, dict) and isinstance(config.get(chave), dict):
                config[chave].update(valor)
            else:
                config[chave] = valor
    else:
        arquivo.write_text(json.dumps(PADRAO, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Criado {arquivo} — preencha o client_id (veja o README).")
    return config


config = carregar_config()
app = Flask(__name__)
db = estado_mod.Estado(PASTA_DADOS / "organizador.sqlite3")
db.marcar_interrompidos()
nuvem = graph_mod.Graph(config, PASTA_DADOS)


@app.get("/")
def pagina():
    return send_from_directory(AQUI / "static", "index.html")


@app.get("/api/config")
def api_config():
    resposta = {k: config[k] for k in ("envio", "comparacao", "notas")}
    resposta["versao"] = VERSAO
    return jsonify(resposta)


@app.get("/api/login/estado")
def api_login_estado():
    return jsonify(nuvem.estado_login())


@app.post("/api/login/iniciar")
def api_login_iniciar():
    try:
        return jsonify(nuvem.iniciar_login())
    except graph_mod.ErroGraph as e:
        return jsonify({"erro": str(e)}), 400


# relatórios em andamento: rid -> threading.Event (pedido de parada) e dict de progresso
cancelamentos = {}
andamentos = {}


def _analise(rid, situacao, params, evento):
    def checar():
        if evento.is_set():
            raise situacoes.AnaliseCancelada()

    def informar(dados):
        andamentos[rid] = dados

    try:
        if situacao == "envio":
            resumo, itens = situacoes.analisar_envio(
                nuvem, params["pasta_local"], params["pasta_onedrive"],
                bool(params.get("conferir_conteudo", True)),
                cancelado=checar, progresso=informar)
        elif situacao == "comparacao":
            resumo, itens = situacoes.analisar_comparacao(
                nuvem, params["pasta_a"], params["pasta_b"],
                params.get("direcao", "ambas"),
                bool(params.get("conferir_conteudo", True)),
                cancelado=checar, progresso=informar)
        elif situacao == "notas":
            resumo, itens = situacoes.analisar_notas(
                nuvem, params["origem"], params["destino"],
                int(params.get("anos", 6)),
                params.get("formato_destino") or "{ano}/{mes:02d}",
                cancelado=checar, progresso=informar)
        else:
            raise ValueError("situação desconhecida: " + situacao)
        db.concluir_analise(rid, resumo, itens)
    except situacoes.AnaliseCancelada:
        db.cancelar_registro(rid)
    except Exception as e:
        db.falhar(rid, e)
    finally:
        cancelamentos.pop(rid, None)
        andamentos.pop(rid, None)


@app.post("/api/analisar")
def api_analisar():
    corpo = request.get_json(force=True)
    situacao = corpo.get("situacao")
    params = corpo.get("params") or {}
    obrigatorios = {"envio": ("pasta_local", "pasta_onedrive"),
                    "comparacao": ("pasta_a", "pasta_b"),
                    "notas": ("origem", "destino")}
    if situacao not in obrigatorios:
        return jsonify({"erro": "situação inválida"}), 400
    faltam = [c for c in obrigatorios[situacao] if not (params.get(c) or "").strip()]
    if faltam:
        return jsonify({"erro": "preencha: " + ", ".join(faltam)}), 400
    rid = db.novo_relatorio(situacao, params)
    evento = threading.Event()
    cancelamentos[rid] = evento
    threading.Thread(target=_analise, args=(rid, situacao, params, evento), daemon=True).start()
    return jsonify({"relatorio": rid})


def _execucao(rid, evento):
    rel = db.obter(rid)
    plano = [i for i in rel["itens"]
             if i["status"] == "planejado" and i["acao"] in ("enviar", "copiar")]
    paralelo = max(1, min(16, int(config.get("transferencias_paralelas", 8))))
    inicio = time.time()
    trava = threading.Lock()
    contagem = {"feitos": 0, "erros": 0}

    def um_item(item):
        if evento.is_set():
            return
        try:
            if item["acao"] == "enviar":
                situacoes.executar_envio_item(nuvem, item)
            else:
                situacoes.copiar_item(nuvem, item["origem"], item["destino"])
            db.atualizar_item(item["id"], "ok")
        except Exception as e:
            with trava:
                contagem["erros"] += 1
            db.atualizar_item(item["id"], "erro", e)
        finally:
            with trava:
                contagem["feitos"] += 1
                andamentos[rid] = {
                    "fase": f"executando as cópias/envios ({paralelo} em paralelo)",
                    "feitos": contagem["feitos"], "total": len(plano),
                    "inicio_fase": inicio}

    with ThreadPoolExecutor(max_workers=paralelo) as executor:
        list(executor.map(um_item, plano))

    if evento.is_set():
        db.cancelar_registro(rid)
    else:
        db.concluir_execucao(rid, contagem["erros"])
    cancelamentos.pop(rid, None)
    andamentos.pop(rid, None)


@app.post("/api/relatorio/<int:rid>/aprovar")
def api_aprovar(rid):
    if not db.aprovar(rid):
        return jsonify({"erro": "este relatório não está pendente de aprovação"}), 409
    evento = threading.Event()
    cancelamentos[rid] = evento
    threading.Thread(target=_execucao, args=(rid, evento), daemon=True).start()
    return jsonify({"ok": True})


@app.post("/api/relatorio/<int:rid>/parar")
def api_parar(rid):
    evento = cancelamentos.get(rid)
    if evento:
        evento.set()
        return jsonify({"ok": True})
    rel = db.obter(rid)
    if rel and rel["status"] in ("analisando", "executando"):
        # órfão de uma execução anterior do aplicativo
        db.cancelar_registro(rid)
        return jsonify({"ok": True})
    return jsonify({"erro": "não há análise ou execução em andamento neste relatório"}), 409


@app.post("/api/relatorio/<int:rid>/descartar")
def api_descartar(rid):
    if not db.descartar(rid):
        return jsonify({"erro": "este relatório não está pendente de aprovação"}), 409
    return jsonify({"ok": True})


@app.get("/api/relatorios")
def api_relatorios():
    return jsonify(db.listar_relatorios())


@app.get("/api/relatorio/<int:rid>")
def api_relatorio(rid):
    rel = db.obter(rid)
    if not rel:
        return jsonify({"erro": "relatório não encontrado"}), 404
    rel["andamento"] = andamentos.get(rid)
    return jsonify(rel)


if __name__ == "__main__":
    porta = int(config.get("porta", 8765))
    print(f"Organizador de Documentos v{VERSAO} — abra http://localhost:{porta}")
    # host 127.0.0.1: o painel só responde na própria máquina
    app.run(host="127.0.0.1", port=porta, threaded=True)
