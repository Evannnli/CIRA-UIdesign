# cira_wake.py — 本地唤醒应答（预录音频，不进模型侧）
# 唤醒是最高优先级的打断（barge-in）：孩子点屏/出声 → 立刻本地播预录应答，
# 不等待网络+推理（延迟≈0），且能盖掉当前正在说的任何内容。
# 播完应答后才进入 LISTENING，准备接收真实输入（经 voice_turn 发模型侧）。
import time
import urandom
import cira_audio

# 两个预录应答（已在板子根目录）："我在。" / "哎！"
_WAVES = ("/wake_wo.wav", "/wake_ai.wav")

# 单次唤醒冷却：一次点触只播一个应答，防抖动/双击导致"哎"和"我在"都播。
_LAST_WAKE_MS = -10000
WAKE_COOLDOWN_MS = 2000


def play_random():
    """随机播一个预录唤醒应答。返回实际播放的文件路径（用于日志）。"""
    f = _WAVES[urandom.getrandbits(1) % len(_WAVES)]
    try:
        with open(f, "rb") as fh:
            wav = fh.read()
    except Exception as e:
        print("[WAKE] 读文件失败", f, e)
        return None
    cira_audio.play_wav(wav)
    return f


def wake():
    """完整唤醒动作：先打断当前播放，再随机播一个应答。返回播放的文件路径。

    内置 2s 冷却：同一时间点触抖动/松手再次触发中断，也不会播第二个应答
    （只剩一个"哎！"或"我在。"）。连续两次真实唤醒需间隔 >2s。
    """
    global _LAST_WAKE_MS
    now = time.ticks_ms()
    if time.ticks_diff(now, _LAST_WAKE_MS) < WAKE_COOLDOWN_MS:
        return None  # 冷却中：忽略这次重复触发的唤醒（不播第二个应答）
    _LAST_WAKE_MS = now
    cira_audio.silence_output()   # barge-in：瞬时静音当前内容（不碰功放）
    return play_random()
