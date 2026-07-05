"""Backgammon: regole del gioco, primo gioco **stocastico** del motore.

Il gioco usa gli hook per i nodi del caso previsti dall'interfaccia ``Game`` fin dal
progetto iniziale: quando i dadi sono da tirare (``state.dice is None``) lo stato è un
**nodo del caso** — non esistono mosse legali finché chi orchestra la partita (il
backend) non estrae un tiro secondo ``chance_outcomes`` e lo applica con
``apply_chance``. Le mosse dei giocatori restano deterministiche e ricercabili.

Modello del turno: **un dado = una mossa** di una singola pedina. Il turno prosegue
finché restano dadi giocabili; quando i dadi finiscono (o nessuno dei rimanenti è
giocabile) il turno passa e i dadi tornano ``None``. Un doppio vale quattro mosse.

Regole implementate: blocco delle punte con ≥2 pedine avversarie, **colpo** della
pedina singola (va sulla barra), **rientro obbligatorio** dalla barra prima di ogni
altra mossa, **uscita** (bear-off) solo con tutte le pedine in casa — con dado esatto,
oppure maggiore solo dalla punta occupata più lontana.

Semplificazioni note (documentate, come per la dama): non è gestito il tiro iniziale
"un dado a testa, il più alto comincia" (inizia X); non è imposta la regola "se puoi
giocare un solo dado devi giocare il maggiore"; niente cubo del raddoppio né punteggi
gammon/backgammon. Verranno affinate in seguito.
"""

from __future__ import annotations

from dataclasses import replace

from ..common.game import Game
from ..common.outcome import Outcome
from .state import BackgammonState

WHITE, BLACK = 0, 1  # X muove 23 → 0 (casa 0..5); O muove 0 → 23 (casa 18..23)
BAR = "bar"  # origine speciale: rientro dalla barra
_PIP_BAR = 25  # distanza convenzionale di una pedina sulla barra

# Simboli per la vista: X = cerchio vuoto, O = cerchio pieno.
_SYM = {WHITE: "○", BLACK: "●"}

# ----- Disposizione iniziale standard (15 pedine a testa) -----
# X: 2 sulla punta 23, 5 sulla 12, 3 sulla 7, 5 sulla 5. O è speculare (23 - punta).
_START = {23: 2, 12: 5, 7: 3, 5: 5}


def _initial_points() -> tuple:
    points = [0] * 24
    for point, count in _START.items():
        points[point] += count  # pedine di X (positive)
        points[23 - point] -= count  # pedine di O (negative), speculari
    return tuple(points)


def _sign(player: int) -> int:
    """Segno delle pedine del giocatore dentro ``points`` (+ per X, − per O)."""
    return 1 if player == WHITE else -1


def _open_for(state: BackgammonState, dst: int, player: int) -> bool:
    """True se la punta ``dst`` è raggiungibile: vuota, propria, o con UNA sola
    pedina avversaria (che verrebbe colpita e mandata sulla barra)."""
    return state.points[dst] * _sign(player) >= -1


def _all_home(state: BackgammonState, player: int) -> bool:
    """True se tutte le pedine del giocatore sono nella sua casa (precondizione
    per portarle fuori). Una pedina sulla barra non è mai 'in casa'."""
    if state.bar[player] > 0:
        return False
    if player == WHITE:  # casa di X: punte 0..5 → nessuna pedina X oltre la 5
        return all(v <= 0 for v in state.points[6:])
    return all(v >= 0 for v in state.points[:18])  # casa di O: punte 18..23


def _pip_of(src, player: int) -> int:
    """Distanza residua (pip) di una pedina: quante caselle mancano all'uscita."""
    if src == BAR:
        return _PIP_BAR
    return src + 1 if player == WHITE else 24 - src


