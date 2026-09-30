from django.urls import path
from .views import RouteView, route_map

urlpatterns = [
    path("", RouteView.as_view(), name="get routes"),
    path("map/", route_map, name="get route map"),
]