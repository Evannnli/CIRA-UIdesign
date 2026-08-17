package com.cira.runtime;

import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.JSObject;

import com.cira.runtime.BuildConfig;

import android.Manifest;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.provider.Settings;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.core.content.ContextCompat;

import java.util.Map;

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
        ret.put("wakewordEnabled", !BuildConfig.PORCUPINE_ACCESS_KEY.isEmpty());
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

    // ---------- Web → 原生：状态回传（仅记录，可扩展联动浮窗） ----------
    @PluginMethod
    public void reportState(PluginCall call) {
        String state = call.getString("state");
        call.resolve();
    }
}
