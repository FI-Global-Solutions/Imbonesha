"""Seed demo data for the inspector assignment workflow.

Creates / ensures:
  - 3 inspectors (inspector1/2/3@imbonesha.gov.rw)
  - Assigns flags to inspectors
  - Creates completed inspections with realistic notes
  - Writes AuditLog entries for every action
"""

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Seed inspector workflow demo data"

    def handle(self, *args, **options):
        from accounts.models import User, UserRole
        from flags.models import AuditLog, Flag, FlagStatus, Inspection

        # ── Ensure inspectors exist ──────────────────────────────────────────
        inspector_specs = [
            ("inspector1@imbonesha.gov.rw", "Jean Claude", "Habimana", "Gasabo"),
            ("inspector2@imbonesha.gov.rw", "Diane", "Ingabire", "Gasabo"),
            ("inspector3@imbonesha.gov.rw", "Patrick", "Nshuti", "Kicukiro"),
        ]
        inspectors = {}
        for email, first, last, district in inspector_specs:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": email,
                    "first_name": first,
                    "last_name": last,
                    "role": UserRole.INSPECTOR,
                    "district": district,
                },
            )
            if created:
                user.set_password("Demo2026!")
                user.save()
                self.stdout.write(f"  Created inspector: {email}")
            else:
                self.stdout.write(f"  Inspector exists: {email}")
            inspectors[email] = user

        admin = User.objects.filter(role=UserRole.ADMIN).first()
        if not admin:
            self.stderr.write("No admin user found — run seed_levir_demo_scenes first.")
            return

        insp1 = inspectors["inspector1@imbonesha.gov.rw"]
        insp2 = inspectors["inspector2@imbonesha.gov.rw"]

        # ── Pick flags to work with ──────────────────────────────────────────
        pending_flags = list(Flag.objects.filter(status=FlagStatus.PENDING).order_by("-created_at")[:6])
        if len(pending_flags) < 6:
            self.stderr.write(
                f"Only {len(pending_flags)} pending flags found — "
                "run a detection job first via the UI."
            )
            if not pending_flags:
                return

        now = timezone.now()

        def _assign(flag, inspector, by_user):
            if not flag.can_transition_to("assigned"):
                return
            old_status = flag.status
            flag.assigned_to = inspector
            flag.assigned_by = by_user
            flag.assigned_at = now
            flag.status = FlagStatus.ASSIGNED
            flag._actor = by_user
            flag._pre_save_snapshot = {"status": old_status, "severity": flag.severity, "assigned_to_id": None}
            flag.save(update_fields=["status", "assigned_to", "assigned_by", "assigned_at", "updated_at"])
            AuditLog.objects.create(
                flag=flag,
                actor=by_user,
                event="assigned",
                before={"status": old_status, "assigned_to": None},
                after={"status": "assigned", "assigned_to": inspector.email},
                message=f"Assigned to {inspector.get_full_name()} by {by_user.email}",
            )
            self.stdout.write(f"  Assigned flag #{flag.id} → {inspector.get_full_name()}")

        # Assign first 3 to inspector1, next 2 to inspector2, leave 1 pending
        assign_to_1 = pending_flags[:3]
        assign_to_2 = pending_flags[3:5]

        for f in assign_to_1:
            _assign(f, insp1, admin)
        for f in assign_to_2:
            _assign(f, insp2, admin)

        # ── Create completed inspections for 2 of inspector1's flags ────────
        if len(assign_to_1) >= 2:
            flag_a = assign_to_1[0]
            flag_b = assign_to_1[1]

            # Flag A: confirmed
            Inspection.objects.get_or_create(
                flag=flag_a,
                inspector=insp1,
                defaults={
                    "verdict": "confirmed",
                    "notes": (
                        "Large commercial structure under construction. "
                        "No permit signage visible on site. Foundation and walls complete, "
                        "roofing in progress. Estimated 3 floors."
                    ),
                    "construction_stage": "roofing",
                    "estimated_floors": 3,
                    "occupancy_observed": False,
                    "visited_at": now - timezone.timedelta(days=2),
                },
            )
            if flag_a.can_transition_to("confirmed"):
                old = flag_a.status
                flag_a.status = "confirmed"
                flag_a._actor = insp1
                flag_a._pre_save_snapshot = {"status": old, "severity": flag_a.severity, "assigned_to_id": flag_a.assigned_to_id}
                flag_a.save(update_fields=["status", "updated_at"])
                AuditLog.objects.create(
                    flag=flag_a, actor=insp1, event="inspection_submitted",
                    before={"status": old}, after={"status": "confirmed", "verdict": "confirmed"},
                    message=f"Inspection submitted by {insp1.get_full_name()}: Confirmed Unauthorized",
                )
                self.stdout.write(f"  Inspection (confirmed) → flag #{flag_a.id}")

            # Flag B: dismissed
            Inspection.objects.get_or_create(
                flag=flag_b,
                inspector=insp1,
                defaults={
                    "verdict": "dismissed",
                    "notes": (
                        "Existing residential structure, no new construction detected. "
                        "Possible AI false positive due to seasonal vegetation change."
                    ),
                    "construction_stage": "none_visible",
                    "estimated_floors": None,
                    "occupancy_observed": True,
                    "visited_at": now - timezone.timedelta(days=1),
                },
            )
            if flag_b.can_transition_to("dismissed"):
                old = flag_b.status
                flag_b.status = "dismissed"
                flag_b._actor = insp1
                flag_b._pre_save_snapshot = {"status": old, "severity": flag_b.severity, "assigned_to_id": flag_b.assigned_to_id}
                flag_b.save(update_fields=["status", "updated_at"])
                AuditLog.objects.create(
                    flag=flag_b, actor=insp1, event="inspection_submitted",
                    before={"status": old}, after={"status": "dismissed", "verdict": "dismissed"},
                    message=f"Inspection submitted by {insp1.get_full_name()}: Dismissed — False Positive",
                )
                self.stdout.write(f"  Inspection (dismissed) → flag #{flag_b.id}")

        self.stdout.write(self.style.SUCCESS("\nInspector workflow seeded successfully."))
        self.stdout.write(
            "\nLogin credentials:\n"
            "  inspector1@imbonesha.gov.rw / Demo2026!  (3 flags: 1 pending, 1 confirmed, 1 dismissed)\n"
            "  inspector2@imbonesha.gov.rw / Demo2026!  (2 flags: assigned)\n"
            "  inspector3@imbonesha.gov.rw / Demo2026!  (0 flags)\n"
        )
