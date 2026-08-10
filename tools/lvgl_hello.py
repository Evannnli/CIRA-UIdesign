# -*- coding: utf-8 -*-
"""
CIRA · LVGL 固件全链路探针（路线 A 验收脚本）
=============================================
在**真 LVGL 固件**（lv_micropython + 自建 st77916 C 扩展）上跑，一次性回答四个问题：

  L0  固件里到底有什么？        —— st77916 / lvgl 模块在不在、LVGL 版本、关键 API 的真实拼写
  L1  QSPI 硬件链路通不通？     —— 不经 LVGL，直接 st77916.fill() 刷红/绿/蓝
  L2  LVGL 渲染管线通不通？     —— display_create + flush_cb → 屏上出现 "CIRA · LVGL"
  L3  能跑多快？               —— 连续刷新计帧，给出 FPS 基线

设计原则：**每一步都不许把整个脚本带崩**。真机往返一次成本很高，所以宁可每步
try/except 兜住并打印详细现场，也要让一次运行把信息吐全。

用法：
    mpremote connect /dev/cu.usbmodem101 run tools/lvgl_hello.py

判读：
    · 屏幕亮起红→绿→蓝                 = QSPI + ST77916 C 驱动通（L1 过）
    · 屏幕出现 "CIRA · LVGL" 白字       = LVGL 全链路通（L2 过），路线 A 成功
    · 颜色对不上（红显示成蓝）           = RGB565 字节序问题，见文末「颜色不对怎么办」
"""

import gc
import time

RESULT = {}


def _hr(title):
    print()
    print("=" * 52)
    print("  " + title)
    print("=" * 52)


def _names(mod, *keywords):
    """列出模块里包含任一关键字的符号名——用来确认 API 的真实拼写。"""
    out = []
    try:
        for n in dir(mod):
            ln = n.lower()
            for k in keywords:
                if k in ln:
                    out.append(n)
                    break
    except Exception as e:
        return ["<dir() 失败: %s>" % e]
    return sorted(out)


# ──────────────────────────────────────────────────────────
# L0 · 固件自省
# ──────────────────────────────────────────────────────────
def probe_L0():
    _hr("L0 · 固件自省")
    import sys
    print("platform :", sys.platform)
    print("version  :", sys.version)
    try:
        import esp32
        print("flash sz :", esp32.flash_size() if hasattr(esp32, "flash_size") else "?")
    except Exception:
        pass
    print("free mem :", gc.mem_free())

    ok_st = ok_lv = False
    try:
        import st77916
        print("[OK] st77916 模块存在 →", _names(st77916, ""))
        ok_st = True
    except Exception as e:
        print("[!!] st77916 模块缺失:", e)

    try:
        import lvgl as lv
        ok_lv = True
        try:
            print("[OK] LVGL 版本: %d.%d.%d" % (
                lv.version_major(), lv.version_minor(), lv.version_patch()))
        except Exception as e:
            print("[OK] lvgl 已导入，但取版本失败:", e)
        # 关键：确认 v9 API 的真实拼写，免得后面靠猜
        print("  display* :", _names(lv, "display_create", "display_set", "draw_buf"))
        print("  color fmt:", _names(lv, "color_format"))
        print("  screen   :", _names(lv, "screen_active", "scr_act"))
        print("  timer    :", _names(lv, "timer_handler", "tick_inc"))
    except Exception as e:
        print("[!!] lvgl 模块缺失:", e)

    RESULT["L0"] = ok_st and ok_lv
    return ok_st, ok_lv


