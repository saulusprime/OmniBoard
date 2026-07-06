"""Viste del frontend: presentazione e form, con i dati letti dal backend."""

from __future__ import annotations

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render

from . import api_client as api
from .forms import (
    GameSetupForm,
    LoginForm,
    MatchForm,
    PlayerPrefsForm,
    ProposalForm,
    UserForm,
    VoteForm,
)


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
    """Richiesta di registrazione: crea un utente NON approvato sul backend.

    Solo il super admin accetta la richiesta (pagina Admin); fino ad allora il
    giocatore non può accedere. La conferma password resta nel frontend.
    """
    if request.method == "POST":
        form = UserForm(request.POST)
        if form.is_valid():
            data = {k: (v or None) for k, v in form.cleaned_data.items()}
            data.pop("password_confirm", None)  # solo controllo locale, non va al backend
            try:
                user = api.create_user(data)
                messages.success(
                    request,
                    f"Richiesta di registrazione inviata per «{user['alias']}»: "
                    "un super admin dovrà approvarla prima che tu possa accedere.",
                )
                return redirect("login")
            except api.ApiError as exc:
                messages.error(request, str(exc))
    else:
        form = UserForm()
    return render(request, "web/user_form.html", {"form": form})


# ----- Autenticazione giocatori (login/logout con sessione) -----
def login_view(request):
    """Login: le credenziali vengono verificate dal backend, che apre la sessione.

    Nel cookie di sessione Django (firmato) restano solo il token del backend e
    i dati minimi del giocatore — mai la password.
    """
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            try:
                out = api.login(form.cleaned_data["identifier"], form.cleaned_data["password"])
                request.session["auth_token"] = out["token"]
                request.session["auth_user"] = {
                    "id": out["user"]["id"],
                    "alias": out["user"]["alias"],
                }
                messages.success(request, f"Bentornato, {out['user']['alias']}!")
                return redirect("home")
            except api.ApiError as exc:
                messages.error(request, str(exc))
    else:
        form = LoginForm()
    return render(request, "web/login.html", {"form": form})


def logout_view(request):
    """Logout: chiude la sessione sul backend e svuota il cookie di sessione."""
    if request.method == "POST":
        token = request.session.get("auth_token")
        if token:
            try:
                api.logout(token)
            except api.ApiError:
                pass  # la sessione locale si chiude comunque
        request.session.flush()
        messages.success(request, "Sei uscito. A presto!")
    return redirect("home")


# ----- Community: presenza online, badge e partite del giocatore -----
def community(request):
    """Area community: chi è online (badge presenza + punti) e le proprie partite.

    È anche il posto dove lo SFIDATO scopre una partita a distanza creata da un
    altro giocatore: la lista «Le tue partite» si aggiorna da sola via polling.
    """
    online = _safe(request, api.community_online, default={"online": []})
    token = request.session.get("auth_token")
    games = []
    if token:
        data = _safe(request, lambda: api.my_games(token), default={"games": []})
        games = (data or {}).get("games", [])
    return render(
        request,
        "web/community.html",
        {"online": online.get("online", []), "my_games": games},
    )


def community_json(request):
    """Snapshot JSON per i badge e l'area community (polling leggero dal client).

    Se il visitatore è loggato fa anche da HEARTBEAT: chiamarlo periodicamente
    mantiene il badge di presenza. Include i punti del giocatore (badge navbar).
    """
    token = request.session.get("auth_token")
    me = None
    games = []
    if token:
        try:
            api.heartbeat(token)
            games = api.my_games(token).get("games", [])
        except api.ApiError:
            token = None  # sessione backend scaduta: si continua da anonimi
    try:
        online = api.community_online().get("online", [])
    except api.ApiError:
        return JsonResponse({"error": "backend non raggiungibile"}, status=503)
    auth_user = request.session.get("auth_user")
    if auth_user:
        me = next((u for u in online if u["id"] == auth_user["id"]), None)
    return JsonResponse({"online": online, "my_games": games, "me": me})


