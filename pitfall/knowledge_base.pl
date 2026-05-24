% knowledge_base.pl - INF1771 Trabalho 2 Pitfall
%
% Representacao do conhecimento seguindo o modelo memory/certeza de main.pl.
%
% memory(R/C, ObsList)
%     ObsList ⊆ {brisa, passos, palmas} e' o conjunto de sinais de perigo
%     que esta celula PODERIA estar emitindo para seus vizinhos.
%     Atualizado por intersecao cada vez que um vizinho visitado e' processado.
%     ObsList = [] => celula confirmada segura.
%
% certeza(R/C)
%     Celula com conhecimento certo: visitada fisicamente OU deduzida segura
%     (memory = []).
%
% visited(R/C)
%     Celula fisicamente visitada pelo agente.
%
% breeze_at/steps_at/flash_at(R/C)
%     Registra quais sinais foram percebidos em cada celula visitada.
%     Usados para inferir a fonte unica de cada perigo.
%
% Mapeamento de percepcoes (Python -> modelo portugues):
%   breeze -> brisa   (poco)
%   steps  -> passos  (inimigo)
%   flash  -> palmas  (teletransporte)
%   glow   -> brilho  (ouro na celula atual)
%   powerup -> reflexo (powerup na celula atual - requer GRAB explicito)

:- dynamic memory/2.
:- dynamic certeza/1.
:- dynamic visited/1.
:- dynamic breeze_at/1.
:- dynamic steps_at/1.
:- dynamic flash_at/1.
:- dynamic confirmed_pit/1.
:- dynamic confirmed_enemy/1.
:- dynamic confirmed_teleport/1.
:- dynamic agent_pos/1.
:- dynamic agent_dir/1.
:- dynamic agent_energy/1.
:- dynamic exit_pos/1.
:- dynamic gold_carried/1.
:- dynamic gold_seen/1.
:- dynamic powerup_seen/1.

grid_size(12).
target_gold(3).
energy_low_threshold(50).   % limiar para buscar/pegar powerup (50% de INITIAL_ENERGY=100)

valid_pos(R/C) :-
    grid_size(N),
    between(1, N, R),
    between(1, N, C).

adjacent(R/C, R1/C) :- R1 is R - 1, R1 >= 1.
adjacent(R/C, R1/C) :- R1 is R + 1, grid_size(N), R1 =< N.
adjacent(R/C, R/C1) :- C1 is C - 1, C1 >= 1.
adjacent(R/C, R/C1) :- C1 is C + 1, grid_size(N), C1 =< N.

assert_unique(F) :- call(F), !.
assert_unique(F) :- assertz(F).

neighbors_of(Pos, Ns) :- findall(N, adjacent(Pos, N), Ns).

% Mapeamento: nome do percepto Python -> atomo de observacao de perigo adjacente
percept_obs(breeze, brisa).
percept_obs(steps,  passos).
percept_obs(flash,  palmas).

% =====================================================================
% Atualizacao da KB a cada percepcao
% =====================================================================

% update_perception(+Pos, +Percepts)
% Percepts e' lista de atomos Python: [breeze, steps, flash, glow, powerup, ...]
update_perception(Pos, Percepts) :-
    % Celula atual: visitada, com certeza e segura.
    % Limpa quaisquer inferencias de perigo sobre esta celula — o agente
    % sobreviveu aqui, entao nao pode ser poco, inimigo ou teletransporte.
    assert_unique(visited(Pos)),
    assert_unique(certeza(Pos)),
    retractall(confirmed_pit(Pos)),
    retractall(confirmed_enemy(Pos)),
    retractall(confirmed_teleport(Pos)),
    retractall(memory(Pos, _)),
    assertz(memory(Pos, [])),
    % Registrar sinais de perigo percebidos nesta celula (para inferencia)
    ( member(breeze, Percepts) -> assert_unique(breeze_at(Pos)) ; retractall(breeze_at(Pos)) ),
    ( member(steps,  Percepts) -> assert_unique(steps_at(Pos))  ; retractall(steps_at(Pos))  ),
    ( member(flash,  Percepts) -> assert_unique(flash_at(Pos))  ; retractall(flash_at(Pos))  ),
    % Percepcoes locais: ouro e powerup na celula atual
    ( member(glow, Percepts)
    -> assert_unique(gold_seen(Pos))
    ;  retractall(gold_seen(Pos))
    ),
    ( member(powerup, Percepts)
    -> assert_unique(powerup_seen(Pos))
    ;  retractall(powerup_seen(Pos))
    ),
    % Construir vetor de sinais de perigo para vizinhos
    findall(Obs, (percept_obs(P, Obs), member(P, Percepts)), HazardObs),
    % Atualizar memoria dos vizinhos por intersecao (modelo main.pl)
    neighbors_of(Pos, Ns),
    maplist(update_neighbor_memory(HazardObs), Ns),
    % Inferencia: celulas com memoria vazia sao seguras; fonte unica de perigo
    infer_safe_from_empty,
    infer_unique_source(breeze_at, brisa,  confirmed_pit),
    infer_unique_source(steps_at,  passos, confirmed_enemy),
    infer_unique_source(flash_at,  palmas, confirmed_teleport).

