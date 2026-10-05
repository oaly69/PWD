"""用 FFmpeg 把分镜合成为成片：每个镜头优先使用视频片段，没有视频时用关键帧做缓慢推镜；
叠加配音，生成内嵌字幕轨（mov_text，不依赖字体）与 SRT 字幕文件。"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Any, Awaitable, Callable

from .media import media_path
from .openai_compat import ProviderError

FPS = 25
RESOLUTION = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (1024, 1024), "4:3": (1024, 768), "3:4": (768, 1024)}


def ffmpeg_available() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


async def _run(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await proc.communicate()
    except asyncio.CancelledError:
        proc.kill()
        raise
    if proc.returncode != 0:
        raise ProviderError(f"FFmpeg 执行失败：{err.decode(errors='ignore')[-600:]}")
    return out.decode(errors="ignore")


async def probe_duration(path: Path) -> float:
    out = await _run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path))
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


def _ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(items: list[tuple[float, float, str]]) -> str:
    blocks = []
    for i, (start, end, text) in enumerate([x for x in items if x[2].strip()], 1):
        blocks.append(f"{i}\n{_ts(start)} --> {_ts(end)}\n{text.strip()}\n")
    return "\n".join(blocks)


async def render(
    shots: list[dict[str, Any]],
    aspect: str,
    on_progress: Callable[[int], Awaitable[None]] | None = None,
) -> tuple[bytes, str]:
    """shots: [{"video": 文件名|None, "image": 文件名|None, "audio": 文件名|None, "duration": 秒, "dialogue": str}]
    返回（mp4 字节，SRT 文本）。"""
    if not ffmpeg_available():
        raise ProviderError("服务器未安装 FFmpeg，无法合成成片（官方镜像已内置）")
    usable = [s for s in shots if s.get("video") or s.get("image")]
    if not usable:
        raise ProviderError("没有可用的镜头：请先为镜头生成关键帧或视频")
    w, h = RESOLUTION.get(aspect, RESOLUTION["16:9"])
    # 画面比例与成片不一致时裁切铺满（不留黑边）
    fit = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
    tmp = Path(tempfile.mkdtemp(prefix="pwd-render-"))
    try:
        segments: list[Path] = []
        subs: list[tuple[float, float, str]] = []
        t = 0.0
        for n, shot in enumerate(usable):
            audio = media_path(shot["audio"]) if shot.get("audio") else None
            duration = float(shot.get("duration") or 4)
            if audio is not None:
                duration = max(duration, await probe_duration(audio) + 0.3)
            seg = tmp / f"seg{n:03d}.mp4"
            args = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
            if shot.get("video"):
                src = media_path(shot["video"])
                args += ["-i", str(src)]
                vf = f"[0:v]{fit},fps={FPS},tpad=stop_mode=clone:stop_duration={duration:.2f},trim=duration={duration:.2f},setpts=PTS-STARTPTS,format=yuv420p[v]"
            else:
                src = media_path(shot["image"])
                frames = int(duration * FPS)
                # 关键帧：放大后缓慢推近（Ken Burns），让静态画面也有运动感
                args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{duration:.2f}", "-i", str(src)]
                vf = (f"[0:v]scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
                      f"zoompan=z='min(zoom+0.0007,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={FPS},"
                      f"trim=duration={duration:.2f},setsar=1,format=yuv420p[v]")
            if audio is not None:
                args += ["-i", str(audio)]
                af = f"[1:a]aresample=44100,aformat=channel_layouts=stereo,apad,atrim=duration={duration:.2f}[a]"
            else:
                args += ["-f", "lavfi", "-t", f"{duration:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
                af = "[1:a]anull[a]"
            args += ["-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[a]",
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-r", str(FPS),
                     "-c:a", "aac", "-b:a", "128k", "-t", f"{duration:.2f}", str(seg)]
            await _run(*args)
            segments.append(seg)
            if shot.get("dialogue"):
                subs.append((t, t + duration, shot["dialogue"]))
            t += duration
            if on_progress:
                await on_progress(int((n + 1) / len(usable) * 90))
        listing = tmp / "list.txt"
        listing.write_text("".join(f"file '{p.name}'\n" for p in segments))
        srt = build_srt(subs)
        out = tmp / "out.mp4"
        args = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing)]
        if srt:
            (tmp / "subs.srt").write_text(srt, encoding="utf-8")
            args += ["-i", str(tmp / "subs.srt"), "-map", "0", "-map", "1", "-c", "copy", "-c:s", "mov_text",
                     "-metadata:s:s:0", "language=chi"]
        else:
            args += ["-c", "copy"]
        args += ["-movflags", "+faststart", str(out)]
        await _run(*args)
        if on_progress:
            await on_progress(98)
        return out.read_bytes(), srt
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
