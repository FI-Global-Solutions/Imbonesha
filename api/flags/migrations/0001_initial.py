"""Initial migration for the flags app — Flag, Inspection, AuditLog."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("detections", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Flag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "detection",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="flag",
                        to="detections.detection",
                    ),
                ),
                (
                    "severity",
                    models.CharField(
                        choices=[
                            ("low", "Low"),
                            ("medium", "Medium"),
                            ("high", "High"),
                            ("critical", "Critical"),
                        ],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("assigned", "Assigned"),
                            ("in_review", "In Review"),
                            ("confirmed", "Confirmed"),
                            ("dismissed", "Dismissed"),
                            ("closed", "Closed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        limit_choices_to={"role": "inspector"},
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_flags",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("district", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "flags_flag",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["severity", "status"], name="flags_flag_sev_stat_idx"),
                    models.Index(fields=["district", "status"], name="flags_flag_dist_stat_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Inspection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "flag",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inspections",
                        to="flags.flag",
                    ),
                ),
                (
                    "inspector",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inspections",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "verdict",
                    models.CharField(
                        choices=[
                            ("confirmed", "Confirmed — construction is unauthorised"),
                            ("dismissed", "Dismissed — no violation found"),
                            ("needs_review", "Needs senior review"),
                        ],
                        max_length=32,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("visited_at", models.DateTimeField(blank=True, null=True)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "flags_inspection",
                "ordering": ["-submitted_at"],
            },
        ),
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "flag",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_logs",
                        to="flags.flag",
                    ),
                ),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_actions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("event", models.CharField(max_length=64)),
                ("before", models.JSONField(blank=True, null=True)),
                ("after", models.JSONField(blank=True, null=True)),
                ("message", models.TextField(blank=True, default="")),
                ("timestamp", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "db_table": "flags_auditlog",
                "ordering": ["-timestamp"],
            },
        ),
    ]
