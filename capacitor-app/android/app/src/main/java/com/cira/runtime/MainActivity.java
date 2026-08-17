package com.cira.runtime;

import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeActivity;

import android.os.Build;
import android.os.Bundle;
import android.content.Intent;
import android.webkit.WebSettings;

public class MainActivity extends BridgeActivity {

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
}
