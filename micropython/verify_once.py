# verify_once.py — 有限轮次链路验证 (非永久循环, 跑完即退)
import cira_main as M

print("[V] 1) 连 WiFi")
M.connect_wifi()

print("[V] 2) 连桥接层 192.168.31.33:8788")
client = M.CIRABridgeClient()
client.connect()
print("[V] 桥接层已连接")

print("[V] 3) 跑 3 轮 voice_turn")
for i in range(3):
    try:
        r = client.voice_turn(transcript="你好，西拉")
        print("  TURN %d | reply=%s | emotion=%s | audio_len=%d | dur=%s"
              % (i, r.get("reply"), r.get("emotion"),
                 len(r.get("audio") or ""), r.get("durationMs")))
    except Exception as e:
        print("  TURN %d ERROR: %r" % (i, e))

client.close()
print("[V] DONE — 链路验证结束")
