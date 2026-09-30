from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from . import services
from .cache import geocode_local, LocalGeocodeError, _lookup
from .planner import plan_fuel, stations_on_route


class PlanFuelTests(TestCase):
    def mk(self, mile, price, name=None):
        return {"mile": mile, "retail_price": price, "truck_stop_name": name or f"S{mile}"}

    def test_no_stations_needed_short_trip(self):
        stops, cost, gallons = plan_fuel([], total_miles=300)
        self.assertEqual(stops, [])
        self.assertEqual(cost, 0.0)
        self.assertEqual(gallons, 0)

    def test_exactly_at_range_no_stop_needed(self):
        stops, cost, gallons = plan_fuel([], total_miles=500)
        self.assertEqual(stops, [])

    def test_single_stop_just_over_range(self):
        stations = [self.mk(450, 3.50)]
        stops, cost, gallons = plan_fuel(stations, total_miles=550)
        self.assertEqual(len(stops), 1)
        self.assertGreater(cost, 0)

    def test_prefers_cheaper_station_within_range(self):
        stations = [self.mk(100, 4.50), self.mk(400, 3.00)]
        stops, cost, gallons = plan_fuel(stations, total_miles=900)
        names = [s["truck_stop_name"] for s in stops]
        self.assertIn("S400", names)

    def test_fills_up_when_no_cheaper_station_in_range(self):
        stations = [self.mk(100, 3.00), self.mk(590, 5.00)]
        stops, cost, gallons = plan_fuel(stations, total_miles=1000)
        first = stops[0]
        self.assertAlmostEqual(first["gallons"], 10.0, delta=0.5)

    def test_unreachable_gap_raises(self):
        stations = [self.mk(100, 3.00)]
        with self.assertRaises(ValueError):
            plan_fuel(stations, total_miles=1000)

    def test_zero_distance_trip(self):
        stops, cost, gallons = plan_fuel([], total_miles=0)
        self.assertEqual(stops, [])
        self.assertEqual(cost, 0.0)

    def test_total_cost_matches_sum_of_stops(self):
        stations = [self.mk(300, 3.50), self.mk(700, 3.00), self.mk(1100, 3.20)]
        stops, cost, gallons = plan_fuel(stations, total_miles=1400)
        self.assertAlmostEqual(cost, sum(s["cost"] for s in stops), places=2)


class StationsOnRouteTests(TestCase):
    def test_empty_station_list_returns_empty(self):
        coords = [[-118.0, 34.0], [-117.0, 34.0]]
        self.assertEqual(stations_on_route(coords, [], corridor_miles=10), [])

    def test_station_far_from_route_excluded(self):
        coords = [[-118.0 + i * 0.01, 34.0] for i in range(50)]
        far_station = [{"truck_stop_name": "far", "retail_price": 3.0, "lat": 45.0, "lng": -100.0}]
        self.assertEqual(stations_on_route(coords, far_station, corridor_miles=10), [])

    def test_station_near_route_included_with_mile_marker(self):
        coords = [[-118.0 + i * 0.01, 34.0] for i in range(50)]
        near_station = [{"truck_stop_name": "near", "retail_price": 3.0, "lat": 34.001, "lng": -117.75}]
        result = stations_on_route(coords, near_station, corridor_miles=10)
        self.assertEqual(len(result), 1)
        self.assertIn("mile", result[0])


class GeocodeLocalTests(TestCase):
    def setUp(self):
        _lookup.cache_clear()

    def test_missing_state_raises(self):
        with self.assertRaises(LocalGeocodeError):
            geocode_local("Los Angeles")

    def test_unknown_city_raises(self):
        with self.assertRaises(LocalGeocodeError):
            geocode_local("Nowhereville, ZZ")

    def test_whitespace_and_case_tolerant(self):
        with self.assertRaises(LocalGeocodeError):
            geocode_local("    , CA")


class RoutePlanViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/routes/"

    def test_missing_params_returns_400(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_end_location_returns_400(self):
        resp = self.client.get(self.url, {"start_location": "Los Angeles, CA"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_blank_params_returns_400(self):
        resp = self.client.get(self.url, {"start_location": "  ", "end_location": "  "})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("routing.views.geocode")
    def test_unknown_city_returns_400(self, mock_geocode):
        mock_geocode.side_effect = services.RoutingError("Unknown city/state: Foo, ZZ")
        resp = self.client.get(self.url, {"start_location": "Foo, ZZ", "end_location": "New York, NY"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", resp.json())

    @patch("routing.views.get_route")
    @patch("routing.views.geocode")
    def test_osrm_down_returns_502(self, mock_geocode, mock_route):
        import requests
        mock_geocode.return_value = (34.0, -118.0)
        mock_route.side_effect = requests.ConnectionError("no network")
        resp = self.client.get(self.url, {"start_location": "Los Angeles, CA", "end_location": "New York, NY"})
        self.assertEqual(resp.status_code, status.HTTP_502_BAD_GATEWAY)

    @patch("routing.views.load_stations")
    @patch("routing.views.get_route")
    @patch("routing.views.geocode")
    def test_unreachable_fuel_gap_returns_422(self, mock_geocode, mock_route, mock_stations):
        mock_geocode.side_effect = [(34.0, -118.0), (40.7, -74.0)]
        mock_route.return_value = ([[-118.0, 34.0], [-74.0, 40.7]], 2800.0)
        mock_stations.return_value = ()
        resp = self.client.get(self.url, {"start_location": "Los Angeles, CA", "end_location": "New York, NY"})
        self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    @patch("routing.views.load_stations")
    @patch("routing.views.get_route")
    @patch("routing.views.geocode")
    def test_successful_short_trip_no_stops(self, mock_geocode, mock_route, mock_stations):
        mock_geocode.side_effect = [(34.0, -118.0), (34.5, -117.5)]
        mock_route.return_value = ([[-118.0, 34.0], [-117.5, 34.5]], 40.0)
        mock_stations.return_value = ()
        resp = self.client.get(self.url, {"start_location": "Los Angeles, CA", "end_location": "Nearby, CA"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body["fuel_stops"], [])
        self.assertEqual(body["total_fuel_cost"], 0.0)

class GetRouteCacheTests(TestCase):
    @patch("routing.services.requests.get")
    def test_repeat_call_skips_the_osrm_request(self, mock_get):
        from django.core.cache import cache as django_cache
        django_cache.clear()

        mock_response = mock_get.return_value
        mock_response.json.return_value = {
            "code": "Ok",
            "routes": [{"geometry": {"coordinates": [[-118.0, 34.0], [-74.0, 40.7]]}, "distance": 4506000.0}],
        }

        first = services.get_route((34.0, -118.0), (40.7, -74.0))
        second = services.get_route((34.0, -118.0), (40.7, -74.0))

        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(first, second)


class RouteMapViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/routes/map/"

    def test_missing_params_renders_form_without_error(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "route_json")

    @patch("routing.views.geocode")
    def test_unknown_city_renders_error(self, mock_geocode):
        mock_geocode.side_effect = services.RoutingError("Unknown city/state: Foo, ZZ")
        resp = self.client.get(self.url, {"start_location": "Foo, ZZ", "end_location": "New York, NY"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Unknown city/state")

    @patch("routing.views.load_stations")
    @patch("routing.views.get_route")
    @patch("routing.views.geocode")
    def test_successful_request_renders_map(self, mock_geocode, mock_route, mock_stations):
        mock_geocode.side_effect = [(34.0, -118.0), (34.5, -117.5)]
        mock_route.return_value = ([[-118.0, 34.0], [-117.5, 34.5]], 40.0)
        mock_stations.return_value = ()
        resp = self.client.get(self.url, {"start_location": "Los Angeles, CA", "end_location": "Nearby, CA"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "LineString")