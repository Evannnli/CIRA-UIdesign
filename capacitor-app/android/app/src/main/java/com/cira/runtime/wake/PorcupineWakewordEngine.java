package com.cira.runtime.wake;

import android.content.Context;

import com.cira.runtime.BuildConfig;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;

import ai.picovoice.porcupine.Porcupine;
import ai.picovoice.porcupine.PorcupineManager;
import ai.picovoice.porcupine.PorcupineManagerCallback;

/**
 * 离线唤醒词引擎（Picovoice Porcupine）。
 *  - 需要 PORCUPINE_ACCESS_KEY（BuildConfig，免费档可在 Picovoice Console 申请）。
 *  - 关键词：优先用 res/raw/cira_wake.ppn（自定义"哎/CIRA"），否则退回内置 COMPUTER。
 *  - 未配置 key 时 start() 直接返空：仅后台保活，不检测唤醒（App 仍可经 FAB/点击触发）。
 */
public class PorcupineWakewordEngine {

    public interface Listener {
        void onWake(String phrase);
    }

    private final Context ctx;
    private final Listener listener;
    private PorcupineManager manager;

    public PorcupineWakewordEngine(Context ctx, Listener listener) {
        this.ctx = ctx.getApplicationContext();
        this.listener = listener;
    }

    public void start() {
        String key = BuildConfig.PORCUPINE_ACCESS_KEY;
        if (key == null || key.isEmpty()) {
            return; // 未配置 key → 仅保活
        }
        try {
            PorcupineManager.Builder b = new PorcupineManager.Builder().setAccessKey(key);
            int kwRes = ctx.getResources().getIdentifier("cira_wake", "raw", ctx.getPackageName());
            if (kwRes != 0) {
                // Porcupine 3.x 的 setKeywordPath 只接受文件路径，需先把 raw 资源拷到缓存目录
                File f = new File(ctx.getCacheDir(), "cira_wake.ppn");
                try (InputStream in = ctx.getResources().openRawResource(kwRes);
                     OutputStream out = new FileOutputStream(f)) {
                    byte[] buf = new byte[8192];
                    int n;
                    while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
                }
                b.setKeywordPath(f.getAbsolutePath());
            } else {
                b.setKeyword(Porcupine.BuiltInKeyword.COMPUTER);
            }
            b.setSensitivity(0.6f);
            manager = b.build(ctx, keywordIndex -> {
                if (listener != null) listener.onWake("CIRA");
            });
            manager.start();
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    public void stop() {
        if (manager != null) {
            try { manager.stop(); } catch (Exception ignore) {}
            try { manager.delete(); } catch (Exception ignore) {}
            manager = null;
        }
    }
}
