"""As três situações do Organizador. Toda função `analisar_*` SÓ LÊ e devolve
(resumo, itens); nada é enviado ou copiado sem aprovação no painel.

Caminhos aceitos nos campos de pasta:
  - caminho local comum:            F:\\Artecon Recibo\\RESTORE
  - caminho na nuvem (OneDrive):    onedrive:/Artecon Recibo/RESTORE
  - caminho da pasta sincronizada:  C:\\...\\OneDrive - Artecon Artes Contábeis\\Sub\\Pasta
    (é tratado como nuvem, consultado pela API — não baixa os arquivos
    somente-nuvem do Explorer)
"""

import os
import posixpath
import re
import shutil
import time
import unicodedata
from datetime import date
from pathlib import Path

import quickxor

class AnaliseCancelada(Exception):
    """Interrompida a pedido do usuário, pelo botão Parar do painel."""


MESES_NOMES = {1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio",
               6: "Junho", 7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro",
               11: "Novembro", 12: "Dezembro"}
_MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
          "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
_RE_NOME_MES = (r"(jan(?:eiro)?|fev(?:ereiro)?|mar(?:co)?|abr(?:il)?|mai(?:o)?|jun(?:ho)?"
                r"|jul(?:ho)?|ago(?:sto)?|set(?:embro)?|out(?:ubro)?|nov(?:embro)?|dez(?:embro)?)")


# ---------- caminhos: local x nuvem ----------

def classificar(pasta):
    """-> ('local', caminho) ou ('nuvem', caminho_relativo_no_onedrive)."""
    p = (pasta or "").strip().strip('"')
    if p.lower().startswith("local:"):
        return "local", p[len("local:"):].strip()
    if p.lower().startswith("onedrive:"):
        return "nuvem", p[len("onedrive:"):].replace("\\", "/").strip("/")
    m = re.search(r"onedrive - [^\\/]+[\\/](.+)$", p, re.I)
    if m:
        return "nuvem", m.group(1).replace("\\", "/").strip("/")
    if re.search(r"onedrive - [^\\/]+[\\/]?$", p, re.I):
        return "nuvem", ""
    return "local", p


def _info(progresso, **dados):
    """Repassa o andamento ao painel (fase, contagens, início da fase)."""
    if progresso:
        progresso(dados)


def _spec(pasta, rel):
    tipo, caminho = classificar(pasta)
    if tipo == "nuvem":
        return "onedrive:/" + (caminho + "/" + rel).strip("/")
    return str(Path(caminho) / Path(rel.replace("/", os.sep)))


def varrer_local(pasta, cancelado=None, progresso=None):
    base = Path(pasta)
    if not base.is_dir():
        raise ValueError(f"Pasta local não encontrada: {pasta}")
    arquivos = {}
    for raiz, _dirs, nomes in os.walk(base):
        if cancelado:
            cancelado()
        _info(progresso, fase="varrendo a pasta local", arquivos=len(arquivos))
        for nome in nomes:
            p = Path(raiz) / nome
            arquivos[p.relative_to(base).as_posix()] = {"tamanho": p.stat().st_size, "hash": None}
    return arquivos


def varrer_qualquer(graph, pasta, vazio_se_faltar=False, cancelado=None, progresso=None):
    tipo, caminho = classificar(pasta)
    try:
        if tipo == "nuvem":
            return graph.varrer(caminho, cancelado=cancelado, progresso=progresso), tipo
        return varrer_local(caminho, cancelado=cancelado, progresso=progresso), tipo
    except Exception as e:
        if vazio_se_faltar and "não encontrada" in str(e):
            return {}, tipo
        raise


def _hash_de(graph, pasta, rel, info):
    if info.get("hash"):
        return info["hash"]
    tipo, caminho = classificar(pasta)
    if tipo == "local":
        return quickxor.hash_arquivo(Path(caminho) / Path(rel.replace("/", os.sep)))
    return None


# ---------- situação 1: envio da pasta local ao OneDrive ----------

