"""Initial migration for the parcels app — Parcel and Permit models."""

import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Parcel",
            fields=[
                ("upi", models.CharField(max_length=32, primary_key=True, serialize=False)),
                ("boundary", django.contrib.gis.db.models.fields.PolygonField(srid=4326)),
                ("centroid", django.contrib.gis.db.models.fields.PointField(srid=4326)),
                ("owner_name", models.CharField(max_length=255)),
                (
                    "land_use",
                    models.CharField(
                        choices=[
                            ("residential", "Residential"),
                            ("commercial", "Commercial"),
                            ("mixed_use", "Mixed Use"),
                            ("industrial", "Industrial"),
                            ("institutional", "Institutional"),
                            ("agricultural", "Agricultural"),
                            ("green_zone", "Green Zone"),
                            ("transport", "Transport"),
                        ],
                        max_length=32,
                    ),
                ),
                ("district", models.CharField(max_length=64)),
                ("sector", models.CharField(max_length=64)),
                ("cell", models.CharField(max_length=64)),
                ("zone_type", models.CharField(max_length=64)),
                ("max_floors_allowed_by_zone", models.PositiveIntegerField(blank=True, null=True)),
                ("last_synced_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "parcels_parcel",
                "ordering": ["upi"],
                "indexes": [
                    models.Index(fields=["district"], name="parcels_par_distric_idx"),
                    models.Index(fields=["sector"], name="parcels_par_sector_idx"),
                    models.Index(fields=["zone_type"], name="parcels_par_zone_ty_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Permit",
            fields=[
                ("permit_no", models.CharField(max_length=64, primary_key=True, serialize=False)),
                (
                    "parcel",
                    models.ForeignKey(
                        db_column="upi",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="permits",
                        to="parcels.parcel",
                        to_field="upi",
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("1", "Cat 1 — Single-family residential, ground floor"),
                            ("2", "Cat 2 — Residential up to G+1"),
                            ("3", "Cat 3 — Towers / G+2 and above / capacity > 100"),
                            ("4", "Cat 4 — Industrial / hazardous / public buildings"),
                            ("5", "Cat 5 — Large commercial complexes"),
                            ("6", "Cat 6 — Critical infrastructure"),
                            ("7", "Cat 7 — Mixed-use developments"),
                        ],
                        max_length=4,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("active", "Active"),
                            ("expired", "Expired"),
                            ("revoked", "Revoked"),
                        ],
                        max_length=16,
                    ),
                ),
                ("issued_date", models.DateField(blank=True, null=True)),
                ("expiry_date", models.DateField(blank=True, null=True)),
                (
                    "intended_use",
                    models.CharField(
                        choices=[
                            ("residential", "Residential"),
                            ("commercial", "Commercial"),
                            ("mixed_use", "Mixed Use"),
                            ("industrial", "Industrial"),
                            ("institutional", "Institutional"),
                            ("agricultural", "Agricultural"),
                            ("green_zone", "Green Zone"),
                            ("transport", "Transport"),
                        ],
                        max_length=32,
                    ),
                ),
                ("max_floors_allowed", models.PositiveIntegerField(default=1)),
                ("max_footprint_sqm", models.FloatField(blank=True, null=True)),
                ("applicant_name", models.CharField(max_length=255)),
                ("last_synced_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "parcels_permit",
                "ordering": ["-issued_date"],
                "indexes": [
                    models.Index(fields=["status"], name="parcels_per_status_idx"),
                    models.Index(fields=["expiry_date"], name="parcels_per_expiry_idx"),
                ],
            },
        ),
    ]