def user_detail(request, user_id):
    user = _safe(request, lambda: api.get_user(user_id))
    if user is None:
        return redirect("users_list")
    # Opzioni estetiche del giocatore (tema scacchiera/pezzi, segno del Tris):
    # personali, senza token — la validazione autorevole è del backend.
    if request.method == "POST" and "save_prefs" in request.POST:
        prefs_form = PlayerPrefsForm(request.POST)
        if prefs_form.is_valid():
            try:
                api.update_user_prefs(
                    user_id,
                    {
                        "board_theme": prefs_form.cleaned_data["board_theme"],
                        "tris_mark": prefs_form.cleaned_data.get("tris_mark") or "",
                    },
                )
                messages.success(request, "Opzioni del giocatore salvate.")
                return redirect("user_detail", user_id=user_id)
            except api.ApiError as exc:
                messages.error(request, str(exc))
    else:
        prefs = user.get("prefs") or {}
        prefs_form = PlayerPrefsForm(
            initial={
                "board_theme": prefs.get("board_theme", "classico"),
                "tris_mark": prefs.get("tris_mark", ""),
            }
        )
    history = _safe(request, lambda: api.get_user_history(user_id), default=[])
    chess = _safe(request, lambda: api.get_chess_profile(user_id), default=None)
    return render(
        request,
        "web/user_detail.html",
        {"u": user, "history": history, "chess": chess, "prefs_form": prefs_form},
    )


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
    # Concorrenti IA multipli: il catalogo provider popola le voci «IA — Claude»,
    # «IA — Gemini», … del form (una per provider, oltre al provider attivo).
    providers = _safe(request, api.get_ai_providers, default={"providers": []})["providers"]
    if request.method == "POST":
        form = GameSetupForm(request.POST, users=users, games=games, providers=providers)
        if form.is_valid():
            game_code = form.cleaned_data["game"]
            x_ai = form.cleaned_data["x_type"].startswith("ai")
            o_ai = form.cleaned_data["o_type"].startswith("ai")
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
                    # Valori del form: "human" | "ai" | "ai:<provider>" |
                    # "stockfish:<livello>". Per Stockfish si scinde in type + level
                    # (preset Zeus/Atena/…); per l'IA il suffisso è il CONCORRENTE
                    # scelto («gioca contro Claude/Gemini/…», nessuno = attivo).
                    kind = form.cleaned_data[f"{side}_type"]
                    if kind == "human":
                        return {"type": "human", "user_id": int(form.cleaned_data[f"{side}_user"])}
                    if kind.startswith("stockfish:"):
                        return {"type": "stockfish", "level": kind.split(":", 1)[1]}
                    if kind.startswith("ai:"):
                        return {"type": "ai", "provider": kind.split(":", 1)[1]}
                    return {"type": kind}

                data = {"game_code": game_code, "x": spec("x"), "o": spec("o")}
                # Partita a distanza: ogni client comanda solo il proprio lato,
                # le mosse viaggiano col token del giocatore (enforcement backend).
                if form.cleaned_data.get("remote"):
                    data["remote"] = True
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
        # Prefill dalla community («Sfida»): io con X, lo sfidato con O, remota.
        initial = {}
        me = request.session.get("auth_user")
        opponent = request.GET.get("opponent")
        if opponent and opponent.isdigit():
            initial.update(o_type="human", o_user=opponent, remote=True)
            if me:
                initial.update(x_type="human", x_user=str(me["id"]))
        if request.GET.get("game"):
            initial["game"] = request.GET["game"]
        form = GameSetupForm(users=users, games=games, providers=providers, initial=initial)
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
            # Chi sta guardando: nelle partite a distanza il client abilita solo
            # il lato di questo giocatore (None = visitatore anonimo/hotseat).
            "my_user_id": (request.session.get("auth_user") or {}).get("id"),
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
        api.session_move(session_id, {"move": move}, token=request.session.get("auth_token"))
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
        token = request.session.get("auth_token")  # necessario nelle partite a distanza
        return JsonResponse(api.session_move(session_id, {"move": move}, token=token))
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
        # Richieste di registrazione: SOLO il super admin accetta (o respinge)
        # un nuovo giocatore. Il backend verifica il token, qui si presenta solo.
        if "approve_user" in request.POST or "reject_user" in request.POST:
            approving = "approve_user" in request.POST
            user_id = request.POST.get("approve_user" if approving else "reject_user")
            try:
                if approving:
                    out = api.approve_user(user_id, token)
                    messages.success(request, f"Giocatore «{out['alias']}» approvato.")
                else:
                    api.reject_user(user_id, token)
                    messages.success(request, "Richiesta respinta ed eliminata.")
            except api.ApiError as exc:
                messages.error(request, str(exc))
            return redirect("admin")
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
    # Richieste di registrazione in attesa di approvazione, mostrate in cima.
    users = _safe(request, api.list_users, default=[])
    pending = [u for u in users if not u.get("is_approved")]
    # Voce sintetica: stato per lingua + URL del backend per le anteprime audio
    # (il tag <audio> del browser chiama direttamente GET /tts del backend).
    tts = _safe(request, api.tts_status, default=None)
    return render(
        request,
        "web/admin.html",
        {"settings": settings, "pending": pending, "tts": tts, "backend_url": api.BASE},
    )


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