def analisar_envio(graph, pasta_local, pasta_onedrive, conferir_conteudo=True,
                   cancelado=None, progresso=None):
    locais = varrer_local(pasta_local, cancelado=cancelado, progresso=progresso)
    print(f"[análise] pasta local varrida: {len(locais)} arquivos", flush=True)
    _tipo, destino = classificar(pasta_onedrive)
    if _tipo == "local":
        destino = pasta_onedrive.replace("\\", "/").strip("/")
    nuvem, _ = varrer_qualquer(graph, "onedrive:/" + destino, vazio_se_faltar=True,
                               cancelado=cancelado, progresso=progresso)

    pares = sum(1 for r, i in locais.items()
                if r in nuvem and nuvem[r]["tamanho"] == i["tamanho"]) if conferir_conteudo else 0
    inicio_fase = time.time()
    itens, ja_enviados, conferidos = [], 0, 0
    for rel, info in sorted(locais.items()):
        if cancelado:
            cancelado()
        origem = str(Path(pasta_local) / Path(rel.replace("/", os.sep)))
        alvo = "onedrive:/" + (destino + "/" + rel).strip("/")
        if rel not in nuvem:
            itens.append({"acao": "enviar", "origem": origem, "destino": alvo,
                          "tamanho": info["tamanho"]})
            continue
        n = nuvem[rel]
        if n["tamanho"] != info["tamanho"]:
            itens.append({"acao": "atencao", "origem": origem, "destino": alvo,
                          "tamanho": info["tamanho"],
                          "detalhe": f"tamanhos diferem — local {info['tamanho']}, nuvem {n['tamanho']}"})
        elif conferir_conteudo and n.get("hash"):
            conferidos += 1
            if conferidos % 10 == 0:
                _info(progresso, fase="conferindo conteúdo (hash)", feitos=conferidos,
                      total=pares, inicio_fase=inicio_fase)
            if quickxor.hash_arquivo(origem) != n["hash"]:
                itens.append({"acao": "atencao", "origem": origem, "destino": alvo,
                              "tamanho": info["tamanho"],
                              "detalhe": "mesmo tamanho, conteúdo diferente (hash divergente)"})
            else:
                ja_enviados += 1
        else:
            ja_enviados += 1

    somente_nuvem = sorted(r for r in nuvem if r not in locais)
    resumo = {
        "pasta_local": pasta_local, "pasta_onedrive": "/" + destino,
        "arquivos_na_pasta_local": len(locais), "arquivos_no_onedrive": len(nuvem),
        "ja_enviados_e_conferidos": ja_enviados,
        "a_enviar": sum(1 for i in itens if i["acao"] == "enviar"),
        "atencao": sum(1 for i in itens if i["acao"] == "atencao"),
        "somente_na_nuvem": len(somente_nuvem),
        "exemplos_somente_na_nuvem": somente_nuvem[:20],
    }
    return resumo, itens


def executar_envio_item(graph, item):
    hash_local = quickxor.hash_arquivo(item["origem"])
    _tipo, destino = classificar(item["destino"])
    graph.enviar(item["origem"], destino)
    meta = graph.metadados(destino)
    if meta is None:
        raise RuntimeError("enviado, mas não encontrado na conferência")
    if meta.get("size") != os.path.getsize(item["origem"]):
        raise RuntimeError(f"enviado, mas o tamanho na nuvem ({meta.get('size')}) difere do local")
    hash_nuvem = ((meta.get("file") or {}).get("hashes") or {}).get("quickXorHash")
    if hash_nuvem and hash_nuvem != hash_local:
        raise RuntimeError("enviado, mas o hash na nuvem difere do local")
    return "enviado e conferido" + (" (hash)" if hash_nuvem else " (tamanho)")


# ---------- situação 2: comparação entre duas pastas ----------

