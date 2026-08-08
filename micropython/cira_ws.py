# cira_ws.py — Device Runtime (MicroPython) 集成接缝
# 对应 Web 原型里的 modules.js：Device Runtime 只经本模块访问模块1/2。
# 传输目标 = 模型侧桥接层 (integration/cira_bridge.py) 或本地 mock_bridge.py，
# 协议一致 (ws://host:8788, JSON-RPC, actions: voice_turn/respond/synthesize/wake_ack/ping)。
# 换真桥接层只改 BRIDGE_HOST，本文件其余不动。
#
# 依赖 (板子 MicroPython 需含): ujson, websocket (micropython-lib)
#   若 import 失败，板端执行: mpremote mip install websocket

import ujson

# ── 接入点配置（真机验证时改成运行桥接层的主机 IP，如 192.168.31.33）──
BRIDGE_HOST = "192.168.31.33"   # ← 这本机 IP；接模型侧时改成对应主机
BRIDGE_PORT = 8788


class CIRABridgeClient:
    """ freezes: 只暴露 冻结接口 CIRA.Core.respond / CIRA.Language.synthesize 的等价物 """

    def __init__(self, host=BRIDGE_HOST, port=BRIDGE_PORT, timeout=15):
        self.url = "ws://%s:%d" % (host, port)
        self.ws = None
        self._timeout = timeout

    def connect(self):
        # websocket 来自 micropython-lib；若板子固件不含，会在此报 ImportError
        import websocket
        self.ws = websocket.WebSocket()
        self.ws.connect(self.url, timeout=self._timeout)
        self.ws.settimeout(self._timeout)

    def _send(self, msg):
        self.ws.send(ujson.dumps(msg))

    def _recv(self):
        return ujson.loads(self.ws.recv())

    # ── 模块1: CIRA Core.respond 的等价 (一体化 voice_turn 最常用) ──
    def voice_turn(self, transcript="", audio_b64="", fmt="wav", tts=True):
        """一轮完整语音对话：ASR(可选)→Core.respond→LS.synthesize。
        返回冻结 ResponsePackage + AudioHandle 合并体。"""
        self._send({
            "action": "voice_turn",
            "input": {"transcript": transcript, "audio": audio_b64},
            "format": fmt, "tts": tts,
        })
        return self._recv()

    def respond(self, transcript, session_id="", locale="zh-CN", age=None):
        self._send({
            "action": "respond",
            "input": {"transcript": transcript, "sessionId": session_id,
                      "locale": locale, "age": age},
        })
        return self._recv()

    # ── 模块2: Language System.synthesize 的等价 ──
    def synthesize(self, package, fmt="wav"):
        self._send({"action": "synthesize", "input": package, "format": fmt})
        return self._recv()

    # ── 唤醒应答（本地优先用预录音频；此为桥接层兜底）──
    def wake_ack(self, ack_type="default"):
        self._send({"action": "wake_ack", "type": ack_type})
        return self._recv()

    def ping(self):
        self._send({"action": "ping"})
        return self._recv()

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
