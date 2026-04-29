"""Initial migration for the imagery app — AOI and ImageScene models."""

import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AOI",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128)),
                ("district", models.CharField(db_index=True, max_length=64)),
                ("boundary", django.contrib.gis.db.models.fields.PolygonField(srid=4326)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "AOI",
                "verbose_name_plural": "AOIs",
                "db_table": "imagery_aoi",
                "ordering": ["district", "name"],
            },
        ),
        migrations.CreateModel(
            name="ImageScene",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "aoi",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="scenes",
                        to="imagery.aoi",
                    ),
                ),
                ("captured_at", models.DateTimeField(help_text="UTC timestamp when the sensor captured this image.")),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("planet", "Planet Labs"),
                            ("maxar", "Maxar"),
                            ("drone", "Drone"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=32,
                    ),
                ),
                ("resolution_m", models.FloatField(help_text="Ground sampling distance in metres.")),
                ("cog_path", models.CharField(help_text="MinIO object key for the Cloud-Optimised GeoTIFF.", max_length=512)),
                ("checksum", models.CharField(blank=True, default="", help_text="SHA-256 hex digest of the COG file.", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Image Scene",
                "verbose_name_plural": "Image Scenes",
                "db_table": "imagery_imagescene",
                "ordering": ["-captured_at"],
                "indexes": [
                    models.Index(fields=["aoi", "captured_at"], name="imagery_ima_aoi_cap_idx"),
                    models.Index(fields=["source"], name="imagery_ima_source_idx"),
                ],
            },
        ),
    ]
