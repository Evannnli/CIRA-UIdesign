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
 *
 * 关键修复（针对"按住说话松手不转文字"）：
 *  - stop() 时若 onFinalResult 没触发，用最后一次中间结果(lastPartial)兜底发出整句，
 *    不再依赖 SpeechService.stop() 是否回调 onFinalResult（实测松手时该回调未必触发）。
 *  - 每次 start() 都新建 Recognizer + SpeechService（session 隔离），避免
 *    stop() 内部 destroy recognizer 后复用导致第二次按下失效。
 *  - Model 只加载一次（65MB 较重），Recognizer/Service 每次新建/销毁。
 *  - 全程用 lock 保护 finalEmitted/lastPartial，避免松手兜底与异步 onFinalResult 重复发。
 */
public class VoskAsrEngine {

    public interface AsrListener {
        void onPartial(String text);
        void onFinal(String text);
        void onError(String msg);
    }

    private final Context ctx;
    private Model model;                 // 模型只加载一次，跨 session 复用
    private Recognizer currentRecognizer;// 当前 session 的识别器（每次 start 新建）
    private SpeechService currentService;// 当前 session 的识别服务（每次 start 新建）
    private AsrListener listener;
    private boolean modelLoaded = false;
    private boolean listening = false;
    private boolean finalEmitted = false;
    private String lastPartial = "";     // 实时缓存最后一次听到的中间结果（兜底用）
    private final Object lock = new Object();

    private static final String MODEL_ASSET = "models/vosk-model-small-cn-0.22";
    private static final String MODEL_DIR = "vosk/vosk-model-small-cn-0.22";
    /**
     * 缓存版本指纹：每次改动拷贝逻辑或更换模型时必须递增此值。
     * 作用：覆盖安装新 APK 后，若指纹不匹配 → 强制删除旧缓存并从新 assets 重拷，
     * 彻底解决"aapt 压缩截断的旧缓存被大小校验(>1MB)误判为有效而永久复用"的问题。
     */
    private static final String CACHE_STAMP = "v2";

    public VoskAsrEngine(Context ctx) {
        this.ctx = ctx.getApplicationContext();
    }

    public void setListener(AsrListener l) {
        this.listener = l;
    }

    // ---- 首次把 assets 里的模型拷到内部存储（Vosk 只能从文件路径加载） ----
    private void copyModelIfNeeded() throws IOException {
        File outDir = new File(ctx.getFilesDir(), MODEL_DIR);
        File finalMdl = new File(outDir, "am/final.mdl");
        File stampFile = new File(outDir, ".cache_stamp");
        // 完整性校验（三层守卫）：
        //   ① .copied sentinel 存在 ② final.mdl 存在且 >1MB ③ 缓存版本指纹匹配
        // 任一不满足 → 删旧缓存、从当前 APK assets 重拷。
        // v2 指纹：修复 aapt 压缩截断旧缓存被"大小>1MB"误判为有效而永久复用的 bug。
        String currentStamp = CACHE_STAMP;
        String cachedStamp = "";
        if (stampFile.exists()) {
            try { cachedStamp = new String(java.nio.file.Files.readAllBytes(stampFile.toPath())).trim(); } catch(Exception ignored) {}
        }
        boolean stampOk = currentStamp.equals(cachedStamp);
        if (new File(outDir, ".copied").exists() && finalMdl.exists()
                && finalMdl.length() > 1024 * 1024 && stampOk) return;
        // 缓存失效 → 清除旧数据重拷
        if (outDir.exists()) deleteRecursively(outDir);
        outDir.mkdirs();
        copyAssetFolder(ctx.getAssets(), MODEL_ASSET, outDir);
        if (!finalMdl.exists() || finalMdl.length() < 1024 * 1024) {
            throw new IOException("Vosk 模型拷贝不完整：am/final.mdl 缺失或过小"
                + " (实际大小=" + (finalMdl.exists() ? finalMdl.length() : -1) + "字节)");
        }
        new File(outDir, ".copied").createNewFile();
        // 写入缓存指纹，供下次启动/覆盖安装后比对
        java.nio.file.Files.write(stampFile.toPath(), currentStamp.getBytes());
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

    // ---- 仅加载模型（较重，只做一次）；失败抛异常由上层转成界面报错 ----
    private void loadModel() throws IOException {
        synchronized (lock) {
            if (modelLoaded) return;
            LibVosk.setLogLevel(LogLevel.WARNINGS);
            copyModelIfNeeded();
            File modelDir = new File(ctx.getFilesDir(), MODEL_DIR);
            model = new Model(modelDir.getAbsolutePath());
            modelLoaded = true;
        }
    }

    /**
     * 开始一次聆听。每次都新建 Recognizer + SpeechService，session 隔离。
     * 必须在后台线程调用（模型加载 + AudioRecord 初始化较重，且 stop() 内部会销毁识别器）。
     */
    public void start() throws Exception {
        synchronized (lock) {
            if (listening) return;
            if (!modelLoaded) loadModel();
            finalEmitted = false;
            lastPartial = "";
            currentRecognizer = new Recognizer(model, 16000.0f);
            currentService = new SpeechService(currentRecognizer, 16000.0f);
            currentService.startListening(new RecognitionListener() {
                @Override
                public void onPartialResult(String hypothesis) {
                    String t = extract(hypothesis, "partial");
                    if (t != null && !t.isEmpty()) {
                        synchronized (lock) { lastPartial = t; }
                    }
                    if (listener != null) listener.onPartial(t);
                }

                @Override
                public void onResult(String hypothesis) {
                    String t = extract(hypothesis, "text");
                    if (t != null && !t.isEmpty()) {
                        boolean emit;
                        synchronized (lock) {
                            lastPartial = t;
                            emit = !finalEmitted;
                            finalEmitted = true;
                        }
                        if (emit && listener != null) listener.onFinal(t);
                    }
                }

                @Override
                public void onFinalResult(String hypothesis) {
                    String t = extract(hypothesis, "text");
                    if (t != null && !t.isEmpty()) {
                        boolean emit;
                        synchronized (lock) {
                            lastPartial = t;
                            emit = !finalEmitted;
                            finalEmitted = true;
                        }
                        if (emit && listener != null) listener.onFinal(t);
                    }
                }

                @Override
                public void onError(Exception e) {
                    if (listener != null) listener.onError(e != null ? e.getMessage() : "识别运行时错误");
                }

                @Override
                public void onTimeout() { /* 持续聆听，不处理超时 */ }
            });
            listening = true;
        }
    }

    /**
     * 停止聆听并回传整句。
     * 先停服务（锁外，避免与回调线程重入），再判断是否用 lastPartial 兜底，
     * 全程 lock 保护 finalEmitted，确保整句只发一次。
     */
    public void stop() {
        SpeechService svc;
        synchronized (lock) {
            if (!listening) { listening = false; return; }
            svc = currentService;
            currentService = null;
            currentRecognizer = null;
            listening = false;
        }
        try { if (svc != null) svc.stop(); } catch (Exception ignore) {}

        synchronized (lock) {
            if (!finalEmitted && lastPartial != null && !lastPartial.isEmpty() && listener != null) {
                finalEmitted = true;
                String fb = lastPartial;
                if (listener != null) listener.onFinal(fb);
            }
        }
    }

    public void shutdown() {
        stop();
        synchronized (lock) {
            if (model != null) { try { model.close(); } catch (Exception ignore) {} model = null; }
            modelLoaded = false;
        }
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