def analisar_comparacao(graph, pasta_a, pasta_b, direcao="ambas", conferir_conteudo=True,
                        cancelado=None, progresso=None):
    # quando a cópia é só numa direção, a pasta de destino pode ainda não
    # existir: ela é criada na execução (a pasta de ORIGEM precisa existir)
    _info(progresso, fase="varrendo a pasta A")
    va, _ = varrer_qualquer(graph, pasta_a, vazio_se_faltar=(direcao == "b_para_a"),
                            cancelado=cancelado, progresso=progresso)
    print(f"[análise] pasta A varrida: {len(va)} arquivos", flush=True)
    _info(progresso, fase="varrendo a pasta B")
    vb, _ = varrer_qualquer(graph, pasta_b, vazio_se_faltar=(direcao == "a_para_b"),
                            cancelado=cancelado, progresso=progresso)
    print(f"[análise] pasta B varrida: {len(vb)} arquivos — comparando...", flush=True)
    pares = sum(1 for r, i in va.items()
                if r in vb and vb[r]["tamanho"] == i["tamanho"]) if conferir_conteudo else 0
    inicio_fase = time.time()
    itens = []
    iguais = 0
    conferidos = 0
    for rel in sorted(set(va) | set(vb)):
        if cancelado:
            cancelado()
        em_a, em_b = rel in va, rel in vb
        if em_a and not em_b:
            if direcao in ("ambas", "a_para_b"):
                itens.append({"acao": "copiar", "origem": _spec(pasta_a, rel),
                              "destino": _spec(pasta_b, rel), "tamanho": va[rel]["tamanho"],
                              "detalhe": "só existe na pasta A"})
            else:
                itens.append({"acao": "informativo", "origem": _spec(pasta_a, rel),
                              "tamanho": va[rel]["tamanho"], "detalhe": "só existe na pasta A"})
        elif em_b and not em_a:
            if direcao in ("ambas", "b_para_a"):
                itens.append({"acao": "copiar", "origem": _spec(pasta_b, rel),
                              "destino": _spec(pasta_a, rel), "tamanho": vb[rel]["tamanho"],
                              "detalhe": "só existe na pasta B"})
            else:
                itens.append({"acao": "informativo", "origem": _spec(pasta_b, rel),
                              "tamanho": vb[rel]["tamanho"], "detalhe": "só existe na pasta B"})
        else:
            ta, tb = va[rel]["tamanho"], vb[rel]["tamanho"]
            if ta != tb:
                itens.append({"acao": "atencao", "origem": _spec(pasta_a, rel),
                              "destino": _spec(pasta_b, rel), "tamanho": ta,
                              "detalhe": f"existe nas duas, tamanhos diferem (A {ta} × B {tb})"})
                continue
            if conferir_conteudo:
                ha = _hash_de(graph, pasta_a, rel, va[rel])
                hb = _hash_de(graph, pasta_b, rel, vb[rel])
                conferidos += 1
                if conferidos % 10 == 0:
                    _info(progresso, fase="conferindo conteúdo (hash)", feitos=conferidos,
                          total=pares, inicio_fase=inicio_fase)
                if conferidos % 100 == 0:
                    print(f"[análise] conteúdo conferido em {conferidos} arquivos...", flush=True)
                if ha and hb and ha != hb:
                    itens.append({"acao": "atencao", "origem": _spec(pasta_a, rel),
                                  "destino": _spec(pasta_b, rel), "tamanho": ta,
                                  "detalhe": "existe nas duas, mesmo tamanho, conteúdo diferente"})
                    continue
            iguais += 1
    resumo = {
        "pasta_a": pasta_a, "pasta_b": pasta_b, "direcao": direcao,
        "arquivos_em_a": len(va), "arquivos_em_b": len(vb), "iguais_nas_duas": iguais,
        "faltando_copiar": sum(1 for i in itens if i["acao"] == "copiar"),
        "atencao": sum(1 for i in itens if i["acao"] == "atencao"),
    }
    if direcao == "b_para_a" and not va:
        resumo["observacao"] = "a pasta A ainda não existe — será criada na execução"
    elif direcao == "a_para_b" and not vb:
        resumo["observacao"] = "a pasta B ainda não existe — será criada na execução"
    return resumo, itens


def copiar_item(graph, origem, destino):
    """Copia sem nunca sobrescrever, em qualquer combinação local/nuvem."""
    to, co = classificar(origem)
    td, cd = classificar(destino)
    if to == "local" and td == "local":
        if os.path.exists(cd):
            raise RuntimeError(f"já existe no destino (nada foi sobrescrito): {cd}")
        pasta = os.path.dirname(cd)
        if pasta:
            os.makedirs(pasta, exist_ok=True)
        shutil.copy2(co, cd)
    elif to == "local" and td == "nuvem":
        graph.enviar(co, cd)
    elif to == "nuvem" and td == "local":
        graph.baixar(co, cd)
    else:
        if posixpath.basename(co) != posixpath.basename(cd):
            raise RuntimeError("cópia na nuvem mantém o nome do arquivo")
        graph.copiar_nuvem(co, posixpath.dirname(cd))
    return "copiado"


# ---------- situação 3: notas dos últimos N anos, por ano/mês ----------

