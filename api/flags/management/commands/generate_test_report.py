"""Generate a test PDF flag report for design iteration.

Usage:
    python manage.py generate_test_report <flag_id> [<flag_id> ...]
    python manage.py generate_test_report --all        # use all existing flags
    python manage.py generate_test_report --out /tmp/my_report.pdf <flag_id>

Output: PDF saved to /tmp/imbonesha_report_<id>.pdf (or --out path).
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from flags.models import Flag
from flags.services.reports import generate_flag_report


class Command(BaseCommand):
    help = "Generate a test PDF flag report and save it to /tmp/."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "flag_ids",
            nargs="*",
            type=int,
            help="Flag PKs to include in the report.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Include all existing flags (ignores positional flag_ids).",
        )
        parser.add_argument(
            "--out",
            type=str,
            default=None,
            help="Output path (default: /tmp/imbonesha_report_<timestamp>.pdf)",
        )

    def handle(self, *args, **options) -> None:
        if options["all"]:
            flag_ids = list(Flag.objects.values_list("pk", flat=True))
        else:
            flag_ids = options["flag_ids"]

        if not flag_ids:
            total = Flag.objects.count()
            if total == 0:
                raise CommandError(
                    "No flags in the database. Run the demo first:\n"
                    "  ./scripts/demo_e2e.sh\n"
                    "Or seed LEVIR pairs:\n"
                    "  python manage.py seed_levir_demo_scenes --pair-ids test_1"
                )
            raise CommandError(
                f"Provide flag IDs or use --all. There are {total} flags available."
            )

        # Use a synthetic user object for the audit log when running from CLI.
        class _CLIUser:
            is_authenticated = False
            username = "cli"
            def get_full_name(self): return "CLI"

        try:
            pdf_bytes = generate_flag_report(flag_ids, _CLIUser())
        except ValueError as exc:
            raise CommandError(str(exc))

        if options["out"]:
            out_path = Path(options["out"])
        else:
            from datetime import datetime, timezone as dt_tz
            ts = datetime.now(tz=dt_tz.utc).strftime("%Y%m%d_%H%M%S")
            out_path = Path(f"/tmp/imbonesha_report_{ts}.pdf")

        out_path.write_bytes(pdf_bytes)
        self.stdout.write(self.style.SUCCESS(f"PDF saved to: {out_path}"))
        self.stdout.write(f"  Flags included: {flag_ids}")
        self.stdout.write(f"  Size: {len(pdf_bytes):,} bytes")
        self.stdout.write(f"\nOpen: open {out_path}")
