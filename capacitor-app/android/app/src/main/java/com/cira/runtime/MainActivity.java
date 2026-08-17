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
        super.onCreate(savedInstanceState);

        // 注册本项目的原生插件（唤醒词 / 浮窗 / 前台保活 / 权限）
        registerPlugin(CiraRuntimePlugin.class);

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
