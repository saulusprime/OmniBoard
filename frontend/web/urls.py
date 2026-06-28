from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("giocatori/", views.users_list, name="users_list"),
    path("giocatori/nuovo/", views.user_create, name="user_create"),
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
]
