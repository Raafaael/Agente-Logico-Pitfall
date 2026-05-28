:- use_module(library(lists)).

:- dynamic posicao/3.
:- dynamic memory/3.
:- dynamic visitado/2.
:- dynamic certeza/2.
:- dynamic certeza_tipo/3.
:- dynamic observado/3.
:- dynamic energia/1.
:- dynamic pontuacao/1.
:- dynamic ouros_coletados/1.
:- dynamic fim/1.
:- dynamic impacto/0.
:- dynamic entrada_em/2.
:- dynamic tile/3.
:- dynamic map_size/2.

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% Utilitarios gerais
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

total_ouros(3).
energia_inicial(100).

map_size_default(12,12).

tamanho_mapa(SX,SY) :- map_size(SX,SY), !.
tamanho_mapa(SX,SY) :- map_size_default(SX,SY).

dentro_mapa(X,Y) :-
    tamanho_mapa(SX,SY),
    between(1,SX,X),
    between(1,SY,Y).

assert_unico(Fato) :- call(Fato), !.
assert_unico(Fato) :- assertz(Fato).

vivo :-
    posicao(_,_,D),
    D \= morto,
    D \= saiu.

limpa_eventos :-
    retractall(impacto),
    retractall(entrada_em(_,_)).

direita(norte,leste).
direita(leste,sul).
direita(sul,oeste).
direita(oeste,norte).

esquerda(norte,oeste).
esquerda(oeste,sul).
esquerda(sul,leste).
esquerda(leste,norte).

delta(norte,0,1).
delta(sul,0,-1).
delta(leste,1,0).
delta(oeste,-1,0).

manhattan(X1,Y1,X2,Y2,D) :-
    D is abs(X1-X2) + abs(Y1-Y2).

marca_visitado(X,Y) :-
    assert_unico(visitado(X,Y)),
    assert_unico(certeza(X,Y)).

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% Estado do jogo
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

reset_game :-
    retractall(memory(_,_,_)),
    retractall(visitado(_,_)),
    retractall(certeza(_,_)),
    retractall(certeza_tipo(_,_,_)),
    retractall(observado(_,_,_)),
    retractall(energia(_)),
    retractall(pontuacao(_)),
    retractall(posicao(_,_,_)),
    retractall(ouros_coletados(_)),
    retractall(fim(_)),
    limpa_eventos,
    energia_inicial(E),
    assertz(energia(E)),
    assertz(pontuacao(0)),
    assertz(ouros_coletados(0)),
    assertz(posicao(1,1,norte)),
    marca_visitado(1,1),
    set_real(1,1).

atualiza_pontuacao(X) :-
    pontuacao(P),
    retract(pontuacao(P)),
    NP is P + X,
    assertz(pontuacao(NP)), !.

atualiza_energia(N) :-
    energia(E),
    retract(energia(E)),
    NE is E + N,
    (
        NE =< 0
    ->  assertz(energia(0)),
        mata_jogador
    ;   energia_inicial(MAX),
        (
            NE > MAX
        ->  assertz(energia(MAX))
        ;   assertz(energia(NE))
        )
    ), !.

mata_jogador :-
    posicao(X,Y,_),
    retractall(posicao(_,_,_)),
    assertz(posicao(X,Y,morto)),
    assert_unico(fim(morto)), !.

aplica_dano(Dano) :-
    atualiza_pontuacao(-Dano),
    atualiza_energia(-Dano),
    ( vivo -> true ; atualiza_pontuacao(-1000) ).

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% Verificacao de eventos da sala atual
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

verifica_player :- \+ vivo, !.

verifica_player :-
    posicao(X,Y,_),
    tile(X,Y,'P'),
    atualiza_energia(-100),
    atualiza_pontuacao(-1000), !.

verifica_player :-
    posicao(X,Y,_),
    tile(X,Y,'D'),
    entrada_em(X,Y),
    retractall(entrada_em(X,Y)),
    aplica_dano(50),
    set_real(X,Y), !.

