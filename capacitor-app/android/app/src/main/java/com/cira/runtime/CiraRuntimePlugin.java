package com.cira.runtime;

import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.JSObject;

import com.cira.runtime.BuildConfig;
import com.cira.runtime.asr.SherpaAsrEngine;

import android.Manifest;
import android.content.Context;
import android.util.Log;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.provider.Settings;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.core.content.ContextCompat;

import java.util.Map;

import android.app.Activity;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * CIRA 原生插件：把"后台运行 / 熄屏唤醒 / 顶层浮窗"三件事暴露给 Web 层。
 * Web 侧通过 window.CiraNative（native-bridge.js）调用，事件 wakeword 回传唤醒命中。
 */
@CapacitorPlugin(name = "CiraRuntime")
public class CiraRuntimePlugin extends Plugin {

    public static final String ACTION_OPEN_MAIN = "com.cira.runtime.OPEN_MAIN";
    private static CiraRuntimePlugin instance;

    private ActivityResultLauncher<String[]> permLauncher;
    private PermissionCallback pendingCallback;
    private PluginCall pendingAsrCall;    // startAsr 因缺权限挂起，待授权后继续
    private PluginCall pendingMicCall;     // requestMicPermission 挂起
    private SherpaAsrEngine asr;          // 离线语音识别引擎（Sherpa-ONNX streaming ASR）

    private interface PermissionCallback {
        void onResult(Map<String, Boolean> result);
    }

    @Override
    public void load() {
        instance = this;
        // 注册权限请求回调（必须在 Activity 进入 STARTED 前）
        permLauncher = getActivity().registerForActivityResult(
                new ActivityResultContracts.RequestMultiplePermissions(),
                result -> {
                    boolean mic = Boolean.TRUE.equals(result.get(Manifest.permission.RECORD_AUDIO));
                    if (pendingAsrCall != null) {
                        PluginCall c = pendingAsrCall; pendingAsrCall = null;
                        if (mic) doStartAsr(c); else c.reject("mic_permission_required", "麦克风权限被拒绝");
                        return;
                    }
                    if (pendingMicCall != null) {
                        PluginCall c = pendingMicCall; pendingMicCall = null;
                        JSObject r = new JSObject();
                        r.put("mic", mic);
                        r.put("notification", Boolean.TRUE.equals(result.get(Manifest.permission.POST_NOTIFICATIONS)));
                        c.resolve(r);
                        return;
                    }
                    if (pendingCallback != null) {
                        pendingCallback.onResult(result);
                        pendingCallback = null;
                    }
                });
    }

    public static CiraRuntimePlugin getInstance() {
        return instance;
    }

    /** 供原生服务回调：通知 Web 唤醒词命中（native-bridge.js → window.CIRA.triggerWake） */
    public void emitWakeword(String phrase) {
        JSObject data = new JSObject();
        data.put("phrase", phrase == null ? "" : phrase);
        notifyListeners("wakeword", data);
    }

    // ---------- 配置 ----------
    @PluginMethod
    public void getConfig(PluginCall call) {
        JSObject ret = new JSObject();
        ret.put("coreUrl", BuildConfig.CIRA_CORE_URL);
        // Sherpa-ONNX KWS 始终可用（无需 API key），模型首次启动时自动下载
        ret.put("wakewordEnabled", true);
        call.resolve(ret);
    }

    @PluginMethod
    public void setConfig(PluginCall call) {
        String coreUrl = call.getString("coreUrl");
        if (coreUrl != null) {
            SharedPreferences sp = getContext().getSharedPreferences("cira", Context.MODE_PRIVATE);
            sp.edit().putString("coreUrl", coreUrl).apply();
        }
        call.resolve();
    }

    // ---------- 权限 ----------
    @PluginMethod
    public void requestPermissions(PluginCall call) {
        Context ctx = getContext();
        // 悬浮窗权限需跳系统设置页单独授予（普通申请无效）
        if (!Settings.canDrawOverlays(ctx)) {
            Intent intent = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:" + ctx.getPackageName()));
            getActivity().startActivity(intent);
        }
        String[] perms = new String[]{
                Manifest.permission.RECORD_AUDIO,
                Manifest.permission.POST_NOTIFICATIONS
        };
        pendingCallback = (res) -> {
            JSObject ret = new JSObject();
            ret.put("mic", Boolean.TRUE.equals(res.get(Manifest.permission.RECORD_AUDIO)));
            ret.put("notification", Boolean.TRUE.equals(res.get(Manifest.permission.POST_NOTIFICATIONS)));
            ret.put("overlay", Settings.canDrawOverlays(ctx));
            call.resolve(ret);
        };
        permLauncher.launch(perms);
    }

