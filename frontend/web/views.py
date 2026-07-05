"""Viste del frontend: presentazione e form, con i dati letti dal backend."""

from __future__ import annotations

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render

from . import api_client as api
from .forms import GameSetupForm, MatchForm, ProposalForm, UserForm, VoteForm


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
    history = _safe(request, lambda: api.get_user_history(user_id), default=[])
    chess = _safe(request, lambda: api.get_chess_profile(user_id), default=None)
    return render(request, "web/user_detail.html", {"u": user, "history": history, "chess": chess})


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


# ----- Partite giocabili -----
def play_setup(request):
    users = _safe(request, api.list_users, default=[])
    all_games = _safe(request, api.list_games, default=[])
    games = [g for g in all_games if g.get("playable")]
    if request.method == "POST":
        form = GameSetupForm(request.POST, users=users, games=games)
        if form.is_valid():
            game_code = form.cleaned_data["game"]
            x_ai = form.cleaned_data["x_type"] == "ai"
            o_ai = form.cleaned_data["o_type"] == "ai"
            count = form.cleaned_data.get("games_count") or 1

            # Entrambi di tipo "IA via API" + più partite → batch di simulazione con
            # riepilogo (l'endpoint batch non supporta Stockfish: con Stockfish si
            # crea una normale sessione singola osservabile in diretta).
            if x_ai and o_ai and count > 1:
                try:
                    result = api.run_batch({"game_code": game_code, "count": count})
                    return render(request, "web/batch_result.html", {"r": result})
                except api.ApiError as exc:
                    messages.error(request, str(exc))
            else:

                def spec(side):
                    # Valori del form: "human" | "ai" | "stockfish:<livello>"; per
                    # Stockfish si scinde in type + level (preset Zeus/Atena/…).
                    kind = form.cleaned_data[f"{side}_type"]
                    if kind == "human":
                        return {"type": "human", "user_id": int(form.cleaned_data[f"{side}_user"])}
                    if kind.startswith("stockfish:"):
                        return {"type": "stockfish", "level": kind.split(":", 1)[1]}
                    return {"type": kind}

                data = {"game_code": game_code, "x": spec("x"), "o": spec("o")}
                # Orologio (solo scacchi): incluso solo se una categoria è stata scelta;
                # la validazione autorevole (range per categoria, FIDE fisso) è del backend.
                if form.cleaned_data.get("time_category"):
                    data["time_category"] = form.cleaned_data["time_category"]
                    if form.cleaned_data.get("time_base_min"):
                        data["time_base_min"] = form.cleaned_data["time_base_min"]
                    data["time_inc_s"] = form.cleaned_data.get("time_inc_s") or 0
                try:
                    session = api.create_session(data)
                    return redirect("play", session_id=session["id"])
                except api.ApiError as exc:
                    messages.error(request, str(exc))
    else:
        form = GameSetupForm(users=users, games=games)
    return render(request, "web/play_setup.html", {"form": form})


def play(request, session_id):
    session = _safe(request, lambda: api.get_session(session_id))
    if session is None:
        return redirect("play_setup")
    config = _safe(request, api.get_config, default={})
    return render(
        request,
        "web/play.html",
        {
            "s": session,
            "ai_delay": config.get("ai_move_delay_ms", 700),
            # Aspetto (categoria super admin): animazione dei pezzi ed effetto sonoro.
            "anim_ms": config.get("anim_ms", 250),
            "sound_on": config.get("sound_enabled", True),
            "sound_vol": config.get("sound_volume", 40),
        },
    )


def play_move(request, session_id):
    if request.method != "POST":
        return redirect("play", session_id=session_id)
    move = request.POST.get("move", "")
    try:
        api.session_move(session_id, {"move": move})
    except api.ApiError as exc:
        messages.error(request, str(exc))
    return redirect("play", session_id=session_id)


def play_move_json(request, session_id):
    """Endpoint JSON per le mosse (usato dal JS per l'animazione, stesso origine)."""
    if request.method != "POST":
        return JsonResponse({"error": "Metodo non consentito"}, status=405)
    move = request.POST.get("move", "")
    if not move:
        return JsonResponse({"error": "Mossa non valida"}, status=400)
    try:
        return JsonResponse(api.session_move(session_id, {"move": move}))
    except api.ApiError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


def play_state_json(request, session_id):
    """Stato corrente della partita in JSON: usato dal client per risincronizzarsi
    quando una mossa fallisce (evita disallineamenti client/server)."""
    try:
        return JsonResponse(api.get_session(session_id))
    except api.ApiError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


# ----- Super admin: parametri di programma -----
def admin(request):
    settings = _safe(request, api.get_settings, default=[])
    if request.method == "POST":
        token = request.POST.get("admin_token", "")
        # Pulsante «Verifica Stockfish»: diagnostica del binario UCI configurato.
        if "test_stockfish" in request.POST:
            try:
                result = api.test_stockfish(token)
                text = f"{result['detail']} (percorso: {result['path'] or 'non risolto'})"
                (messages.success if result["ok"] else messages.error)(
                    request, f"Stockfish: {text}"
                )
            except api.ApiError as exc:
                messages.error(request, str(exc))
            return redirect("admin")
        values = {
            s["key"]: request.POST.get(s["key"], "") for s in settings if s["key"] in request.POST
        }
        try:
            api.update_settings(values, token)
            messages.success(request, "Parametri aggiornati.")
            return redirect("admin")
        except api.ApiError as exc:
            messages.error(request, str(exc))
    return render(request, "web/admin.html", {"settings": settings})


def admin_ai(request):
    data = _safe(request, api.get_ai_providers, default={"providers": [], "active": ""})
    if request.method == "POST":
        token = request.POST.get("admin_token", "")
        test_code = request.POST.get("test_provider")
        if test_code:
            try:
                result = api.test_ai_provider(test_code, token)
                if result.get("ok"):
                    messages.success(
                        request, f"{test_code}: connessione OK — {result.get('detail', '')}"
                    )
                else:
                    messages.error(
                        request, f"{test_code}: {result.get('detail', 'verifica fallita')}"
                    )
            except api.ApiError as exc:
                messages.error(request, str(exc))
        else:
            providers = {
                p["code"]: {
                    "base_url": request.POST.get(f"{p['code']}__base_url", ""),
                    "model": request.POST.get(f"{p['code']}__model", ""),
                    "api_key": request.POST.get(f"{p['code']}__api_key", ""),
                }
                for p in data.get("providers", [])
            }
            try:
                api.update_ai_providers(request.POST.get("active", ""), providers, token)
                messages.success(request, "Provider IA aggiornati.")
                return redirect("admin_ai")
            except api.ApiError as exc:
                messages.error(request, str(exc))
        data = _safe(request, api.get_ai_providers, default={"providers": [], "active": ""})
    return render(request, "web/admin_ai.html", data)
