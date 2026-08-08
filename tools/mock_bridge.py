# -*- coding: utf-8 -*-
"""
CIRA 本地 Mock 桥接层（Device Runtime 真机验证用）
====================================================
模型侧的 integration/cira_bridge.py 需要 engine/* (真实 LLM/TTS) 才能跑。
本文件是**独立可运行**的 WS 桩，实现完全相同的协议 (MODULE_INTERFACES §4 + 模型侧 README)：

  默认监听 ws://0.0.0.0:8788
  actions: respond / synthesize / voice_turn / transcribe / wake_ack / ping
  返回的 ResponsePackage / AudioHandle 形状与本仓库冻结契约 §2.2 / §3 完全一致

用途：在没有模型侧 engine 代码时，让 ESP32 板子(或网页)连上来真机验证
      "状态机 + 星云渲染 + 唤醒 + 音频播放" 全链路。桥接层就绪后，只需把
      Device Runtime 里的 BRIDGE_HOST 从 127.0.0.1 改成真实主机 IP 即可。

运行：
  /Users/evanli/.workbuddy/binaries/python/envs/default/bin/python3 tools/mock_bridge.py
依赖：websockets (已装于 managed venv)
"""
import asyncio
import base64
import json
import math
import io
import wave
import os
import uuid

try:
    import websockets
except ImportError:
    raise SystemExit("需安装 websockets: pip install websockets")

HOST = os.environ.get("CIRA_BRIDGE_HOST", "0.0.0.0")
PORT = int(os.environ.get("CIRA_BRIDGE_PORT", "8788"))

# ── 伪造的"模型侧"应答（儿童陪伴语气，轮换）──
_REPLIES = [
    ("哇，你也想聊聊这个呀？我好期待！", "happy"),
    ("嗯嗯，我在听你说，慢慢来。", "calm"),
    ("这个想法好特别，你是怎么想到的呀？", "curious"),
    ("我有点担心你，发生什么了吗？", "worried"),
    ("让我想一想……你说得好像有道理。", "thinking"),
    ("太棒啦！我们再来画一只小兔子好不好？", "happy"),
]


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _make_wav_base64(freq: int, dur_ms: int, vol: float = 0.3, sr: int = 16000) -> str:
    """生成一段正弦 beep 的 WAV，返回 base64（设备端解码→I2S 验证音频通路）。"""
    n = int(sr * dur_ms / 1000)
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sr)
    frames = b"".join(
        __import__("struct").pack(
            "<h", int(vol * 32767 * math.sin(2 * math.pi * freq * i / sr))
        )
        for i in range(n)
    )
    w.writeframes(frames)
    w.close()
    return base64.b64encode(buf.getvalue()).decode("ascii")


# 预生成两段音频（唤醒应答 + 普通回复）
_WAKE_WAV = _make_wav_base64(660, 400, vol=0.35)
_REPLY_WAV = _make_wav_base64(440, 500, vol=0.30)


def _ext(emotion: str) -> dict:
    return {
        "coreEmotion": emotion,
        "ignite": "creativity",
        "domain": "G01",
        "domainName": "日常陪伴",
        "riskLevel": "low",
        "profile": {"estimatedAge": 7, "tags": ["艺术兴趣"]},
    }


def respond(user_input: dict) -> dict:
    transcript = (user_input.get("transcript") or user_input.get("text") or "").strip()
    if not transcript:
        return {"error": "empty transcript", "packageId": _new_id(), "ok": False}
    text, emotion = _REPLIES[len(transcript) % len(_REPLIES)]
    return {
        "packageId": _new_id(),
        "text": text,
        "emotion": emotion,          # 已是 5 值 (mock 直接给)
        "mode": "normal",
        "priority": "normal",
        "endOfTurn": True,
        "crisis": False,
        "_ext": _ext(emotion),
        "ok": True,
    }


def synthesize(pkg: dict, fmt: str = "wav") -> dict:
    text = (pkg.get("text") or "").strip()
    if not text:
        return {"ok": False, "error": "empty text", "audio": None, "format": None, "durationMs": 0}
    return {
        "ok": True,
        "provider": "mock_tts",
        "audio": _REPLY_WAV,
        "format": "wav",
        "durationMs": 500,
        "playable": True,
    }


def transcribe(audio_b64: str, fmt: str = "wav") -> dict:
    # mock: 不真做 ASR, 返回提示性文字
    return {"ok": True, "transcript": "我想画一只小兔子", "provider": "mock_asr"}


def wake_ack(ack_type: str = "default") -> dict:
    return {"ok": True, "audio": _WAKE_WAV, "format": "wav", "durationMs": 400}


