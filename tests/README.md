# Testes do bot

```bash
pip install -r requirements-test.txt
pytest                                   # tudo (~12s)
pytest -m "not performance and not property"   # só os rápidos
pytest --cov=main --cov=ai --cov=racas --cov-branch --cov-report=term-missing
```

Nenhum teste usa rede, Discord, Google ou Groq: tudo é simulado (`conftest.py`).

| Arquivo | Tipo | O que cobre |
|---|---|---|
| `test_planilha_leitura.py` | unitário | parsing da tabela, cabeçalhos variados, conexão com o Google (arquivo/env/erros) |
| `test_planilha_escrita.py` | unitário + **regressão** | `posse`/`ingerir`/`cuspir`, **erro 403 do log**, aprovação da staff |
| `test_planilha_comandos.py` | unitário | `enc` (paginação por reação), `fruta`, `check_pool` |
| `test_persistencia.py` | unitário | `mensagens.json`, cache, backoff de login, `main()` e tratamento do 429 |
| `test_mercado.py` | unitário | sorteio com histórico, textos das lojas, `run_update`, `auto_update`, `proxima` |
| `test_comandos_staff.py` | unitário + contrato | todos os comandos da staff, permissões, `ajuda`, `on_command_error`, startup |
| `test_ai.py` | unitário | Groq, prompt, comando `chat`, resposta ao ser marcado |
| `test_racas.py` | unitário + concorrência | rolagem d100, tickets, **race conditions**, permissões |
| `test_integracao.py` | integração | mensagem → `get_context` → `invoke` reais, ponta a ponta |
| `test_propriedades.py` | propriedades (hypothesis) | entradas aleatórias contra invariantes |
| `test_desempenho.py` | desempenho | limites de tempo e event loop não bloqueado |
| `test_estatico.py` | estático/contrato | sintaxe, segredos no código, imports vs requirements, limites do Discord |

## `xfail(strict=True)` = bug conhecido

Testes marcados assim documentam um defeito real ainda não corrigido. Quando o bug for
corrigido o teste passa a "XPASS" e **falha de propósito**: é o sinal para remover o marcador.

## Ao criar um comando novo

- Adicione-o em `COMANDOS_ESPERADOS` (`test_integracao.py`) e em `STAFF_CMDS` se for da staff.
- Documente em `doffy!ajuda` (`test_todo_comando_publico_novo_precisa_estar_na_ajuda` avisa).
