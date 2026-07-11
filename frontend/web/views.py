"""Viste del frontend: presentazione e form, con i dati letti dal backend."""

from __future__ import annotations

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

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
    """Area community: chi è online, le proprie partite, SFIDE pendenti e notifiche.

    È il posto dove lo sfidato scopre gli inviti a giocare (li accetta o
    rifiuta) e dove le notifiche si leggono: aprire la pagina le segna lette
    (la campanella in navbar si azzera al giro di polling successivo).
    """
    online = _safe(request, api.community_online, default={"online": []})
    live = _safe(request, api.community_live, default={}) or {}
    token = request.session.get("auth_token")
    games = []
    challenges = {"incoming": [], "outgoing": []}
    notices = []
    if token:
        data = _safe(request, lambda: api.my_games(token), default={"games": []})
        games = (data or {}).get("games", [])
        challenges = _safe(request, lambda: api.my_challenges(token), default=challenges)
        notif = _safe(request, lambda: api.notifications_list(token), default={}) or {}
        notices = notif.get("notifications", [])
        if notif.get("unread"):
            _safe(request, lambda: api.notifications_read(token))
    return render(
        request,
        "web/community.html",
        {
            "online": online.get("online", []),
            "live": live.get("live", []),
            "my_games": games,
            "challenges": challenges,
            "notices": notices,
        },
    )


def community_json(request):
    """Snapshot JSON per i badge e l'area community (polling leggero dal client).

    Se il visitatore è loggato fa anche da HEARTBEAT: chiamarlo periodicamente
    mantiene il badge di presenza. Include i punti del giocatore (badge navbar)
    e il conteggio delle notifiche non lette (campanella).
    """
    token = request.session.get("auth_token")
    me = None
    games = []
    unread = 0
    if token:
        try:
            api.heartbeat(token)
            games = api.my_games(token).get("games", [])
            unread = api.notifications_list(token).get("unread", 0)
        except api.ApiError:
            token = None  # sessione backend scaduta: si continua da anonimi
    try:
        online = api.community_online().get("online", [])
    except api.ApiError:
        return JsonResponse({"error": "backend non raggiungibile"}, status=503)
    auth_user = request.session.get("auth_user")
    if auth_user:
        me = next((u for u in online if u["id"] == auth_user["id"]), None)
    try:
        live = api.community_live().get("live", [])
    except api.ApiError:
        live = []
    return JsonResponse(
        {"online": online, "my_games": games, "me": me, "unread": unread, "live": live}
    )


def watch(request, session_id):
    """Pagina SPETTATORE: partita live in sola lettura o replay animato.

    Nessuna azione di gioco: solo scacchiera, stato/orologio e — a partita
    finita — i controlli della riproduzione automatica dallo storico mosse.
    """
    session = _safe(request, lambda: api.get_session(session_id))
    if session is None:
        return redirect("community")
    return render(request, "web/watch.html", {"s": session, "session_id": session_id})


def challenge_new(request, user_id):
    """Form della sfida: gioco, colore dello sfidante, cadenza opzionale."""
    target = _safe(request, lambda: api.get_user(user_id))
    if target is None or not request.session.get("auth_token"):
        return redirect("community")
    if request.method == "POST":
        data = {
            "game_code": request.POST.get("game_code", "chess"),
            "to_user_id": user_id,
            "side": request.POST.get("side", "x"),
        }
        if request.POST.get("time_category"):
            data["time_category"] = request.POST["time_category"]
            if request.POST.get("time_base_min"):
                data["time_base_min"] = int(request.POST["time_base_min"])
            data["time_inc_s"] = int(request.POST.get("time_inc_s") or 0)
        try:
            api.create_challenge(data, request.session["auth_token"])
            messages.success(
                request,
                _("Sfida spedita a %(alias)s: parte quando l'accetta.")
                % {"alias": target["alias"]},
            )
            return redirect("community")
        except api.ApiError as exc:
            messages.error(request, str(exc))
    games = [g for g in _safe(request, api.list_games, default=[]) if g.get("playable")]
    return render(request, "web/challenge_form.html", {"target": target, "games": games})


