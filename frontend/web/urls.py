from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("giocatori/", views.users_list, name="users_list"),
    path("giocatori/nuovo/", views.user_create, name="user_create"),
    path("accedi/", views.login_view, name="login"),
    path("esci/", views.logout_view, name="logout"),
    path("community/", views.community, name="community"),
    path("community.json", views.community_json, name="community_json"),
    path("impara/", views.learn_index, name="learn_index"),
    path("impara/<slug:code>/", views.learn_lesson, name="learn_lesson"),
    path(
        "impara/<slug:code>/progresso.json",
        views.learn_progress_json,
        name="learn_progress_json",
    ),
    path("giocatori/<int:user_id>/", views.user_detail, name="user_detail"),
    path("gruppi/", views.groups, name="groups"),
    path("gruppi/proponi/", views.group_propose, name="group_propose"),
    path(
        "gruppi/proposte/<int:proposal_id>/vota/",
        views.proposal_vote,
        name="proposal_vote",
    ),
    path("classifiche/", views.rankings, name="rankings"),
    path("arena/", views.arena, name="arena"),
    path("arena/tornei/<int:tournament_id>/", views.arena_tournament, name="arena_tournament"),
    path(
        "arena/tornei/<int:tournament_id>/stato.json",
        views.arena_tournament_json,
        name="arena_tournament_json",
    ),
    path("partite/registra/", views.match_create, name="match_create"),
    path("gioca/", views.play_setup, name="play_setup"),
    path("partite/<int:session_id>/", views.play, name="play"),
    path("partite/<int:session_id>/mossa/", views.play_move, name="play_move"),
    path("partite/<int:session_id>/mossa.json", views.play_move_json, name="play_move_json"),
    path("partite/<int:session_id>/stato.json", views.play_state_json, name="play_state_json"),
    path("partite/<int:session_id>/replay.json", views.play_replay_json, name="play_replay_json"),
    path("partite/<int:session_id>/nota.json", views.play_note_json, name="play_note_json"),
    path(
        "partite/<int:session_id>/spiega.json",
        views.play_explain_json,
        name="play_explain_json",
    ),
    path("partite/<int:session_id>/hint.json", views.play_hint_json, name="play_hint_json"),
    path("partite/<int:session_id>/fine.json", views.play_endgame_json, name="play_endgame_json"),
    path(
        "partite/<int:session_id>/analisi.json",
        views.play_analysis_json,
        name="play_analysis_json",
    ),
    path("admin/", views.admin, name="admin"),
    path("admin/ia/", views.admin_ai, name="admin_ai"),
]
