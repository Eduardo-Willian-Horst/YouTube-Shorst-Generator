import datetime
import time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Mantém um loop e dispara o fluxo diário ao meio-dia (timezone do Django)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--target-channel-id",
            default=None,
            help="Filtra por target_channel_id (quando aplicável).",
        )
        parser.add_argument(
            "--r2-prefix",
            default="",
            help="Prefixo opcional no R2 (padrão vazio).",
        )
        parser.add_argument(
            "--sleep-between-steps",
            type=float,
            default=0.0,
            help="Tempo (segundos) para aguardar entre etapas do fluxo.",
        )

    def handle(self, *args, **options):
        tz = ZoneInfo(getattr(settings, "TIME_ZONE", "America/Sao_Paulo"))
        target_channel_id: str | None = options["target_channel_id"]
        r2_prefix: str = options["r2_prefix"] or ""
        sleep_between_steps: float = options["sleep_between_steps"]

        self.stdout.write(f"Scheduler iniciado (timezone={tz.key}).")

        while True:
            now = datetime.datetime.now(tz=tz)
            next_noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
            if next_noon <= now:
                next_noon = next_noon + datetime.timedelta(days=1)

            wait_seconds = int((next_noon - now).total_seconds())
            self.stdout.write(
                f"Próxima execução: {next_noon.isoformat()} (em {wait_seconds}s)."
            )
            time.sleep(max(1, wait_seconds))

            self.stdout.write("Disparando fluxo diário.")
            call_command(
                "run_daily_flow",
                target_channel_id=target_channel_id,
                r2_prefix=r2_prefix,
                sleep_between_steps=sleep_between_steps,
            )

