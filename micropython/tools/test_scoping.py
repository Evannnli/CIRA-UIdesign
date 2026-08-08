# tools/test_scoping.py — 在 Mac 用假硬件模块验证 cira_main 的作用域修复
# 专测 Evan 投诉 #3 根因：do_conversation 调 ui_state / ws 曾是 NameError。
# 这里用 CPython + 桩模块 import 真实 cira_main.py，断言 do_conversation 能跑到 voice_turn。
import sys, types

def fake_mod(name, attrs=None):
    m = types.ModuleType(name)
    if attrs:
        for k, v in attrs.items():
            setattr(m, k, v)
    sys.modules[name] = m
    return m

# ── 桩掉所有 MicroPython / 硬件模块 ──
class FakeWDT:
    def feed(self): pass
fake_mod("machine", {"WDT": lambda *a, **k: FakeWDT()})
fake_mod("network")

fake_mod("cira_pins", {"LCD_W": 360, "LCD_H": 360, "TOUCH_RST": 1, "TOUCH_INT": 2})
fake_mod("cira_audio", {"warmup": lambda: None, "play_wav": lambda d: None, "get_codec": lambda: None})
fake_mod("cira_expander", {"init": lambda: None})
class FakeTouch:
    chip_id = 0xB5; awake = True
    def touching(self): return False
    def take_edge(self): return False
    def read_point(self): return (0, 0, 0)
fake_mod("cira_touch", {"CST816": FakeTouch})
fake_mod("cira_wake", {"wake": lambda: "/wake_ai.wav"})
class FakeWSClient:
    def __init__(self, *a, **k): pass
    def connect(self): pass
fake_mod("cira_ws", {"CIRABridgeClient": FakeWSClient})
fake_mod("cira_display", {"init_display": lambda: object(), "set_nit": lambda n: None})
fake_mod("cira_face", {"make_canvas": lambda *a, **k: type("C", (), {"W": 360, "H": 360})()})
class FakeLF:
    _frames = 0; _dirty = False; paused = False
    def clear_screen(self): pass
    def set_state(self, s): pass
    def set_subtitle(self, s): pass
    def set_emotion(self, e): pass
    def tick(self): self._frames += 1
fake_mod("cira_lifeform", {"Lifeform": FakeLF})
fake_mod("cira_audio_in", {"record_wav": lambda seconds=3: b"\x00\x00" * 8000})

# MicroPython 的 time 扩展在 CPython 里没有，桩掉
import time as _time
_time.ticks_ms = lambda: 0
_time.ticks_diff = lambda a, b: 0
_time.sleep_ms = lambda n: None

# ── 用真实文件 import cira_main（不走 __main__，不跑 main()）──
import importlib.util
spec = importlib.util.spec_from_file_location("cira_main_test", "cira_main.py")
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)

# main() 不会自动跑；手动摆好 do_conversation 需要的全局
cm.lf = FakeLF()

class FakeWS:
    def __init__(self): self.called = False
    def voice_turn(self, **kw):
        self.called = True
        print("[TEST] voice_turn OK, audio_b64_len=%d" % len(kw.get("audio_b64") or ""))
        return {"heard": "你好", "reply": "你好呀，我是CIRA", "emotion": "happy", "audio": ""}

fw = FakeWS()
cm.ws = fw
print("[TEST] hasattr ws=%s ui_state=%s do_conversation=%s lf=%s"
      % (hasattr(cm, "ws"), hasattr(cm, "ui_state"), hasattr(cm, "do_conversation"), cm.lf is not None))

# ── 关键断言：do_conversation 不再 NameError，且真调到 voice_turn ──
try:
    cm.do_conversation()
    print("[TEST] do_conversation(ws) 返回 OK; ws_called=%s" % fw.called)
except Exception as e:
    import traceback; traceback.print_exc()
    print("[TEST] do_conversation(ws) CRASH:", repr(e)); sys.exit(1)

# ws=None 分支也不崩
cm.ws = None
try:
    cm.do_conversation()
    print("[TEST] do_conversation(ws=None) OK (WS none 分支)")
except Exception as e:
    import traceback; traceback.print_exc()
    print("[TEST] do_conversation(ws=None) CRASH:", repr(e)); sys.exit(1)

print("[TEST] ALL PASS — 投诉#3 作用域 bug 已修复")
