# cira_display.py — ST77916 圆形 TFT 显示封装（360×360 QSPI）
# =============================================================
# 板子固件里 ST77916 是 frozen 模块（硬件 QSPI + _blit_kernel 加速），
# 我们直接复用它，不自己写位模拟。这里只做三件事：
#   1. 开机先释放 TCA9554 的 EXIO（LCD 的硬复位走 EXIO2，上电默认输入态=被复位）；
#   2. 用权威引脚构造 st77916.ST77916；
#   3. 暴露屏幕 on/off（背光）和整屏填充等便捷接口，供 cira_main / lifeform 调用。
#
# 依赖：frozen `st77916`（提供 ST77916 类，含 fill/hline/vline/line/fill_rect/
#       blit/on/off/set_nit 等）；本仓库 cira_expander / cira_pins。

import time
import cira_expander
import cira_pins as P
from machine import mem32

# ── 修复：冷启动 viper 内核读 PSRAM 缓冲区偶发硬件 fault 冻死 ──
# 固件自带的 _blit_kernel 是 viper 原生内核，直接 ptr8 读 PSRAM 字节数组，
# 冷启动 PSRAM cache/MMU 未稳时会触发不可捕获的硬 fault（板子冻死、不抛异常、
# try/except 兜不住、也不自动重启）。
# 解决：先用纯 Python 安全版做几帧"预热"（Python 读路径会由运行时正确建立
# PSRAM cache/MMU 一致性），预热完成后由 _blit_kernel_safe 自行切回 viper 原生
# 内核（~50~160ms/帧，220×256，星云才呼吸得起来）。实测：预热 3 帧后 viper 稳定
# （tools/probe_viper.py 验证：VIPER_OK dt=164，VIPER_STABLE frames=19），故冷启动
# 不再冻死、且星云顺滑呼吸。machine.WDT（cira_main 里开）兜底任何残留硬 fault。
_GPIO_OUT1_REG = 0x60004010

# 预热/切回状态
_patched = False
_viper = None          # 原始 viper 内核（预热后切回）
_warm_frames = 0
_WARMUP_N = 3          # 预热帧数：纯 Python 安全 blit 先把 PSRAM 跑热再切 viper

def _blit_kernel_safe(buf, npix, nibp, o1, cl):
    reg = _GPIO_OUT1_REG
    nib = nibp
    for i in range(0, npix * 2, 2):
        hi = buf[i]
        lo = buf[i + 1]
        v0 = o1 | nib[(hi >> 4) & 0x0F]
        v1 = o1 | nib[hi & 0x0F]
        v2 = o1 | nib[(lo >> 4) & 0x0F]
        v3 = o1 | nib[lo & 0x0F]
        mem32[reg] = v0; mem32[reg] = v0 | cl; mem32[reg] = v0
        mem32[reg] = v1; mem32[reg] = v1 | cl; mem32[reg] = v1
        mem32[reg] = v2; mem32[reg] = v2 | cl; mem32[reg] = v2
        mem32[reg] = v3; mem32[reg] = v3 | cl; mem32[reg] = v3
    # 预热计数：凑够 _WARMUP_N 帧（纯 Python 读已把 PSRAM cache/MMU 跑热），
    # 之后切回 viper 原生内核（~50~160ms/帧，星云才呼吸得起来）。
    global _warm_frames
    _warm_frames += 1
    if _warm_frames >= _WARMUP_N and _viper is not None:
        try:
            import st77916
            st77916._blit_kernel = _viper
            print("[DISP] blit 切回 viper（PSRAM 已预热，~50ms/帧）")
            try:
                with open("/viper_on", "w") as _f:
                    _f.write("1")
            except Exception:
                pass
        except Exception as e:
            print("[DISP] viper 切回失败（维持安全版）:", e)
        _warm_frames = 1 << 30   # 只尝试切回一次


def _patch_blit():
    """把 st77916 的 viper blit 内核暂替为纯 Python 安全版做预热；
    预热 _WARMUP_N 帧后由 _blit_kernel_safe 自行切回 viper（只做一次）。"""
    global _patched, _viper
    if _patched:
        return
    try:
        import st77916
        _viper = getattr(st77916, "_blit_kernel", None)   # 保存原始 viper
        st77916._blit_kernel = _blit_kernel_safe
        _patched = True
        print("[DISP] blit 内核暂替为安全预热版（%d 帧后切回 viper）" % _WARMUP_N)
    except Exception as e:
        print("[DISP] blit 补丁失败（将走驱动自带 viper）:", e)


_disp = None   # 全局显示对象（供 screen_on/off 控背光）


def init_display():
    """初始化并显示器，返回 st77916.ST77916 实例。

    必须在本函数里先 cira_expander.init()：TCA9554 上电默认所有 EXIO 为输入，
    等效把 LCD（EXIO2）压在复位态；设成输出+高电平才释放，面板才能退出复位、
   接受后续初始化命令。clean boot（CIRA 当主固件）时这一步尤其关键。
   多次调用幂等：TCA9554 重写下配置/电平无害。
    """
    global _disp
    # 1) 释放 TCA9554 扩展脚（含 LCD 复位 EXIO2、CST816 RST EXIO 等）
    cira_expander.init()          # 全部 EXIO → 输出高
    # 2) 构造 frozen 硬件 QSPI 驱动
    import st77916
    disp = st77916.ST77916(
        P.LCD_W, P.LCD_H,
        cs=P.LCD_CS, pclk=P.LCD_PCLK,
        d0=P.LCD_D0, d1=P.LCD_D1, d2=P.LCD_D2, d3=P.LCD_D3,
        rst=P.LCD_RST, bl=P.LCD_BL,
        madctl=P.LCD_MADCTL, invert=P.LCD_INVERT,
    )
    # 冷启动关键修复：把 viper blit 内核换成纯 Python 安全版，规避 PSRAM fault 冻死。
    # 必须在任何 blit 之前替换，否则第一次 tick 仍可能冻。
    _patch_blit()
    _disp = disp
    # 冷启动关键：显式打开面板输出 + 整屏清黑，抹掉上电残留画面。
    # （warm run 时 frozen 启动代码已开过显示，故看不出差异；纯冷启动
    #  若不开 on()，GRAM 写入不刷新到屏，会停在旧画面/黑屏。）
    try:
        disp.on()
    except Exception:
        pass
    try:
        disp.fill(0)
    except Exception:
        pass
    time.sleep_ms(60)   # 等面板稳定
    return disp


def screen_on():
    """点亮背光（显示本身不关，只是省电把背光灭掉）。"""
    global _disp
    if _disp is not None:
        try:
            _disp.on()
        except Exception:
            pass


def screen_off():
    """熄灭背光（省电大头）。显示 RAM 仍在，亮回来看不到残影需上层先清/重绘。"""
    global _disp
    if _disp is not None:
        try:
            _disp.off()
        except Exception:
            pass


def fill(color):
    """整屏填充一个 RGB565 颜色。"""
    global _disp
    if _disp is not None:
        _disp.fill(color)


def set_nit(nit):
    """背光亮度（nit）。frozen 驱动走 PWM 真调光，省电就用它，别走软件遮罩。"""
    global _disp
    if _disp is not None:
        try:
            _disp.set_nit(nit)
        except Exception:
            pass
