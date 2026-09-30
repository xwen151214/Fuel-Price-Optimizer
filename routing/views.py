import json
import requests
from django.shortcuts import render
from rest_framework.generics import (RetrieveAPIView)
from rest_framework.response import Response
from rest_framework import status
from .services import (geocode, RoutingError, load_stations, get_route)
from .planner import (stations_on_route, plan_fuel)


def get_route_data(start_location, end_location):
    start_ll = geocode(start_location)
    end_ll = geocode(end_location)
    coordinates, miles = get_route(start_ll, end_ll)
    return coordinates, miles


def get_fuel_plan(coordinates, miles):
    stations = load_stations()
    candidates = stations_on_route(coordinates, stations, corridor_miles=10)
    return plan_fuel(candidates, miles)


def serialize_stops(stops):
    return [
        {
            "name": s["truck_stop_name"], "city": s["city"], "state": s["state"],
            "lat": s["lat"], "lng": s["lng"], "price": s["retail_price"],
            "mile": round(s["mile"], 1), "gallons": s["gallons"], "cost": s["cost"],
        }
        for s in stops
    ]


class RouteView(RetrieveAPIView):

    def get(self, request):

        start_location = request.query_params.get("start_location", "").strip()
        end_location = request.query_params.get("end_location", "").strip()
        if not start_location or not end_location:
            return Response(   
                {"error": "Both 'start_location' and 'end_location' query params are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            coordinates, miles = get_route_data(start_location, end_location)
        except RoutingError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except requests.RequestException:
            return Response({"error": "Routing service unavailable"},status=status.HTTP_502_BAD_GATEWAY)

        try:
            stops, total_cost, total_gallons = get_fuel_plan(coordinates, miles)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        return Response({
            "start": start_location,
            "finish": end_location,
            "total_miles": round(miles, 1),
            "total_gallons": total_gallons,
            "total_fuel_cost": total_cost,
            "route": {"type": "LineString", "coordinates": coordinates},
            "fuel_stops": serialize_stops(stops),
        })


def route_map(request):

    start_location = request.GET.get("start_location", "").strip()
    end_location = request.GET.get("end_location", "").strip()

    context = {"start_location": start_location, "end_location": end_location}

    if not start_location or not end_location:
        return render(request, "routing/map.html", context)

    try:
        coordinates, miles = get_route_data(start_location, end_location)
        stops, total_cost, total_gallons = get_fuel_plan(coordinates, miles)
    except RoutingError as e:
        context["error"] = str(e)
        return render(request, "routing/map.html", context)
    except requests.RequestException:
        context["error"] = "Routing service unavailable"
        return render(request, "routing/map.html", context)
    except ValueError as e:
        context["error"] = str(e)
        return render(request, "routing/map.html", context)

    context["total_miles"] = round(miles, 1)
    context["total_gallons"] = total_gallons
    context["total_fuel_cost"] = total_cost
    context["route_json"] = json.dumps({"type": "LineString", "coordinates": coordinates})
    context["fuel_stops_json"] = json.dumps(serialize_stops(stops))
    return render(request, "routing/map.html", context)
