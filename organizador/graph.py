"""Acesso ao OneDrive pela API do Microsoft Graph.

Login por código de dispositivo (device code): o painel mostra um código,
a pessoa confirma em microsoft.com/devicelogin e o token fica guardado em
dados/token_cache.json. Nenhuma senha passa pelo aplicativo.

Regra de segurança: nenhum método deste módulo apaga ou sobrescreve nada —
envios e cópias usam conflictBehavior=fail (se já existe, dá erro).
"""

import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import quote

import msal
import requests

GRAPH = "https://graph.microsoft.com/v1.0"
_PEDACO_ENVIO = 32 * 327680  # 10 MiB, múltiplo exigido de 320 KiB
_LIMITE_ENVIO_SIMPLES = 4 * 1024 * 1024


class ErroGraph(RuntimeError):
    pass


class Graph:
    def __init__(self, config: dict, pasta_dados: Path):
        self._client_id = (config.get("client_id") or "").strip()
        self._autoridade = "https://login.microsoftonline.com/" + (config.get("tenant") or "organizations")
        self._escopos = config.get("escopos") or ["Files.ReadWrite.All", "User.Read"]
        pasta_dados.mkdir(parents=True, exist_ok=True)
        self._cache_arquivo = pasta_dados / "token_cache.json"
        self._cache = msal.SerializableTokenCache()
        if self._cache_arquivo.exists():
            self._cache.deserialize(self._cache_arquivo.read_text())
        self._app = None
        self._fluxo = None
        self._usuario = None

    # ---------- login ----------

    def _msal(self):
        if not self._client_id:
            raise ErroGraph("client_id não configurado no config.json — veja o README "
                            "(registro do aplicativo no Microsoft Entra).")
        if self._app is None:
            self._app = msal.PublicClientApplication(
                self._client_id, authority=self._autoridade, token_cache=self._cache)
        return self._app

    def _salvar_cache(self):
        if self._cache.has_state_changed:
            self._cache_arquivo.write_text(self._cache.serialize())
            try:
                os.chmod(self._cache_arquivo, 0o600)
            except OSError:
                pass

    def token_silencioso(self):
        app = self._msal()
        contas = app.get_accounts()
        if contas:
            r = app.acquire_token_silent(self._escopos, account=contas[0])
            if r and "access_token" in r:
                self._salvar_cache()
                return r["access_token"]
        return None

    def iniciar_login(self):
        app = self._msal()
        fluxo = app.initiate_device_flow(scopes=self._escopos)
        if "user_code" not in fluxo:
            raise ErroGraph("Falha ao iniciar o login: " + json.dumps(fluxo, ensure_ascii=False))
        registro = {"fluxo": fluxo, "resultado": None}
        self._fluxo = registro

        def esperar():
            registro["resultado"] = app.acquire_token_by_device_flow(fluxo)
            self._salvar_cache()

        threading.Thread(target=esperar, daemon=True).start()
        return {"codigo": fluxo["user_code"], "endereco": fluxo["verification_uri"]}

    def estado_login(self):
        try:
            token = self.token_silencioso()
        except ErroGraph as e:
            return {"conectado": False, "erro": str(e)}
        if token:
            if not self._usuario:
                r = self._req_token("GET", "/me?$select=displayName,userPrincipalName", token)
                if r.ok:
                    d = r.json()
                    self._usuario = d.get("displayName") or d.get("userPrincipalName")
            return {"conectado": True, "usuario": self._usuario}
        f = self._fluxo
        if f and f["resultado"] is None:
            return {"conectado": False,
                    "aguardando": {"codigo": f["fluxo"]["user_code"],
                                   "endereco": f["fluxo"]["verification_uri"]}}
        if f and f["resultado"] is not None and "access_token" not in f["resultado"]:
            return {"conectado": False,
                    "erro": f["resultado"].get("error_description", "falha no login")}
        return {"conectado": False}

    # ---------- requisições ----------

    def _req(self, metodo, url, headers=None, **kw):
        token = self.token_silencioso()
        if not token:
            raise ErroGraph("Não conectado ao Microsoft 365 — faça o login no painel.")
        return self._req_token(metodo, url, token, headers=headers, **kw)

    def _req_token(self, metodo, url, token, headers=None, **kw):
        if url.startswith("/"):
            url = GRAPH + url
        cab = {"Authorization": "Bearer " + token}
        if headers:
            cab.update(headers)
        tempo = kw.pop("timeout", 300)
        r = None
        for _ in range(5):
            r = requests.request(metodo, url, headers=cab, timeout=tempo, **kw)
            if r.status_code in (429, 502, 503, 504):
                try:
                    espera = int(r.headers.get("Retry-After", "3"))
                except ValueError:
                    espera = 3
                time.sleep(max(espera, 1))
                continue
            return r
        return r

    @staticmethod
    def _item(caminho, sufixo=""):
        caminho = (caminho or "").strip("/")
        if not caminho:
            return "/me/drive/root" + sufixo
        base = "/me/drive/root:/" + quote(caminho, safe="/")
        return base + ":" + sufixo if sufixo else base

    @staticmethod
    def _erro(r, contexto):
        try:
            detalhe = r.json().get("error", {}).get("message", "")
        except Exception:
            detalhe = r.text[:300]
        return ErroGraph(f"{contexto}: HTTP {r.status_code} — {detalhe}")

    # ---------- leitura ----------

    def listar(self, caminho):
        url = self._item(caminho, "/children"
                         "?$top=500&$select=name,size,folder,file,lastModifiedDateTime,id,parentReference")
        itens = []
        while url:
            r = self._req("GET", url)
            if r.status_code == 404:
                raise ErroGraph(f"Pasta não encontrada no OneDrive: /{(caminho or '').strip('/')}")
            if not r.ok:
                raise self._erro(r, f"Falha ao listar /{caminho}")
            dados = r.json()
            itens += dados.get("value", [])
            url = dados.get("@odata.nextLink")
        return itens

    def varrer(self, caminho):
        """Todos os arquivos sob a pasta, sem baixar nada:
        caminho relativo -> {tamanho, hash (QuickXor do servidor), modificado}."""
        base = (caminho or "").strip("/")
        arquivos = {}
        pilha = [""]
        while pilha:
            rel = pilha.pop()
            completo = (base + "/" + rel).strip("/")
            for it in self.listar(completo):
                rel_filho = (rel + "/" + it["name"]).strip("/")
                if "folder" in it:
                    pilha.append(rel_filho)
                else:
                    arquivos[rel_filho] = {
                        "tamanho": it.get("size", 0),
                        "hash": ((it.get("file") or {}).get("hashes") or {}).get("quickXorHash"),
                        "modificado": it.get("lastModifiedDateTime"),
                    }
        return arquivos

    def metadados(self, caminho):
        r = self._req("GET", self._item(caminho) + "?$select=name,size,file,folder,lastModifiedDateTime")
        if r.status_code == 404:
            return None
        if not r.ok:
            raise self._erro(r, f"Falha ao consultar /{caminho}")
        return r.json()

    # ---------- escrita (nunca sobrescreve) ----------

    def garantir_pasta(self, caminho):
        caminho = (caminho or "").strip("/")
        if not caminho:
            r = self._req("GET", "/me/drive/root")
            if not r.ok:
                raise self._erro(r, "Falha ao abrir a raiz do OneDrive")
            return r.json()
        pai = ""
        item = None
        for seg in caminho.split("/"):
            atual = (pai + "/" + seg).strip("/")
            r = self._req("GET", self._item(atual))
            if r.status_code == 404:
                r = self._req("POST", self._item(pai, "/children"),
                              json={"name": seg, "folder": {},
                                    "@microsoft.graph.conflictBehavior": "fail"})
                if r.status_code == 409:
                    r = self._req("GET", self._item(atual))
            if not r.ok:
                raise self._erro(r, f"Falha ao criar a pasta /{atual}")
            item = r.json()
            pai = atual
        return item

    def enviar(self, caminho_local, caminho_nuvem):
        destino = caminho_nuvem.strip("/")
        tamanho = os.path.getsize(caminho_local)
        if tamanho <= _LIMITE_ENVIO_SIMPLES:
            with open(caminho_local, "rb") as f:
                dados = f.read()
            r = self._req("PUT",
                          self._item(destino, "/content?@microsoft.graph.conflictBehavior=fail"),
                          headers={"Content-Type": "application/octet-stream"}, data=dados)
            if r.status_code == 409:
                raise ErroGraph(f"Já existe no OneDrive (nada foi sobrescrito): /{destino}")
            if not r.ok:
                raise self._erro(r, f"Falha no envio de /{destino}")
            return r.json()
        r = self._req("POST", self._item(destino, "/createUploadSession"),
                      json={"item": {"@microsoft.graph.conflictBehavior": "fail"}})
        if r.status_code == 409:
            raise ErroGraph(f"Já existe no OneDrive (nada foi sobrescrito): /{destino}")
        if not r.ok:
            raise self._erro(r, f"Falha ao abrir sessão de envio de /{destino}")
        url = r.json()["uploadUrl"]
        enviado = 0
        with open(caminho_local, "rb") as f:
            while enviado < tamanho:
                dados = f.read(_PEDACO_ENVIO)
                r = requests.put(url, data=dados, timeout=900, headers={
                    "Content-Range": f"bytes {enviado}-{enviado + len(dados) - 1}/{tamanho}"})
                if r.status_code not in (200, 201, 202):
                    raise self._erro(r, f"Falha no envio de /{destino} (byte {enviado})")
                enviado += len(dados)
        return r.json()

    def baixar(self, caminho_nuvem, destino_local):
        if os.path.exists(destino_local):
            raise ErroGraph(f"Já existe no destino (nada foi sobrescrito): {destino_local}")
        r = self._req("GET", self._item(caminho_nuvem, "/content"), stream=True)
        if not r.ok:
            raise self._erro(r, f"Falha ao baixar /{caminho_nuvem}")
        pasta = os.path.dirname(destino_local)
        if pasta:
            os.makedirs(pasta, exist_ok=True)
        with open(destino_local, "wb") as f:
            for parte in r.iter_content(512 * 1024):
                f.write(parte)

    def copiar_nuvem(self, origem, pasta_destino):
        destino = self.garantir_pasta(pasta_destino)
        drive_id = (destino.get("parentReference") or {}).get("driveId")
        if not drive_id:
            r = self._req("GET", "/me/drive?$select=id")
            drive_id = r.json().get("id")
        r = self._req("POST", self._item(origem, "/copy"),
                      json={"parentReference": {"driveId": drive_id, "id": destino["id"]}})
        if r.status_code != 202:
            raise self._erro(r, f"Falha ao copiar /{origem}")
        monitor = r.headers.get("Location")
        prazo = time.time() + 600
        while monitor and time.time() < prazo:
            m = requests.get(monitor, timeout=60)
            if m.ok:
                estado = m.json()
                if estado.get("status") == "completed":
                    return
                if estado.get("status") == "failed":
                    erro = (estado.get("error") or {}).get("message", "erro desconhecido")
                    raise ErroGraph(f"Cópia de /{origem} falhou: {erro}")
            time.sleep(2)
        raise ErroGraph(f"Tempo esgotado ao copiar /{origem}")
