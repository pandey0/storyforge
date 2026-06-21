import json
import subprocess
import tempfile
import os
from loguru import logger


class AudioMixer:

    def _run(self, cmd: list[str], description: str) -> subprocess.CompletedProcess:
        logger.info(f"{description}: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg failed [{description}]: {result.stderr}"
            )
        return result

    def get_duration(self, audio_path: str) -> float:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            audio_path,
        ]
        logger.info(f"get_duration: probing {audio_path}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])

    def loop_music_to_duration(self, music_path: str, duration: float, output_path: str) -> str:
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", music_path,
            "-t", str(duration),
            "-c", "copy",
            output_path,
        ]
        self._run(cmd, f"loop_music_to_duration → {output_path}")
        return output_path

    def normalize_voice(self, vo_path: str, output_path: str) -> str:
        cmd = [
            "ffmpeg", "-y",
            "-i", vo_path,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            output_path,
        ]
        self._run(cmd, f"normalize_voice → {output_path}")
        return output_path

    def duck_music(self, music_path: str, vo_path: str, output_path: str) -> str:
        filter_complex = (
            "[1]agate=threshold=0.01[gate];"
            "[0][gate]sidechaincompress=threshold=0.015:ratio=4:attack=5:release=200[out]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", music_path,
            "-i", vo_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            output_path,
        ]
        self._run(cmd, f"duck_music → {output_path}")
        return output_path

    def mix(
        self,
        vo_path: str,
        music_path: str,
        output_path: str,
        sfx_events: list[dict] = None,
    ) -> str:
        vo_duration = self.get_duration(vo_path)
        logger.info(f"mix: voice duration = {vo_duration:.2f}s")

        with tempfile.TemporaryDirectory() as tmp:
            looped_music = os.path.join(tmp, "music_looped.mp3")
            self.loop_music_to_duration(music_path, vo_duration, looped_music)

            if not sfx_events:
                filter_complex = (
                    "[0]volume=-6dB[v];"
                    "[1]volume=-24dB[m];"
                    "[v][m]amix=inputs=2:duration=first[out]"
                )
                cmd = [
                    "ffmpeg", "-y",
                    "-i", vo_path,
                    "-i", looped_music,
                    "-filter_complex", filter_complex,
                    "-map", "[out]",
                    "-ar", "44100",
                    "-ac", "2",
                    "-b:a", "192k",
                    output_path,
                ]
                self._run(cmd, f"mix (no SFX) → {output_path}")
            else:
                inputs = ["-i", vo_path, "-i", looped_music]
                filter_parts = [
                    "[0]volume=-6dB[v]",
                    "[1]volume=-24dB[m]",
                ]

                sfx_labels = []
                for idx, sfx in enumerate(sfx_events):
                    input_idx = idx + 2
                    inputs += ["-i", sfx["path"]]
                    vol_db = sfx.get("volume_db", -18)
                    start_sec = sfx.get("start_sec", 0.0)
                    label = f"sfx{idx}"
                    filter_parts.append(
                        f"[{input_idx}]volume={vol_db}dB,"
                        f"adelay={int(start_sec * 1000)}|{int(start_sec * 1000)}[{label}]"
                    )
                    sfx_labels.append(f"[{label}]")

                all_inputs_str = "[v][m]" + "".join(sfx_labels)
                n_inputs = 2 + len(sfx_events)
                filter_parts.append(
                    f"{all_inputs_str}amix=inputs={n_inputs}:duration=first[out]"
                )

                filter_complex = ";".join(filter_parts)
                cmd = (
                    ["ffmpeg", "-y"]
                    + inputs
                    + [
                        "-filter_complex", filter_complex,
                        "-map", "[out]",
                        "-ar", "44100",
                        "-ac", "2",
                        "-b:a", "192k",
                        output_path,
                    ]
                )
                self._run(cmd, f"mix (with {len(sfx_events)} SFX) → {output_path}")

        return output_path
