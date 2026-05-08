% =====================================================================
% knowledge_base.pl - Pitfall agent knowledge base (INF1771)
%
% Conhecimento que o agente acumula ao explorar o mundo. O Prolog NAO tem
% acesso ao mapa real: ele recebe somente percepcoes via assertz/retract
% disparados do lado Python.
%
% Posicoes: par R/C com 1 =< R,C =< 12.
%
% Inferencia (mundo de Wumpus classico):
%   `likely_safe(P)` so e' verdadeiro se ja temos prova positiva de que
%   nenhum dos perigos esta em P -- por visita (`confirmed_safe`) ou por
%   percepcao em um vizinho que NAO sentiu o perigo correspondente
%   (`pit_clear`, `enemy_clear`, `tele_clear`). Celulas sem evidencia
%   permanecem desconhecidas e NAO sao consideradas seguras.
% =====================================================================

:- dynamic visited/1.
:- dynamic confirmed_safe/1.
:- dynamic risk_pit/1.
:- dynamic risk_enemy/1.
:- dynamic risk_teleport/1.
:- dynamic confirmed_pit/1.
:- dynamic confirmed_enemy/1.
:- dynamic confirmed_teleport/1.
:- dynamic pit_clear/1.
:- dynamic enemy_clear/1.
:- dynamic tele_clear/1.
:- dynamic breeze_at/1.
:- dynamic steps_at/1.
:- dynamic flash_at/1.
:- dynamic gold_seen/1.
:- dynamic agent_pos/1.
:- dynamic agent_dir/1.
:- dynamic gold_carried/1.
:- dynamic exit_pos/1.

grid_size(12).
target_gold(3).

valid_pos(R/C) :-
    grid_size(N),
    between(1, N, R),
    between(1, N, C).

adjacent(R/C, R1/C) :- R1 is R - 1, R1 >= 1.
adjacent(R/C, R1/C) :- R1 is R + 1, grid_size(N), R1 =< N.
adjacent(R/C, R/C1) :- C1 is C - 1, C1 >= 1.
adjacent(R/C, R/C1) :- C1 is C + 1, grid_size(N), C1 =< N.

assert_unique(F) :- F, !.
assert_unique(F) :- assertz(F).

% ---------------------------------------------------------------------
% Atualizacao da percepcao da sala atual.
%
% Para cada perigo (poco/inimigo/teletransporte):
%   - se a percepcao correspondente esta presente, marca os vizinhos
%     ainda desconhecidos como suspeitos;
%   - se nao esta presente, marca os vizinhos como `*_clear`
%     (positivamente livres daquele perigo) e remove qualquer suspeita.
% ---------------------------------------------------------------------

apply_present(_, _, []).
apply_present(Risk, ClearPred, [N|T]) :-
    Clear =.. [ClearPred, N],
    ( call(Clear) -> true
    ; confirmed_safe(N) -> true
    ; visited(N) -> true
    ; Goal =.. [Risk, N], assert_unique(Goal)
    ),
    apply_present(Risk, ClearPred, T).

apply_absent(_, _, _, []).
apply_absent(Risk, ClearPred, ConfirmPred, [N|T]) :-
    Clear =.. [ClearPred, N],
    assert_unique(Clear),
    ToDrop =.. [Risk, N],
    retractall(ToDrop),
    Confirmed =.. [ConfirmPred, N],
    retractall(Confirmed),
    apply_absent(Risk, ClearPred, ConfirmPred, T).

neighbors_of(Pos, Ns) :- findall(N, adjacent(Pos, N), Ns).

update_perception(Pos, Percepts) :-
    assert_unique(visited(Pos)),
    assert_unique(confirmed_safe(Pos)),
    assert_unique(pit_clear(Pos)),
    assert_unique(enemy_clear(Pos)),
    assert_unique(tele_clear(Pos)),
    retractall(risk_pit(Pos)),
    retractall(risk_enemy(Pos)),
    retractall(risk_teleport(Pos)),
    neighbors_of(Pos, Ns),
    handle_percept(breeze, Percepts, breeze_at,
                   risk_pit, pit_clear, confirmed_pit, Ns),
    handle_percept(steps,  Percepts, steps_at,
                   risk_enemy, enemy_clear, confirmed_enemy, Ns),
    handle_percept(flash,  Percepts, flash_at,
                   risk_teleport, tele_clear, confirmed_teleport, Ns),
    ( member(glow, Percepts) -> assert_unique(gold_seen(Pos))
    ;                           retractall(gold_seen(Pos))
    ),
    infer_confirmed_hazards.

