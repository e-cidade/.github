# Operação dos mirrors

Os mirrors são declarados em `mirrors/mirrors.json` e sincronizados pelo
workflow `Mirror sync`.

## Funcionamento

A execução agendada processa diariamente todos os mirrors habilitados.

Sem mudança no upstream, a execução termina sem criar commit, branch ou PR.

Com mudança, a automação:

1. atualiza as refs `upstream/*`;
2. cria `sync/upstream-<branch>-<sha>`;
3. preserva o histórico do upstream;
4. reaplica a camada administrativa;
5. abre um PR para a branch principal.

PRs de sincronização devem usar merge commit.

## Execução manual

Inspeção:

    gh workflow run mirror-sync.yml --repo e-cidade/.github \
      -f mirror=dbseller -f dry_run=true

Sincronização real:

    gh workflow run mirror-sync.yml --repo e-cidade/.github \
      -f mirror=dbseller -f dry_run=false

Logs:

    gh run list --repo e-cidade/.github --workflow mirror-sync.yml
    gh run view RUN_ID --repo e-cidade/.github --log

## Pausar um mirror

Adicionar à entrada em `mirrors/mirrors.json`:

    "enabled": false

O mirror deixa de participar do agendamento, mas continua disponível para
execução manual.

A pausa ou reativação deve passar por PR.

## Conflitos

Conflitos funcionais fora dos arquivos administrativos interrompem a
sincronização e exigem análise humana.

Arquivos administrativos:

- `README.md`
- `CONTRIBUTING.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/ecidade-mirror.json`

Não resolver automaticamente conflitos no código do upstream.

## Workflows upstream

`.github/workflows` do upstream não é publicado na branch principal do mirror.
Isso evita executar workflows externos no contexto da organização e-Cidade.

## Credenciais

A private key do GitHub App nunca deve ser registrada em commit, issue ou log.

Após trocar a chave:

    gh secret set MIRROR_APP_PRIVATE_KEY \
      --repo e-cidade/.github < nova-chave.pem

Depois, validar com uma sincronização real. O dry-run não autentica o App.

## Recuperação

A branch principal não deve receber force push.

Após um merge incorreto:

1. criar uma branch de recuperação;
2. executar `git revert -m 1 <merge-commit>`;
3. abrir PR;
4. revisar e fazer merge normalmente.

## Novo mirror

1. validar origem e mantenedor;
2. criar o destino vazio;
3. instalar o GitHub App de mirror;
4. cadastrar com `"enabled": false`;
5. executar o bootstrap manual;
6. validar histórico, README e refs;
7. adicionar a política em `governance.config.json`;
8. aplicar a governança;
9. habilitar o mirror.

Criação de Apps, secrets, inclusão de mirrors, resolução de conflitos e
recuperações continuam exigindo intervenção humana.
