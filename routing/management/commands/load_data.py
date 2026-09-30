import pandas as pd
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from ...models import FuelStation

class Command(BaseCommand):

    help = "loads csv data to database"

    def add_arguments(self, parser):
        return parser.add_argument("csv_path", type=str)

    def handle(self, *args, **kwargs):

        rows = []
        df = pd.read_csv(kwargs["csv_path"])
        for i in range(len(df) - 1):
            rows.append(
              FuelStation(
                  tracking_id=df.iloc[i]["OPIS Truckstop ID"],
                  truck_stop_name=df.iloc[i]["Truckstop Name"].strip(),
                  address = df.iloc[i]["Address"].strip(),
                  city = df.iloc[i]["City"].strip(),
                  state = df.iloc[i]["State"].strip(),
                  rack_id = df.iloc[i]["Rack ID"],
                  retail_price = df.iloc[i]["Retail Price"]
              )
            )
        FuelStation.objects.all().delete()
        FuelStation.objects.bulk_create(rows, batch_size=500)
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} stations"))

        