def challenge_action(request, invite_id):
    """Risposta a una sfida (POST): accetta (apre la partita), rifiuta o ritira."""
    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("accept", "decline", "cancel"):
            token = request.session.get("auth_token")
            try:
                out = api.challenge_action(invite_id, action, token)
                if action == "accept" and out.get("session_id"):
                    messages.success(request, _("Sfida accettata: si gioca!"))
                    return redirect("play", session_id=out["session_id"])
                messages.success(
                    request,
                    _("Sfida rifiutata.") if action == "decline" else _("Sfida ritirata."),
                )
            except api.ApiError as exc:
                messages.error(request, str(exc))
    return redirect("community")


# ----- Tutorial: istruzione guidata con voce sintetica -----
def learn_index(request):
    """Indice delle lezioni per gioco, con i progressi del giocatore loggato."""
    token = request.session.get("auth_token")
    data = _safe(request, lambda: api.list_lessons(token), default={"lessons": []})
    # Raggruppa per gioco mantenendo l'ordine (gioco, grado) del backend.
    by_game: dict[str, list] = {}
    for lesson in data.get("lessons", []):
        by_game.setdefault(lesson["game_name"], []).append(lesson)
    return render(request, "web/learn_index.html", {"by_game": by_game})


def learn_lesson(request, code):
    """Una lezione a passi: scacchiera preimpostata, evidenziazioni, verifica, voce."""
    token = request.session.get("auth_token")
    lesson = _safe(request, lambda: api.get_lesson(code, token))
    if lesson is None:
        return redirect("learn_index")
    return render(
        request,
        "web/learn_lesson.html",
        {"lesson": lesson, "backend_url": api.BASE},
    )


def learn_progress_json(request, code):
    """Proxy del salvataggio progressi: aggiunge il token della sessione Django."""
    if request.method != "POST":
        return JsonResponse({"error": "Metodo non consentito"}, status=405)
    token = request.session.get("auth_token")
    if not token:
        return JsonResponse({"saved": False, "reason": "anonimo"})  # nulla da salvare
    try:
        step = int(request.POST.get("step", "0"))
        completed = request.POST.get("completed") == "1"
        out = api.save_lesson_progress(code, step, completed, token)
        return JsonResponse({"saved": True, **out})
    except (ValueError, api.ApiError) as exc:
        return JsonResponse({"saved": False, "reason": str(exc)}, status=400)


def user_detail(request, user_id):
    user = _safe(request, lambda: api.get_user(user_id))
    if user is None:
        return redirect("users_list")
    # Stima delle blunder: analizza (in background) le partite non ancora
    # analizzate; il profilo si arricchisce alle letture successive.
    if request.method == "POST" and "analyze_history" in request.POST:
        try:
            out = api.analyze_user_history(user_id)
            if out["queued"]:
                messages.success(
                    request,
                    f"Analisi avviata su {out['queued']} partite: ricarica tra qualche "
                    "istante per vedere la precisione aggiornata.",
                )
            else:
                messages.success(request, "Tutte le partite recenti sono già analizzate.")
        except api.ApiError as exc:
            messages.error(request, str(exc))
        return redirect("user_detail", user_id=user_id)
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
    ratings = _safe(request, lambda: api.get_user_ratings(user_id), default=None)
    return render(
        request,
        "web/user_detail.html",
        {
            "ratings": ratings,
            "u": user,
            "history": history,
            "chess": chess,
            "prefs_form": prefs_form,
        },
    )