def _can_bear_off(state: BackgammonState, src: int, die: int, player: int) -> bool:
    """Uscita dalla punta ``src`` col dado ``die``: dado esatto sempre consentito;
    dado maggiore solo se non restano pedine su punte più lontane dalla porta."""
    if not _all_home(state, player):
        return False
    pip = _pip_of(src, player)
    if die == pip:
        return True
    if die < pip:
        return False  # non arriva fuori (la mossa interna è gestita altrove)
    if player == WHITE:  # più lontane = punte 5..src+1
        return all(state.points[i] <= 0 for i in range(src + 1, 6))
    return all(state.points[i] >= 0 for i in range(18, src))


def _die_moves(state: BackgammonState, die: int) -> list:
    """Mosse legali del giocatore di turno che usano il singolo dado ``die``.

    Con pedine sulla barra il rientro è **obbligatorio**: nessun'altra mossa è
    concessa finché la barra non è vuota.
    """
    player = state.current
    sign = _sign(player)
    moves = []
    if state.bar[player] > 0:
        entry = 24 - die if player == WHITE else die - 1  # si rientra nella casa avversaria
        if _open_for(state, entry, player):
            moves.append((BAR, die))
        return moves
    for src in range(24):
        if state.points[src] * sign <= 0:
            continue  # nessuna propria pedina su questa punta
        dst = src - die if player == WHITE else src + die
        if 0 <= dst < 24:
            if _open_for(state, dst, player):
                moves.append((src, die))
        elif _can_bear_off(state, src, die, player):
            moves.append((src, die))  # esce dal tavoliere
    return moves


def _dst_of(move, player: int):
    """Destinazione di una mossa: indice di punta, oppure "off" se esce."""
    src, die = move
    if src == BAR:
        return 24 - die if player == WHITE else die - 1
    dst = src - die if player == WHITE else src + die
    return dst if 0 <= dst < 24 else "off"


def _normalize(state: BackgammonState) -> BackgammonState:
    """Chiude il turno quando non c'è più nulla da giocare.

    Se restano dadi ma nessuno è giocabile (o sono finiti), il turno passa
    all'avversario e i dadi tornano ``None`` (nuovo nodo del caso). A partita
    finita lo stato resta com'è.
    """
    if state.off[WHITE] == 15 or state.off[BLACK] == 15:
        return state
    if state.dice:
        for die in set(state.dice):
            if _die_moves(state, die):
                return state  # c'è ancora almeno una mossa: il turno continua
    return replace(state, current=1 - state.current, dice=None)


