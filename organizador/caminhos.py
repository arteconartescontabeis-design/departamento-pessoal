"""Caminhos longos no Windows: o limite clássico é 260 caracteres, e acervos
de notas estouram isso fácil. O prefixo especial \\\\?\\ destrava até ~32 mil."""

import os


def longo(caminho):
    c = str(caminho)
    if os.name != "nt":
        return c
    c = os.path.abspath(c)
    if c.startswith("\\\\?\\"):
        return c
    if c.startswith("\\\\"):          # compartilhamento de rede (UNC)
        return "\\\\?\\UNC" + c[1:]
    return "\\\\?\\" + c
