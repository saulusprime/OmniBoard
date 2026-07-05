"""Form Django per la raccolta dei dati lato frontend.

Le scelte (giocatori, giochi) vengono popolate dinamicamente dai dati del backend.
"""

from __future__ import annotations

from django import forms


def _user_choices(users):
    return [
        (str(u["id"]), f"{u['alias']} — {u['first_name']} {u['last_name']}") for u in (users or [])
    ]


def _game_choices(games):
    return [(g["code"], g["name"]) for g in (games or [])]


class UserForm(forms.Form):
    first_name = forms.CharField(label="Nome", max_length=80)
    last_name = forms.CharField(label="Cognome", max_length=80)
    alias = forms.CharField(label="Alias", max_length=50)
    email = forms.EmailField(label="Email")
    nationality = forms.CharField(label="Nazionalità", max_length=60, required=False)
    region = forms.CharField(label="Regione", max_length=60, required=False)
    password = forms.CharField(
        label="Password (opzionale)", widget=forms.PasswordInput, required=False
    )


class ProposalForm(forms.Form):
    name = forms.CharField(label="Nome del gruppo", max_length=80)
    proposed_by = forms.ChoiceField(label="Proponente")
    threshold = forms.IntegerField(label="Voti a favore necessari", min_value=2, initial=2)

    def __init__(self, *args, users=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proposed_by"].choices = _user_choices(users)


class VoteForm(forms.Form):
    user_id = forms.ChoiceField(label="Vota come")
    in_favor = forms.ChoiceField(
        label="Voto",
        choices=[("true", "A favore"), ("false", "Contrario")],
        initial="true",
    )

    def __init__(self, *args, users=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user_id"].choices = _user_choices(users)


class GameSetupForm(forms.Form):
    """Configurazione di una partita: gioco scelto e tipo di ogni lato.

    Tre tipi di giocatore: umano, IA via API (il provider attivo: Qwen/Claude/…) e
    Stockfish in **sei livelli preconfigurati** con nomi di divinità greche, dal più
    forte al più debole (il valore "stockfish:<livello>" viene scisso dalla vista in
    type + level per l'API). I tipi non umani ripiegano sul giocatore locale se non
    configurati o irraggiungibili.
    """

    PLAYER_TYPES = [
        ("human", "Umano"),
        ("ai", "IA via API (Qwen, Claude, …)"),
        ("stockfish:zeus", "Stockfish — Zeus (Extreme)"),
        ("stockfish:atena", "Stockfish — Atena (Master)"),
        ("stockfish:apollo", "Stockfish — Apollo (Champion)"),
        ("stockfish:ares", "Stockfish — Ares (Expert)"),
        ("stockfish:hermes", "Stockfish — Hermes (Middle)"),
        ("stockfish:pan", "Stockfish — Pan (Learner)"),
    ]

    game = forms.ChoiceField(label="Gioco")
    x_type = forms.ChoiceField(label="Giocatore X (primo a muovere)", choices=PLAYER_TYPES)
    x_user = forms.ChoiceField(label="Utente per X", required=False)
    o_type = forms.ChoiceField(label="Giocatore O", choices=PLAYER_TYPES)
    o_user = forms.ChoiceField(label="Utente per O", required=False)
    games_count = forms.IntegerField(
        label="Partite consecutive (solo se entrambi IA)",
        min_value=1,
        max_value=1000,
        initial=1,
        required=False,
    )

    def __init__(self, *args, users=None, games=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["game"].choices = [(g["code"], g["name"]) for g in (games or [])]
        choices = [("", "—")] + _user_choices(users)
        self.fields["x_user"].choices = choices
        self.fields["o_user"].choices = choices

    def clean(self):
        cleaned = super().clean()
        for side in ("x", "o"):
            if cleaned.get(f"{side}_type") == "human" and not cleaned.get(f"{side}_user"):
                self.add_error(f"{side}_user", "Seleziona un utente per il giocatore umano.")
        return cleaned


class MatchForm(forms.Form):
    game_code = forms.ChoiceField(label="Gioco")
    player_a = forms.ChoiceField(label="Giocatore A")
    player_b = forms.ChoiceField(label="Giocatore B")
    result = forms.ChoiceField(
        label="Risultato",
        choices=[("a", "Vince A"), ("b", "Vince B"), ("draw", "Patta")],
    )

    def __init__(self, *args, users=None, games=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["game_code"].choices = _game_choices(games)
        self.fields["player_a"].choices = _user_choices(users)
        self.fields["player_b"].choices = _user_choices(users)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("player_a") and cleaned.get("player_a") == cleaned.get("player_b"):
            raise forms.ValidationError("I due giocatori devono essere diversi.")
        return cleaned
