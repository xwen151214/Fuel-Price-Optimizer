import csv
from django.core.management.base import BaseCommand
from routing.models import FuelStation


class Command(BaseCommand):
    help = "Fill in lat/lng for stations by matching city+state against a cities CSV"

    def add_arguments(self, parser):
        parser.add_argument("cities_csv", type=str)

    def handle(self, *args, **options):
        lookup = {}
        with open(options["cities_csv"], encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                key = (row["city"].strip().lower(), row["state_id"].strip().upper())
                lookup[key] = (float(row["lat"]), float(row["lng"]))

        updated, missing = 0, 0
        for station in FuelStation.objects.filter(lat__isnull=True):
            key = (station.city.strip().lower(), station.state.strip().upper())
            if key in lookup:
                station.lat, station.lng = lookup[key]
                station.save(update_fields=["lat", "lng"])
                updated += 1
            else:
                missing += 1

        self.stdout.write(self.style.SUCCESS(f"Updated {updated}, missing {missing}"))