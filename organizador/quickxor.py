"""QuickXorHash — o hash que o OneDrive corporativo calcula no servidor.

O Graph devolve `file.hashes.quickXorHash` nos metadados de cada arquivo,
o que permite comparar um arquivo local com o da nuvem sem baixar nada.
Algoritmo conforme a especificação da Microsoft (160 bits, deslocamento
de 11 bits por byte, comprimento XORado nos 8 bytes finais).
"""

import base64

import caminhos

_LARGURA = 160           # bits do vetor circular
_DESLOC = 11             # bits deslocados a cada byte
_MASCARA = (1 << _LARGURA) - 1


def _finalizar(acumulado: int, comprimento: int) -> str:
    digesto = bytearray(acumulado.to_bytes(20, "little"))
    for i, b in enumerate(comprimento.to_bytes(8, "little")):
        digesto[12 + i] ^= b
    return base64.b64encode(bytes(digesto)).decode()


def _expandir(dobra: int) -> int:
    """Aplica os deslocamentos aos 160 bytes da dobra (posições 0..159)."""
    acumulado = 0
    for n, b in enumerate(dobra.to_bytes(160, "little")):
        s = b << ((n * _DESLOC) % _LARGURA)
        acumulado ^= (s & _MASCARA) ^ (s >> _LARGURA)
    return acumulado


def hash_ingenuo(dados: bytes) -> str:
    """Versão byte a byte, usada nos testes para conferir a versão rápida."""
    acumulado = 0
    for n, b in enumerate(dados):
        s = b << ((n * _DESLOC) % _LARGURA)
        acumulado ^= (s & _MASCARA) ^ (s >> _LARGURA)
    return _finalizar(acumulado, len(dados))


def hash_fluxo(f, tam_leitura: int = 160 * 8192) -> str:
    # Bytes em posições que diferem por 160 recebem o mesmo deslocamento,
    # então os blocos de 160 bytes podem ser XORados entre si ("dobra")
    # e o deslocamento aplicado uma única vez no final.
    dobra = 0
    comprimento = 0
    resto = b""
    while True:
        pedaco = f.read(tam_leitura)
        if not pedaco:
            break
        comprimento += len(pedaco)
        dados = resto + pedaco
        corte = len(dados) - (len(dados) % 160)
        resto = dados[corte:]
        for i in range(0, corte, 160):
            dobra ^= int.from_bytes(dados[i:i + 160], "little")
    dobra ^= int.from_bytes(resto, "little")
    return _finalizar(_expandir(dobra), comprimento)


def hash_arquivo(caminho) -> str:
    with open(caminhos.longo(caminho), "rb") as f:
        return hash_fluxo(f)
