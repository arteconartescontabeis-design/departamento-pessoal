# Departamento Pessoal — Artecon

Repositório do departamento, um aplicativo por pasta (decisão de 13/10/2026). Entre sempre pelo
[Portal Artecon](https://arteconartescontabeis-design.github.io/portal/).

| Pasta | Aplicativo (Portal) | Endereço |
|---|---|---|
| `rescisoes/` | **Rescisões** e **Férias** (Rescisões Pro — o mesmo app) | `/departamento-pessoal/rescisoes/` |
| `cct/` | **Convenções Coletivas** (CCT Monitor) | `/departamento-pessoal/cct/` |
| `robo/` | Robô do CCT (GitHub Actions `monitor-cct.yml`) | — |
| `sql/` | Scripts de instalação do CCT (histórico) | — |
| `tests/` | `pytest tests/` (regras do robô) · `node tests/test_cct_app.js` (regras do app) | — |
| `banco/` | Scripts de virada e de volta (Portal e repositório do robô) | — |

**Banco:** projeto Supabase **Departamento Pessoal** (`fbxelwhdiisfmnwrerbl`) — o mesmo de antes; também abriga o
Portal (schema `core`) e a IA Central. Nenhum dado mudou de lugar na migração.

## Robô do CCT
- Roda no GitHub Actions deste repositório. O banco dispara o robô pelo `cct_config.github_repo`
  (funções `cct_consultar_agora`, `cct_pedir_analise_agora`, `cct_vigia`, `cct_vigia_robo`) com o
  `GITHUB_DISPATCH_TOKEN` guardado no Vault do Supabase.
- **Secrets deste repositório** (Settings → Secrets and variables → Actions; valores digitados só no GitHub):
  `SUPABASE_SERVICE_KEY`, `MAIL_API_KEY`, `IA_GATEWAY_TOKEN` e, só em teste, `MAIL_DESTINO_UNICO`.
  (`SUPABASE_URL` já vem no workflow — é o endereço público do banco; um secret com esse nome, se existir, prevalece.)
- **Nunca dois robôs ao mesmo tempo.** Até a virada o agendamento fica comentado no `monitor-cct.yml` e o robô
  continua rodando no repositório antigo `rescisoes`. Antes da virada, use aqui só o disparo manual com
  `teste_email` (testa os secrets sem consultar nada).

## Migração (outubro/2026)
Origem: repositório `rescisoes` (commit `1917478`). Mudanças em relação à origem:
- `index.html` → `rescisoes/index.html`; `cct.html` → `cct/index.html` (conteúdo idêntico; logos ao lado).
- `robo/monitor_cct.py`: `LOGO_URL` e `APP_URL` dos e-mails apontam para `departamento-pessoal/cct/`.
- Testes e `testes-cct.yml`: caminho `cct/index.html`. `tests/cct_smoke (1).js` e `tests/verificar_robo (1).py`
  perderam o "(1)" do nome. `setup_cct_v0.19.0.sql` foi para `sql/`.
- Não vieram: `analisar_cct.py` da raiz (cópia antiga do `robo/analisar_cct.py`, sem uso) e o secret legado
  `ANTHROPIC_API_KEY` (sem uso desde a v0.20.0).
- Função `bright-task` v6.1 (e-mails do Rescisões/Férias com o endereço novo): fonte oficial no `artecon-supabase`,
  publicada na virada.

Virada: `banco/cct/virada_github_repo.sql` + `banco/portal/virada_destinos.sql` (projeto Departamento Pessoal),
agendamento ligado aqui e desligado no `rescisoes`, `bright-task` v6.1.
Volta: `volta_github_repo.sql` + `volta_destinos.sql`, agendamento de volta ao `rescisoes`, `bright-task` v6.0.