def _analyze_audio(audio_b64: str):
    """粗略分析设备传来的 WAV：返回 (rms 0..1, 时长秒)。dev 模式用来判断"有没有说话"。"""
    try:
        raw = base64.b64decode(audio_b64)
        if raw[:4] != b"RIFF" or len(raw) < 44:
            return 0.0, 0.0
        sr = int.from_bytes(raw[24:28], "little") or 16000
        pcm = raw[44:]
        n = len(pcm) // 2
        if n == 0:
            return 0.0, 0.0
        s = 0
        # 抽点计算 RMS（每 16 样本取 1，省时间）
        step = 16
        cnt = 0
        for i in range(0, n, step):
            v = int.from_bytes(pcm[i * 2:i * 2 + 2], "little", signed=True)
            s += v * v
            cnt += 1
        rms = math.sqrt(s / cnt) / 32768.0 if cnt else 0.0
        dur = n / sr
        return rms, dur
    except Exception:
        return 0.0, 0.0


def voice_turn(user_input: dict, audio_fmt: str = "wav", do_tts: bool = True) -> dict:
    audio_b64 = user_input.get("audio") or ""
    transcript = (user_input.get("transcript") or user_input.get("text") or "").strip()

    # dev 回显：设备真录了音 → 分析能量，决定"说话了"还是"没听清"
    if audio_b64:
        rms, dur = _analyze_audio(audio_b64)
        if rms > 0.012:   # 有说活
            reply = "（dev 回显）我听到你说了约 %.1f 秒！模型侧接好后就是真对话啦～" % dur
            emotion = "happy" if rms > 0.05 else "curious"
            audio = audio_b64          # 把孩子的声音原样回放（验证 mic→WS→喇叭 全链路）
            heard = "（dev 回显：%.1fs 语音）" % dur
        else:
            reply = "（dev 模式）麦克风链路是通的，但没听清你说话～"
            emotion = "calm"
            audio = _REPLY_WAV
            heard = ""
        pkg = respond({"transcript": transcript or "（语音）"})
        return {
            "heard": heard,
            "reply": reply,
            "emotion": emotion,
            "crisis": False,
            "packageId": pkg.get("packageId"),
            "audio": audio,
            "format": "wav",
            "durationMs": int(dur * 1000) if audio == audio_b64 else 500,
            "timings": {"total": 0.05},
            "_ext": pkg.get("_ext"),
            "ok": True,
        }

    # 旧路径（仅传 transcript，无音频）：合成器 beep + 轮换应答
    if not transcript:
        r = transcribe(audio_b64, fmt=user_input.get("format", "wav"))
        transcript = (r.get("transcript") or "").strip()
    pkg = respond({"transcript": transcript})
    if not pkg.get("text"):
        return {"heard": transcript, "reply": "", "emotion": "calm", "silent": True, "ok": True}
    audio = synthesize(pkg) if do_tts else {}
    return {
        "heard": transcript,
        "reply": pkg.get("text", ""),
        "emotion": pkg.get("emotion", "calm"),
        "crisis": pkg.get("crisis", False),
        "packageId": pkg.get("packageId"),
        "audio": audio.get("audio"),
        "format": audio.get("format"),
        "durationMs": audio.get("durationMs", 0),
        "timings": {"total": 0.1},
        "_ext": pkg.get("_ext"),
        "ok": True,
    }


_DISPATCH = {
    "respond": lambda m: respond(m.get("input") or m),
    "synthesize": lambda m: synthesize(m.get("input") or m, fmt=m.get("format", "wav")),
    "voice_turn": lambda m: voice_turn(m.get("input") or m, audio_fmt=m.get("format", "wav"), do_tts=m.get("tts", True)),
    "transcribe": lambda m: transcribe(m.get("audio", ""), fmt=m.get("format", "wav")),
    "wake_ack": lambda m: wake_ack(m.get("type", "default")),
}


async def _handler(websocket):
    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"error": "invalid json", "ok": False}))
                continue
            action = (msg.get("action") or "").strip().lower()
            if action == "ping":
                result = {"action": "pong", "ok": True}
            elif action in _DISPATCH:
                try:
                    result = _DISPATCH[action](msg)
                except Exception as e:
                    result = {"action": action, "error": str(e), "ok": False}
                result["action"] = action
            else:
                result = {"action": action, "error": f"unknown action: {action}", "ok": False}
            await websocket.send(json.dumps(result, ensure_ascii=False))
    except (ConnectionResetError, BrokenPipeError):
        pass


async def _main():
    print(f"[Mock Bridge] ws://{HOST}:{PORT}  (Device Runtime 验证用, 非模型侧)")
    print(f"  actions: respond / synthesize / voice_turn / transcribe / wake_ack / ping\n")
    async with websockets.serve(_handler, HOST, PORT):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(_main())
