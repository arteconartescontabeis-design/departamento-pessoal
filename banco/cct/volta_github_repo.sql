-- VOLTA ATRÁS · CCT — o banco volta a disparar o robô no repositório antigo (rescisoes).
update public.cct_config set github_repo = 'arteconartescontabeis-design/rescisoes'
 where github_repo = 'arteconartescontabeis-design/departamento-pessoal';
select github_repo from public.cct_config;