% Atualiza memoria de um vizinho: se ainda nao confirmado, faz intersecao
% com os sinais observados na celula atual.
update_neighbor_memory(_, N) :- certeza(N), !.
update_neighbor_memory(HazardObs, N) :-
    ( retract(memory(N, OldObs))
    -> intersection(OldObs, HazardObs, NewObs),
       assertz(memory(N, NewObs))
    ;  assertz(memory(N, HazardObs))
    ).

% =====================================================================
% Inferencia (equivalente a observacao_certeza / deduz_buracos de main.pl)
% =====================================================================

% Celulas com memoria vazia sao seguras: marcar como certeza.
infer_safe_from_empty :-
    forall(
        ( memory(Pos, []), \+ certeza(Pos) ),
        ( assertz(certeza(Pos)),
          retractall(confirmed_pit(Pos)),
          retractall(confirmed_enemy(Pos)),
          retractall(confirmed_teleport(Pos))
        )
    ).

% Se exatamente um vizinho incerto de uma celula sensoreada ainda pode ser
% a fonte do sinal HazardObs, confirmar aquele vizinho como o perigo.
% Repete ate fixpoint.
infer_unique_source(SensePred, HazardObs, ConfirmPred) :-
    infer_unique_source_step(SensePred, HazardObs, ConfirmPred), !,
    infer_unique_source(SensePred, HazardObs, ConfirmPred).
infer_unique_source(_, _, _).

infer_unique_source_step(SensePred, HazardObs, ConfirmPred) :-
    Sense =.. [SensePred, Sensed],
    call(Sense),
    neighbors_of(Sensed, Ns),
    findall(N,
        ( member(N, Ns),
          \+ certeza(N),
          \+ visited(N),
          ( memory(N, MObs) -> member(HazardObs, MObs) ; true )
        ),
        Cands),
    Cands = [Target],
    Confirm =.. [ConfirmPred, Target],
    \+ call(Confirm),
    assertz(Confirm).

% =====================================================================
% Predicados de seguranca
% =====================================================================

likely_safe(Pos) :-
    valid_pos(Pos),
    \+ confirmed_pit(Pos),
    (
        certeza(Pos)
    ;
        ( memory(Pos, Obs),
          \+ member(brisa,  Obs),
          \+ member(passos, Obs),
          \+ member(palmas, Obs)
        )
    ).

unvisited_safe_frontier(Pos) :-
    valid_pos(Pos),
    likely_safe(Pos),
    \+ visited(Pos).

risky(Pos) :-
    \+ certeza(Pos),
    ( confirmed_pit(Pos)
    ; confirmed_enemy(Pos)
    ; confirmed_teleport(Pos)
    ; ( memory(Pos, Obs),
        ( member(brisa,  Obs)
        ; member(passos, Obs)
        ; member(palmas, Obs)
        )
      )
    ).

risky_frontier(Pos) :-
    ( visited(Seen) ; certeza(Seen) ),
    adjacent(Seen, Pos),
    \+ visited(Pos),
    \+ likely_safe(Pos),
    \+ confirmed_pit(Pos),
    valid_pos(Pos).

% Predicados derivados para snapshot do bridge.
% memory/2 DEVE vir antes de \+certeza para instanciar Pos antes do teste negativo.
% Com Pos nao-instanciado, \+certeza(Pos) falharia sempre (unifica com qualquer fato).
risk_pit(Pos)       :- memory(Pos, Obs), \+ certeza(Pos), member(brisa,  Obs).
risk_enemy(Pos)     :- memory(Pos, Obs), \+ certeza(Pos), member(passos, Obs).
risk_teleport(Pos)  :- memory(Pos, Obs), \+ certeza(Pos), member(palmas, Obs).

risk_score(Pos, 10000) :- confirmed_pit(Pos), !.
risk_score(Pos, Score) :-
    ( memory(Pos, Obs) -> true ; Obs = [] ),
    ( member(brisa,  Obs) -> BScore = 900 ; BScore = 0 ),
    ( member(passos, Obs) -> PScore =  60 ; PScore = 0 ),
    ( member(palmas, Obs) -> TScore = 180 ; TScore = 0 ),
    ( confirmed_enemy(Pos)    -> EScore   =  80 ; EScore   = 0 ),
    ( confirmed_teleport(Pos) -> TelScore = 260 ; TelScore = 0 ),
    Score is 10 + BScore + PScore + TScore + EScore + TelScore.

% =====================================================================
% Tomada de decisao - decide/1  (equivalente a executa_acao de main.pl)
%
% O agente NUNCA retorna para a saida com ouro parcial por energia baixa
% (fiel ao main.pl). O retorno forçado por energia critica e' responsabilidade
% do lado Python (CRITICAL_ENERGY_RETURN=25 em agent.py).
%
% Prioridade:
%   1. pegar ouro no local
%   2. pegar powerup no local quando energia baixa  (energia_baixa)
%   3. sair com todos os ouros na saida
%   4. mover para ouro seguro conhecido
%   5. mover para powerup mais proximo quando energia baixa  (energia_baixa)
%   6. explorar fronteira segura nao visitada
%   7. arriscar fronteira de menor risco
%   8. voltar para saida (fallback — sem mais o que explorar)
% =====================================================================

