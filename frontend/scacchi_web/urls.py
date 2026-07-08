from django.urls import include, path

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),  # set_language (selettore lingua)
    path("", include("web.urls")),
]
