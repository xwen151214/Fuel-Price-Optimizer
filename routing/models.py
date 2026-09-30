from django.db import models

# Create your models here.
class FuelStation(models.Model):

    id = models.AutoField(primary_key=True, null=False)
    tracking_id = models.IntegerField( null=False)
    truck_stop_name = models.CharField(max_length=50, null=False)
    address = models.CharField(max_length=50, null=False)
    city = models.CharField(max_length=25, null=False)
    state = models.CharField(max_length=2, null=False)
    rack_id = models.IntegerField(null=False)
    retail_price = models.FloatField(null=False)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)