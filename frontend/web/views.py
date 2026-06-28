"""Viste del frontend: presentazione e form, con i dati letti dal backend."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect, render

from . import api_client as api
from .forms import MatchForm, ProposalForm, UserForm, VoteForm


def _safe(request, fn, default=None):
    """Esegue una chiamata API mostrando un messaggio d'errore se fallisce."""
    try:
        return fn()
    except api.ApiError as exc:
        messages.error(request, str(exc))
        return default


def home(request):
    games = _safe(request, api.list_games, default=[])
    return render(request, "web/home.html", {"games": games})


def users_list(request):
    users = _safe(request, api.list_users, default=[])
    return render(request, "web/users_list.html", {"users": users})


def user_create(request):
    if request.method == "POST":
        form = UserForm(request.POST)
        if form.is_valid():
            data = {k: (v or None) for k, v in form.cleaned_data.items()}
            try:
                user = api.create_user(data)
                messages.success(request, f"Giocatore «{user['alias']}» creato.")
                return redirect("user_detail", user_id=user["id"])
            except api.ApiError as exc:
                messages.error(request, str(exc))
    else:
        form = UserForm()
    return render(request, "web/user_form.html", {"form": form})


def user_detail(request, user_id):
    user = _safe(request, lambda: api.get_user(user_id))
    if user is None:
        return redirect("users_list")
    return render(request, "web/user_detail.html", {"u": user})


def groups(request):
    groups_ = _safe(request, api.list_groups, default=[])
    proposals = _safe(request, api.list_proposals, default=[])
    users = _safe(request, api.list_users, default=[])
    return render(
        request,
        "web/groups.html",
        {"groups": groups_, "proposals": proposals, "vote_form": VoteForm(users=users)},
    )


def group_propose(request):
    users = _safe(request, api.list_users, default=[])
    if request.method == "POST":
        form = ProposalForm(request.POST, users=users)
        if form.is_valid():
            data = {
                "name": form.cleaned_data["name"],
                "proposed_by": int(form.cleaned_data["proposed_by"]),
                "threshold": form.cleaned_data["threshold"],
            }
            try:
                api.create_proposal(data)
                messages.success(
                    request, "Proposta creata. Servono altri voti per fondare il gruppo."
                )
                return redirect("groups")
            except api.ApiError as exc:
                messages.error(request, str(exc))
    else:
        form = ProposalForm(users=users)
    return render(request, "web/group_propose.html", {"form": form})


def proposal_vote(request, proposal_id):
    if request.method != "POST":
        return redirect("groups")
    users = _safe(request, api.list_users, default=[])
    form = VoteForm(request.POST, users=users)
    if form.is_valid():
        data = {
            "user_id": int(form.cleaned_data["user_id"]),
            "in_favor": form.cleaned_data["in_favor"] == "true",
        }
        try:
            result = api.vote_proposal(proposal_id, data)
            if result.get("status") == "founded":
                messages.success(
                    request, f"Voto registrato. Il gruppo «{result['name']}» è stato fondato!"
                )
            else:
                messages.success(
                    request,
                    f"Voto registrato ({result['favor_count']}/{result['threshold']} a favore).",
                )
        except api.ApiError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Dati del voto non validi.")
    return redirect("groups")


def rankings(request):
    games = _safe(request, api.list_games, default=[])
    universal = _safe(request, api.universal_ranking, default=[])
    game_code = request.GET.get("game")
    scope = request.GET.get("scope", "global")
    country = request.GET.get("country") or None
    region = request.GET.get("region") or None
    game_rank = None
    if game_code:
        game_rank = _safe(
            request,
            lambda: api.game_ranking(game_code, scope, country, region),
            default=[],
        )
    return render(
        request,
        "web/rankings.html",
        {
            "games": games,
            "universal": universal,
            "game_rank": game_rank,
            "sel_game": game_code,
            "scope": scope,
            "country": country or "",
            "region": region or "",
        },
    )


def match_create(request):
    users = _safe(request, api.list_users, default=[])
    games = _safe(request, api.list_games, default=[])
    if request.method == "POST":
        form = MatchForm(request.POST, users=users, games=games)
        if form.is_valid():
            data = {
                "game_code": form.cleaned_data["game_code"],
                "player_a": int(form.cleaned_data["player_a"]),
                "player_b": int(form.cleaned_data["player_b"]),
                "result": form.cleaned_data["result"],
            }
            try:
                api.record_match(data)
                messages.success(request, "Partita registrata. Punteggi aggiornati.")
                return redirect("rankings")
            except api.ApiError as exc:
                messages.error(request, str(exc))
    else:
        form = MatchForm(users=users, games=games)
    return render(request, "web/match_form.html", {"form": form})
