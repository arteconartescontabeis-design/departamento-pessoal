-- VOLTA ATRÁS · Portal — os 3 aplicativos do DP voltam para os endereços antigos (repositório rescisoes).
update core.apps set destino_url = 'https://arteconartescontabeis-design.github.io/rescisoes/',         atualizado_em = now() where id = 'rescisoes';
update core.apps set destino_url = 'https://arteconartescontabeis-design.github.io/rescisoes/',         atualizado_em = now() where id = 'ferias';
update core.apps set destino_url = 'https://arteconartescontabeis-design.github.io/rescisoes/cct.html', atualizado_em = now() where id = 'cct';
select id, destino_url from core.apps where area_id = 'dp' order by ordem;
