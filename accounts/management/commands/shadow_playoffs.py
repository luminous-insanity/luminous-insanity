"""
Management command: run the new qualification algorithm in shadow mode.

Drop this file into:
    accounts/management/commands/shadow_playoffs.py

Usage:
    python manage.py shadow_playoffs
    python manage.py shadow_playoffs --season 2026
    python manage.py shadow_playoffs --write   # actually lock the field (careful)
"""

from django.core.management.base import BaseCommand
from django.conf import settings

from accounts.django_adapter import (  # adjust import path once placed
    run_qualification,
    shadow_compare,
)


class Command(BaseCommand):
    help = "Run dynamic playoff qualification (shadow by default)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            type=int,
            default=getattr(settings, "NFL_SEASON", 2026),
        )
        parser.add_argument(
            "--write",
            action="store_true",
            help="Persist PlayoffEntry rows (final lock). Default is shadow-only.",
        )
        parser.add_argument(
            "--lambda",
            dest="lambda_mult",
            type=float,
            default=1.0,
            help="Difficulty multiplier applied to E(N).",
        )
        parser.add_argument(
            "--k",
            type=int,
            default=250,
            help="Shrinkage pseudo-picks for Season Score.",
        )

    def handle(self, *args, **options):
        season = options["season"]
        write = options["write"]
        lambda_mult = options["lambda_mult"]
        k = options["k"]

        self.stdout.write(f"Season {season} – {'WRITE' if write else 'SHADOW'} mode")

        if not write:
            comparison = shadow_compare(season)
            self.stdout.write(self.style.SUCCESS("Shadow comparison"))
            for k_, v in comparison.items():
                self.stdout.write(f"  {k_}: {v}")
            return

        result = run_qualification(
            season,
            k=k,
            lambda_mult=lambda_mult,
            write_entries=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f"Locked field of {len(result.qualified)} / E={result.E} "
            f"(N={result.N}, lapsed={result.lapsed})"
        ))
        self.stdout.write(
            f"  Routes: div={result.division_filled}  "
            f"at-large={result.at_large_filled}  "
            f"h2h={result.h2h_filled}  "
            f"roll-down={result.rolled_down}"
        )
