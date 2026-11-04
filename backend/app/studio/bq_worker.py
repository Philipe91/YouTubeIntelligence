"""Worker da produção real com o pipeline Brother Quill. Roda em processo próprio.

Garantias:
- Comandos saem de OPERATIONS, sempre como lista de argumentos e sem shell. Texto do roteiro vai para
  arquivos JSON, nunca para argumentos.
- Só operações listadas em config/execucao.toml executam.
- Nada roda na pasta original: uma cópia do commit fixado é extraída para a pasta da tarefa.
- Progresso real: quadros contados no disco. Queda de memória ou cancelamento param a execução.
Uso: python -m app.studio.bq_worker <job_id>
"""
from __future__ import annotations

import ctypes
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config import Settings, get_settings
from ..db import to_iso, utcnow
from ..logging_safe import install_redaction, redact
from .bq_script import pipeline_id, scene_for_pipeline
from .contract import Contract
from .store import StudioError, open_studio

log = logging.getLogger("yti.bq")
_JOB_ID = re.compile(r"^job_[0-9a-f]{16}$")
LEASE_SECONDS = 120
TICK_SECONDS = 3
RENDER = "render.mjs"

STAGES = (
    ("preparar", "Preparar cópia do pipeline"), ("narracao", "Narração"), ("timeline", "Cenas e tempos"),
    ("qa", "Revisão geométrica"), ("frames", "Renderização dos quadros"), ("encode", "Codificação"),
    ("mix", "Áudio e montagem"), ("validar", "Validação do arquivo"), ("entregar", "Entrega"),
)
# Peso de cada etapa no progresso geral. Só "frames" avança dentro da etapa, pela contagem real de quadros.
ENDS = {"preparar": 4, "narracao": 12, "timeline": 14, "qa": 24, "frames": 84, "encode": 90, "mix": 95, "validar": 98, "entregar": 100}


# Correções aplicadas só na cópia da tarefa. O projeto original não muda: cabe ao dono levá-las para lá.
# Se o texto não existir na cópia, a produção para em vez de seguir com outro código.
ENGINE_PATCHES = (
    ("src/v44/mundo44.js", "Céu sem cobrir o topo em cenas externas: o papel aparecia como uma faixa clara.",
     "Math.max(4, hz / 10) + 8 + (i === 9 ? H * 3 : 0)", "Math.max(4, hz / 10) + 8 + (i === 9 ? H * 3 : 0) + (i === 0 ? H * 3 + Math.abs(hz) : 0)"),
)
MUSIC_VOLUME = 0.08  # cerca de 10 dB abaixo da narração do Edge-TTS, medida no primeiro vídeo real

# Efeitos do catálogo para os sons disponíveis em sons_dir.
FX_SOUNDS = {"tambor": "drum", "sino": "ding", "pop": "pop", "ding": "ding", "whoosh": "whoosh", "carimbo": "thud", "erro": "thud", "explosao": "boom", "boing": "pop"}


def word_time(cena: dict, word: str) -> float | None:
    """Instante da palavra, com o mesmo critério do motor: ignora pontuação e maiúsculas."""
    key = re.sub(r"\W", "", word).lower()
    for item in cena.get("palavras", []):
        if re.sub(r"\W", "", item["w"]).lower().startswith(key):
            return float(cena["inicio"]) + float(item["t"])
    return None


class Abort(Exception):
    """Parada pedida: cancelamento, perda do prazo ou memória baixa."""

    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


