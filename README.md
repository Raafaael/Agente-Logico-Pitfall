# INF1771 - Trabalho 2: Agente Logico Pitfall

Implementacao de um agente logico para o jogo Pitfall, desenvolvida para a
disciplina INF1771. O projeto e inspirado no Mundo de Wumpus: o agente precisa
explorar um labirinto desconhecido, interpretar percepcoes do ambiente, evitar
perigos, coletar os ouros e retornar vivo para a saida.

No codigo atual, a parte logica fica em SWI-Prolog e a execucao visual fica em
Python com Pygame. O agente nao usa o mapa real para decidir; ele construiu uma
memoria propria a partir dos sensores, como pede o enunciado.

## Apresentacao

### Video

- Link do video: `https://drive.google.com/file/d/1nZIxE9kbBYjdpDB6WbXqk5eOo5Yfbm0C/view?usp=drive_link`

### Integrantes

| Nome | Matricula |
| --- | --- |
| Breno de Andrade Soares | 2320363 |
| Dante Honorato Navaza | 2321406 |
| Rafael Soares Estevao | 2320470 |

## Objetivo do agente

O agente controla o personagem dentro de um mapa `12x12`. Ele inicia na posicao
`[1,1]`, que tambem e a saida do labirinto. Para vencer, precisa:

1. explorar o ambiente;
2. coletar os `3` ouros;
3. evitar pocos, inimigos e teletransportes sempre que possivel;
4. voltar para `[1,1]`;
5. executar a acao `sair`.

Durante a partida, o agente recebe percepcoes locais e inferencias sobre casas
vizinhas. Ele nao conhece previamente a posicao real dos perigos.

## O que esta implementado

- Mapa `12x12`.
- Posicao inicial e saida em `[1,1]`.
- Energia inicial de `100`.
- Tres ouros obrigatorios para finalizar a partida.
- Tres powerups de energia em mapas aleatorios.
- Oito pocos/obstaculos em mapas aleatorios.
- Quatro teletransportes em mapas aleatorios.
- Dois inimigos pequenos, com `20` de dano.
- Dois inimigos grandes, com `50` de dano.
- Pontuacao com custo de acao, recompensa por ouro e penalidades por dano/morte.
- Base de conhecimento em Prolog.
- Memoria de percepcoes e certezas do agente.
- Tomada de decisao em Prolog por metas candidatas.
- Planejamento de caminho com A* em Python.
- Interface grafica com Pygame.
- Modo automatico, modo manual e modo terminal sem interface.
- Leitura de mapas `.pl` e geracao de mapas aleatorios.

## Arquitetura

O projeto esta dividido em tres partes principais:

| Arquivo | Responsabilidade |
| --- | --- |
| `base/gmap.py` | Ponto de entrada do programa. Carrega mapas, inicia Pygame, consulta o Prolog, executa o agente automatico, trata teclado, roda modo terminal e usa A*. |
| `base/main.pl` | Base logica do agente. Guarda estado, memoria, percepcoes, regras do jogo, inferencias e metas de decisao. |
| `base/TreeNode.py` | Estrutura auxiliar usada pelo A* para reconstruir caminhos. |

Pastas auxiliares:

- `maps/`: mapas de teste em Prolog.
- `assets/`: imagens usadas na interface grafica.
- `requirements.txt`: dependencias Python (`pygame` e `pyswip`).

## Requisitos

- Python `3.10+`.
- SWI-Prolog instalado.
- Dependencias Python do arquivo `requirements.txt`.

No PowerShell, a configuracao recomendada e:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Verifique se o SWI-Prolog esta disponivel:

```powershell
swipl --version
```

Se o comando acima nao funcionar, instale o SWI-Prolog e confirme que ele esta
no `PATH` do Windows.

## Como executar no PowerShell

### Interface grafica com o mapa padrao

```powershell
python .\base\gmap.py
```

### Interface grafica com mapa especifico

```powershell
python .\base\gmap.py --map .\maps\mapa-facil.pl
python .\base\gmap.py --map .\maps\mapa-medio.pl
python .\base\gmap.py --map .\maps\mapa-dificil.pl
```

### Modo manual

```powershell
python .\base\gmap.py --manual --map .\maps\mapa-facil.pl
```

### Mostrar o mapa real desde o inicio

```powershell
python .\base\gmap.py --show-map --map .\maps\mapa-facil.pl
```

Esse modo revela os elementos reais do mapa. Ele e util para debug e
apresentacao, mas nao representa a informacao disponivel para o agente.

### Modo terminal sem interface

```powershell
python .\base\gmap.py --headless --map .\maps\mapa-facil.pl --max-steps 1000
```

### Modo terminal com rastreamento das acoes

```powershell
python .\base\gmap.py --headless --trace --map .\maps\mapa-facil.pl --max-steps 1000
```

### Gerar mapa aleatorio

```powershell
python .\base\gmap.py --random-map --seed 42
```

### Ver a ajuda do programa

```powershell
python .\base\gmap.py --help
```