def groups(request):
    groups_ = _safe(request, api.list_groups, default=[])
    proposals = _safe(request, api.list_proposals, default=[])
    users = _safe(request, api.list_users, default=[])
    token = request.session.get("auth_token")
    my_invites = _safe(request, lambda: api.my_group_invites(token), default=[]) if token else []
    return render(
        request,
        "web/groups.html",
        {
            "groups": groups_,
            "proposals": proposals,
            "vote_form": VoteForm(users=users),
            "my_invites": my_invites,
        },
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


def group_detail(request, group_id):
    """Scheda del gruppo: membri, gestione, classifica, tornei e sfide di gruppo."""
    group = _safe(request, lambda: api.group_detail(group_id))
    if group is None:
        return redirect("groups")
    game_code = request.GET.get("game") or ""
    ranking = _safe(request, lambda: api.group_ranking(group_id, game_code or None), default={})
    games = [g for g in _safe(request, api.list_games, default=[]) if g.get("playable")]
    tournaments = _safe(request, lambda: api.list_human_tournaments(group_id=group_id), default={})
    matches = _safe(request, lambda: api.list_group_matches(group_id), default={}) or {}
    users = _safe(request, api.list_users, default=[])
    all_groups = _safe(request, api.list_groups, default=[])
    member_ids = {m["user_id"] for m in group["members"]}
    my_role = None
    if request.session.get("auth_user"):
        me = request.session["auth_user"]["id"]
        my_role = next((m["role"] for m in group["members"] if m["user_id"] == me), None)
    return render(
        request,
        "web/group_detail.html",
        {
            "g": group,
            "ranking": (ranking or {}).get("ranking", []),
            "games": games,
            "sel_game": game_code,
            "tournaments": (tournaments or {}).get("tournaments", []),
            "matches": matches.get("matches", []),
            "record": matches.get("record"),
            "rival_groups": [x for x in all_groups if x["id"] != group_id],
            "invitable": [u for u in users if u["id"] not in member_ids],
            "my_role": my_role,
        },
    )


def group_match_create(request, group_id):
    """Proposta di sfida gruppo-vs-gruppo (POST dalla scheda del gruppo)."""
    if request.method == "POST":
        token = request.session.get("auth_token")
        data = {
            "game_code": request.POST.get("game_code", "chess"),
            "challenger_group_id": group_id,
            "opponent_group_id": int(request.POST.get("opponent_group_id") or 0),
            "boards": int(request.POST.get("boards") or 2),
        }
        try:
            api.create_group_match(data, token)
            messages.success(
                request, _("Sfida proposta: i manager dell'altro gruppo sono stati avvisati.")
            )
        except api.ApiError as exc:
            messages.error(request, str(exc))
    return redirect("group_detail", group_id=group_id)


def group_match_detail(request, match_id):
    """La sfida a squadre: tavolieri, esiti e punteggio."""
    try:
        m = api.group_match(match_id)
    except api.ApiError as exc:
        messages.error(request, str(exc))
        return redirect("groups")
    return render(request, "web/group_match_detail.html", {"m": m})


def group_match_action(request, match_id):
    """Accetta/rifiuta/ritira una sfida di gruppo (POST, manager)."""
    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("accept", "decline", "cancel"):
            token = request.session.get("auth_token")
            try:
                api.group_match_action(match_id, action, token)
                done = {
                    "accept": _("Sfida accettata: formazioni schierate, si gioca!"),
                    "decline": _("Sfida di gruppo rifiutata."),
                    "cancel": _("Sfida di gruppo ritirata."),
                }
                messages.success(request, done[action])
            except api.ApiError as exc:
                messages.error(request, str(exc))
    return redirect("group_match_detail", match_id=match_id)


def group_action(request, group_id):
    """Azioni di gestione del gruppo (POST): invita, espelli/esci, cambia ruolo."""
    if request.method != "POST":
        return redirect("group_detail", group_id=group_id)
    token = request.session.get("auth_token")
    action = request.POST.get("action")
    try:
        if action == "invite":
            api.group_invite(group_id, request.POST.get("user_id"), token)
            messages.success(request, _("Invito spedito."))
        elif action == "remove":
            api.remove_group_member(group_id, request.POST.get("user_id"), token)
            messages.success(request, _("Membro rimosso dal gruppo."))
        elif action == "role":
            api.change_group_role(
                group_id, request.POST.get("user_id"), request.POST.get("role"), token
            )
            messages.success(request, _("Ruolo aggiornato."))
    except api.ApiError as exc:
        messages.error(request, str(exc))
    return redirect("group_detail", group_id=group_id)


def group_invite_respond(request, invite_id):
    """Risposta dell'invitato (POST): accetta o rifiuta l'invito al gruppo."""
    if request.method == "POST":
        token = request.session.get("auth_token")
        accept = request.POST.get("accept") == "1"
        try:
            out = api.respond_group_invite(invite_id, accept, token)
            if accept:
                messages.success(
                    request, _("Benvenuto nel gruppo «%(name)s»!") % {"name": out["group_name"]}
                )
            else:
                messages.success(request, _("Invito rifiutato."))
        except api.ApiError as exc:
            messages.error(request, str(exc))
    return redirect("groups")


def tournaments_page(request):
    """Tornei fra giocatori: elenco e organizzazione (eliminazione o girone)."""
    token = request.session.get("auth_token")
    if request.method == "POST":
        data = {
            "game_code": request.POST.get("game_code", "chess"),
            "name": request.POST.get("name", "").strip(),
            "format": request.POST.get("format", "knockout"),
            "double_round": request.POST.get("double_round") == "on",
        }
        if request.POST.get("group_id"):
            data["group_id"] = int(request.POST["group_id"])
        try:
            created = api.create_human_tournament(data, token)
            api.tournament_action(created["id"], "join", token)  # chi organizza gioca
            messages.success(request, _("Torneo creato: le iscrizioni sono aperte."))
            return redirect("tournament_detail", tournament_id=created["id"])
        except api.ApiError as exc:
            messages.error(request, str(exc))
    games = [g for g in _safe(request, api.list_games, default=[]) if g.get("playable")]
    data = _safe(
        request,
        lambda: api.list_human_tournaments(request.GET.get("game") or None),
        default={},
    )
    groups_ = _safe(request, api.list_groups, default=[])
    me = (request.session.get("auth_user") or {}).get("id")
    my_groups = [g for g in groups_ if any(m["user_id"] == me for m in g.get("members", []))]
    return render(
        request,
        "web/tournaments.html",
        {
            "tournaments": (data or {}).get("tournaments", []),
            "games": games,
            "sel_game": request.GET.get("game") or "",
            "my_groups": my_groups,
        },
    )


def tournament_detail(request, tournament_id):
    """Tabellone (eliminazione) o classifica (girone), con iscrizione e avvio."""
    try:
        t = api.human_tournament(tournament_id)
    except api.ApiError as exc:
        messages.error(request, str(exc))
        return redirect("tournaments")
    me = (request.session.get("auth_user") or {}).get("id")
    return render(
        request,
        "web/tournament_detail.html",
        {
            "t": t,
            "joined": any(p["user_id"] == me for p in t["players"]),
            "is_creator": me == t["created_by"],
            "me": me,
        },
    )


def tournament_action(request, tournament_id):
    """Iscrizione, ritiro o avvio del torneo (POST)."""
    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("join", "leave", "start"):
            token = request.session.get("auth_token")
            try:
                api.tournament_action(tournament_id, action, token)
                done = {
                    "join": _("Iscrizione registrata."),
                    "leave": _("Iscrizione ritirata."),
                    "start": _("Torneo avviato: le partite sono in «Community»."),
                }
                messages.success(request, done[action])
            except api.ApiError as exc:
                messages.error(request, str(exc))
    return redirect("tournament_detail", tournament_id=tournament_id)


def rankings(request):
    games = _safe(request, api.list_games, default=[])
    universal = _safe(request, api.universal_ranking, default=[])
    game_code = request.GET.get("game")
    scope = request.GET.get("scope", "global")
    country = request.GET.get("country") or None
    region = request.GET.get("region") or None
    game_rank = None
    elo_rank = None
    if game_code:
        game_rank = _safe(
            request,
            lambda: api.game_ranking(game_code, scope, country, region),
            default=[],
        )
        # Classifica Elo (rating di forza, stagione corrente): affianca i punti.
        elo_rank = _safe(request, lambda: api.elo_ranking(game_code), default=None)
    return render(
        request,
        "web/rankings.html",
        {
            "games": games,
            "universal": universal,
            "game_rank": game_rank,
            "elo_rank": elo_rank,
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
def play_explain_json(request, session_id):
    """«Spiegami questa mossa»: proxy verso il backend (LLM, risposta salvata)."""
    if request.method != "POST":
        return JsonResponse({"error": "POST richiesto"}, status=405)
    try:
        ply = int(request.POST.get("ply", "0"))
        return JsonResponse(api.explain_move(session_id, ply))
    except api.ApiError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status or 502)
    except ValueError:
        return JsonResponse({"error": "Semimossa non valida"}, status=400)


def user_stats(request, user_id):
    """Statistiche avanzate del giocatore + raccolta delle mosse geniali."""
    data = _safe(request, lambda: api.get_user_insights(user_id))
    if data is None:
        return redirect("user_detail", user_id=user_id)
    gems = _safe(request, lambda: api.get_user_brilliancies(user_id), default={})
    return render(
        request,
        "web/user_stats.html",
        {
            "st": data,
            "gems": (gems or {}).get("brilliancies", []),
            "user_id": user_id,
            "backend_url": api.BASE,  # per gli screenshot board.png della galleria
        },
    )


def puzzles_list(request):
    """Catalogo dei puzzle: filtri, progressi (se loggati), generazione dai blunder."""
    token = request.session.get("auth_token")
    if request.method == "POST" and "generate" in request.POST:
        if not token:
            messages.error(request, _("Accedi per generare i puzzle dai tuoi errori."))
        else:
            try:
                out = api.puzzles_generate(token)
                messages.success(
                    request,
                    _("Creati %(n)s puzzle dai tuoi errori.") % {"n": out["created"]},
                )
            except api.ApiError as exc:
                messages.error(request, str(exc))
        return redirect("puzzles")
    theme = request.GET.get("theme") or None
    data = _safe(
        request, lambda: api.list_puzzles(token, theme=theme), default={"puzzles": [], "themes": []}
    )
    return render(
        request,
        "web/puzzles.html",
        {"data": data, "sel_theme": theme or ""},
    )


def puzzle_play(request, puzzle_id):
    puzzle = _safe(request, lambda: api.get_puzzle(puzzle_id))
    if puzzle is None:
        return redirect("puzzles")
    return render(request, "web/puzzle_play.html", {"p": puzzle, "ui": _play_ui_strings()})


def puzzle_attempt_json(request, puzzle_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST richiesto"}, status=405)
    token = request.session.get("auth_token")
    try:
        step = int(request.POST.get("step", "0"))
        return JsonResponse(
            api.puzzle_attempt(puzzle_id, step, request.POST.get("move", ""), token)
        )
    except api.ApiError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status or 502)
    except ValueError:
        return JsonResponse({"error": "step non valido"}, status=400)


def arena(request):
    """Arena IA: classifica Elo dei concorrenti e tornei IA-vs-IA.

    La classifica si alimenta da ogni partita IA-vs-IA conclusa; il form crea un
    torneo (girone all'italiana) che il backend gioca in sequenza in background.
    """
    all_games = _safe(request, api.list_games, default=[])
    games = [g for g in all_games if g.get("playable")]
    game_code = request.GET.get("game") or (
        "chess" if any(g["code"] == "chess" for g in games) else (games[0]["code"] if games else "")
    )

    if request.method == "POST":
        data = {
            "game_code": request.POST.get("game_code", "chess"),
            "participants": request.POST.getlist("participants"),
            "double_round": request.POST.get("double_round") == "on",
            "name": request.POST.get("name", "").strip(),
        }
        try:
            created = api.create_tournament(data)
            messages.success(request, f"Torneo «{created['name']}» avviato.")
            return redirect("arena_tournament", tournament_id=created["id"])
        except api.ApiError as exc:
            messages.error(request, str(exc))

    ranking = (
        _safe(request, lambda: api.arena_ranking(game_code), default={"rows": []})
        if game_code
        else {"rows": []}
    )
    return render(
        request,
        "web/arena.html",
        {
            "games": games,
            "game_code": game_code,
            "ranking": ranking.get("rows", []),
            "identities": _safe(request, api.arena_identities, default=[]),
            "tournaments": _safe(request, api.arena_tournaments, default=[]),
        },
    )


def arena_tournament(request, tournament_id):
    """Dettaglio di un torneo: classifica del girone e partite (con link)."""
    try:
        tournament = api.arena_tournament(tournament_id)
    except api.ApiError as exc:
        messages.error(request, str(exc))
        return redirect("arena")
    return render(request, "web/arena_tournament.html", {"t": tournament})


def arena_tournament_json(request, tournament_id):
    """Stato del torneo per il polling della pagina di dettaglio."""
    try:
        return JsonResponse(api.arena_tournament(tournament_id))
    except api.ApiError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status or 502)


def play_setup(request):
    users = _safe(request, api.list_users, default=[])
    # Avviso SOFT anti-tilt per chi è loggato: banner nel setup, mai un blocco
    # (il blocco forzato esiste solo come opzione admin, lato backend).
    tilt_state = None
    me = request.session.get("auth_user")
    if me:
        tilt_state = _safe(request, lambda: api.get_tilt(me["id"]), default=None)
        if tilt_state and not tilt_state.get("tilted"):
            tilt_state = None
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
                    # "motore:<livello>" | "stockfish:<livello>". Per Stockfish e
                    # motore locale si scinde in type + level
                    # (preset Zeus/Atena/…); per l'IA il suffisso è il CONCORRENTE
                    # scelto («gioca contro Claude/Gemini/…», nessuno = attivo).
                    kind = form.cleaned_data[f"{side}_type"]
                    if kind == "human":
                        return {"type": "human", "user_id": int(form.cleaned_data[f"{side}_user"])}
                    if kind.startswith("stockfish:"):
                        return {"type": "stockfish", "level": kind.split(":", 1)[1]}
                    if kind.startswith("ai:"):
                        return {"type": "ai", "provider": kind.split(":", 1)[1]}
                    if kind.startswith("motore:"):
                        return {"type": "ai", "level": kind.split(":", 1)[1]}
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
                # Posizione iniziale FEN (solo scacchi): la valida il backend.
                if form.cleaned_data.get("start_fen", "").strip():
                    data["start_fen"] = form.cleaned_data["start_fen"].strip()
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
    return render(request, "web/play_setup.html", {"form": form, "tilt": tilt_state})


def _play_ui_strings():
    """Stringhe della pagina di gioco usate DAL JAVASCRIPT, tradotte qui
    (gettext le vede, il template le passa con json_script)."""
    return {
        "thinking_ai": _("L'IA sta pensando…"),
        "waiting_opponent": _("In attesa della mossa dell'avversario…"),
        "turn_of": _("Tocca a:"),
        "ai_suffix": _("(IA)"),
        "won_by": _("Ha vinto"),
        "draw": _("Patta"),
        "by_time": _("(tempo scaduto)"),
        "by_repetition": _("(triplice ripetizione)"),
        "by_resign": _("(per abbandono)"),
        "by_agreement": _("(patta d'accordo)"),
        "opening": _("Apertura:"),
        "hint_prefix": _("Suggerimento:"),
        "invalid_move": _("Mossa non valida"),
        "confirm_resign": _("Abbandonare la partita?"),
        "explain_busy": _("Sto guardando la posizione…"),
        "explain_error": _("Spiegazione non disponibile (backend irraggiungibile?)"),
        "analysis_running": _("Analisi in corso… (Stockfish valuta ogni posizione)"),
        "analysis_done": _("Analisi completata: ?? = blunder, ? = errore, ?! = imprecisione."),
        "white": _("Bianco"),
        "black": _("Nero"),
        "promotion": _("Promozione"),
        "board": _("Scacchiera"),
        "empty_square": _("vuota"),
        "row": _("riga"),
        "column": _("colonna"),
        "drop_col": _("Gioca nella colonna"),
        # Forza 4: i lati per gli screen reader sono i colori dei dischi.
        "c4_red": _("pedina rossa"),
        "c4_yellow": _("pedina gialla"),
        # Nomi dei pezzi per le etichette ARIA delle caselle (screen reader).
        "pieces": {
            "♔": _("re bianco"),
            "♕": _("donna bianca"),
            "♖": _("torre bianca"),
            "♗": _("alfiere bianco"),
            "♘": _("cavallo bianco"),
            "♙": _("pedone bianco"),
            "♚": _("re nero"),
            "♛": _("donna nera"),
            "♜": _("torre nera"),
            "♝": _("alfiere nero"),
            "♞": _("cavallo nero"),
            "♟": _("pedone nero"),
            "⛀": _("pedina bianca"),
            "⛁": _("dama bianca"),
            "⛂": _("pedina nera"),
            "⛃": _("dama nera"),
            "○": _("pedina bianca"),
            "●": _("pedina nera"),
        },
        "promo_labels": {
            "q": _("Donna"),
            "r": _("Torre"),
            "b": _("Alfiere"),
            "n": _("Cavallo"),
        },
        "nav_first": _("Inizio"),
        "nav_prev": _("Indietro"),
        "nav_next": _("Avanti"),
        "nav_last": _("Fine"),
    }


def play(request, session_id):
    session = _safe(request, lambda: api.get_session(session_id))
    if session is None:
        return redirect("play_setup")
    config = _safe(request, api.get_config, default={})
    return render(
        request,
        "web/play.html",
        {
            "ui": _play_ui_strings(),
            "s": session,
            # Chi sta guardando: nelle partite a distanza il client abilita solo
            # il lato di questo giocatore (None = visitatore anonimo/hotseat).
            "my_user_id": (request.session.get("auth_user") or {}).get("id"),
            "backend_url": api.BASE,  # per il download diretto della GIF
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


def play_replay_json(request, session_id):
    """Moviola: le posizioni della partita, per il rewind lato client."""
    try:
        return JsonResponse(api.session_replay(session_id))
    except api.ApiError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


def play_note_json(request, session_id):
    """Salva una nota su una semimossa (col token del giocatore, se loggato)."""
    if request.method != "POST":
        return JsonResponse({"error": "Metodo non consentito"}, status=405)
    try:
        ply = int(request.POST.get("ply", "0"))
        out = api.session_note(
            session_id,
            ply,
            request.POST.get("text", ""),
            token=request.session.get("auth_token"),
        )
        return JsonResponse(out)
    except (ValueError, api.ApiError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


def play_analysis_json(request, session_id):
    """Avvia (POST) o legge (GET) l'analisi post-partita."""
    try:
        if request.method == "POST":
            return JsonResponse(api.start_analysis(session_id))
        return JsonResponse(api.get_analysis(session_id))
    except api.ApiError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status or 400)


def play_hint_json(request, session_id):
    """Suggerimento di mossa (motore a budget ridotto), col token se loggati."""
    if request.method != "POST":
        return JsonResponse({"error": "Metodo non consentito"}, status=405)
    try:
        return JsonResponse(api.session_hint(session_id, token=request.session.get("auth_token")))
    except api.ApiError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status or 400)


def play_endgame_json(request, session_id):
    """Abbandono e patta d'accordo (proxy col token della sessione, se loggati)."""
    if request.method != "POST":
        return JsonResponse({"error": "Metodo non consentito"}, status=405)
    token = request.session.get("auth_token")
    side = request.POST.get("side", "")
    try:
        if request.POST.get("what") == "resign":
            return JsonResponse(api.session_resign(session_id, side, token=token))
        return JsonResponse(
            api.session_draw(session_id, side, request.POST.get("action", "offer"), token=token)
        )
    except api.ApiError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status or 400)


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
        # Sparring: motore interno vs Stockfish per stimare l'Elo (in background).
        if "start_sparring" in request.POST:
            try:
                api.start_sparring(
                    request.POST.get("sparring_level", "hermes"),
                    int(request.POST.get("sparring_games", "4") or 4),
                    int(request.POST.get("sparring_ms", "300") or 300),
                    token,
                )
                messages.success(request, "Sparring avviato: il risultato comparirà qui sotto.")
            except (ValueError, api.ApiError) as exc:
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
    sparring = _safe(request, api.sparring_state, default=None)
    return render(
        request,
        "web/admin.html",
        {
            "settings": settings,
            "pending": pending,
            "tts": tts,
            "sparring": sparring,
            "backend_url": api.BASE,
        },
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
