# Agente Logico Pitfall

Trabalho em SWI-Prolog + Python/PySwip para o agente logico do Pitfall.

## Requisitos

- Python 3
- SWI-Prolog instalado e disponivel no PATH
- Dependencias Python em `requirements.txt`

Instalacao:

```powershell
py -m pip install -r requirements.txt
```

## Como rodar

Modo grafico:

```powershell
py base\gmap.py --map maps\mapa.pl
```

Modo terminal:

```powershell
py base\gmap.py --headless --map maps\mapa-medio.pl
```

Mapa aleatorio:

```powershell
py base\gmap.py --headless --random-map --seed 42
```

## Observacao

`tile/3` representa o ambiente real usado para sensores e eventos. A decisao do agente usa a memoria e as inferencias do Prolog, como `memory/3`, `visitado/2`, `certeza/2`, `seguro/2` e `meta_candidata/4`.
