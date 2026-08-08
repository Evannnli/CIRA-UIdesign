# ws_native.py — 最小 WebSocket 客户端 (MicroPython, 原生 socket)
# 原因: 板子自带 websocket 模块是非标准流式封装, 无 WebSocket 客户端类。
# 本模块提供与标准 micropython-lib 兼容的 API:
#   ws = WebSocket(); ws.connect("ws://host:port"); ws.send(str); ws.recv(); ws.close()
# 仅实现我们需要的子集: text 帧收发 + ping/pong + close + client 掩码。

import socket

try:
    import ustruct as struct
except ImportError:
    import struct
try:
    import ubase64 as base64
except ImportError:
    import base64
try:
    import uos as os
except ImportError:
    import os


class WebSocket:
    def __init__(self):
        self.sock = None
        self._buf = b""
        self._timeout = 10

    def connect(self, url, timeout=10):
        self._timeout = timeout
        self._buf = b""
        if url.startswith("ws://"):
            url = url[5:]
        elif url.startswith("wss://"):
            raise NotImplementedError("wss:// not supported in native client")
        if "/" in url:
            hostport, path = url.split("/", 1)
            path = "/" + path
        else:
            hostport, path = url, "/"
        if ":" in hostport:
            host, port = hostport.rsplit(":", 1)
            port = int(port)
        else:
            host, port = hostport, 80

        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET %s HTTP/1.1\r\n"
            "Host: %s:%d\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ) % (path, host, port, key)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect((host, port))
        self.sock.send(req.encode())

        # 读握手响应头, 多余字节留给后续帧解析
        header = b""
        while b"\r\n\r\n" not in header:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise OSError("WS handshake failed")
            header += chunk
        self._buf = header.split(b"\r\n\r\n", 1)[1]

    def settimeout(self, t):
        self._timeout = t
        if self.sock:
            self.sock.settimeout(t)

    def _fill(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise OSError("WS connection closed")
            self._buf += chunk

    def _recv_exact(self, n):
        self._fill(n)
        data = self._buf[:n]
        self._buf = self._buf[n:]
        return data

    def _recv_frame(self):
        hdr = self._recv_exact(2)
        opcode = hdr[0] & 0x0F
        masked = (hdr[1] & 0x80) != 0
        length = hdr[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._recv_exact(8))[0]
        if masked:
            mask = self._recv_exact(4)
        payload = self._recv_exact(length)
        if masked:
            payload = bytes(payload[i] ^ mask[i & 3] for i in range(len(payload)))
        return opcode, payload

    def recv(self):
        """返回 str(text) / bytes(binary) / None(已关闭)。自动响应 ping。"""
        while True:
            opcode, payload = self._recv_frame()
            if opcode == 0x1:
                return payload.decode()
            elif opcode == 0x2:
                return payload
            elif opcode == 0x8:
                self.close()
                return None
            elif opcode == 0x9:
                self._send_frame(0xA, payload)  # pong
            # 0xA pong / 分片: 继续读

    def _send_frame(self, opcode, data):
        if isinstance(data, str):
            data = data.encode()
        frame = bytes([0x80 | (opcode & 0x0F)])
        length = len(data)
        if length < 126:
            frame += bytes([0x80 | length])
        elif length < 65536:
            frame += bytes([0x80 | 126]) + struct.pack(">H", length)
        else:
            frame += bytes([0x80 | 127]) + struct.pack(">Q", length)
        mask = os.urandom(4)
        masked = bytes(data[i] ^ mask[i & 3] for i in range(length))
        # ⚠️ 大帧（如整段录音 base64 ≈ 170KB）必须分块 send：
        # socket.send 不一定一次发完，不处理剩余字节会丢数据、炸 WS 协议。
        buf = frame + mask + masked
        off = 0
        n = len(buf)
        while off < n:
            sent = self.sock.send(buf[off:off + 4096])
            if sent <= 0:
                raise OSError("WS send 中断")
            off += sent

    def send(self, data):
        self._send_frame(0x1, data)

    def close(self):
        if self.sock:
            try:
                self._send_frame(0x8, b"")
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
