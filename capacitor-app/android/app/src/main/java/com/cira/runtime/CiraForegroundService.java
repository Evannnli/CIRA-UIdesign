package com.cira.runtime;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.provider.Settings;

import androidx.core.app.NotificationCompat;

/**
 * 后台唤醒词前台服务：
 *  - 常驻通知（Android 8+ 必需），保证进程不被回收；
 *  - 持有 PARTIAL_WAKE_LOCK，熄屏/后台时仍能采集麦克风；
 *  - 运行 Porcupine 唤醒词引擎，命中后回调 Web（triggerWake）+ 拉起主界面/浮窗。
 */
public class CiraForegroundService extends Service {

    public static final String ACTION_START = "com.cira.runtime.action.WAKEWORD_START";
    public static final String ACTION_STOP = "com.cira.runtime.action.WAKEWORD_STOP";
    private static final String CHANNEL_ID = "cira_wakeword";
    private static final int NOTIFY_ID = 1;

    private com.cira.runtime.wake.PorcupineWakewordEngine engine;
    private PowerManager.WakeLock wakeLock;

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }
        // 必须先 startForeground 再做事
        startForeground(NOTIFY_ID, buildNotification());

        // 持有 CPU 唤醒锁（麦克风常驻）
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "CIRA::WakeLock");
        wakeLock.acquire();

        // 启动唤醒词引擎（无 key 时仅保活不检测）
        engine = new com.cira.runtime.wake.PorcupineWakewordEngine(this, this::onWake);
        engine.start();

        // 被杀后系统重启（需用户授权自启动）
        return START_STICKY;
    }

    private void onWake(String phrase) {
        // 1) 通知 Web（native-bridge → window.CIRA.triggerWake）
        if (CiraRuntimePlugin.getInstance() != null) {
            CiraRuntimePlugin.getInstance().emitWakeword(phrase);
        }
        // 2) 拉起主界面（singleTask 带到前台）
        Intent i = new Intent(this, MainActivity.class);
        i.setAction(CiraRuntimePlugin.ACTION_OPEN_MAIN);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        startActivity(i);
        // 3) 若已授权悬浮窗，同时显示顶层浮窗
        if (Settings.canDrawOverlays(this)) {
            startService(new Intent(this, CiraOverlayService.class).setAction(CiraOverlayService.ACTION_SHOW));
        }
    }

    private Notification buildNotification() {
        Intent pi = new Intent(this, MainActivity.class);
        PendingIntent contentIntent = PendingIntent.getActivity(this, 0, pi,
                PendingIntent.FLAG_IMMUTABLE);
        return new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("CIRA 正在聆听")
                .setContentText("后台唤醒已开启 · 喊一声即可唤醒")
                .setSmallIcon(R.drawable.ic_stat_notify)
                .setContentIntent(contentIntent)
                .setOngoing(true)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build();
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                    CHANNEL_ID, "CIRA 唤醒", NotificationManager.IMPORTANCE_LOW);
            getSystemService(NotificationManager.class).createNotificationChannel(ch);
        }
    }

    @Override
    public void onDestroy() {
        if (engine != null) engine.stop();
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