handle_percept(Sense, Percepts, StorePred, Risk, ClearPred, ConfirmPred, Ns) :-
    ( member(Sense, Percepts)
    -> remember_signal(StorePred, true),
       apply_present(Risk, ClearPred, Ns)
    ;  remember_signal(StorePred, false),
       apply_absent(Risk, ClearPred, ConfirmPred, Ns)
    ).

remember_signal(StorePred, Present) :-
    agent_pos(Pos),
    Goal =.. [StorePred, Pos],
    ( Present == true -> assert_unique(Goal) ; retractall(Goal) ).

mark_gold_taken(Pos) :- retractall(gold_seen(Pos)).

infer_confirmed_hazards :- infer_one_hazard, !, infer_confirmed_hazards.
infer_confirmed_hazards.

infer_one_hazard :-
    infer_kind(breeze_at, pit_clear, risk_pit, confirmed_pit).
infer_one_hazard :-
    infer_kind(steps_at, enemy_clear, risk_enemy, confirmed_enemy).
infer_one_hazard :-
    infer_kind(flash_at, tele_clear, risk_teleport, confirmed_teleport).

infer_kind(SensePred, ClearPred, RiskPred, ConfirmPred) :-
    Sense =.. [SensePred, Source],
    call(Sense),
    neighbors_of(Source, Ns),
    hazard_candidates(Ns, ClearPred, ConfirmPred, Cands),
    Cands = [Target],
    Confirm =.. [ConfirmPred, Target],
    \+ call(Confirm),
    assertz(Confirm),
    Risk =.. [RiskPred, Target],
    assert_unique(Risk).

hazard_candidates([], _, _, []).
hazard_candidates([P|T], ClearPred, ConfirmPred, Out) :-
    hazard_candidate(P, ClearPred, ConfirmPred), !,
    hazard_candidates(T, ClearPred, ConfirmPred, Rest),
    Out = [P|Rest].
hazard_candidates([_|T], ClearPred, ConfirmPred, Out) :-
    hazard_candidates(T, ClearPred, ConfirmPred, Out).

hazard_candidate(P, ClearPred, ConfirmPred) :-
    valid_pos(P),
    \+ visited(P),
    \+ confirmed_safe(P),
    Clear =.. [ClearPred, P],
    \+ call(Clear),
    ( confirmed_any(P)
    -> Confirm =.. [ConfirmPred, P], call(Confirm)
    ;  true
    ).

confirmed_any(P) :- confirmed_pit(P), !.
confirmed_any(P) :- confirmed_enemy(P), !.
confirmed_any(P) :- confirmed_teleport(P).

% ---------------------------------------------------------------------
% Seguranca derivada
% ---------------------------------------------------------------------

likely_safe(Pos) :-
    valid_pos(Pos),
    \+ confirmed_any(Pos),
    ( confirmed_safe(Pos)
    ; (pit_clear(Pos), enemy_clear(Pos), tele_clear(Pos))
    ).

unvisited_safe_frontier(Pos) :-
    valid_pos(Pos),
    likely_safe(Pos),
    \+ visited(Pos).

risky(Pos) :-
    \+ confirmed_safe(Pos),
    ( risk_pit(Pos)
    ; risk_enemy(Pos)
    ; risk_teleport(Pos)
    ; confirmed_any(Pos)
    ).

risky_frontier(Pos) :-
    ( visited(Seen) ; confirmed_safe(Seen) ),
    adjacent(Seen, Pos),
    \+ visited(Pos),
    \+ likely_safe(Pos),
    \+ confirmed_pit(Pos).