verifica_player :-
    posicao(X,Y,_),
    tile(X,Y,'d'),
    entrada_em(X,Y),
    retractall(entrada_em(X,Y)),
    aplica_dano(20),
    set_real(X,Y), !.

verifica_player :-
    posicao(X,Y,D),
    tile(X,Y,'T'),
    teletransporta(X,Y,D), !.

verifica_player :- true.

teletransporta(X,Y,D) :-
    set_real(X,Y),
    tamanho_mapa(SX,SY),
    random_between(1,SX,NX),
    random_between(1,SY,NY),
    retractall(posicao(_,_,_)),
    assertz(posicao(NX,NY,D)),
    assertz(entrada_em(NX,NY)),
    marca_visitado(NX,NY),
    set_real(NX,NY),
    atualiza_obs,
    verifica_player.

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% Comandos
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

virar_direita :-
    vivo,
    limpa_eventos,
    posicao(X,Y,D),
    direita(D,ND),
    retractall(posicao(_,_,_)),
    assertz(posicao(X,Y,ND)),
    atualiza_pontuacao(-1), !.

virar_esquerda :-
    vivo,
    limpa_eventos,
    posicao(X,Y,D),
    esquerda(D,ND),
    retractall(posicao(_,_,_)),
    assertz(posicao(X,Y,ND)),
    atualiza_pontuacao(-1), !.

andar :-
    vivo,
    limpa_eventos,
    posicao(X,Y,D),
    delta(D,DX,DY),
    NX is X + DX,
    NY is Y + DY,
    (
        dentro_mapa(NX,NY)
    ->  retractall(posicao(_,_,_)),
        assertz(posicao(NX,NY,D)),
        assertz(entrada_em(NX,NY)),
        marca_visitado(NX,NY),
        set_real(NX,NY),
        atualiza_pontuacao(-1)
    ;   assertz(impacto),
        atualiza_pontuacao(-1)
    ), !.

pegar :-
    vivo,
    limpa_eventos,
    posicao(X,Y,_),
    tile(X,Y,'O'),
    retractall(tile(X,Y,_)),
    assertz(tile(X,Y,'')),
    ouros_coletados(N),
    retract(ouros_coletados(N)),
    N1 is N + 1,
    assertz(ouros_coletados(N1)),
    atualiza_pontuacao(-1),
    atualiza_pontuacao(1000),
    set_real(X,Y), !.

pegar :-
    vivo,
    limpa_eventos,
    posicao(X,Y,_),
    tile(X,Y,'U'),
    retractall(tile(X,Y,_)),
    assertz(tile(X,Y,'')),
    atualiza_pontuacao(-1),
    atualiza_energia(20),
    set_real(X,Y), !.

pegar :-
    vivo,
    limpa_eventos,
    atualiza_pontuacao(-1), !.

sair :-
    vivo,
    posicao(1,1,_),
    ouros_coletados(N),
    total_ouros(T),
    N >= T,
    retractall(posicao(_,_,_)),
    assertz(posicao(1,1,saiu)),
    assert_unico(fim(saiu)), !.

sair :-
    vivo,
    atualiza_pontuacao(-1), !.

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% Observacao e memoria
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

adjacente(X,Y) :-
    posicao(PX,Y,_),
    tamanho_mapa(SX,_),
    PX < SX,
    X is PX + 1.
adjacente(X,Y) :-
    posicao(PX,Y,_),
    PX > 1,
    X is PX - 1.
adjacente(X,Y) :-
    posicao(X,PY,_),
    tamanho_mapa(_,SY),
    PY < SY,
    Y is PY + 1.
adjacente(X,Y) :-
    posicao(X,PY,_),
    PY > 1,
    Y is PY - 1.

adjacente_pos(X,Y,NX,Y) :-
    NX is X + 1,
    dentro_mapa(NX,Y).
adjacente_pos(X,Y,NX,Y) :-
    NX is X - 1,
    dentro_mapa(NX,Y).
adjacente_pos(X,Y,X,NY) :-
    NY is Y + 1,
    dentro_mapa(X,NY).
