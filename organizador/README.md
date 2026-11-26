# Organizador de Documentos — aplicativo local (APP01)

Aplicativo local (fora do Portal) para três situações do departamento, sempre no ciclo
**Analisar (só leitura) → Relatório → Aprovação no painel → Executar → Registro**:

1. **Envio ao OneDrive com acompanhamento** — confere o que está na pasta local
   (ex.: `F:\Artecon Recibo\RESTORE`) e ainda não chegou ao OneDrive; depois da aprovação
   envia e **confere arquivo por arquivo** na nuvem (tamanho e hash).
2. **Comparação entre dois grupos de pastas** — mapeia o que existe em uma e falta na outra
   (pastas locais, do OneDrive, ou um de cada); depois da aprovação copia os faltantes.
3. **Notas dos últimos 6 anos por ano/mês** — identifica o período de cada nota pela **pasta**
   em que ela está (ex.: `2023\05 - Maio`, `Maio 2023`, `05-2023`), separa as dos últimos
   N anos e copia para o destino em subpastas `AAAA/MM`. Nota sem período identificável
   não é movida: entra no relatório como "revisar manualmente".

**Regras fixas de segurança**
- Nenhuma análise altera nada; execução só depois do botão **Aprovar** no painel.
- O aplicativo **nunca apaga nem sobrescreve** — só envia e copia (`conflictBehavior=fail`:
  se o arquivo já existe no destino, a ação falha e fica marcada no relatório).
- Tudo fica registrado em `dados/organizador.sqlite3` (relatórios, aprovações, resultado item a item).
- A nuvem é consultada pela API do Microsoft Graph: comparar **não baixa** os arquivos
  (usa nome, tamanho e o hash QuickXor calculado pelo servidor da Microsoft), inclusive os
  "somente na nuvem" do OneDrive sincronizado.
- O painel responde só em `http://localhost` (127.0.0.1) — não fica acessível pela rede.

## Instalação (no APP01)

1. Instalar o [Python 3.10+](https://www.python.org/downloads/) (marcar "Add python.exe to PATH").
2. Copiar a pasta `organizador/` para o APP01 (ex.: `C:\Artecon\organizador`).
3. No prompt de comando, dentro da pasta:

```bash
pip install -r requirements.txt
```

4. Copiar `config.exemplo.json` para `config.json` e preencher o `client_id` (abaixo).
5. Rodar:

```bash
python app.py
```

e abrir **http://localhost:8765** no navegador.

## Registro no Microsoft Entra (uma vez só — gera o `client_id`)

O aplicativo acessa o OneDrive em nome do usuário que fizer login (sem senha no app,
sem chave em arquivo). Para isso precisa de um registro no Entra:

1. <https://portal.azure.com> → **Microsoft Entra ID** → **App registrations** → **New registration**.
2. Nome: `Organizador DP`; contas: **somente este diretório (Artecon)**; Redirect URI: deixar vazio. Registrar.
3. Em **Authentication** → **Advanced settings** → **Allow public client flows** → **Yes** → Save.
4. Em **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated**:
   `Files.ReadWrite.All` e `User.Read`. Se o botão **Grant admin consent** aparecer, clicar
   (dependendo da política do locatário, o consentimento do próprio usuário já basta).
5. Em **Overview**, copiar o **Application (client) ID** para o `client_id` do `config.json`
   (`tenant` pode ficar `artecon.cnt.br`).

No primeiro uso, o painel mostra um código e o endereço <https://microsoft.com/devicelogin>;
depois de confirmar, o acesso fica guardado em `dados/token_cache.json` (arquivo local — não
versionar nem copiar para outra máquina).

## Como indicar as pastas no painel

| Tipo | Exemplo |
|---|---|
| Pasta local / rede | `F:\Artecon Recibo\RESTORE` |
| Pasta no OneDrive | `onedrive:/Artecon Recibo/RESTORE` |
| Pasta sincronizada | `C:\Artecon\DF - one drive\OneDrive - Artecon Artes Contábeis\Sub\Pasta` |

O caminho da pasta sincronizada (`...\OneDrive - Artecon Artes Contábeis\...`) é tratado como
nuvem e consultado pela API — os arquivos somente-nuvem não são baixados para a máquina.

## Testes

```bash
python -m pytest tests/ -q
```

Cobrem o hash QuickXor (contra a versão de referência byte a byte), a leitura de período
(mês/ano) nos nomes de pastas, a comparação de pastas e o plano das notas por ano/mês.
A primeira execução real da situação 1 também serve de conferência ponta a ponta: cada
arquivo enviado é verificado contra o hash devolvido pelo servidor da Microsoft.

## Observações

- "Últimos 6 anos" = do mesmo mês de 6 anos atrás até hoje (configurável em `anos`).
- O formato das subpastas de destino é configurável: `{ano}/{mes:02d}` → `2023/05`;
  `{ano}/{mes:02d} - {mes_nome}` → `2023/05 - Maio`.
- `dados/` (banco e token) é criado ao lado do `app.py` e está no `.gitignore` do repositório.
