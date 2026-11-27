from datetime import date
from pathlib import Path

import pytest

import situacoes


# ---------- período (mês/ano) a partir de pastas ----------

@pytest.mark.parametrize("texto, esperado", [
    ("2023-05", (2023, 5)),
    ("2023.05", (2023, 5)),
    ("202305", (2023, 5)),
    ("05-2023", (2023, 5)),
    ("052023", (2023, 5)),
    ("05.2023", (2023, 5)),
    ("Maio 2023", (2023, 5)),
    ("maio de 2023", (2023, 5)),
    ("MAIO-2023", (2023, 5)),
    ("Março 2021", (2021, 3)),
    ("marco_2021", (2021, 3)),
    ("2023 - Maio", (2023, 5)),
    ("NF dez 2024", (2024, 12)),
])
def test_ano_e_mes_juntos(texto, esperado):
    assert situacoes.ano_mes_do_texto(texto) == esperado


@pytest.mark.parametrize("texto, ano, mes", [
    ("Notas 2023", 2023, None),
    ("05 - Maio", None, 5),
    ("Maio", None, 5),
    ("05", None, 5),
    ("Fornecedores", None, None),
    ("20230512", None, None),   # parece data com dia: não arriscar
    ("Sala 13", None, None),
])
def test_partes_soltas(texto, ano, mes):
    assert situacoes.ano_mes_do_texto(texto) == (ano, mes)


def test_periodo_combinando_pastas_do_caminho():
    assert situacoes.periodo_do_caminho(["2023", "05 - Maio"]) == (2023, 5)
    assert situacoes.periodo_do_caminho(["Notas", "2023", "Maio"]) == (2023, 5)
    assert situacoes.periodo_do_caminho(["2023-05"]) == (2023, 5)
    assert situacoes.periodo_do_caminho(["Clientes", "Acme"]) is None
    assert situacoes.periodo_do_caminho(["2023"]) is None  # só o ano não basta


# ---------- classificação local x nuvem ----------

def test_classificar_caminhos():
    assert situacoes.classificar("F:\\Artecon Recibo\\RESTORE") == ("local", "F:\\Artecon Recibo\\RESTORE")
    assert situacoes.classificar("onedrive:/Artecon Recibo/RESTORE") == ("nuvem", "Artecon Recibo/RESTORE")
    assert situacoes.classificar(
        "C:\\Artecon\\DF - one drive\\OneDrive - Artecon Artes Contábeis\\Notas\\2023"
    ) == ("nuvem", "Notas/2023")
    assert situacoes.classificar(
        "C:\\Artecon\\DF - one drive\\OneDrive - Artecon Artes Contábeis\\"
    ) == ("nuvem", "")
    assert situacoes.classificar(
        "local:C:\\Artecon\\DF - one drive\\OneDrive - Artecon Artes Contábeis\\Notas"
    ) == ("local", "C:\\Artecon\\DF - one drive\\OneDrive - Artecon Artes Contábeis\\Notas")


# ---------- comparação entre pastas locais ----------

def _criar(base: Path, rel: str, conteudo: bytes):
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(conteudo)