adjacente_pos(X,Y,X,NY) :-
    NY is Y - 1,
    dentro_mapa(X,NY).

adjacentes(L) :-
    findall(Z,(adjacente(X,Y), tile(X,Y,Z)), L).

observacao_adj(brisa,L) :- member('P',L).
observacao_adj(flash,L) :- member('T',L).
observacao_adj(passos,L) :- member('D',L).
observacao_adj(passos,L) :- member('d',L).

atualiza_obs :-
    posicao(X,Y,_),
    marca_visitado(X,Y),
    adj_cand_obs(LP),
    observacoes(LO),
    registra_observacao(X,Y,LO),
    iter_pos_list(LP,LO),
    propaga_certezas,
    observacao_certeza,
    observacao_vazia.

registra_observacao(X,Y,LO) :-
    retractall(observado(X,Y,_)),
    assertz(observado(X,Y,LO)).

adj_cand_obs(L) :-
    findall((X,Y), (adjacente(X,Y), \+ visitado(X,Y)), L).

observacoes(X) :-
    adjacentes(L),
    findall(Y, observacao_adj(Y,L), X).

iter_pos_list([], _) :- !.
iter_pos_list([H|T], LO) :-
    H = (X,Y),
    (
        corrige_observacoes_antigas(X,Y,LO), !
    ;   adiciona_observacoes(X,Y,LO)
    ),
    iter_pos_list(T,LO).

corrige_observacoes_antigas(X,Y,[]) :-
    \+ certeza(X,Y),
    memory(X,Y,[]).

corrige_observacoes_antigas(X,Y,LO) :-
    \+ certeza(X,Y),
    \+ memory(X,Y,[]),
    memory(X,Y,LM),
    intersection(LO,LM,L),
    retract(memory(X,Y,LM)),
    assertz(memory(X,Y,L)).

adiciona_observacoes(X,Y,_) :- certeza(X,Y), !.
adiciona_observacoes(X,Y,LO) :-
    \+ certeza(X,Y),
    \+ memory(X,Y,_),
    assertz(memory(X,Y,LO)).

observacao_certeza :-
    observacao_certeza(brisa),
    observacao_certeza(flash),
    observacao_certeza(passos).

observacao_certeza(Z) :-
    posicao(VX,VY,_),
    \+ observacao_satisfeita(Z,VX,VY),
    findall(
        (X,Y),
        (
            adjacente(X,Y),
            \+ visitado(X,Y),
            \+ certeza(X,Y),
            memory(X,Y,[Z])
        ),
        L
    ),
    (
        L = [(XX,YY)]
    ->  confirma_obs(XX,YY,Z)
    ;   true
    ).

propaga_certezas :-
    propaga_certezas(brisa),
    propaga_certezas(flash),
    propaga_certezas(passos).

propaga_certezas(Z) :-
    observado(VX,VY,LO),
    member(Z,LO),
    \+ observacao_satisfeita(Z,VX,VY),
    findall(
        (X,Y),
        (
            adjacente_pos(VX,VY,X,Y),
            \+ visitado(X,Y),
            \+ certeza(X,Y),
            memory(X,Y,M),
            member(Z,M)
        ),
        L
    ),
    (
        L = [(XX,YY)]
    ->  confirma_obs(XX,YY,Z)
    ;   true
    ),
    fail.

propaga_certezas(_).

observacao_satisfeita(Z,VX,VY) :-
    adjacente_pos(VX,VY,X,Y),
    certeza_tipo(X,Y,Z).

observacao_vazia :-
    findall((X,Y), (memory(X,Y,[]), \+ certeza(X,Y)), LP),
    observacao_vazia(LP).

observacao_vazia([]) :- !.
observacao_vazia([(X,Y)|T]) :-
    assert_unico(certeza(X,Y)),
    observacao_vazia(T).

set_real(X,Y) :-
    assert_unico(certeza(X,Y)),
    set_real2(X,Y), !.

