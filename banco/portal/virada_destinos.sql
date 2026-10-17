-- VIRADA · Portal (banco do Departamento Pessoal / fbxelwhdiisfmnwrerbl, schema core)
-- Aponta os 3 aplicativos do Departamento Pessoal para os endereços novos. Volta: volta_destinos.sql.
update core.apps set destino_url = 'https://arteconartescontabeis-design.github.io/departamento-pessoal/rescisoes/', atualizado_em = now() where id = 'rescisoes';
update core.apps set destino_url = 'https://arteconartescontabeis-design.github.io/departamento-pessoal/rescisoes/', atualizado_em = now() where id = 'ferias';
update core.apps set destino_url = 'https://arteconartescontabeis-design.github.io/departamento-pessoal/cct/',       atualizado_em = now() where id = 'cct';
select id, destino_url from core.apps where area_id = 'dp' order by ordem;
