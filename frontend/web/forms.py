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