    /** 轻量申请麦克风+通知权限（不跳转悬浮窗设置页），供 App 启动时预申请 */
    @PluginMethod
    public void requestMicPermission(PluginCall call) {
        Context ctx = getContext();
        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.RECORD_AUDIO)
                == PackageManager.PERMISSION_GRANTED) {
            JSObject r = new JSObject();
            r.put("mic", true);
            r.put("notification", ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS)
                    == PackageManager.PERMISSION_GRANTED);
            call.resolve(r);
            return;
        }
        pendingMicCall = call;
        permLauncher.launch(new String[]{
                Manifest.permission.RECORD_AUDIO,
                Manifest.permission.POST_NOTIFICATIONS
        });
    }

    // ---------- 唤醒词（前台 Service） ----------
    @PluginMethod
    public void startWakeword(PluginCall call) {
        Context ctx = getContext();
        Intent svc = new Intent(ctx, CiraForegroundService.class);
        svc.setAction(CiraForegroundService.ACTION_START);
        ctx.startForegroundService(svc);
        call.resolve();
    }

    @PluginMethod
    public void stopWakeword(PluginCall call) {
        Context ctx = getContext();
        ctx.stopService(new Intent(ctx, CiraForegroundService.class));
        call.resolve();
    }

    // ---------- 浮窗 ----------
    @PluginMethod
    public void showOverlay(PluginCall call) {
        if (!Settings.canDrawOverlays(getContext())) {
            call.reject("overlay_permission_denied", "需要系统悬浮窗权限");
            return;
        }
        Context ctx = getContext();
        ctx.startService(new Intent(ctx, CiraOverlayService.class).setAction(CiraOverlayService.ACTION_SHOW));
        call.resolve();
    }

    @PluginMethod
    public void hideOverlay(PluginCall call) {
        Context ctx = getContext();
        ctx.startService(new Intent(ctx, CiraOverlayService.class).setAction(CiraOverlayService.ACTION_HIDE));
        call.resolve();
    }

    // ---------- 回到主界面 ----------
    @PluginMethod
    public void openMain(PluginCall call) {
        Context ctx = getContext();
        Intent i = new Intent(ctx, MainActivity.class);
        i.setAction(ACTION_OPEN_MAIN);
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        ctx.startActivity(i);
        call.resolve();
    }

    // ---------- 离线语音识别（Sherpa-ONNX streaming ASR，替代 Web Speech API） ----------
    @PluginMethod
    public void startAsr(PluginCall call) {
        // 缺麦克风权限时自动申请，避免 Web 层忘记调 requestPermissions 导致识别永不启动
        if (ContextCompat.checkSelfPermission(getContext(), Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            pendingAsrCall = call;
            permLauncher.launch(new String[]{
                    Manifest.permission.RECORD_AUDIO,
                    Manifest.permission.POST_NOTIFICATIONS
            });
            return;
        }
        doStartAsr(call);
    }

    private void doStartAsr(PluginCall call) {
        try {
            if (asr == null) {
                asr = new SherpaAsrEngine(getContext());
                asr.setListener(new SherpaAsrEngine.AsrListener() {
                    @Override public void onPartial(String text) { emitAsr("asrPartial", text); }
                    @Override public void onFinal(String text) { emitAsr("asrFinal", text); }
                    @Override public void onError(String msg) { emitAsr("asrError", msg); }
                });
                // 模型已预装在 assets 中，从 assets 复制到内部存储（很快）
                asr.prepareModel(new SherpaAsrEngine.ModelReadyCallback() {
                    @Override public void onReady() {
                        // 模型就绪后自动开始识别
                        try { asr.start(); } catch (Exception e) { emitAsr("asrError", e.getMessage()); }
                    }
                    @Override public void onError(String msg) { emitAsr("asrError", msg); }
                    @Override public void onProgress(int percent) {
                        Log.d("SherpaAsr", "模型准备: " + percent + "%");
                    }
                });
                // call.resolve() 在这里——模型从 assets 复制很快，先 resolve 让 Web 层继续
                // ASR 引擎会在模型就绪后自动开始识别
            } else if (asr.isModelReady()) {
                // 模型已就绪，直接开始
                new Thread(() -> {
                    try { asr.start(); }
                    catch (Exception e) { emitAsr("asrError", e.getMessage()); }
                }).start();
            } else {
                // 模型正在准备中，不重复启动
                Log.d("SherpaAsr", "模型正在准备中…");
            }
            call.resolve();
        } catch (Exception e) {
            call.reject("asr_start_failed", e.getMessage());
        }
    }

    @PluginMethod
    public void stopAsr(PluginCall call) {
        if (asr != null) asr.stop();
        call.resolve();
    }

    // 在 UI 线程回传事件，规避 Capacitor notifyListeners 从后台线程调用可能的问题
    private void emitAsr(String event, String text) {
        final String t = text == null ? "" : text;
        Activity a = getActivity();
        if (a != null) {
            a.runOnUiThread(() -> {
                JSObject d = new JSObject();
                d.put("text", t);
                notifyListeners(event, d);
            });
        } else {
            JSObject d = new JSObject();
            d.put("text", t);
            notifyListeners(event, d);
        }
    }

    // ---------- 原生 HTTP 代理（绕过 WebView CORS，所有 /api/* 走原生） ----------
    @PluginMethod
    public void apiFetch(PluginCall call) {
        String path = call.getString("path");
        String method = call.getString("method", "GET");
        String body = call.getString("body");
        int timeout = call.getInt("timeout", 15000);
        if (path == null || path.isEmpty()) { call.reject("missing_path"); return; }
        String base = BuildConfig.CIRA_CORE_URL;
        if (base == null || base.isEmpty()) { call.reject("core_url_empty"); return; }
        final String url = base + path;
        final String fMethod = method;
        final String fBody = (body == null) ? null : body;
        final int fTimeout = timeout;
        new Thread(() -> {
            int status = -1;
            String bodyText = "";
            String errMsg = null;
            try {
                URL u = new URL(url);
                HttpURLConnection conn = (HttpURLConnection) u.openConnection();
                conn.setRequestMethod(fMethod);
                conn.setConnectTimeout(fTimeout);
                conn.setReadTimeout(fTimeout);
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setRequestProperty("Accept", "application/json");
                if (fBody != null && !fBody.isEmpty() && !"GET".equalsIgnoreCase(fMethod)) {
                    conn.setDoOutput(true);
                    try (OutputStream os = conn.getOutputStream()) {
                        os.write(fBody.getBytes(StandardCharsets.UTF_8));
                    }
                }
                status = conn.getResponseCode();
                StringBuilder sb = new StringBuilder();
                try (BufferedReader br = new BufferedReader(new InputStreamReader(
                        (status >= 200 && status < 400) ? conn.getInputStream() : conn.getErrorStream(),
                        StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = br.readLine()) != null) sb.append(line);
                }
                bodyText = sb.toString();
            } catch (Exception e) {
                errMsg = e.getMessage();
            }
            // Capacitor 要求 PluginCall 结果必须在主线程回传，否则 JS 侧 Promise 永不 resolve
            final int fStatus = status;
            final String fBodyText = bodyText;
            final String fErr = errMsg;
            final Activity a = getActivity();
            if (a != null) {
                a.runOnUiThread(() -> deliverApiResult(call, fStatus, fBodyText, fErr));
            } else {
                deliverApiResult(call, fStatus, fBodyText, fErr);
            }
        }).start();
    }

    private void deliverApiResult(PluginCall call, int status, String bodyText, String errMsg) {
        if (errMsg != null) {
            // 让错误信息对用户友好：检测常见网络错误模式
            String lower = errMsg.toLowerCase();
            String hint;
            if (lower.contains("timeout") || lower.contains("abort") || lower.contains("connect timed out")) {
                hint = "网络超时，请检查连接";
            } else if (lower.contains("refused") || lower.contains("unreachable")) {
                hint = "无法连接到服务器，请检查网络";
            } else {
                hint = "请求失败，请重试";
            }
            Log.e("CiraRuntime", "apiFetch error: " + errMsg + " -> user hint: " + hint);
            call.reject(hint, errMsg);
            return;
        }
        JSObject ret = new JSObject();
        ret.put("status", status);
        ret.put("body", bodyText == null ? "" : bodyText);
        call.resolve(ret);
    }

    // ---------- Web → 原生：状态回传（仅记录，可扩展联动浮窗） ----------
    @PluginMethod
    public void reportState(PluginCall call) {
        String state = call.getString("state");
        call.resolve();
    }
}
