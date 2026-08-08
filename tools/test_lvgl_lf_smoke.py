# -*- coding: utf-8 -*-
"""
Mac 桩：cira_lvgl_lifeform 渲染逻辑冒烟（无需硬件/无需 lvgl）
=============================================================
只验证「数学移植」是否正确：构造 Lifeform、跨六态 tick()、确认缓冲区被写入
非零像素且六态亮度有区分。LVGL 显示部分（canvas.set_buffer/commit）不在此测，
那是阶段0探针 + 真机的事。
运行：python3 tools/test_lvgl_lf_smoke.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "micropython"))

import cira_lvgl_lifeform as LF

W = H = 360


def _nonzero(buf):
    n = 0
    for i in range(0, len(buf), 2):
        if buf[i] or buf[i + 1]:
            n += 1
    return n


def _bright(buf):
    s = 0
    for i in range(0, len(buf), 2):
        v = (buf[i] << 8) | buf[i + 1]
        s += ((v >> 11) & 31) + ((v >> 5) & 63) + (v & 31)
    return s


def main():
    lf = LF.Lifeform(scale=0.5)
    lf._commit = None          # 无 LVGL，跳过推送
    states = ["idle", "listen", "think", "speak", "offline", "wake"]
    print("构造 OK，粒子数 =", len(lf.particles))
    assert len(lf.particles) > 50, "粒子数异常"

    results = {}
    for s in states:
        lf.set_state(s)
        lf._dirty = True
        for _ in range(3):
            lf.tick()
        nz = _nonzero(lf.buf)
        br = _bright(lf.buf)
        results[s] = (nz, br)
        print("  %-7s nonzero=%6d  bright=%9d" % (s, nz, br))
        assert nz > 500, "%s 几乎全黑，渲染可能失败" % s

    # 六态亮度应有区分（至少离线明显偏暗）
    idle_br = results["idle"][1]
    off_br = results["offline"][1]
    assert off_br < idle_br, "离线态应明显比 idle 暗"
    print("六态亮度区分 OK（idle=%d > offline=%d）" % (idle_br, off_br))

    # 字幕渲染不崩
    lf.set_subtitle("你好，我在听", dim=False)
    lf._dirty = True
    lf.tick()
    print("字幕渲染 OK")

    print("LVGL 星云数学冒烟：全部通过 ✅")
    return True


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("LVGL 星云数学冒烟：失败 ❌")
        sys.exit(1)
