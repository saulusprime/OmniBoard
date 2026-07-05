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
    path("giocatori/<int:user_id>/", views.user_detail, name="user_detail"),
    path("gruppi/", views.groups, name="groups"),
    path("gruppi/proponi/", views.group_propose, name="group_propose"),
    path(
        "gruppi/proposte/<int:proposal_id>/vota/",
        views.proposal_vote,
        name="proposal_vote",
    ),
    path("classifiche/", views.rankings, name="rankings"),
    path("partite/registra/", views.match_create, name="match_create"),
    path("gioca/", views.play_setup, name="play_setup"),
    path("partite/<int:session_id>/", views.play, name="play"),
    path("partite/<int:session_id>/mossa/", views.play_move, name="play_move"),
    path("partite/<int:session_id>/mossa.json", views.play_move_json, name="play_move_json"),
    path("partite/<int:session_id>/stato.json", views.play_state_json, name="play_state_json"),
    path("admin/", views.admin, name="admin"),
    path("admin/ia/", views.admin_ai, name="admin_ai"),
]
