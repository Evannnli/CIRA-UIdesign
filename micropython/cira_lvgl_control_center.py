# -*- coding: utf-8 -*-
"""
CIRA 控制中心 · LVGL 版（lv_micropython, v9 假设）
================================================
策略：复用 cira_control_center 已验证的【像素绘制 + 状态机逻辑】（Evan 已确认交互/视觉），
只把「显示表面」从 st77916 换成 LVGL canvas：
  · 绘制写进 self.buf（RGB565 360×360 bytearray，ByteDisp 垫片实现 fill/fill_rect）
  · ByteDisp 喂给 cira_control_center._redraw（原样复用，零改视觉）
  · 画完 self.canvas.invalidate() → LVGL 平滑合成，根治「一帧一帧」

为什么不全用 LVGL widgets（lv_list/lv_slider）：LVGL 默认字体不含中文，
本板中文靠 subtitle_font 点阵。先用 canvas 方案把交互/顺滑度跑通（低风险、观感不变），
等有了中文 LVGL 字体（lv_font_conv 生成）再升级为原生 widgets（见 LVGL_MIGRATION.md）。

输入：由 cira_main_lvgl 的触摸状态机触发 open()，之后每帧 feed(touch, now) 驱动，
返回 True = 应退出（调用方恢复星云）。非阻塞，契合 LVGL timer 循环。

⚠ 沙盒无硬件/无 lvgl，本文件未运行；像素绘制逻辑移植自已验证的 cira_control_center v0.8.7。
"""
import time
import cira_control_center as _cc

W = H = 360
LONG_MS = _cc.LONG_MS
RELEASE_MS = _cc.RELEASE_MS


class _ByteDisp:
    """把 cira_control_center 的 fill/fill_rect 调用落进 RGB565 bytearray。"""
    def __init__(self, buf):
        self.buf = buf
        self.W = W
        self.H = H

    def fill(self, c):
        hi = (c >> 8) & 0xFF
        lo = c & 0xFF
        b = self.buf
        for i in range(0, len(b), 2):
            b[i] = hi
            b[i + 1] = lo

    def fill_rect(self, x, y, w, h, c):
        bx = x if x > 0 else 0
        by = y if y > 0 else 0
        ex = min(self.W, x + w)
        ey = min(self.H, y + h)
        if bx >= ex or by >= ey:
            return
        hi = (c >> 8) & 0xFF
        lo = c & 0xFF
        for yy in range(by, ey):
            o = (yy * self.W + bx) * 2
            for _ in range(ex - bx):
                self.buf[o] = hi
                self.buf[o + 1] = lo
                o += 2


class ControlCenter:
    def __init__(self, parent, touch):
        import lvgl as lv
        self._lv = lv
        self.touch = touch
        self.buf = bytearray(W * H * 2)
        self.disp = _ByteDisp(self.buf)
        self.canvas = lv.canvas(parent)
        self.canvas.set_buffer(self.buf, W, H, lv.COLOR_FORMAT_RGB565)
        self.canvas.set_size(W, H)
        self.canvas.set_pos(0, 0)
        self.canvas.add_flag(self._lv.obj.FLAG.HIDDEN)   # 默认隐藏，open 时显示

        self.view = "home"
        self.sel = 0
        self.closed = True
        self.done_cb = None

        # 输入状态（非阻塞，由 feed 推进）
        self._pressed = False
        self._start = 0
        self._rel_det = 0
        self._px = None
        self._py = None
        self._waiting = False

    # ── 公开 ──
    def open(self, done_cb):
        self.closed = False
        self.done_cb = done_cb
        self.view = "home"
        self.sel = 0
        self._pressed = False
        self._rel_det = 0
        self._waiting = True          # 吃掉进入时长按残余，避免一进就被判退出
        self.canvas.clear_flag(self._lv.obj.FLAG.HIDDEN)
        self._redraw()

    def close(self):
        self.closed = True
        self.canvas.add_flag(self._lv.obj.FLAG.HIDDEN)
        if self.done_cb is not None:
            try:
                self.done_cb()
            except Exception:
                pass
            self.done_cb = None

    def _redraw(self):
        _cc._redraw(self.disp, self.view, self.sel)
        try:
            self.canvas.invalidate()
        except Exception as e:
            print("[CC] canvas invalidate 失败:", e)

    # ── 非阻塞输入（移植自 cira_control_center._get_event + run）──
    def feed(self, now):
        """每帧调用。返回 True = 应退出控制中心。"""
        if self.closed:
            return False

        # 1) 消费残余按压（进入长按 / 子视图返回后）
        if self._waiting:
            if not self.touch.touching() and not self.touch.take_edge():
                self._waiting = False
                self._pressed = False
                self._rel_det = 0
            return False

        finger = self.touch.touching() or self.touch.take_edge()
        if finger and not self._pressed:
            self._pressed = True
            self._start = now
            self._rel_det = 0
            try:
                px, py, _ = self.touch.read_point()
                self._px, self._py = px, py
            except Exception:
                self._px = self._py = None
        elif self._pressed and not finger and self._rel_det == 0:
            self._rel_det = now

        # 2) 长按
        if self._pressed and time.ticks_diff(now, self._start) >= LONG_MS:
            self._pressed = False
            self._rel_det = 0
            self._waiting = True
            return self._on_long()

        # 3) 点按结算（消抖）
        if self._pressed and self._rel_det != 0 and time.ticks_diff(now, self._rel_det) >= RELEASE_MS:
            held = time.ticks_diff(now, self._start)
            self._pressed = False
            self._rel_det = 0
            self._waiting = True
            if held < LONG_MS and self._px is not None:
                return self._on_tap(self._px, self._py)
        return False

    def _on_long(self):
        if self.view == "home":
            return True                      # 长按退出（等价原型"完成"）
        self.view = "home"
        self.sel = 0
        self._redraw()
        return False

    def _on_tap(self, x, y):
        if self.view == "home":
            if _cc._in_done(y):
                return True
            r = _cc._row_at(y)
            if r is not None:
                self.view = _cc.ROWS[r]["sub"]
                self.sel = r
                self._redraw()
                return False
            if x < 120:
                self.sel = (self.sel - 1) % (len(_cc.ROWS) + 1)
            elif x > 240:
                self.sel = (self.sel + 1) % (len(_cc.ROWS) + 1)
            self._redraw()
            return False
        else:
            if x < 120:
                _cc._adjust(self.view, -1)
                self._redraw()
            elif x > 240:
                _cc._adjust(self.view, +1)
                self._redraw()
            else:
                self.view = "home"
                self._redraw()
            return False