class Backgammon(Game):
    code = "backgammon"
    name = "Backgammon"
    is_stochastic = True  # primo gioco che usa i nodi del caso
    # Vista a griglia 2×14: riga alta = punte 12..23 + barra X + uscita O;
    # riga bassa = punte 11..0 + barra O + uscita X (vedi _view_index).
    rows = 2
    cols = 14
    move_type = "backgammon"
    # L'IA locale gioca "greedy" dado per dado: valuta con l'euristica lo stato dopo
    # ogni singola mossa (una ricerca più profonda richiederebbe l'expectiminimax
    # sui tiri avversari: annotato in TODO.md).
    search_depth = 1

    # ----- Ciclo di vita della partita -----
    def initial_state(self) -> BackgammonState:
        # Semplificazione: comincia X (il tiro iniziale "un dado a testa" non è
        # modellato). I primi dadi sono da tirare: si parte da un nodo del caso.
        return BackgammonState(
            points=_initial_points(), bar=(0, 0), off=(0, 0), current=WHITE, dice=None
        )

    def current_player(self, state):
        return state.current

    def is_terminal(self, state):
        # La partita finisce solo portando fuori tutte e 15 le pedine: lo stallo non
        # esiste (un turno senza mosse passa automaticamente, vedi _normalize).
        return state.off[WHITE] == 15 or state.off[BLACK] == 15

    def outcome(self, state):
        if state.off[WHITE] == 15:
            return Outcome(winner=WHITE)
        if state.off[BLACK] == 15:
            return Outcome(winner=BLACK)
        return Outcome(winner=None)

    # ----- Nodi del caso: il tiro dei dadi -----
    def is_chance_node(self, state):
        return state.dice is None and not self.is_terminal(state)

    def chance_outcomes(self, state):
        """I 21 tiri distinti di due dadi: un doppio esce 1/36, gli altri 2/36."""
        outcomes = []
        for hi in range(1, 7):
            for lo in range(1, hi + 1):
                probability = (1 if hi == lo else 2) / 36
                outcomes.append(((hi, lo), probability))
        return outcomes

    def apply_chance(self, state, event):
        """Materializza un tiro: un doppio dà quattro mosse, altrimenti due.

        Se il tiro non è giocabile il turno passa subito (``_normalize``): chi
        orchestra vedrà di nuovo un nodo del caso, stavolta dell'avversario.
        """
        hi, lo = event
        dice = (hi,) * 4 if hi == lo else (hi, lo)
        return _normalize(replace(state, dice=dice))

    def describe_chance(self, event):
        hi, lo = event
        return f"🎲 {hi}-{lo}"

    # ----- Mosse (deterministiche, un dado alla volta) -----
    def legal_moves(self, state):
        if state.dice is None or self.is_terminal(state):
            return []  # nodo del caso (o partita finita): prima si tirano i dadi
        moves = []
        seen = set()
        for die in sorted(set(state.dice)):
            for move in _die_moves(state, die):
                # Due dadi diversi possono portare la stessa pedina fuori ("off"):
                # si tiene solo la prima variante (il dado esatto, più economico).
                key = (move[0], _dst_of(move, state.current))
                if key not in seen:
                    seen.add(key)
                    moves.append(move)
        return moves

    def apply(self, state, move):
        src, die = move
        player = state.current
        sign = _sign(player)
        points = list(state.points)
        bar = list(state.bar)
        off = list(state.off)

        # Solleva la pedina dall'origine (barra o punta).
        if src == BAR:
            bar[player] -= 1
        else:
            points[src] -= sign

        dst = _dst_of(move, player)
        if dst == "off":
            off[player] += 1  # pedina portata fuori
        else:
            if points[dst] == -sign:  # colpo: la singola avversaria va sulla barra
                points[dst] = 0
                bar[1 - player] += 1
            points[dst] += sign

        remaining = list(state.dice)
        remaining.remove(die)  # il dado usato è consumato
        new_state = BackgammonState(
            points=tuple(points),
            bar=tuple(bar),
            off=tuple(off),
            current=player,
            dice=tuple(remaining),
        )
        return _normalize(new_state)  # passa il turno se non resta nulla da giocare

    # ----- Serializzazione -----
    def serialize_state(self, state):
        return {
            "points": list(state.points),
            "bar": list(state.bar),
            "off": list(state.off),
            "current": state.current,
            "dice": list(state.dice) if state.dice is not None else None,
        }

    def deserialize_state(self, data):
        return BackgammonState(
            points=tuple(data["points"]),
            bar=tuple(data["bar"]),
            off=tuple(data["off"]),
            current=data["current"],
            dice=tuple(data["dice"]) if data["dice"] is not None else None,
        )

    # ----- Notazione -----
    def move_id(self, move):
        src, die = move
        return f"{src}:{die}"  # es. "12:5", "bar:3" — univoco e facile da confrontare

    def describe_move(self, state, move):
        """Notazione classica per pip del giocatore che muove: "13/8", "bar/22",
        "6/off"; l'asterisco segnala il colpo alla pedina avversaria."""
        src, die = move
        player = state.current
        pip_src = _pip_of(src, player)
        pip_dst = pip_src - die
        dst = _dst_of(move, player)
        text = f"{'bar' if src == BAR else pip_src}/{'off' if dst == 'off' else pip_dst}"
        if dst != "off" and state.points[dst] == -_sign(player):
            text += "*"  # colpo
        return text

    def render_text(self, state):
        """Vista compatta per log e prompt IA: punte 23..12 sopra, 11..0 sotto."""

        def row(indices):
            return " ".join(f"{state.points[i]:+d}" if state.points[i] else "." for i in indices)

        top = row(range(23, 11, -1))
        bottom = row(range(12))
        dice = " ".join(map(str, state.dice)) if state.dice else "da tirare"
        return (
            f"punte 23..12: {top}\npunte 11..0 : {bottom}\n"
            f"barra X/O: {state.bar}  fuori X/O: {state.off}  dadi: {dice}"
        )

    # ----- Vista a griglia per il frontend generico -----
    # Layout 2×14 (indici di vista): riga alta = punte 12..23 da sinistra a destra,
    # poi barra di X (le sue pedine rientrano nelle punte alte) e uscita di O;
    # riga bassa = punte 11..0 da sinistra a destra, poi barra di O e uscita di X.
    _V_BAR = {WHITE: 12, BLACK: 26}
    _V_OFF = {WHITE: 27, BLACK: 13}

    @classmethod
    def _view_index(cls, point: int) -> int:
        if point >= 12:
            return point - 12  # riga alta: 12..23 → viste 0..11
        return 14 + (11 - point)  # riga bassa: 11..0 → viste 14..25

    @staticmethod
    def _cell_text(count: int, player: int):
        """Contenuto di una cella: simbolo del giocatore, col numero se sono ≥2."""
        if count <= 0:
            return None
        sym = _SYM[player]
        return sym if count == 1 else f"{count}{sym}"

    def view_board(self, state):
        cells = [None] * (self.rows * self.cols)
        for point, value in enumerate(state.points):
            if value != 0:
                player = WHITE if value > 0 else BLACK
                cells[self._view_index(point)] = self._cell_text(abs(value), player)
        for player in (WHITE, BLACK):
            cells[self._V_BAR[player]] = self._cell_text(state.bar[player], player)
            cells[self._V_OFF[player]] = self._cell_text(state.off[player], player)
        return cells

    def legal_moves_view(self, state):
        views = []
        for move in self.legal_moves(state):
            src, _die = move
            dst = _dst_of(move, state.current)
            views.append(
                {
                    "id": self.move_id(move),
                    "from": self._V_BAR[state.current] if src == BAR else self._view_index(src),
                    "to": self._V_OFF[state.current] if dst == "off" else self._view_index(dst),
                    "changes": self.board_changes(state, move),
                }
            )
        return views

    def view_status(self, state):
        """Riga informativa mostrata in partita: i dadi del turno e gli obblighi."""
        if self.is_terminal(state):
            return None
        if state.dice is None:
            return "In attesa del tiro dei dadi…"
        text = "Dadi da giocare: " + " ".join(str(d) for d in state.dice)
        if state.bar[state.current] > 0:
            text += " — obbligo di rientro dalla barra"
        return text

    # ----- Euristica per l'IA locale (greedy dado per dado) -----
    def heuristic(self, state, player):
        """Valutazione dal punto di vista di ``player``.

        Componenti classiche del gioco di corsa: differenza di **pip** (la distanza
        totale residua: meno è meglio), pedine già **fuori**, penalità per i **blot**
        (pedine singole colpibili) e per le pedine sulla **barra**.
        """
        pip = [0, 0]
        blots = [0, 0]
        for point, value in enumerate(state.points):
            if value == 0:
                continue
            owner = WHITE if value > 0 else BLACK
            count = abs(value)
            pip[owner] += count * _pip_of(point, owner)
            if count == 1:
                blots[owner] += 1
        for p in (WHITE, BLACK):
            pip[p] += state.bar[p] * _PIP_BAR
        me, opp = player, 1 - player
        return (
            (pip[opp] - pip[me])  # corsa: vantaggio se all'avversario manca più strada
            + 20 * (state.off[me] - state.off[opp])  # pedine già al sicuro
            - 4 * blots[me]  # le proprie singole rischiano il colpo
            + 4 * blots[opp]
            - 6 * state.bar[me]  # dalla barra si perde tempo (oltre al pip già contato)
            + 6 * state.bar[opp]
        )
