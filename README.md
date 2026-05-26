# Agente Logico - Pitfall

## Video da apresentacao

- Link do video: `a definir`

## Integrantes

- `Breno de Andrade Soares` - Matricula: `2320363`
- `Dante Honorato Navaza` - Matricula: `2321406`
- `Rafael Soares Estevao` - Matricula: `2320470`

Implementacao do trabalho `INF1771_trabalho_2_pitfall.pdf` usando:

- `SWI-Prolog` para representar a base de conhecimento e tomar decisoes logicas.
- `A*` em Python para transformar metas da base de conhecimento em rotas no mapa.
- `Memoria de percepcoes` para deduzir salas seguras, pocos, inimigos e teletransportes.
- `Fallback Python` equivalente para executar o projeto quando `swipl` nao esta disponivel.
- `Interface grafica (GUI)` para acompanhar o agente, score, energia e conhecimento descoberto.

## Configurabilidade

Tudo que precisa ser configurado fica nos argumentos do `main.py` e nos arquivos da pasta `maps/`:

- caminho do mapa (`--map`);
- seed de mapa aleatorio (`--seed`);
- salvamento de mapa gerado (`--save-map`);
- limite de turnos (`--max-steps`);
- backend da base de conhecimento (`--kb auto`, `--kb prolog` ou `--kb python`);
- renderizacao terminal (`--render-every`, `--reveal`, `--quiet`, `--delay`);
- execucao pela interface grafica (`--gui`).

Os mapas podem ser carregados em `.pl`, `.json` ou texto puro com 12 linhas.

## Resultado


| Mapa | Backend | Score | Energia | Ouros | Powerups | Acoes |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `maps/mapa-facil.pl` | `swi-prolog` | `2734` | `100` | `3/3` | `0/3` | `267` |
| `maps/mapa-facil.pl` | `python` | `2734` | `100` | `3/3` | `0/3` | `267` |
| `maps/mapa-medio.pl` | `swi-prolog` | `2671` | `80` | `3/3` | `1/3` | `330` |
| `maps/mapa-medio.pl` | `python` | `2609` | `90` | `3/3` | `3/3` | `392` |
| `maps/mapa-dificil.pl` | `swi-prolog` | `2617` | `80` | `3/3` | `1/3` | `384` |
| `maps/mapa-dificil.pl` | `python` | `2617` | `80` | `3/3` | `1/3` | `384` |


## Regras implementadas

- Labirinto `12x12`.
- Posicao inicial e saida em `[1,1]`.
- Acoes: `andar`, `virar_a_esquerda`, `virar_a_direita`, `pegar` e `sair`.
- Score: cada acao custa `-1`, ouro vale `+1000`, poco aplica `-1000`, morte aplica `-1000`.
- Energia inicial `100`.
- Inimigo pequeno tira `20` de energia; inimigo grande tira `50` de energia.
- Ao encontrar um inimigo, ele causa dano, desaparece e o ambiente retorna a percepcao `scream` naquele turno.
- Poco encerra o jogo imediatamente.
- Teletransporte move o agente para uma sala aleatoria, inclusive outra sala perigosa.
- Powerup aparece como percepcao local e recupera ate `20` de energia ao executar `pegar`.
- Sair do labirinto e uma acao explicita: passar por `[1,1]` nao encerra o jogo sozinho.
- O agente nao consulta o mapa real para decidir.

## Estrutura

- `main.py`: ponto de entrada da aplicacao, argumentos de execucao e loop principal.
- `pitfall/types.py`: constantes, enumeracoes, acoes, percepcoes e resultado de turno.
- `pitfall/environment.py`: ambiente real do jogo, aplicacao das acoes, score, energia, dano, poco e teletransporte.
- `pitfall/agent.py`: politica do agente, controle de retorno, escolha de metas e integracao com a KB.
- `pitfall/knowledge_base.pl`: base de conhecimento em Prolog, memoria, certeza, riscos e regra `decide/1`.
- `pitfall/kb_python.py`: fallback Python que replica as regras principais da KB Prolog.
- `pitfall/prolog_bridge.py`: comunicacao com o processo `swipl` e fallback automatico.
- `pitfall/planner.py`: A* e conversao de caminhos em acoes concretas.
- `pitfall/TreeNode.py`: no de busca usado pelo planejador A*.
- `pitfall/map_loader.py`: carregamento de mapas `.pl`, `.json`, texto e geracao aleatoria.
- `pitfall/render.py`: renderizacao textual do mapa e do conhecimento do agente.
- `pitfall/gui.py`: interface grafica em Tkinter.
- `maps/`: mapas de teste fornecidos.
- `assets/`: imagens usadas pela GUI.
- `Instrucoes/`: PDF do enunciado.

## Como executar

### Configuracao inicial

Use Python `3.10+`. Nao ha dependencias Python externas obrigatorias; a GUI usa `Tkinter`, que normalmente ja vem com Python no Windows.

Opcionalmente, crie e ative um ambiente virtual:

```bash
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
```

Instale o arquivo de requisitos, mesmo ele servindo apenas como documentacao das dependencias:

```bash
pip install -r requirements.txt
```

Para rodar com Prolog, instale o `SWI-Prolog`. Se ele estiver no `PATH`, o comando abaixo deve funcionar:

```bash
swipl --version
```

### Executando a aplicacao

Para rodar um mapa fixo no terminal:

```bash
py -3 main.py --map maps/mapa-facil.pl --render-every 0
```

Para forcar o backend Prolog:

```bash
py -3 main.py --kb prolog --map maps/mapa-facil.pl --render-every 0
```

Para forcar o fallback Python:

```bash
py -3 main.py --kb python --map maps/mapa-facil.pl --render-every 0
```

Para gerar um mapa aleatorio:

```bash
py -3 main.py --seed 42
```

Para salvar um mapa aleatorio gerado:

```bash
py -3 main.py --seed 42 --save-map maps/seed-42.json
```

Para abrir a interface grafica:

```bash
py -3 main.py --gui --map maps/mapa-facil.pl
```

Para ver todas as opcoes:

```bash
py -3 main.py --help
```

## Observacoes

- `--kb auto` tenta usar `swipl`; se nao encontrar, usa `pitfall/kb_python.py`.
- `--kb prolog` falha explicitamente se o SWI-Prolog nao estiver instalado.
