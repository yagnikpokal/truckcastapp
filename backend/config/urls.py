from django.urls import path

from routing.views import analyze, geocode, health, heatmap, spa_index

urlpatterns = [
    path("api/health", health),
    path("api/geocode", geocode),
    path("api/analyze", analyze),
    path("api/heatmap", heatmap),
    path("", spa_index),
]