# ──────────────────────────────────────────────────────────
# L1 · 硬件直驱（绕开 LVGL，单独验证 QSPI + C 驱动）
# ──────────────────────────────────────────────────────────
def probe_L1():
    _hr("L1 · ST77916 硬件直驱（不经 LVGL）")
    try:
        import st77916
        import cira_pins as P
    except Exception as e:
        print("[skip] 依赖缺失:", e)
        RESULT["L1"] = False
        return None

    # LCD 硬复位挂在 TCA9554 的 EXIO2 上，构造面板前必须先把扩展器全部置高，
    # 否则面板一直被摁在复位态，QSPI 写进去也不会亮。
    try:
        import cira_expander
        cira_expander.init()
        print("[ok] TCA9554 已释放（EXIO 全部输出高）")
    except Exception as e:
        print("[warn] cira_expander.init 失败（若屏不亮多半就是这里）:", e)

    try:
        st = st77916.ST77916(
            P.LCD_W, P.LCD_H,
            cs=P.LCD_CS, pclk=P.LCD_PCLK,
            d0=P.LCD_D0, d1=P.LCD_D1, d2=P.LCD_D2, d3=P.LCD_D3,
            rst=P.LCD_RST, bl=P.LCD_BL,
            madctl=P.LCD_MADCTL, invert=P.LCD_INVERT,
        )
        print("[ok] ST77916 构造成功")
    except Exception as e:
        print("[!!] ST77916 构造失败:", e)
        RESULT["L1"] = False
        return None

    try:
        st.on()
        st.set_nit(300)
    except Exception as e:
        print("[warn] on/set_nit 失败:", e)

    # RGB565：红 0xF800 / 绿 0x07E0 / 蓝 0x001F
    for name, color in (("红 0xF800", 0xF800), ("绿 0x07E0", 0x07E0), ("蓝 0x001F", 0x001F)):
        try:
            t0 = time.ticks_ms()
            st.fill(color)
            dt = time.ticks_diff(time.ticks_ms(), t0)
            print("  fill %-10s 用时 %d ms" % (name, dt))
            time.sleep_ms(500)
        except Exception as e:
            print("  [!!] fill %s 失败: %s" % (name, e))
            RESULT["L1"] = False
            return st

    try:
        st.fill(0x0000)
    except Exception:
        pass

    print("[判读] 若刚才屏幕依次出现 红→绿→蓝，则 QSPI + C 驱动链路通。")
    print("       若顺序变成 蓝→绿→红，是 RGB565 高低字节颠倒（见文末）。")
    RESULT["L1"] = True
    return st


# ──────────────────────────────────────────────────────────
# L2 · LVGL 渲染管线
# ──────────────────────────────────────────────────────────
def probe_L2():
    _hr("L2 · LVGL 渲染管线")
    try:
        import cira_lvgl_display as D
    except Exception as e:
        print("[skip] cira_lvgl_display 导入失败:", e)
        RESULT["L2"] = False
        return None, None

    try:
        disp, scr = D.init_lvgl_display()
        print("[ok] display 注册成功:", disp)
    except Exception as e:
        print("[!!] init_lvgl_display 失败:", e)
        import sys
        sys.print_exception(e)
        RESULT["L2"] = False
        return None, None

    import lvgl as lv
    try:
        scr.set_style_bg_color(lv.color_black(), 0)

        label = lv.label(scr)
        label.set_text("CIRA · LVGL")
        label.set_style_text_color(lv.color_white(), 0)
        label.center()

        # 圆屏上画个环，顺带验证抗锯齿绘制
        arc = lv.arc(scr)
        arc.set_size(300, 300)
        arc.center()
        arc.set_rotation(270)
        arc.set_bg_angles(0, 360)
        arc.set_value(70)
        arc.remove_style(None, lv.PART.KNOB)

        print("[ok] label + arc 已创建")
    except Exception as e:
        print("[!!] 创建控件失败:", e)
        import sys
        sys.print_exception(e)
        RESULT["L2"] = False
        return disp, None

    # 把渲染推出去：LVGL 需要 tick 与 timer_handler 双轮驱动
    try:
        for _ in range(60):
            try:
                lv.tick_inc(20)
            except Exception:
                pass
            lv.timer_handler()
            time.sleep_ms(20)
        print("[ok] timer_handler 跑通 60 轮")
        RESULT["L2"] = True
    except Exception as e:
        print("[!!] timer_handler 失败:", e)
        import sys
        sys.print_exception(e)
        RESULT["L2"] = False

    print("[判读] 屏上出现白字 'CIRA · LVGL' + 圆环 = 路线 A 全链路打通。")
    return disp, scr


