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


def test_notas_conflito_de_nomes(tmp_path):
    origem, destino = tmp_path / "origem", tmp_path / "destino"
    _criar(origem, "loja1/2024/03/nota.pdf", b"aaa")
    _criar(origem, "loja2/2024/03/nota.pdf", b"bbbb")
    resumo, itens = situacoes.analisar_notas(
        None, str(origem), str(destino), anos=6, hoje=date(2026, 11, 26))
    assert resumo["a_copiar"] == 1
    assert resumo["atencao"] == 1