risk_score(Pos, 10000) :- confirmed_pit(Pos), !.
risk_score(Pos, Score) :-
    risk_component(confirmed_enemy(Pos), 80, A),
    risk_component(confirmed_teleport(Pos), 260, B),
    risk_component_with_sources(risk_enemy(Pos), steps_at, Pos, 60, 30, C),
    risk_component_with_sources(risk_teleport(Pos), flash_at, Pos, 180, 60, D),
    risk_component_with_sources(risk_pit(Pos), breeze_at, Pos, 900, 120, E),
    ( risky(Pos) -> Unknown = 0 ; Unknown = 40 ),
    Score is 10 + A + B + C + D + E + Unknown.

risk_component(Goal, Value, Value) :- call(Goal), !.
risk_component(_, _, 0).

risk_component_with_sources(Goal, SensePred, Pos, Base, PerSource, Score) :-
    call(Goal), !,
    source_count(Pos, SensePred, Count),
    Score is Base + PerSource * Count.
risk_component_with_sources(_, _, _, _, _, 0).

source_count(Pos, SensePred, Count) :-
    findall(Src,
            (Sense =.. [SensePred, Src], call(Sense), adjacent(Src, Pos)),
            Sources),
    length(Sources, Count).

% ---------------------------------------------------------------------
% Decisao de alto nivel.
% Resultado em um dos formatos:
%   pegar
%   sair
%   mover(R/C)
% O lado Python aplica A* pelas celulas seguras conhecidas para chegar la.
% ---------------------------------------------------------------------

decide(pegar) :-
    agent_pos(Pos),
    gold_seen(Pos), !.

decide(sair) :-
    agent_pos(Pos),
    exit_pos(Pos),
    gold_carried(N),
    target_gold(T),
    N >= T, !.

decide(mover(Target)) :-
    agent_pos(Pos),
    gold_seen(Target),
    Target \= Pos,
    likely_safe(Target), !.

decide(mover(Target)) :-
    agent_pos(Pos),
    findall(D-T, (unvisited_safe_frontier(T), manhattan(Pos, T, D)), Cands),
    Cands \= [],
    keysort(Cands, [_-Target|_]), !.

decide(mover(Target)) :-
    agent_pos(Pos),
    findall(Score-D-T,
            (risky_frontier(T), risk_score(T, Score), manhattan(Pos, T, D)),
            Cands),
    Cands \= [],
    keysort(Cands, [_-Target|_]), !.

decide(mover(Exit)) :-
    agent_pos(Pos),
    exit_pos(Exit),
    Pos \= Exit, !.

decide(sair).

manhattan(R1/C1, R2/C2, D) :-
    D is abs(R1 - R2) + abs(C1 - C2).

% ---------------------------------------------------------------------
% Reset / inicializacao usados pelo lado Python.
% ---------------------------------------------------------------------

reset_kb :-
    retractall(visited(_)),
    retractall(confirmed_safe(_)),
    retractall(risk_pit(_)),
    retractall(risk_enemy(_)),
    retractall(risk_teleport(_)),
    retractall(confirmed_pit(_)),
    retractall(confirmed_enemy(_)),
    retractall(confirmed_teleport(_)),
    retractall(pit_clear(_)),
    retractall(enemy_clear(_)),
    retractall(tele_clear(_)),
    retractall(breeze_at(_)),
    retractall(steps_at(_)),
    retractall(flash_at(_)),
    retractall(gold_seen(_)),
    retractall(agent_pos(_)),
    retractall(agent_dir(_)),
    retractall(gold_carried(_)),
    ( exit_pos(_) -> true ; assertz(exit_pos(1/1)) ),
    assertz(gold_carried(0)).

set_agent_pos(P) :- retractall(agent_pos(_)), assertz(agent_pos(P)).
set_agent_dir(D) :- retractall(agent_dir(_)), assertz(agent_dir(D)).
set_exit(P) :- retractall(exit_pos(_)), assertz(exit_pos(P)).
inc_gold :-
    ( retract(gold_carried(N)) -> N1 is N + 1 ; N1 = 1 ),
    assertz(gold_carried(N1)).

% ---------------------------------------------------------------------
% Loop interativo (usado pelo prolog_bridge para comunicacao stdin/stdout).
% Le termos prolog do stdin, executa-os e marca o fim com '---END---'.
% ---------------------------------------------------------------------

bridge_loop :-
    repeat,
    catch(read_term(user_input, T, []), _, T = end_of_file),
    ( T == end_of_file
    -> !, halt
    ; bridge_handle(T),
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