set_real2(X,Y) :-
    tile(X,Y,'P'),
    confirma_real(X,Y,brisa), !.
set_real2(X,Y) :-
    tile(X,Y,'O'),
    atualiza_memoria_real(X,Y,[brilho]), !.
set_real2(X,Y) :-
    tile(X,Y,'T'),
    confirma_real(X,Y,flash), !.
set_real2(X,Y) :-
    (tile(X,Y,'D') ; tile(X,Y,'d')),
    confirma_real(X,Y,passos), !.
set_real2(X,Y) :-
    tile(X,Y,'U'),
    atualiza_memoria_real(X,Y,[reflexo]), !.
set_real2(X,Y) :-
    atualiza_memoria_real(X,Y,[]), !.

atualiza_memoria_real(X,Y,Info) :-
    retractall(memory(X,Y,_)),
    assertz(memory(X,Y,Info)).

confirma_real(X,Y,Z) :-
    atualiza_memoria_real(X,Y,[Z]),
    assert_unico(certeza_tipo(X,Y,Z)).

confirma_obs(X,Y,Z) :-
    atualiza_memoria_real(X,Y,[Z]),
    assert_unico(certeza(X,Y)),
    assert_unico(certeza_tipo(X,Y,Z)).

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% Predicados de conhecimento usados pelo A* em Python
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

conteudo_memoria(X,Y,M) :- memory(X,Y,M), !.
conteudo_memoria(_,_,[]).

tem_obs(X,Y,Obs) :-
    memory(X,Y,M),
    member(Obs,M).

seguro(X,Y) :-
    dentro_mapa(X,Y),
    memory(X,Y,M),
    \+ member(brisa,M),
    \+ member(passos,M),
    \+ member(flash,M).

fronteira_segura(X,Y) :-
    seguro(X,Y),
    \+ visitado(X,Y).

poco_confirmado(X,Y) :-
    certeza_tipo(X,Y,brisa),
    tem_obs(X,Y,brisa).

inimigo_confirmado(X,Y) :-
    certeza_tipo(X,Y,passos),
    tem_obs(X,Y,passos).

teleporte_confirmado(X,Y) :-
    certeza_tipo(X,Y,flash),
    tem_obs(X,Y,flash).

risco_poco(X,Y) :-
    \+ visitado(X,Y),
    tem_obs(X,Y,brisa).

risco_inimigo(X,Y) :-
    \+ visitado(X,Y),
    tem_obs(X,Y,passos).

risco_teleporte(X,Y) :-
    \+ visitado(X,Y),
    tem_obs(X,Y,flash).

arriscado(X,Y) :-
    risco_poco(X,Y)
    ; risco_inimigo(X,Y)
    ; risco_teleporte(X,Y)
    ; poco_confirmado(X,Y)
    ; inimigo_confirmado(X,Y)
    ; teleporte_confirmado(X,Y).

fronteira_arriscada(X,Y) :-
    dentro_mapa(X,Y),
    \+ visitado(X,Y),
    \+ seguro(X,Y),
    \+ poco_confirmado(X,Y),
    \+ inimigo_confirmado(X,Y),
    \+ teleporte_confirmado(X,Y),
    (
        visitado(VX,VY)
    ;   certeza(VX,VY)
    ),
    adjacente_pos(VX,VY,X,Y).

risco_score(X,Y,10000) :- poco_confirmado(X,Y), !.
risco_score(X,Y,Score) :-
    conteudo_memoria(X,Y,M),
    (member(brisa,M) -> suporte_obs(brisa,X,Y,SB), B is 900 * max(1,SB) ; B = 0),
    (member(passos,M) -> suporte_obs(passos,X,Y,SP), P is 700 * max(1,SP) ; P = 0),
    (member(flash,M) -> suporte_obs(flash,X,Y,ST), T is 900 * max(1,ST) ; T = 0),
    (inimigo_confirmado(X,Y) -> IC = 3000 ; IC = 0),
    (teleporte_confirmado(X,Y) -> TC = 3500 ; TC = 0),
    Score is 10 + B + P + T + IC + TC.

