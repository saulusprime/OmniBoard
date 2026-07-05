"""Context processor: rende disponibile il giocatore loggato a tutti i template.

Il login (views.login_view) salva nella sessione Django — su cookie firmato,
il frontend non ha DB — il token del backend e i dati minimi del giocatore.
Qui si espone solo la parte presentabile: i template usano ``auth_user.alias``
e ``auth_user.id`` per la barra di navigazione e i link al profilo.
"""

from __future__ import annotations


def auth_user(request):
    return {"auth_user": request.session.get("auth_user")}