# ──────────────────────────────────────────────────────────
# L3 · 帧率基线
# ──────────────────────────────────────────────────────────
def probe_L3(scr):
    _hr("L3 · 帧率基线（LVGL 全屏动画 3 秒）")
    if scr is None:
        print("[skip] L2 未通过")
        RESULT["L3"] = None
        return
    import lvgl as lv
    try:
        box = lv.obj(scr)
        box.set_size(80, 80)
        box.set_style_bg_color(lv.color_hex(0x33CCFF), 0)
        box.set_style_radius(40, 0)

        frames = 0
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < 3000:
            # 让方块绕圈跑，强制 LVGL 每帧产生脏区
            ph = (time.ticks_diff(time.ticks_ms(), t0) % 2000) / 2000.0
            x = int(140 + 110 * _cos(ph))
            y = int(140 + 110 * _sin(ph))
            box.set_pos(x, y)
            try:
                lv.tick_inc(5)
            except Exception:
                pass
            lv.timer_handler()
            frames += 1
        dt = time.ticks_diff(time.ticks_ms(), t0)
        fps = frames * 1000.0 / dt
        print("  帧数 %d / %d ms → %.1f FPS" % (frames, dt, fps))
        print("  free mem:", gc.mem_free())
        RESULT["L3"] = fps
    except Exception as e:
        print("[!!] 帧率测试失败:", e)
        RESULT["L3"] = None


def _cos(ph):
    import math
    return math.cos(ph * 6.2831853)


def _sin(ph):
    import math
    return math.sin(ph * 6.2831853)


# ──────────────────────────────────────────────────────────
def main():
    print()
    print("###  CIRA · LVGL 固件探针  ###")
    ok_st, ok_lv = probe_L0()

    st = probe_L1() if ok_st else None
    # L1 已经占了面板；L2 会在 cira_lvgl_display 里重新构造，
    # 这里先把 L1 的引用丢掉，避免两份对象抢同一条 QSPI 总线。
    del st
    gc.collect()

    disp = scr = None
    if ok_lv:
        disp, scr = probe_L2()
        probe_L3(scr)

    _hr("汇总")
    for k in ("L0", "L1", "L2", "L3"):
        print("  %s : %s" % (k, RESULT.get(k, "未执行")))
    if RESULT.get("L2"):
        print()
        print("  ✅ 路线 A 打通：真 LVGL 固件 + 自建 ST77916 C 驱动跑起来了。")
    elif RESULT.get("L1"):
        print()
        print("  ⚠️ 硬件通、LVGL 未通：问题在 cira_lvgl_display 的 v9 API 适配。")
    else:
        print()
        print("  ❌ 硬件链路未通：先查 TCA9554 复位与 cira_pins 引脚定义。")


main()

"""
── 颜色不对怎么办 ─────────────────────────────────────────
若 L1 里「红」显示成蓝色，是 RGB565 的高低字节顺序反了。两种改法（选一）：
  1. C 侧（推荐，零成本）：st77916.c 的 fill() 里交换 line[i*2] 与 line[i*2+1]；
     blit() 的数据来自 LVGL，则改用 LV_COLOR_16_SWAP=1 重新编译。
  2. 面板侧：给 madctl 加 0x08（BGR 位），在 cira_pins.LCD_MADCTL 里改，不用重编固件。
优先试 2，因为不用重新编译。

── 屏幕全黑怎么办 ─────────────────────────────────────────
按这个顺序排查：
  a. cira_expander.init() 是否成功（EXIO2 = LCD 复位，没释放则面板永远在复位态）
  b. 背光：st.set_nit(300) 有没有报错；LCD_BL 引脚号对不对
  c. QSPI 引脚：cira_pins 的 LCD_CS/PCLK/D0..D3 与原理图核对
  d. 串口有没有打印 "[st77916] blit 首次调用 ..."，有 = 数据在发，问题在面板初始化序列
"""
