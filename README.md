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

Ajustar o piso de score (aborta a partida se cair abaixo):

```bash
py main.py --min-score -800
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
- `Andar` nao consome energia por si so; energia cai ao entrar em inimigos.
- Pontuacao por acao, ouro, dano de inimigo, poco e morte.
- Powerup recupera energia ao executar `pegar` na sala; se nao for necessario
  na hora, ele permanece conhecido para uma busca posterior.
- Teletransporte pode cair em qualquer outra sala, inclusive perigo. Quando
  `--seed` e' usado, os teletransportes tambem ficam reprodutiveis.
- Agente nao consulta o mapa real para decidir.
- O planejamento de rota roda em Python sobre salas conhecidas/seguras,
  otimizando a sequencia real de acoes (andar e giros).
- Prolog representa conhecimento e tomada de decisao quando `swipl` existe.
- Fallback Python mantem o projeto executavel sem SWI-Prolog instalado.

## Inteligencia do Agente

A base de conhecimento (Python e Prolog) raciocina em camadas:

1. **Logica classica do Wumpus**: para cada percepcao ausente, marca todos os
   vizinhos como positivamente livres do perigo correspondente; para cada
   percepcao presente, marca como suspeitos os vizinhos que ainda nao foram
   provados seguros. Quando, depois de eliminar candidatos, sobra apenas um
   vizinho consistente com uma brisa/passos/flash, o perigo e' confirmado.
2. **Visita = prova**: ao sobreviver em uma sala, o agente desconfirma poco e
   teletransporte naquela celula. Inimigo permanece confirmado: o agente
   levou dano mas a sala continua hostil.
3. **Deducao por dano**: se a energia caiu apos um `andar`,
   o agente conclui que a sala em que acabou de entrar abriga um inimigo,
   mesmo sem ter passos como percepcao. O dano recebido fica associado aquela sala
   para evitar atravessar um inimigo perigoso no retorno.
4. **Deducao por teletransporte**: se um `andar` deveria terminar em uma sala
   vizinha, mas o agente acorda em outra posicao, a KB confirma que a sala
   intermediaria era um teletransporte.
5. **Planejamento em duas pistas**: `likely_safe` rege a exploracao e e' o
   filtro do A* por padrao; `walkable_for_path` permite voltar pra base
   atravessando salas conhecidas (incluindo inimigos ja revelados) quando
   nao ha corredor estritamente seguro. Em mapas dificeis, o agente tambem
   pode retrilhar inimigos visitados para escapar de bolsoes isolados quando
   ainda tem energia suficiente.
6. **Politica de decisao**:
   - pega o ouro da sala atual e guarda powerups conhecidos para usar com energia baixa;
   - persegue ouros ou powerups conhecidos atingiveis por caminhos seguros;
   - expande a fronteira segura, classificando alvos por distancia real (BFS)
     e ganho de informacao (vizinhos desconhecidos);
   - quando ja carrega ouro e o melhor passo restante e' um poco suspeito,
     desiste e volta pro portal.

## Melhorias Ja Incluidas

- Inferencia de perigos confirmados quando uma percepcao aponta para um unico
  vizinho possivel.
- Politica de risco quando nao ha fronteira segura: evita poco confirmado e
  prefere riscos menores.
- Agente recua quando tem ouro suficiente, esta com energia baixa, ou quando
  a unica opcao restante e' um poco provavel.
- Caminho de volta pela trilha visitada quando o corredor seguro foi cortado.
- Planejador orientado por direcao: entre rotas com o mesmo numero de salas,
  prefere a que usa menos giros e portanto perde menos score.
- Fallback contra planos impossiveis: se a KB escolhe um alvo sem rota
  executavel, o agente troca para retorno ao portal em vez de gastar turnos
  tentando sair fora da base.
- Ultimo recurso contra bolsao isolado: se nao ha rota segura e a
  alternativa e' abortar, o agente pode apostar em uma fronteira de inimigo
  alcancavel, evitando pocos e teletransportes.
- Inferencia explicita de teletransportes quando a posicao final do movimento
  nao corresponde a sala vizinha esperada.
- Geracao aleatoria com vizinhanca de [1,1] sempre livre de perigos, para que
  a primeira percepcao do agente seja sempre informativa.
- GUI mostra o plano A* atual sobre o tabuleiro e a decisao corrente da KB,
  alem dos modos automatico e manual.

## Limitacoes

- Nao ha acao explicita de ataque no enunciado; por isso o sensor `scream`
  fica reservado para uma extensao futura.
- Se o SWI-Prolog nao estiver instalado, o backend usado sera Python.
- A politica de risco melhora a exploracao, mas ainda nao garante vitoria em
  todos os mapas aleatorios -- alguns isolam ouros atras de teleportes.
