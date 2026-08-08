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

import cira_expander
import cira_pins as P


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
    _disp = disp
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
