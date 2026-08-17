package com.cira.runtime.asr;

import android.content.Context;
import android.content.res.AssetManager;

import org.json.JSONObject;
import org.vosk.LibVosk;
import org.vosk.LogLevel;
import org.vosk.Model;
import org.vosk.Recognizer;
import org.vosk.android.RecognitionListener;
import org.vosk.android.SpeechService;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * CIRA 离线语音识别引擎（Vosk）。
 * 解决根本问题：Android WebView 不实现 Web Speech API（浏览器原型用的识别方式），
 * 所以在原生 App 里必须走原生 ASR，把识别到的文字回传给 Web 的对话流程。
 * Vosk 完全离线、不依赖谷歌服务，国行 HyperOS 也能用。
 */
public class VoskAsrEngine {

    public interface AsrListener {
        void onPartial(String text);
        void onFinal(String text);
        void onError(String msg);
    }

    private final Context ctx;
    private Model model;
    private SpeechService speechService;
    private AsrListener listener;
    private boolean inited = false;
    private boolean listening = false;
    private final Object lock = new Object();

    private static final String MODEL_ASSET = "models/vosk-model-small-cn-0.22";
    private static final String MODEL_DIR = "vosk/vosk-model-small-cn-0.22";

    public VoskAsrEngine(Context ctx) {
        this.ctx = ctx.getApplicationContext();
    }

    public void setListener(AsrListener l) {
        this.listener = l;
    }

    // ---- 首次把 assets 里的模型拷到内部存储（Vosk 只能从文件路径加载） ----
    private void copyModelIfNeeded() throws IOException {
        File outDir = new File(ctx.getFilesDir(), MODEL_DIR);
        File sentinel = new File(outDir, ".copied");
        if (sentinel.exists()) return;
        if (outDir.exists()) deleteRecursively(outDir);
        outDir.mkdirs();
        copyAssetFolder(ctx.getAssets(), MODEL_ASSET, outDir);
        sentinel.createNewFile();
    }

    private void copyAssetFolder(AssetManager am, String src, File dst) throws IOException {
        String[] files = am.list(src);
        if (files == null) {            // src 是一个文件，不是目录
            copyAssetFile(am, src, dst);
            return;
        }
        dst.mkdirs();
        for (String f : files) {
            copyAssetFolder(am, src + "/" + f, new File(dst, f));
        }
    }

    private void copyAssetFile(AssetManager am, String src, File dst) throws IOException {
        InputStream in = am.open(src);
        dst.getParentFile().mkdirs();
        OutputStream out = new FileOutputStream(dst);
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        in.close();
        out.close();
    }

    private void deleteRecursively(File f) {
        if (f.isDirectory()) {
            File[] children = f.listFiles();
            if (children != null) for (File c : children) deleteRecursively(c);
        }
        f.delete();
    }

    public void init() throws IOException {
        synchronized (lock) {
            if (inited) return;
            LibVosk.setLogLevel(LogLevel.WARNINGS);
            copyModelIfNeeded();
            File modelDir = new File(ctx.getFilesDir(), MODEL_DIR);
            model = new Model(modelDir.getAbsolutePath());
            Recognizer recognizer = new Recognizer(model, 16000.0f);
            speechService = new SpeechService(recognizer, 16000.0f);
            inited = true;
        }
    }

    public void start() throws Exception {
        synchronized (lock) {
            if (!inited) init();
            if (listening) return;
            speechService.startListening(new RecognitionListener() {
                @Override
                public void onPartialResult(String hypothesis) {
                    String t = extract(hypothesis, "partial");
                    if (t != null && !t.isEmpty() && listener != null) listener.onPartial(t);
                }

                @Override
                public void onResult(String hypothesis) {
                    String t = extract(hypothesis, "text");
                    if (t != null && !t.isEmpty() && listener != null) listener.onFinal(t);
                }

                @Override
                public void onFinalResult(String hypothesis) {
                    String t = extract(hypothesis, "text");
                    if (t != null && !t.isEmpty() && listener != null) listener.onFinal(t);
                }

                @Override
                public void onError(Exception e) {
                    if (listener != null) listener.onError(e.getMessage());
                }

                @Override
                public void onTimeout() { /* 持续聆听，不处理超时 */ }
            });
            listening = true;
        }
    }

    public void stop() {
        synchronized (lock) {
            if (speechService != null && listening) {
                speechService.stop();
            }
            listening = false;
        }
    }

    public void shutdown() {
        stop();
        if (speechService != null) speechService.shutdown();
        if (model != null) model.close();
    }

    /** 从 Vosk 返回的 JSON 里取字段（partial/final 二选一） */
    private String extract(String json, String key) {
        try {
            JSONObject o = new JSONObject(json);
            return o.optString(key, "");
        } catch (Exception e) {
            return "";
        }
    }
}