def test_comparacao_local(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _criar(a, "igual.txt", b"x" * 10)
    _criar(b, "igual.txt", b"x" * 10)
    _criar(a, "so_em_a.txt", b"aaa")
    _criar(b, "sub/so_em_b.txt", b"bbb")
    _criar(a, "difere.txt", b"1234")
    _criar(b, "difere.txt", b"12345")
    _criar(a, "mesmo_tamanho.txt", b"abcd")
    _criar(b, "mesmo_tamanho.txt", b"abce")

    resumo, itens = situacoes.analisar_comparacao(None, str(a), str(b), "ambas")
    por_acao = {}
    for i in itens:
        por_acao.setdefault(i["acao"], []).append(i)
    assert resumo["iguais_nas_duas"] == 1
    assert resumo["faltando_copiar"] == 2
    assert len(por_acao["atencao"]) == 2
    assert any("so_em_a" in i["origem"] for i in por_acao["copiar"])
    assert any("so_em_b" in i["origem"] for i in por_acao["copiar"])


def test_comparacao_direcao_unica(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _criar(a, "so_em_a.txt", b"aaa")
    _criar(b, "so_em_b.txt", b"bbb")
    resumo, itens = situacoes.analisar_comparacao(None, str(a), str(b), "a_para_b")
    copiar = [i for i in itens if i["acao"] == "copiar"]
    assert len(copiar) == 1 and "so_em_a" in copiar[0]["origem"]
    assert any(i["acao"] == "informativo" for i in itens)


def test_copiar_item_local_nao_sobrescreve(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _criar(a, "novo.txt", b"abc")
    situacoes.copiar_item(None, str(a / "novo.txt"), str(b / "sub" / "novo.txt"))
    assert (b / "sub" / "novo.txt").read_bytes() == b"abc"
    with pytest.raises(RuntimeError, match="sobrescrito"):
        situacoes.copiar_item(None, str(a / "novo.txt"), str(b / "sub" / "novo.txt"))


# ---------- notas por ano/mês ----------

def test_notas_local(tmp_path):
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    _criar(origem, "2019/12/antiga.pdf", b"velha")
    _criar(origem, "2020/11/no_limite.pdf", b"ok1")
    _criar(origem, "2021/Maio/dentro.pdf", b"ok2")
    _criar(origem, "2026/05 - Maio/recente.pdf", b"ok3")
    _criar(origem, "diversos/sem_data.pdf", b"????")
    _criar(destino, "2021/05/dentro.pdf", b"ok2")  # já organizada

    resumo, itens = situacoes.analisar_notas(
        None, str(origem), str(destino), anos=6, hoje=date(2026, 11, 26))

    assert resumo["periodo_considerado"] == "de 11/2020 até 11/2026"
    assert resumo["fora_do_periodo"] == 1
    assert resumo["ja_no_destino"] == 1
    assert resumo["sem_periodo_identificado"] == 1
    copiar = sorted(i["destino"].replace("\\", "/") for i in itens if i["acao"] == "copiar")
    assert len(copiar) == 2
    assert copiar[0].endswith("destino/2020/11/no_limite.pdf")
    assert copiar[1].endswith("destino/2026/05/recente.pdf")


def test_comparacao_destino_inexistente_em_direcao_unica(tmp_path):
    a, b = tmp_path / "nao_existe", tmp_path / "b"
    _criar(b, "x.txt", b"abc")
    resumo, itens = situacoes.analisar_comparacao(None, str(a), str(b), "b_para_a")
    assert resumo["faltando_copiar"] == 1
    assert "será criada" in resumo["observacao"]
    with pytest.raises(ValueError, match="não encontrada"):
        situacoes.analisar_comparacao(None, str(a), str(b), "ambas")


def test_cancelamento_interrompe_analise(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _criar(a, "x.txt", b"1")
    b.mkdir()

    def cancelar():
        raise situacoes.AnaliseCancelada()

    with pytest.raises(situacoes.AnaliseCancelada):
        situacoes.analisar_comparacao(None, str(a), str(b), cancelado=cancelar)


_XML_NFE = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe><infNFe><ide><dhEmi>2023-05-12T10:30:00-03:00</dhEmi></ide></infNFe></NFe>
</nfeProc>"""


def test_data_da_nota_xml(tmp_path):
    p = tmp_path / "nfe.xml"
    p.write_text(_XML_NFE, encoding="utf-8")
    assert situacoes.data_da_nota(p) == (2023, 5)
    sem_data = tmp_path / "outro.xml"
    sem_data.write_text("<a><b>nada</b></a>", encoding="utf-8")
    assert situacoes.data_da_nota(sem_data) is None


def test_notas_conferindo_o_arquivo(tmp_path):
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    destino.mkdir()
    # pasta diz 2022/07, emissão interna 05/2023 -> a pasta manda; divergência vira auditoria
    _criar(origem, "2022/07/divergente.xml", _XML_NFE.encode())
    # sem período na pasta, mas a nota revela 05/2023 -> copiar para 2023/05
    _criar(origem, "diversos/resgatada.xml", _XML_NFE.encode())
    # sem período em lugar nenhum -> manual
    _criar(origem, "diversos/misterio.pdf", b"%PDF-1.4 vazio")

    resumo, itens = situacoes.analisar_notas(
        None, str(origem), str(destino), anos=6, hoje=date(2026, 11, 26),
        conferir_arquivo=True)

    assert resumo["emissao_divergente_copiada_pela_pasta"] == 1
    assert resumo["emissao_lida_dentro_da_nota"] == 2
    assert resumo["a_copiar"] == 2
    assert resumo["sem_periodo_identificado"] == 1
    assert resumo["atencao"] == 0
    por_destino = {i["destino"].replace("\\", "/"): i for i in itens if i["acao"] == "copiar"}
    divergente = next(v for k, v in por_destino.items() if k.endswith("destino/2022/07/divergente.xml"))
    assert "05/2023" in divergente["detalhe"] and "pela pasta" in divergente["detalhe"]
    # "diversos" vem antes do período no caminho -> fica antes do ano/mês
    resgatada = next(v for k, v in por_destino.items()
                     if k.endswith("destino/diversos/2023/05/resgatada.xml"))
    assert "emissão lida na nota" in resgatada["detalhe"]


def test_arquivo_de_apoio_acompanha_a_pasta(tmp_path):
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    destino.mkdir()
    # relatório dentro da pasta 2021/03, mas com data interna 05/2023:
    # é apoio -> acompanha a pasta, sem virar divergência
    _criar(origem, "2021/03/Relatorio_Reducao_Z.xml", _XML_NFE.encode())
    resumo, itens = situacoes.analisar_notas(
        None, str(origem), str(destino), anos=6, hoje=date(2026, 11, 26),
        conferir_arquivo=True)
    assert resumo["emissao_divergente_copiada_pela_pasta"] == 0
    assert resumo["arquivos_de_apoio_pela_pasta"] == 1
    assert resumo["a_copiar"] == 1
    item = itens[0]
    assert item["destino"].replace("\\", "/").endswith("destino/2021/03/Relatorio_Reducao_Z.xml")
    assert "acompanha a pasta" in item["detalhe"]


def test_notas_cache_evita_reler(tmp_path):
    import estado as estado_mod
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    destino.mkdir()
    _criar(origem, "diversos/nota.xml", _XML_NFE.encode())
    arquivo = origem / "diversos" / "nota.xml"
    tam, mt = arquivo.stat().st_size, int(arquivo.stat().st_mtime)
    cache = estado_mod.CachePeriodos(tmp_path / "cache.sqlite3")
    try:
        r1, _ = situacoes.analisar_notas(None, str(origem), str(destino), anos=6,
                                         hoje=date(2026, 11, 26), conferir_arquivo=True,
                                         cache_periodos=cache)
        assert r1["emissao_lida_dentro_da_nota"] == 1
        # a leitura ficou guardada: a próxima análise responde pelo cache
        assert cache.obter(str(arquivo), tam, mt) == (2023, 5)
        r2, _ = situacoes.analisar_notas(None, str(origem), str(destino), anos=6,
                                         hoje=date(2026, 11, 26), conferir_arquivo=True,
                                         cache_periodos=cache)
        assert r2["emissao_lida_dentro_da_nota"] == 1
    finally:
        cache.fechar()


def test_notas_conferir_arquivo_exige_origem_local():
    with pytest.raises(ValueError, match="ORIGEM local"):
        situacoes.analisar_notas(None, "onedrive:/Notas", "C:\\destino",
                                 conferir_arquivo=True)


def test_nome_repetido_duplicado_e_renomeado(tmp_path):
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    destino.mkdir()
    # mesmo destino (2024/03/nota.pdf) a partir de duas grafias de pasta:
    # conteúdo idêntico -> um só é copiado; conteúdo diferente -> ganha " (2)"
    _criar(origem, "2024/03/nota.pdf", b"conteudo igual")
    _criar(origem, "03-2024/nota.pdf", b"conteudo igual")
    _criar(origem, "Marco 2024/nota.pdf", b"conteudo DIFERENTE")
    resumo, itens = situacoes.analisar_notas(
        None, str(origem), str(destino), anos=6, hoje=date(2026, 11, 26))
    # nota fiscal não se descarta: as três vão, duas com sufixo
    assert resumo["a_copiar"] == 3
    assert resumo["duplicados_identicos_copiados_com_sufixo"] == 1
    assert resumo["renomeados_por_nome_repetido"] == 1
    assert resumo["atencao"] == 0
    destinos = sorted(i["destino"].replace("\\", "/") for i in itens if i["acao"] == "copiar")
    assert destinos[0].endswith("destino/2024/03/nota (2).pdf")
    assert destinos[1].endswith("destino/2024/03/nota (3).pdf")
    assert destinos[2].endswith("destino/2024/03/nota.pdf")


def test_destino_com_grafia_diferente_nao_recopia(tmp_path):
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    _criar(origem, "2024/09/SINTEGRA/LMF_ESP.txt", b"conteudo")
    _criar(destino, "2024/09/Sintegra/LMF_ESP.txt", b"conteudo")  # mesma pasta p/ Windows
    resumo, itens = situacoes.analisar_notas(
        None, str(origem), str(destino), anos=6, hoje=date(2026, 11, 26))
    assert resumo["ja_no_destino"] == 1
    assert resumo["a_copiar"] == 0


def test_notas_subpastas_da_empresa_acompanham(tmp_path):
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    # mesma nota (nome igual) na pasta normal e na subpasta Cancelada:
    # as duas vão, cada uma no seu lugar — sem conflito
    _criar(origem, "2024/03/nota.xml", b"normal")
    _criar(origem, "2024/03/Cancelada/nota.xml", b"cancelada")
    resumo, itens = situacoes.analisar_notas(
        None, str(origem), str(destino), anos=6, hoje=date(2026, 11, 26))
    assert resumo["a_copiar"] == 2
    assert resumo["atencao"] == 0
    destinos = sorted(i["destino"].replace("\\", "/") for i in itens)
    assert destinos[0].endswith("destino/2024/03/Cancelada/nota.xml")
    assert destinos[1].endswith("destino/2024/03/nota.xml")


def test_notas_conflito_de_nomes(tmp_path):
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    _criar(origem, "loja1/2024/03/nota.pdf", b"aaa")
    _criar(origem, "loja2/2024/03/nota.pdf", b"bbbb")
    resumo, itens = situacoes.analisar_notas(
        None, str(origem), str(destino), anos=6, hoje=date(2026, 11, 26))
    # loja1/loja2 vêm antes do período: viram prefixo (empresa -> ano -> mês)
    assert resumo["a_copiar"] == 2
    assert resumo["atencao"] == 0
    destinos = sorted(i["destino"].replace("\\", "/") for i in itens)
    assert destinos[0].endswith("destino/loja1/2024/03/nota.pdf")
    assert destinos[1].endswith("destino/loja2/2024/03/nota.pdf")


def test_estrutura_empresa_ano_mes_cancelada(tmp_path):
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    destino.mkdir()
    _criar(origem, "Ap Maquinas/2021/04/nota.xml", b"normal")
    _criar(origem, "Ap Maquinas/2021/04/Cancelada/cancelada.xml", b"cancelada")
    resumo, itens = situacoes.analisar_notas(
        None, str(origem), str(destino), anos=6, hoje=date(2026, 11, 26))
    destinos = sorted(i["destino"].replace("\\", "/") for i in itens)
    assert destinos[0].endswith("destino/Ap Maquinas/2021/04/Cancelada/cancelada.xml")
    assert destinos[1].endswith("destino/Ap Maquinas/2021/04/nota.xml")
