import base64
import io
import random

import quickxor


def test_vazio_e_zero_mais_comprimento():
    assert quickxor.hash_fluxo(io.BytesIO(b"")) == base64.b64encode(bytes(20)).decode()


def test_rapido_igual_ao_ingenuo_em_varios_tamanhos():
    rnd = random.Random(42)
    for tamanho in [0, 1, 7, 11, 159, 160, 161, 320, 479, 480, 481, 1000, 4096 * 3 + 5]:
        dados = bytes(rnd.randrange(256) for _ in range(tamanho))
        assert quickxor.hash_fluxo(io.BytesIO(dados)) == quickxor.hash_ingenuo(dados), tamanho


def test_leituras_picadas_dao_o_mesmo_resultado():
    rnd = random.Random(7)
    dados = bytes(rnd.randrange(256) for _ in range(10_000))
    inteiro = quickxor.hash_fluxo(io.BytesIO(dados))
    picado = quickxor.hash_fluxo(io.BytesIO(dados), tam_leitura=333)
    assert inteiro == picado


def test_comprimento_entra_no_digesto():
    assert quickxor.hash_ingenuo(b"\0") != quickxor.hash_ingenuo(b"\0\0")