suporte_obs(Z,X,Y,N) :-
    findall(
        1,
        (
            observado(VX,VY,LO),
            member(Z,LO),
            adjacente_pos(VX,VY,X,Y)
        ),
        L
    ),
    length(L,N).

sem_alvo_seguro :-
    \+ fronteira_segura(_,_),
    \+ (
        ouro_conhecido(X,Y),
        posicao(PX,PY,_),
        (X =\= PX ; Y =\= PY)
    ),
    \+ (
        powerup_conhecido(X,Y),
        posicao(PX,PY,_),
        (X =\= PX ; Y =\= PY)
    ).

ganho_info(X,Y,G) :-
    findall(
        1,
        (
            adjacente_pos(X,Y,NX,NY),
            \+ visitado(NX,NY)
        ),
        L
    ),
    length(L,G).

ouro_conhecido(X,Y) :-
    tem_obs(X,Y,brilho),
    seguro(X,Y).

powerup_conhecido(X,Y) :-
    tem_obs(X,Y,reflexo),
    seguro(X,Y).

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% Tomada de decisao em Prolog
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

meta_candidata(pegar,0,0,-100000) :-
    posicao(X,Y,_),
    ouro_conhecido(X,Y), !.

meta_candidata(pegar,0,0,-90000) :-
    posicao(X,Y,_),
    powerup_conhecido(X,Y),
    energia(E),
    E =< 80, !.

meta_candidata(sair,1,1,-80000) :-
    posicao(1,1,_),
    ouros_coletados(N),
    total_ouros(T),
    N >= T, !.

meta_candidata(mover,1,1,-70000) :-
    posicao(X,Y,_),
    (X =\= 1 ; Y =\= 1),
    ouros_coletados(N),
    total_ouros(T),
    N >= T, !.

meta_candidata(mover,X,Y,Custo) :-
    posicao(PX,PY,_),
    inimigo_confirmado(PX,PY),
    adjacente_pos(PX,PY,X,Y),
    (
        seguro(X,Y)
    ;   visitado(X,Y)
    ),
    \+ poco_confirmado(X,Y),
    \+ inimigo_confirmado(X,Y),
    \+ teleporte_confirmado(X,Y),
    manhattan(X,Y,1,1,D),
    Custo is -55000 + D.

meta_candidata(mover,X,Y,Custo) :-
    posicao(PX,PY,_),
    ouro_conhecido(X,Y),
    (X =\= PX ; Y =\= PY),
    manhattan(PX,PY,X,Y,D),
    Custo is -60000 + D.

meta_candidata(mover,X,Y,Custo) :-
    energia(E),
    E =< 50,
    posicao(PX,PY,_),
    powerup_conhecido(X,Y),
    (X =\= PX ; Y =\= PY),
    manhattan(PX,PY,X,Y,D),
    Custo is -30000 + D.

meta_candidata(mover,X,Y,Custo) :-
    posicao(PX,PY,_),
    fronteira_segura(X,Y),
    manhattan(PX,PY,X,Y,D),
    ganho_info(X,Y,G),
    Custo is D * 5 - G * 3.

meta_candidata(mover,X,Y,Custo) :-
    posicao(PX,PY,_),
    fronteira_arriscada(X,Y),
    risco_score(X,Y,R),
    R < 10000,
    (
        energia(E),
        E =< 70
    ->  \+ risco_inimigo(X,Y),
        \+ inimigo_confirmado(X,Y)
    ;   true
    ),
    manhattan(PX,PY,X,Y,D),
    ganho_info(X,Y,G),
    Custo is 5000 + R + D * 8 - G + Y * 2 - X.

meta_candidata(mover,1,1,90000) :-
    posicao(X,Y,_),
    (X =\= 1 ; Y =\= 1).

meta_decisao(Tipo,X,Y) :-
    findall(cand(C,Tipo0,X0,Y0), meta_candidata(Tipo0,X0,Y0,C), L),
    L \= [],
    sort(L, [cand(_,Tipo,X,Y)|_]), !.

