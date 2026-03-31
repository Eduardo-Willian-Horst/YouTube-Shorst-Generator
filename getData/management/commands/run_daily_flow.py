import json
import time
from dataclasses import dataclass

from django.core.management.base import BaseCommand
from django.db import transaction

from download.download_video import download_video
from download.r2_storage import delete_file_from_r2, download_string_from_r2, has_files_in_r2_prefix
from getData.models import ChannelConfig, InProgressVideo
from getData.views import get_last_video_info
from gpu.video_processor import processar_clipes
from transcribe.extract_audio import extract_audio_from_video
from transcribe.gemini_process import processar_audio_com_gemini
from upload.models import UploadedClip
from upload.title_utils import formatar_titulo_shorts
from upload.views import get_next_clip_to_upload, upload_video, youtube_authenticator


@dataclass(frozen=True)
class StepResult:
    ok: list[str]
    error: list[str]


class Command(BaseCommand):
    help = "Roda o fluxo completo (getdata→download→extractaudio→transcribe→process_clips→clear→markprocessed→upload)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--target-channel-id",
            default=None,
            help="Filtra por target_channel_id (quando aplicável).",
        )
        parser.add_argument(
            "--sleep-between-steps",
            type=float,
            default=0.0,
            help="Tempo (segundos) para aguardar entre etapas do fluxo.",
        )
        parser.add_argument(
            "--r2-prefix",
            default="",
            help="Prefixo opcional no R2 (padrão vazio).",
        )

    def handle(self, *args, **options):
        target_channel_id: str | None = options["target_channel_id"]
        sleep_between_steps: float = options["sleep_between_steps"]
        r2_prefix: str = options["r2_prefix"] or ""

        self.stdout.write("Iniciando fluxo diário.")

        self._run_getdata(target_channel_id=target_channel_id)
        self._sleep(sleep_between_steps)

        download_res = self._run_download(target_channel_id=target_channel_id)
        self._print_result("download", download_res)
        self._sleep(sleep_between_steps)

        extract_res = self._run_extract_audio(target_channel_id=target_channel_id, r2_prefix=r2_prefix)
        self._print_result("extractaudio", extract_res)
        self._sleep(sleep_between_steps)

        transcribe_res = self._run_transcribe(target_channel_id=target_channel_id, r2_prefix=r2_prefix)
        self._print_result("transcribe", transcribe_res)
        self._sleep(sleep_between_steps)

        process_res = self._run_process_clips(target_channel_id=target_channel_id, r2_prefix=r2_prefix)
        self._print_result("process_clips", process_res)
        self._sleep(sleep_between_steps)

        clear_res = self._run_clear(target_channel_id=target_channel_id, r2_prefix=r2_prefix)
        self._print_result("clear", clear_res)
        self._sleep(sleep_between_steps)

        marked = self._run_markprocessed(target_channel_id=target_channel_id, r2_prefix=r2_prefix)
        self.stdout.write(f"markprocessed: marcados={marked}")
        self._sleep(sleep_between_steps)

        upload_res = self._run_upload(target_channel_id=target_channel_id)
        self.stdout.write(f"upload: ok={upload_res.ok} erro={upload_res.error}")

        self.stdout.write("Fluxo diário finalizado.")

    def _sleep(self, seconds: float) -> None:
        if seconds and seconds > 0:
            time.sleep(seconds)

    def _print_result(self, step: str, res: StepResult) -> None:
        self.stdout.write(f"{step}: ok={len(res.ok)} erro={len(res.error)}")

    def _run_getdata(self, target_channel_id: str | None) -> None:
        default_api_key = None
        try:
            from decouple import config

            default_api_key = config("YOUTUBE_API_KEY", default=None)
        except Exception:
            default_api_key = None

        channel_configs = ChannelConfig.objects.filter(is_active=True).select_related("credentials").all()
        if target_channel_id:
            channel_configs = channel_configs.filter(target_channel_id=target_channel_id)

        if not channel_configs.exists():
            self.stdout.write("getdata: nenhuma configuração ativa encontrada.")
            return

        created = 0
        for config_obj in channel_configs:
            api_key = config_obj.get_api_key() or default_api_key
            if not api_key:
                continue

            for source_channel_id in config_obj.get_source_channel_ids_list():
                result = get_last_video_info(api_key, source_channel_id)
                if not result:
                    continue

                video_id = result["video_id"]
                if not InProgressVideo.objects.filter(
                    video_id=video_id,
                    target_channel_id=config_obj.target_channel_id,
                ).exists():
                    InProgressVideo.objects.create(
                        video_id=video_id,
                        source_channel_id=source_channel_id,
                        target_channel_id=config_obj.target_channel_id,
                    )
                    created += 1

        self.stdout.write(f"getdata: novos_in_progress={created}")

    def _get_in_progress(self, target_channel_id: str | None):
        videos = InProgressVideo.objects.filter(is_finished=False)
        if target_channel_id:
            videos = videos.filter(target_channel_id=target_channel_id)
        return videos

    def _run_download(self, target_channel_id: str | None) -> StepResult:
        ok: list[str] = []
        error: list[str] = []
        for video in self._get_in_progress(target_channel_id):
            try:
                download_video(video.video_id)
                ok.append(video.video_id)
            except Exception:
                error.append(video.video_id)
        return StepResult(ok=ok, error=error)

    def _run_extract_audio(self, target_channel_id: str | None, r2_prefix: str) -> StepResult:
        ok: list[str] = []
        error: list[str] = []
        for video in self._get_in_progress(target_channel_id):
            try:
                extract_audio_from_video(video.video_id, r2_prefix)
                ok.append(video.video_id)
            except Exception:
                error.append(video.video_id)
        return StepResult(ok=ok, error=error)

    def _run_transcribe(self, target_channel_id: str | None, r2_prefix: str) -> StepResult:
        ok: list[str] = []
        error: list[str] = []
        for video in self._get_in_progress(target_channel_id):
            try:
                processar_audio_com_gemini(
                    f"{r2_prefix}{video.video_id}.mp3", r2_prefix, video.video_id
                )
                ok.append(video.video_id)
            except Exception:
                error.append(video.video_id)
        return StepResult(ok=ok, error=error)

    def _run_process_clips(self, target_channel_id: str | None, r2_prefix: str) -> StepResult:
        ok: list[str] = []
        error: list[str] = []
        for video in self._get_in_progress(target_channel_id):
            try:
                json_key = f"{r2_prefix}{video.video_id}.json" if r2_prefix else f"{video.video_id}.json"
                json_content = download_string_from_r2(json_key)
                if not json_content:
                    error.append(video.video_id)
                    continue

                json_content = json_content.strip()
                if json_content.startswith("```json"):
                    json_content = json_content[7:]
                if json_content.startswith("```"):
                    json_content = json_content[3:]
                if json_content.endswith("```"):
                    json_content = json_content[:-3]
                json_content = json_content.strip()

                clipes = json.loads(json_content)
                processar_clipes(clipes, r2_prefix, video.video_id)
                ok.append(video.video_id)
            except Exception:
                error.append(video.video_id)
        return StepResult(ok=ok, error=error)

    def _run_clear(self, target_channel_id: str | None, r2_prefix: str) -> StepResult:
        ok: list[str] = []
        error: list[str] = []

        for video in self._get_in_progress(target_channel_id):
            arquivos_para_excluir = [
                f"{r2_prefix}{video.video_id}.json" if r2_prefix else f"{video.video_id}.json",
                f"{r2_prefix}{video.video_id}.mp4" if r2_prefix else f"{video.video_id}.mp4",
                f"{r2_prefix}{video.video_id}.txt" if r2_prefix else f"{video.video_id}.txt",
                f"{r2_prefix}{video.video_id}.mp3" if r2_prefix else f"{video.video_id}.mp3",
            ]

            any_error = False
            for key in arquivos_para_excluir:
                try:
                    delete_file_from_r2(key)
                except Exception:
                    any_error = True

            if any_error:
                error.append(video.video_id)
            else:
                ok.append(video.video_id)

        return StepResult(ok=ok, error=error)

    def _run_markprocessed(self, target_channel_id: str | None, r2_prefix: str) -> int:
        marked = 0
        videos = self._get_in_progress(target_channel_id)

        with transaction.atomic():
            for video in videos.select_for_update():
                clips_prefix = f"{r2_prefix}clips/{video.video_id}/" if r2_prefix else f"clips/{video.video_id}/"
                if has_files_in_r2_prefix(clips_prefix):
                    video.is_finished = True
                    video.save(update_fields=["is_finished"])
                    marked += 1

        return marked

    def _run_upload(self, target_channel_id: str | None) -> StepResult:
        ok: list[str] = []
        error: list[str] = []

        if target_channel_id:
            target_channel_ids = [target_channel_id]
        else:
            target_channel_ids = list(
                InProgressVideo.objects.filter(is_finished=True)
                .values_list("target_channel_id", flat=True)
                .distinct()
            )

        for channel_id in target_channel_ids:
            clip_info = get_next_clip_to_upload(channel_id)
            if not clip_info:
                continue

            r2_key = clip_info["r2_key"]
            try:
                youtube = youtube_authenticator(channel_id)
                filename = r2_key.split("/")[-1]
                title = formatar_titulo_shorts(filename)
                description = ""
                category_id = "17"
                try:
                    channel_config = ChannelConfig.objects.only("upload_category_id").get(
                        target_channel_id=channel_id
                    )
                    category_id = channel_config.upload_category_id or "17"
                except ChannelConfig.DoesNotExist:
                    category_id = "17"
                privacy_status = "public"

                import os
                import tempfile

                from download.r2_storage import delete_file_from_r2, download_file_from_r2

                with tempfile.TemporaryDirectory() as temp_dir:
                    local_file_path = os.path.join(temp_dir, filename)
                    if not download_file_from_r2(r2_key, local_file_path):
                        raise RuntimeError(f"Falha ao baixar clipe {r2_key} do R2")

                    youtube_video_id = upload_video(
                        youtube,
                        local_file_path,
                        title,
                        description,
                        category_id,
                        privacy_status,
                    )

                UploadedClip.objects.create(
                    r2_key=r2_key,
                    video_id=clip_info["video_id"],
                    channel_id=channel_id,
                    youtube_video_id=youtube_video_id,
                )

                delete_file_from_r2(r2_key)
                ok.append(r2_key)
                return StepResult(ok=ok, error=error)
            except Exception as e:
                import traceback

                self.stderr.write(
                    f"upload: erro ao enviar r2_key={r2_key} channel_id={channel_id} erro={str(e)}"
                )
                traceback.print_exc()
                error.append(r2_key)
                continue

        return StepResult(ok=ok, error=error)

