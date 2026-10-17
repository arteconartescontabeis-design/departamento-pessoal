-- VIRADA · CCT (banco do Departamento Pessoal) — o banco passa a disparar o robô no repositório novo.
-- Usado por cct_consultar_agora, cct_pedir_analise_agora, cct_vigia e cct_vigia_robo
-- (https://api.github.com/repos/<github_repo>/actions/workflows/monitor-cct.yml/dispatches).
-- ANTES: o token fine-grained do GITHUB_DISPATCH_TOKEN (Vault) precisa incluir o repositório departamento-pessoal.
update public.cct_config set github_repo = 'arteconartescontabeis-design/departamento-pessoal'
 where github_repo = 'arteconartescontabeis-design/rescisoes';
select github_repo from public.cct_config;
