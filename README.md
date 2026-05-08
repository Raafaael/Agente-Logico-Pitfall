# Agente Logico - Pitfall (INF1771)

Agente logico inspirado no Mundo de Wumpus/Pitfall, desenvolvido em
Python + SWI-Prolog para a disciplina INF1771.

O agente explora um labirinto 12x12 usando apenas percepcoes: brisa, passos,
flash, brilho e impacto. O mapa real fica isolado no ambiente Python; a base de
conhecimento em Prolog, ou o fallback Python equivalente, decide o que fazer a
partir do que o agente ja percebeu.

## Estrutura

```text
.
|-- main.py
|-- requirements.txt
|-- pitfall/
|   |-- types.py
|   |-- environment.py
|   |-- map_loader.py
|   |-- planner.py
|   |-- agent.py
|   |-- prolog_bridge.py
|   |-- kb_python.py
|   |-- knowledge_base.pl
|   |-- render.py
|   `-- gui.py
|-- maps/
|   |-- mapa.pl
|   |-- mapa-facil.pl
|   |-- mapa-medio.pl
|   `-- mapa-dificil.pl
|-- assets/
`-- Instrucoes/
    `-- INF1771_trabalho_2_pitfall.pdf
```

## Requisitos

- Python 3.10+
- SWI-Prolog opcional, com `swipl` no PATH

Sem dependencias Python externas obrigatorias. A GUI usa Tkinter, que
normalmente ja vem com Python no Windows.

Se `python` nao estiver configurado no Windows, use `py` nos comandos.

## Como Rodar

Mapa aleatorio:

```bash
py main.py --seed 42
```

Interface grafica:

```bash
py main.py --gui
```

Interface grafica com mapa carregado:

```bash
py main.py --gui --map maps/mapa-facil.pl --reveal
```

Mapa Prolog/manual:

```bash
py main.py --map maps/mapa.pl
```

Forcar fallback Python:

```bash
py main.py --kb python --map maps/mapa.pl
```

Ver opcoes:

```bash
py main.py --help
```

## GUI

A GUI permite:

- executar o agente passo a passo;
- rodar e pausar a execucao automatica;
- controlar manualmente o personagem;
- carregar mapas `.json`, `.txt` e `.pl`;
- gerar novo mapa aleatorio;
- alternar visualizacao entre conhecimento do agente e mapa real;
- acompanhar posicao, direcao, energia, score, percepcoes, acao e historico.

Atalhos:

- seta para cima: andar;
- seta esquerda/direita: virar;
- espaco: pegar;
- Enter: passo automatico do agente.

## Formatos de Mapa

JSON com grade:

```json
{
  "size": 12,
  "start": [1, 1],
  "initial_direction": "east",
  "grid": [
    "............",
    "....O.......",
    "............",
    "............",
    "............",
    "............",
    "............",
    "............",
    "............",
    "............",
    "............",
    "............"
  ]
}
```

JSON com lista de celulas:

```json
{
  "size": 12,
  "start": [1, 1],
  "initial_direction": "east",
  "cells": [
    {"pos": [2, 5], "type": "gold"},
    {"pos": [4, 3], "type": "pit"}
  ]
}
```

Texto puro tambem funciona: 12 linhas com 12 simbolos cada.

Simbolos aceitos:

- `.` ou `S`: vazio;
- `P`: poco/obstaculo;
- `d`: inimigo pequeno, dano 20;
- `D`: inimigo grande, dano 50;
- `T`: teletransporte;
- `O`: ouro;
- `U`: powerup.

Mapas `.pl` no formato `tile(X, Y, 'O').` tambem sao carregados.

## Regras Implementadas

- Labirinto 12x12.
- Energia inicial 100.
- Geracao aleatoria com 2 inimigos pequenos, 2 grandes, 4 teletransportes,
  8 pocos, 3 ouros e 3 powerups.
- Pontuacao por acao, ouro, poco e morte.
- Powerup recupera energia automaticamente ao entrar na sala.
- Teletransporte pode cair em qualquer outra sala, inclusive perigo.
- Agente nao consulta o mapa real para decidir.
- A* roda em Python sobre salas conhecidas/seguras.
- Prolog representa conhecimento e tomada de decisao quando `swipl` existe.
- Fallback Python mantem o projeto executavel sem SWI-Prolog instalado.

## Melhorias Ja Incluidas

- Inferencia de perigos confirmados quando uma percepcao aponta para um unico
  vizinho possivel.
- Politica de risco quando nao ha fronteira segura: evita poco confirmado e
  prefere riscos menores.
- Agente so volta para sair quando tem os 3 ouros, ou quando tem ouro e energia
  baixa.
- GUI com modo automatico e modo manual.
- Documentacao centralizada apenas neste README.

## Limitacoes

- Nao ha acao explicita de ataque no enunciado; por isso o sensor `scream`
  fica reservado para uma extensao futura.
- Se o SWI-Prolog nao estiver instalado, o backend usado sera Python.
- A politica de risco melhora a exploracao, mas ainda nao garante vitoria em
  todos os mapas aleatorios.