def free_ram_gb() -> float:
    class Status(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                    ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
    status = Status()
    status.length = ctypes.sizeof(Status)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.avail / 1024**3


def job_dir(settings: Settings, job_id: str) -> Path:
    if not _JOB_ID.match(job_id):
        raise StudioError("invalid_job_id", "Identificador de tarefa inválido.", 422)
    base = (Path(settings.data_dir) / "producao").resolve()
    path = (base / job_id).resolve()
    if not path.is_relative_to(base):
        raise StudioError("invalid_job_id", "Caminho fora da pasta de produção.", 422)
    return path


def _inside(base: Path, candidate: Path) -> Path:
    resolved = candidate.resolve()
    if not resolved.is_relative_to(base.resolve()):
        raise StudioError("path_outside_job", f"Caminho fora da pasta da tarefa: {candidate.name}", 422)
    return resolved


class Executor:
    """Roda uma operação permitida. Testes substituem esta classe: nada externo roda neles."""

    def __init__(self, allowed: list[str], log_path: Path):
        self.allowed, self.log_path = set(allowed), log_path

    def run(self, operation: str, argv: list[str], cwd: Path, env: dict[str, str] | None = None, tick: Callable[[], None] | None = None) -> None:
        if operation not in self.allowed:
            raise StudioError("operation_not_allowed", f"Operação não permitida: {operation}", 403)
        executable = shutil.which(argv[0])
        if executable is None:
            raise StudioError("executable_not_found", f"Programa não encontrado: {argv[0]}", 409)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(f"\n=== {operation} {to_iso(utcnow())}\n")
            handle.flush()
            process = subprocess.Popen([executable, *argv[1:]], cwd=cwd, env={**os.environ, **(env or {})}, stdout=handle, stderr=subprocess.STDOUT, shell=False)
            try:
                while process.poll() is None:
                    if tick:
                        tick()
                    time.sleep(TICK_SECONDS)
            except BaseException:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
                raise
        if process.returncode != 0:
            raise StudioError("operation_failed", f"{operation} terminou com código {process.returncode}. Veja worker.log.", 500, retryable=False)


class BQWorker:
    def __init__(self, conn, settings: Settings, job_id: str, executor: Any | None = None, ram: Callable[[], float] = free_ram_gb):
        self.conn, self.settings, self.job_id, self.ram = conn, settings, job_id, ram
        self.config = settings.execution["brother_quill_v1"]
        self.contract = Contract(conn, settings)
        self.dir = job_dir(settings, job_id)
        self.anim = self.dir / "ws" / "anim"
        self.frames_dir = self.dir / "frames"
        self.vid = pipeline_id(job_id)
        self.executor = executor or Executor(self.config["operations"], self.dir / "worker.log")
        self.token = ""
        self.total_frames = 0

    # --- Estado ------------------------------------------------------------------------------

    def _stage(self, stage: str, status: str, detail: str = "", done: int | None = None, total: int | None = None) -> None:
        stamp = to_iso(utcnow())
        started = stamp if status == "em_andamento" else None
        ended = stamp if status in {"concluida", "falhou"} else None
        self.conn.execute(
            """UPDATE job_stages SET status = ?, detail = ?, done = COALESCE(?, done), total = COALESCE(?, total),
               started_at = COALESCE(started_at, ?), ended_at = ? WHERE job_id = ? AND stage = ?""",
            (status, redact(detail)[:500], done, total, started, ended, self.job_id, stage),
        )
        self.conn.commit()

    def _beat(self, progress: int | None = None, step: str | None = None) -> None:
        """Renova o prazo e confere se a tarefa ainda é deste worker e se há memória."""
        job = self.contract._job(self.job_id)
        if job["state"] != "running" or job["lease_token"] != self.token:
            raise Abort("A tarefa foi cancelada ou assumida por outro agente.", False)
        floor = self.settings.execution["min_free_ram_gb_running"]
        free = self.ram()
        if free < floor:
            raise Abort(f"Memória livre em {free:.1f} GB, abaixo do mínimo de {floor} GB. A retomada aproveita os quadros prontos.", True)
        fields: dict[str, Any] = {"lease_expires_at": to_iso(self.contract.clock() + _seconds(LEASE_SECONDS))}
        if progress is not None:
            fields["progress"] = progress
        if step is not None:
            fields["step"] = step
        self.contract._set_job(self.job_id, **fields)
        self.conn.commit()

    def _run(self, operation: str, argv: list[str], cwd: Path, env: dict[str, str] | None = None, tick: Callable[[], None] | None = None) -> None:
        self.executor.run(operation, argv, cwd, env, tick or self._beat)

    # --- Etapas ------------------------------------------------------------------------------

    def preparar(self) -> str:
        if (self.anim / "studio.html").is_file():
            return "Cópia já existente reaproveitada."
        repo, commit = self.config["repo"], self.config["commit"]
        tar_path = self.dir / "base.tar"
        self._run("git_archive", ["git", "-C", repo, "archive", "--format=tar", "-o", str(tar_path), commit, "anim"], self.dir)
        with tarfile.open(tar_path) as archive:
            archive.extractall(self.dir / "ws", filter="data")
        tar_path.unlink()
        for relative, _, old, new in ENGINE_PATCHES:
            target = _inside(self.anim, self.anim / relative)
            source = target.read_bytes().decode("utf-8")
            if source.count(old) != 1:
                raise StudioError("engine_patch_failed", f"A correção de {relative} não se aplica a este commit.", 409)
            target.write_bytes(source.replace(old, new).encode("utf-8"))
        modules = self.anim / "node_modules"
        if not modules.exists():
            import _winapi

            _winapi.CreateJunction(str(Path(self.config["node_modules"]).resolve()), str(modules))
        return f"Commit {commit} extraído na pasta da tarefa, com {len(ENGINE_PATCHES)} correção na cópia. Projeto original não tocado."

    def narracao(self, script: dict) -> str:
        roteiro = {"id": self.vid, "base": self.vid, "voz": self.config["voz"], "lang": "en", "rate": "+0%", "pausa": 0.12, "formato": "short", "apertar": True,
                   "cenas": [scene_for_pipeline(cena) for cena in script["cenas"]]}
        path = self.dir / "roteiro.json"
        path.write_text(json.dumps(roteiro, ensure_ascii=False, indent=1), encoding="utf-8")
        self._run("narrar", [self.config["tts_python"], self.config["tts_script"], str(path)], self.dir, {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        timeline = json.loads((self.dir / "public" / self.vid / "timeline.json").read_text(encoding="utf-8"))
        limit = self.settings.execution["max_video_seconds"]
        if timeline["total"] > limit:
            raise StudioError("video_too_long", f"Narração de {timeline['total']:.1f} s passa do limite de {limit} s.", 422)
        return f"{timeline['total']:.1f} s de narração em {len(timeline['cenas'])} cenas. Voz: {self.config['voz']}."

    def timeline(self) -> str:
        data = json.loads((self.dir / "public" / self.vid / "timeline.json").read_text(encoding="utf-8"))
        scenes = []
        for cena in data["cenas"]:
            item = {key: value for key, value in cena.items() if key not in ("palavras", "audio")}
            item["palavras"] = [{"w": w["w"], "t": round(cena["inicio"] + w["t"], 3), "d": w["d"]} for w in cena["palavras"]]
            scenes.append(item)
        payload = {self.vid: {"total": data["total"], "formato": "short", "cenas": scenes}}
        (self.anim / "src" / "tl.js").write_text("// gerado pelo YouTube Intelligence\nconst TLS = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
        duration = math.ceil((data["total"] + 0.8) * 24) / 24
        self.total_frames = math.ceil(duration * 24)
        return f"{self.total_frames} quadros previstos, {duration:.1f} s."

    def qa(self) -> str:
        report = self.dir / "qa.json"
        self._run("qa", ["node", RENDER, f"--v={self.vid}", f"--qa={report}"], self.anim)
        problems = json.loads(report.read_text(encoding="utf-8"))
        broken = [p for p in problems if p.get("tipo") == "erro_mundo"]
        if broken:
            raise StudioError("scene_error", f"Erro ao montar cena: {str(broken[0].get('msg'))[:200]}", 422)
        if problems:
            kinds = sorted({str(p.get("tipo")) for p in problems})
            self.contract.log_event(self.job_id, "warning", f"Revisão geométrica: {len(problems)} avisos ({', '.join(kinds)[:160]}).", f"qa-{self.contract._job(self.job_id)['attempts']}")
        return f"{len(problems)} avisos geométricos."

    def _count_frames(self) -> int:
        return sum(1 for _ in self.frames_dir.glob("f*.jpg")) if self.frames_dir.is_dir() else 0

    def frames(self) -> str:
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        start, end = ENDS["qa"], ENDS["frames"]

        def tick() -> None:
            done = self._count_frames()
            self._stage("frames", "em_andamento", f"{done} de {self.total_frames} quadros no disco", done, self.total_frames)
            self._beat(start + (end - start) * done // max(self.total_frames, 1), "Renderização dos quadros")

        self._run("frames", ["node", RENDER, f"--v={self.vid}", "--frames", "--fps=24", "--workers=1", f"--framesdir={self.frames_dir}"], self.anim, tick=tick)
        done = self._count_frames()
        if done < self.total_frames:
            raise StudioError("frames_incomplete", f"Só {done} de {self.total_frames} quadros foram gerados.", 500)
        self._stage("frames", "em_andamento", f"{done} quadros no disco", done, self.total_frames)
        return f"{done} quadros reais."

    def encode(self) -> str:
        mudo = self.dir / "mudo.mp4"
        self._run("encode", ["node", RENDER, "--encode", "--fps=24", f"--framesdir={self.frames_dir}", f"--out={mudo}"], self.anim)
        return f"{mudo.stat().st_size} bytes."

    def mix(self) -> str:
        timeline = json.loads((self.dir / "public" / self.vid / "timeline.json").read_text(encoding="utf-8"))
        public = self.dir / "public"
        sons = Path(self.config["sons_dir"])
        duration = math.ceil((timeline["total"] + 0.8) * 24) / 24  # igual à duração dos quadros
        inputs: list[str] = []
        filters: list[str] = []

        def add(path: Path, start: float, volume: float, loop: bool = False) -> None:
            index = len(inputs) // 2
            inputs.extend(["-i", str(path)])
            repeat = "aloop=loop=-1:size=2147483647," if loop else ""
            filters.append(f"[{index}:a]{repeat}aresample=44100,aformat=channel_layouts=stereo,volume={volume:.2f},adelay={int(start * 1000)}:all=1[a{index}]")

        add(sons / "trilha.wav", 0, MUSIC_VOLUME, loop=True)
        for cena in timeline["cenas"]:
            add(_inside(public, public / cena["audio"]), float(cena["inicio"]), 1.0)
        for cena in timeline["cenas"][1:]:
            add(sons / "whoosh.wav", max(0.0, float(cena["inicio"]) - 0.15), 0.45)
        for cena in timeline["cenas"]:
            for word, effect in cena.get("fx", []):
                start = word_time(cena, word)
                if start is not None and effect in FX_SOUNDS:
                    add(sons / f"{FX_SOUNDS[effect]}.wav", start, 0.7)
        count = len(inputs) // 2
        filters.append("".join(f"[a{i}]" for i in range(count)) + f"amix=inputs={count}:normalize=0,atrim=0:{duration:.2f},afade=t=out:st={duration - 0.4:.2f}:d=0.4,loudnorm=I=-14:TP=-1.5:LRA=11[out]")
        wav = self.dir / "audio.wav"
        self._run("mix", ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]", "-ar", "44100", str(wav)], self.dir)
        final = self.dir / "final.mp4"
        self._run("mux", ["ffmpeg", "-v", "error", "-y", "-i", str(self.dir / "mudo.mp4"), "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(final)], self.dir)
        return f"{final.stat().st_size} bytes com narração, trilha e transições."

    def validar(self) -> str:
        sheet = self.dir / "folha_de_contato.jpg"
        final = self.dir / "final.mp4"
        self._run("folha", ["ffmpeg", "-v", "error", "-y", "-i", str(final), "-vf", "select='not(mod(n,48))',scale=216:-1,tile=6x2", "-frames:v", "1", str(sheet)], self.dir)
        report = validate_file(self.settings, self.job_id, final)
        store_validation(self.conn, self.job_id, report, "bq_worker")
        if not report["ok"]:
            raise StudioError("video_invalid", "; ".join(report["problems"]), 422)
        return f"{report['width']}x{report['height']}, {report['duration_seconds']} s, {report['video_codec']}/{report['audio_codec']}."

    def entregar(self) -> str:
        attempt = self.contract._job(self.job_id)["attempts"]
        result = self.contract.deliver_artifacts(self.job_id, self.token, [
            {"kind": "short", "path": str(self.dir / "final.mp4"), "label": "Vídeo final"},
            {"kind": "other", "path": str(self.dir / "folha_de_contato.jpg"), "label": "Folha de contato"},
            {"kind": "other", "path": str(self.dir / "worker.log"), "label": "Registro da execução"},
        ], f"bq:{self.job_id}:{attempt}:entrega")
        for path in (self.frames_dir, self.dir / "mudo.mp4", self.dir / "audio.wav"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink()
        return f"{len(result['artifacts'])} arquivos entregues. Quadros temporários apagados."

    # --- Execução ------------------------------------------------------------------------------

    def run(self) -> int:
        job = self.contract._job(self.job_id)
        if job["simulated"] or job["state"] != "running":
            raise StudioError("job_not_runnable", "Só tarefa real em execução roda neste worker.", 409)
        self.token = job["lease_token"]
        row = self.conn.execute("SELECT payload_json FROM job_scripts WHERE job_id = ?", (self.job_id,)).fetchone()
        if row is None:
            raise StudioError("script_required", "A tarefa não tem roteiro.", 409)
        script = json.loads(row["payload_json"])
        self.dir.mkdir(parents=True, exist_ok=True)
        steps: dict[str, Callable[[], str]] = {
            "preparar": self.preparar, "narracao": lambda: self.narracao(script), "timeline": self.timeline, "qa": self.qa, "frames": self.frames,
            "encode": self.encode, "mix": self.mix, "validar": self.validar, "entregar": self.entregar,
        }
        current = ""
        try:
            for key, label in STAGES:
                current = key
                self._beat(step=label)
                self._stage(key, "em_andamento")
                detail = steps[key]()
                self._stage(key, "concluida", detail)
                if key != "entregar":
                    self._beat(ENDS[key], label)
            return 0
        except Abort as stop:
            self._stage(current, "falhou", str(stop))
            job = self.contract._job(self.job_id)
            if job["state"] == "running" and job["lease_token"] == self.token:
                self._fail(str(stop), stop.retryable)
            return 3
        except StudioError as error:
            self._stage(current, "falhou", error.message)
            self._fail(error.message, error.retryable)
            return 2
        except Exception as error:  # noqa: BLE001 - qualquer falha precisa aparecer no painel
            log.exception("Falha na etapa %s", current)
            self._stage(current, "falhou", f"{type(error).__name__}: {error}")
            self._fail(f"Falha inesperada em {current}: {type(error).__name__}", True)
            return 1

    def _fail(self, message: str, retryable: bool) -> None:
        attempt = self.contract._job(self.job_id)["attempts"]
        self.contract.report_failure(self.job_id, self.token, message, retryable, f"bq:{self.job_id}:{attempt}:falha:{to_iso(utcnow())}")


def _seconds(value: int):
    from datetime import timedelta

    return timedelta(seconds=value)


def probe(path: Path) -> dict:
    done = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], capture_output=True, text=True, shell=False, timeout=60)
    if done.returncode != 0:
        raise StudioError("video_unreadable", "O ffprobe não conseguiu ler o arquivo.", 422)
    return json.loads(done.stdout)


def validate_file(settings: Settings, job_id: str, path: Path, reader: Callable[[Path], dict] = probe) -> dict:
    """Confere o arquivo de verdade: existência, codecs, resolução, duração e áudio."""
    base = job_dir(settings, job_id)
    path = _inside(base, path)
    if not path.is_file():
        return {"ok": False, "problems": ["Arquivo não encontrado."], "file": path.name}
    data = reader(path)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    duration = float(data.get("format", {}).get("duration", 0) or 0)
    size = path.stat().st_size
    problems = []
    if video is None:
        problems.append("Sem faixa de vídeo.")
    elif (video.get("width"), video.get("height")) != (1080, 1920):
        problems.append(f"Resolução {video.get('width')}x{video.get('height')}: esperado 1080x1920.")
    if audio is None:
        problems.append("Sem faixa de áudio.")
    limit = settings.execution["max_video_seconds"] + 2
    if not 3 <= duration <= limit:
        problems.append(f"Duração de {duration:.1f} s fora do esperado.")
    if size < 100_000:
        problems.append(f"Arquivo pequeno demais: {size} bytes.")
    return {
        "ok": not problems, "problems": problems, "file": path.name, "size_bytes": size, "duration_seconds": round(duration, 2),
        "width": video.get("width") if video else None, "height": video.get("height") if video else None,
        "video_codec": video.get("codec_name") if video else None, "audio_codec": audio.get("codec_name") if audio else None,
        "frames": int(video.get("nb_frames", 0) or 0) if video else 0, "fps": video.get("r_frame_rate") if video else None,
    }


def store_validation(conn, job_id: str, report: dict, by: str) -> None:
    conn.execute("INSERT OR REPLACE INTO job_validation (job_id, ok, report_json, validated_by, validated_at) VALUES (?, ?, ?, ?, ?)",
                 (job_id, int(report["ok"]), json.dumps(report, ensure_ascii=False), by, to_iso(utcnow())))
    conn.commit()


def main(argv: list[str]) -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    install_redaction()
    if len(argv) != 2 or not _JOB_ID.match(argv[1]):
        print("Uso: python -m app.studio.bq_worker <job_id>", file=sys.stderr)
        return 64
    settings = get_settings()
    conn = open_studio(settings)
    try:
        return BQWorker(conn, settings, argv[1]).run()
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
