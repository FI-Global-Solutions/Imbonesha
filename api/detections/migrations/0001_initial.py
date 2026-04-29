"""Initial migration for the detections app."""

import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("imagery", "0001_initial"),
        ("parcels", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DetectionJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "t1_scene",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="jobs_as_t1",
                        to="imagery.imagescene",
                    ),
                ),
                (
                    "t2_scene",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="jobs_as_t2",
                        to="imagery.imagescene",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="queued",
                        max_length=16,
                    ),
                ),
                ("model_version", models.CharField(default="stub-v0", max_length=64)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("ran_at", models.DateTimeField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "detections_job",
                "ordering": ["-created_at"],
                "indexes": [models.Index(fields=["status"], name="detections_job_status_idx")],
            },
        ),
        migrations.CreateModel(
            name="Detection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="detections",
                        to="detections.detectionjob",
                    ),
                ),
                ("footprint", django.contrib.gis.db.models.fields.PolygonField(srid=4326)),
                ("footprint_hash", models.CharField(db_index=True, max_length=64)),
                ("confidence", models.FloatField(default=1.0, help_text="Model confidence in [0, 1]. Stub always emits 1.0.")),
                (
                    "change_type",
                    models.CharField(
                        choices=[
                            ("new_building", "New Building"),
                            ("extension", "Extension"),
                            ("demolition", "Demolition"),
                            ("commercial", "Commercial Structure"),
                            ("unknown", "Unknown"),
                        ],
                        default="new_building",
                        max_length=32,
                    ),
                ),
                ("area_sqm", models.FloatField(help_text="Approximate footprint area in square metres.")),
                (
                    "parcel",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="detections",
                        to="parcels.parcel",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "detections_detection",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["job", "change_type"], name="detections_det_job_type_idx"),
                    models.Index(fields=["parcel"], name="detections_det_parcel_idx"),
                ],
            },
        ),
        migrations.AlterUniqueTogether(
            name="detection",
            unique_together={("job", "footprint_hash")},
        ),
    ]