## Argumentos disponiveis

| Argumento | Funcao |
| --- | --- |
| `--map` | Carrega um arquivo `.pl` com fatos `tile/3`. |
| `--random-map` | Gera um mapa aleatorio com as quantidades do enunciado. |
| `--seed` | Fixa a aleatoriedade para repetir testes. |
| `--manual` | Inicia com o autoplay desligado. |
| `--delay` | Define o intervalo entre acoes automaticas. |
| `--show-map` | Mostra o mapa real em vez da memoria do agente. |
| `--headless` | Executa somente no terminal. |
| `--max-steps` | Define o limite de acoes no modo terminal. |
| `--trace` | Mostra o estado antes e depois de cada acao no terminal. |

## Controles da interface

| Tecla | Acao |
| --- | --- |
| `A` | Liga ou desliga o autoplay. |
| `Seta para cima` | Anda uma casa para frente no modo manual. |
| `Seta esquerda` | Vira para a esquerda no modo manual. |
| `Seta direita` | Vira para a direita no modo manual. |
| `Espaco` | Pega ouro ou powerup na casa atual. |
| `S` | Tenta sair do labirinto. |
| `M` | Alterna entre mapa conhecido e mapa real. |

## Sensores do agente

O agente interpreta as seguintes percepcoes:

| Percepcao | Significado |
| --- | --- |
| `brisa` | Ha um poco/obstaculo em alguma casa adjacente. |
| `passos` | Ha um inimigo pequeno ou grande em alguma casa adjacente. |
| `flash` | Ha um teletransporte em alguma casa adjacente. |
| `brilho` | Ha ouro na casa atual. |
| `reflexo` | Ha powerup na casa atual. |
| `impacto` | O agente tentou andar contra uma parede. |

As percepcoes alimentam `memory/3` no Prolog. A partir dessa memoria, o agente
marca casas como visitadas, suspeitas, seguras ou confirmadas.

## Pontuacao e eventos

| Evento | Efeito |
| --- | --- |
| Qualquer acao | `-1` ponto. |
| Pegar ouro | `+1000` pontos. |
| Pegar powerup | Recupera ate `20` de energia. |
| Cair em poco | Morte imediata e penalidade de `-1000`. |
| Inimigo pequeno | `20` de dano e perda equivalente na pontuacao. |
| Inimigo grande | `50` de dano e perda equivalente na pontuacao. |
| Morrer por dano | Penalidade adicional de `-1000`. |
| Teletransporte | Move o agente para uma casa aleatoria. |
| Sair com 3 ouros | Encerra a partida com sucesso. |

## Mapas

Os mapas disponiveis no repositorio sao:

- `maps/mapa.pl`
- `maps/mapa-facil.pl`
- `maps/mapa-medio.pl`
- `maps/mapa-dificil.pl`

Cada mapa e um arquivo Prolog com fatos no formato:

```prolog
tile(X, Y, Conteudo).
```

Simbolos aceitos:

| Simbolo | Conteudo |
| --- | --- |
| `'P'` | Poco/obstaculo. |
| `'T'` | Teletransporte. |
| `'D'` | Inimigo grande. |
| `'d'` | Inimigo pequeno. |
| `'O'` | Ouro. |
| `'U'` | Powerup. |
| `''` | Casa vazia. |

## Resultados atuais

Resultados obtidos com o codigo atual usando `--headless` e `--max-steps 1000`.
Todos os mapas abaixo foram concluidos com sucesso, retornando para `[1,1]`
apos coletar os `3` ouros.

| Mapa | Status | Passos | Energia final | Pontuacao | Ouros | Posicao final |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `maps/mapa-facil.pl` | `saiu` | `365` | `100` | `2636` | `3` | `(1,1)` |
| `maps/mapa-medio.pl` | `saiu` | `431` | `100` | `2530` | `3` | `(1,1)` |
| `maps/mapa-dificil.pl` | `saiu` | `437` | `100` | `2564` | `3` | `(1,1)` |

## Testes rapidos no PowerShell

Para validar os mapas fixos sem abrir a interface:

```powershell
python .\base\gmap.py --headless --map .\maps\mapa.pl --max-steps 1000
python .\base\gmap.py --headless --map .\maps\mapa-facil.pl --max-steps 1000
python .\base\gmap.py --headless --map .\maps\mapa-medio.pl --max-steps 1000
python .\base\gmap.py --headless --map .\maps\mapa-dificil.pl --max-steps 1000
```

Para testar varios mapas aleatorios:

```powershell
foreach ($seed in 1..10) {
    python .\base\gmap.py --headless --random-map --seed $seed --max-steps 1000
}
```

Um teste bem-sucedido termina com uma linha parecida com:

```text
resultado status=saiu passos=365 energia=100 pontuacao=2636 ouros=3 pos=(1,1)
```

O valor exato de passos e pontuacao pode variar conforme o mapa, mas
`status=saiu` e `ouros=3` indicam que o agente completou o objetivo.