% 1. Ouro no local: coletar sempre
decide(pegar) :-
    agent_pos(Pos),
    gold_seen(Pos), !.

% 2. Powerup no local: coletar sempre que encontrado
decide(pegar) :-
    agent_pos(Pos),
    powerup_seen(Pos), !.

% 3. Saida com todos os ouros
decide(sair) :-
    agent_pos(Pos),
    exit_pos(Pos),
    gold_carried(N),
    target_gold(T),
    N >= T, !.

% 4. Mover para ouro conhecido e alcancavel
decide(mover(Target)) :-
    agent_pos(Pos),
    gold_seen(Target),
    Target \= Pos,
    likely_safe(Target), !.

% 5. energia_baixa: buscar powerup mais proximo quando energia esta baixa
decide(mover(Target)) :-
    agent_energy(E),
    energy_low_threshold(T),
    E =< T,
    agent_pos(Pos),
    findall(D-P,
        ( powerup_seen(P),
          P \= Pos,
          likely_safe(P),
          manhattan(Pos, P, D)
        ),
        Cands),
    Cands \= [],
    keysort(Cands, [_-Target|_]), !.

% 6. Explorar fronteira segura nao visitada (mais proxima primeiro)
decide(mover(Target)) :-
    agent_pos(Pos),
    findall(D-T, (unvisited_safe_frontier(T), manhattan(Pos, T, D)), Cands),
    Cands \= [],
    keysort(Cands, [_-Target|_]), !.

% 7. Arriscar fronteira de menor risco quando nao ha opcao segura
decide(mover(Target)) :-
    agent_pos(Pos),
    findall(Score-D-T,
        ( risky_frontier(T),
          risk_score(T, Score),
          manhattan(Pos, T, D)
        ),
        Cands),
    sort(Cands, Sorted),
    Sorted \= [],
    Sorted = [_-_-Target|_], !.

% 8. Voltar para saida se nao houver nada mais a explorar
decide(mover(Exit)) :-
    exit_pos(Exit),
    agent_pos(Pos),
    Pos \= Exit, !.

decide(sair).

manhattan(R1/C1, R2/C2, D) :-
    D is abs(R1 - R2) + abs(C1 - C2).

% =====================================================================
% API chamada pelo lado Python (prolog_bridge.py)
% =====================================================================

mark_gold_taken(Pos)   :- retractall(gold_seen(Pos)).
mark_powerup_taken(Pos):- retractall(powerup_seen(Pos)).

set_agent_pos(P)    :- retractall(agent_pos(_)),    assertz(agent_pos(P)).
set_agent_dir(D)    :- retractall(agent_dir(_)),    assertz(agent_dir(D)).
set_agent_energy(E) :- retractall(agent_energy(_)), assertz(agent_energy(E)).
set_exit(P)         :- retractall(exit_pos(_)),     assertz(exit_pos(P)).

inc_gold :-
    ( retract(gold_carried(N)) -> N1 is N + 1 ; N1 = 1 ),
    assertz(gold_carried(N1)).

is_visited(Pos)    :- visited(Pos).
is_known_gold(Pos) :- gold_seen(Pos).
is_risky(Pos)      :- risky(Pos).

reset_kb :-
    retractall(memory(_, _)),
    retractall(certeza(_)),
    retractall(visited(_)),
    retractall(breeze_at(_)),
    retractall(steps_at(_)),
    retractall(flash_at(_)),
    retractall(confirmed_pit(_)),
    retractall(confirmed_enemy(_)),
    retractall(confirmed_teleport(_)),
    retractall(gold_seen(_)),
    retractall(powerup_seen(_)),
    retractall(agent_pos(_)),
    retractall(agent_dir(_)),
    retractall(agent_energy(_)),
    retractall(gold_carried(_)),
    ( exit_pos(_) -> true ; assertz(exit_pos(1/1)) ),
    assertz(gold_carried(0)),
    assertz(agent_energy(100)).

% =====================================================================
% Bridge loop (protocolo stdin/stdout usado por prolog_bridge.py)
% =====================================================================

bridge_loop :-
    repeat,
    catch(read_term(user_input, T, []), _, T = end_of_file),
    ( T == end_of_file
    -> !, halt
    ;  bridge_handle(T),
       format('---END---~n'),
       flush_output
    ),
    fail.

bridge_handle(do(Goal)) :- !,
    ( catch(call(Goal), _, fail) -> format('OK~n') ; format('FAIL~n') ).
bridge_handle(query(Goal, Template)) :- !,
    ( findall(Template, Goal, Sols)
    -> ( Sols == []
       -> format('SOLUTIONS:[]~n')
       ;  format('SOLUTIONS:'), write(Sols), nl
       )
    ; format('SOLUTIONS:[]~n')
    ).
bridge_handle(_) :- format('UNKNOWN~n').

:- initialization(bridge_loop, main).
