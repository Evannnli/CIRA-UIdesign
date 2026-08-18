package com.cira.runtime;

import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeActivity;

import android.Manifest;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.webkit.WebSettings;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.core.content.ContextCompat;

import java.util.Map;

public class MainActivity extends BridgeActivity {

    private static final String TAG = "CiraMain";
    private ActivityResultLauncher<String[]> permLauncher;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // ⚠️ 必须在 super.onCreate()【之前】注册：Bridge 在 super.onCreate() 内部 this.load() 里就已经
        // bridgeBuilder.create() 把 Bridge 实例建好了；之后再 registerPlugin 只是往已废弃的 builder 加，
        // 不会进入已创建的 Bridge → 插件永不生效 → 所有原生调用（apiFetch/startAsr/showOverlay）静默失败
        // （表现为手机端 0 流量、文字/语音/浮窗全无反馈）。这是此前所有"修了没用"的真正根因。
        registerPlugin(CiraRuntimePlugin.class);

        super.onCreate(savedInstanceState);

        // 允许 WebView 访问 http 的 Core（小米15 上指向局域网/云 Core，避免 mixed-content 拦截）
        Bridge bridge = getBridge();
        if (bridge != null && bridge.getWebView() != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            bridge.getWebView().getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        }

        handleOpenMain(getIntent());

        // 注册权限请求回调
        permLauncher = registerForActivityResult(
                new ActivityResultContracts.RequestMultiplePermissions(),
                result -> {
                    boolean mic = Boolean.TRUE.equals(result.get(Manifest.permission.RECORD_AUDIO));
                    boolean notif = Boolean.TRUE.equals(result.get(Manifest.permission.POST_NOTIFICATIONS));
                    if (mic) {
                        Log.i(TAG, "麦克风权限已授予，启动全局唤醒服务");
                        startWakeWordService();
                    } else {
                        Log.w(TAG, "麦克风权限被拒绝，全局唤醒无法启动");
                    }
                });

        // 自动启动全局唤醒服务（如果权限已授予）
        autoStartWakeWordService();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        handleOpenMain(intent);
    }

    // 浮窗/后台服务请求"回到主界面"：singleTask 下由系统带到前台，无需额外动作
    private void handleOpenMain(Intent intent) {
        if (intent != null && CiraRuntimePlugin.ACTION_OPEN_MAIN.equals(intent.getAction())) {
            // no-op
        }
    }

    /**
     * 自动启动全局唤醒服务
     * - 如果权限已授予，直接启动
     * - 如果权限未授予，请求权限后再启动
     */
    private void autoStartWakeWordService() {
        Context ctx = this;

        // 检查麦克风权限
        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            Log.i(TAG, "请求麦克风权限以启动全局唤醒");
            permLauncher.launch(new String[]{
                    Manifest.permission.RECORD_AUDIO,
                    Manifest.permission.POST_NOTIFICATIONS
            });
            return;
        }

        // 权限已授予，直接启动服务
        startWakeWordService();
    }

    /**
     * 启动前台唤醒服务
     */
    private void startWakeWordService() {
        Context ctx = this;
        Intent svc = new Intent(ctx, CiraForegroundService.class);
        svc.setAction(CiraForegroundService.ACTION_START);
        ctx.startForegroundService(svc);
        Log.i(TAG, "全局唤醒服务已启动");
    }
}