def _normalizar(texto):
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def ano_mes_do_texto(texto):
    """-> (ano|None, mes|None) extraídos de um nome de pasta/arquivo."""
    t = _normalizar(texto)
    m = re.search(r"(?<!\d)(20\d{2})[-_. /\\]*(0[1-9]|1[0-2])(?!\d)", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(?<!\d)(0[1-9]|1[0-2])[-_. /\\]*(20\d{2})(?!\d)", t)
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.search(r"\b" + _RE_NOME_MES + r"[\s._/-]*(?:de[\s._-]+)?(20\d{2})(?!\d)", t)
    if m:
        return int(m.group(2)), _MESES[m.group(1)[:3]]
    m = re.search(r"(?<!\d)(20\d{2})[\s._/-]*" + _RE_NOME_MES + r"\b", t)
    if m:
        return int(m.group(1)), _MESES[m.group(2)[:3]]
    ano = mes = None
    m = re.search(r"\b" + _RE_NOME_MES + r"\b", t)
    if m:
        mes = _MESES[m.group(1)[:3]]
    m = re.fullmatch(r"\s*(0?[1-9]|1[0-2])\s*", t)
    if m and mes is None:
        mes = int(m.group(1))
    m = re.search(r"(?<!\d)(20\d{2})(?!\d)", t)
    if m:
        ano = int(m.group(1))
    return ano, mes


def periodo_do_caminho(componentes):
    """Combina as pastas do caminho, da mais interna para a mais externa
    (ex.: ['2023', '05 - Maio'] -> (2023, 5))."""
    ano = mes = None
    for comp in reversed(componentes):
        a, m = ano_mes_do_texto(comp)
        if m and mes is None:
            mes = m
        if a and ano is None:
            ano = a
        if ano and mes:
            return ano, mes
    return None


def analisar_notas(graph, origem, destino, anos=6, formato="{ano}/{mes:02d}", hoje=None,
                   cancelado=None, progresso=None):
    hoje = hoje or date.today()
    corte = (hoje.year - int(anos), hoje.month)
    _info(progresso, fase="varrendo a pasta de origem")
    arquivos, _ = varrer_qualquer(graph, origem, cancelado=cancelado, progresso=progresso)
    _info(progresso, fase="varrendo a pasta de destino")
    existentes, _ = varrer_qualquer(graph, destino, vazio_se_faltar=True,
                                    cancelado=cancelado, progresso=progresso)

    inicio_fase = time.time()
    itens = []
    fora_do_periodo = ja_no_destino = feitos = 0
    planejados = set()
    for rel, info in sorted(arquivos.items()):
        if cancelado:
            cancelado()
        feitos += 1
        if feitos % 500 == 0:
            _info(progresso, fase="classificando as notas", feitos=feitos,
                  total=len(arquivos), inicio_fase=inicio_fase)
        partes = rel.split("/")
        periodo = periodo_do_caminho(partes[:-1])
        if not periodo:
            a, m = ano_mes_do_texto(partes[-1])
            periodo = (a, m) if a and m else None
        spec_origem = _spec(origem, rel)
        if not periodo:
            itens.append({"acao": "manual", "origem": spec_origem, "tamanho": info["tamanho"],
                          "detalhe": "período (mês/ano) não identificado no caminho"})
            continue
        ano, mes = periodo
        if (ano, mes) < corte:
            fora_do_periodo += 1
            continue
        sub = formato.format(ano=ano, mes=mes, mes_nome=MESES_NOMES[mes])
        rel_destino = sub.strip("/") + "/" + partes[-1]
        spec_destino = _spec(destino, rel_destino)
        if rel_destino in existentes:
            if existentes[rel_destino]["tamanho"] == info["tamanho"]:
                ja_no_destino += 1
            else:
                itens.append({"acao": "atencao", "origem": spec_origem, "destino": spec_destino,
                              "tamanho": info["tamanho"],
                              "detalhe": "já existe no destino com tamanho diferente — revisar"})
            continue
        if rel_destino in planejados:
            itens.append({"acao": "atencao", "origem": spec_origem, "destino": spec_destino,
                          "tamanho": info["tamanho"],
                          "detalhe": "duas notas de origens diferentes cairiam no mesmo destino — revisar"})
            continue
        planejados.add(rel_destino)
        itens.append({"acao": "copiar", "origem": spec_origem, "destino": spec_destino,
                      "tamanho": info["tamanho"], "detalhe": f"{mes:02d}/{ano}"})

    resumo = {
        "origem": origem, "destino": destino, "anos": int(anos),
        "periodo_considerado": f"de {corte[1]:02d}/{corte[0]} até {hoje.month:02d}/{hoje.year}",
        "arquivos_na_origem": len(arquivos),
        "a_copiar": sum(1 for i in itens if i["acao"] == "copiar"),
        "ja_no_destino": ja_no_destino,
        "fora_do_periodo": fora_do_periodo,
        "sem_periodo_identificado": sum(1 for i in itens if i["acao"] == "manual"),
        "atencao": sum(1 for i in itens if i["acao"] == "atencao"),
    }
    return resumo, itens
