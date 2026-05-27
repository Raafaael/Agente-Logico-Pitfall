# INF1771 - Agente Logico Pitfall

Projeto do Trabalho 2 de INF1771, baseado em Pitfall e no Mundo do Wumpus. O agente usa SWI-Prolog para representar conhecimento, memoria e decisoes, enquanto o Python executa a interface grafica, consulta a base Prolog e transforma metas em movimentos.

## Requisitos

- Python 3.10 ou superior
- Dependencias Python listadas em `requirements.txt`

Instale as dependencias Python:

```bash
python3 -m pip install -r requirements.txt
```

## Como Executar

Executar com o mapa padrao:

```bash
python3 base/gmap.py
```

Executar com um mapa especifico:

```bash
python3 base/gmap.py --map maps/mapa-facil.pl
python3 base/gmap.py --map maps/mapa-medio.pl
python3 base/gmap.py --map maps/mapa-dificil.pl
```

Executar sem abrir a janela grafica:

```bash
python3 base/gmap.py --headless --map maps/mapa-facil.pl --max-steps 1000
```

Gerar um mapa aleatorio:

```bash
python3 base/gmap.py --random-map --seed 42
```

Ver todos os argumentos disponiveis:

```bash
python3 base/gmap.py --help
```

## Controles

- `Seta para cima`: andar
- `Seta esquerda`: virar para a esquerda
- `Seta direita`: virar para a direita
- `Espaco`: pegar ouro ou powerup
- `S`: sair do labirinto
- `M`: alternar exibicao do mapa conhecido/real
- `A`: ligar ou desligar autoplay

Use `--manual` para iniciar com controle manual.

## Regras do Jogo

- O mapa tem tamanho `12x12`.
- A posicao inicial e a saida ficam em `[1,1]`.
- O agente comeca com `100` pontos de energia.
- Cada acao executada custa `-1` ponto.
- Pegar ouro concede `+1000` pontos.
- Powerup recupera `20` pontos de energia, limitado ao maximo de `100`.
- Cair em um poco/obstaculo mata o agente e aplica `-1000` pontos.
- Inimigo pequeno causa `20` de dano.
- Inimigo grande causa `50` de dano.
- Morte por inimigo aplica penalidade adicional de `-1000`.
- Morcego teletransporta o agente para uma posicao aleatoria.

## Sensores

- Brisa: existe poco/obstaculo em uma casa adjacente.
- Passos: existe inimigo em uma casa adjacente.
- Flash: existe morcego/teletransporte em uma casa adjacente.
- Brilho: existe ouro na sala atual.
- Reflexo: existe powerup na sala atual.
- Impacto: o agente tentou andar contra a parede.

## Mapas

Os mapas ficam na pasta `maps/`:

- `maps/mapa.pl`
- `maps/mapa-facil.pl`
- `maps/mapa-medio.pl`
- `maps/mapa-dificil.pl`

Cada mapa define `map_size/2` e fatos `tile(X,Y,Conteudo)`.

## Estrutura

- `base/gmap.py`: interface Pygame, argumentos, autoplay, modo headless e planejamento A\*
- `base/main.pl`: base de conhecimento, memoria, regras do jogo e decisao logica
- `base/TreeNode.py`: no usado na busca A\*
- `maps/`: mapas em Prolog
- `assets/`: imagens usadas pela interface grafica