% Compatibilidade com o codigo-base: o Python principal usa meta_decisao/3 e A*,
% mas executa_acao/1 permanece disponivel para consultas simples.
executa_acao(pegar) :-
    meta_decisao(pegar,_,_), !.

executa_acao(sair) :-
    meta_decisao(sair,_,_), !.

executa_acao(andar) :-
    meta_decisao(mover,X,Y),
    posicao(PX,PY,D),
    delta(D,DX,DY),
    X is PX + DX,
    Y is PY + DY, !.

executa_acao(virar_direita).

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% Mostra mapa real
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

show_player(X,Y) :- posicao(X,Y,norte), write('^'), !.
show_player(X,Y) :- posicao(X,Y,oeste), write('<'), !.
show_player(X,Y) :- posicao(X,Y,leste), write('>'), !.
show_player(X,Y) :- posicao(X,Y,sul), write('v'), !.
show_player(X,Y) :- posicao(X,Y,morto), write('+'), !.
show_player(X,Y) :- posicao(X,Y,saiu), write('S'), !.

show_position(X,Y) :-
    (show_player(X,Y) ; write(' ')),
    tile(X,Y,Z),
    ((Z='', write(' ')) ; write(Z)), !.

show_map :-
    tamanho_mapa(_,MAX_Y),
    show_map(1,MAX_Y), !.

show_map(X,Y) :-
    Y >= 1,
    tamanho_mapa(MAX_X,_),
    X =< MAX_X,
    show_position(X,Y),
    write(' | '),
    XX is X + 1,
    show_map(XX,Y), !.

show_map(_,Y) :-
    Y >= 1,
    YY is Y - 1,
    write(Y), nl,
    show_map(1,YY), !.

show_map(_,0) :-
    energia(E),
    pontuacao(P),
    ouros_coletados(O),
    write('E: '), write(E),
    write('   P: '), write(P),
    write('   O: '), write(O), !.

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%% Mostra mapa conhecido
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

show_mem_info(X,Y) :-
    memory(X,Y,Z),
    ((visitado(X,Y), write('.'), !) ; (\+ certeza(X,Y), write('?'), !) ; write('!')),
    ((member(brisa,Z), write('P')) ; write(' ')),
    ((member(flash,Z), write('T')) ; write(' ')),
    ((member(brilho,Z), write('O')) ; write(' ')),
    ((member(passos,Z), write('D')) ; write(' ')),
    ((member(reflexo,Z), write('U')) ; write(' ')), !.

show_mem_info(X,Y) :-
    \+ memory(X,Y,[]),
    ((visitado(X,Y), write('.'), !) ; (\+ certeza(X,Y), write('?'), !) ; write('!')),
    write('     '), !.

show_mem_position(X,Y) :-
    posicao(X,Y,_),
    ((visitado(X,Y), write('.'), !) ; (certeza(X,Y), write('!'), !) ; write(' ')),
    write(' '),
    show_player(X,Y),
    (
        memory(X,Y,Z),
        ((member(brilho,Z), write('O')) ; write(' ')),
        ((member(passos,Z), write('D')) ; write(' ')),
        ((member(reflexo,Z), write('U')) ; write(' ')), !
    ;   write('   '), !
    ).

show_mem_position(X,Y) :- show_mem_info(X,Y), !.

show_mem :-
    tamanho_mapa(_,MAX_Y),
    show_mem(1,MAX_Y), !.

show_mem(X,Y) :-
    Y >= 1,
    tamanho_mapa(MAX_X,_),
    X =< MAX_X,
    show_mem_position(X,Y),
    write('|'),
    XX is X + 1,
    show_mem(XX,Y), !.

show_mem(_,Y) :-
    Y >= 1,
    YY is Y - 1,
    write(Y), nl,
    show_mem(1,YY), !.

show_mem(_,0) :-
    energia(E),
    pontuacao(P),
    ouros_coletados(O),
    write('E: '), write(E),
    write('   P: '), write(P),
    write('   O: '), write(O), !.
