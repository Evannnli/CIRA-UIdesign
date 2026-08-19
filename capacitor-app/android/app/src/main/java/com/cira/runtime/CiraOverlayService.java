package com.cira.runtime;

import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.graphics.PixelFormat;
import android.net.Uri;
import android.os.Build;
import android.os.IBinder;
import android.provider.Settings;
import android.util.Log;
import android.view.Gravity;
import android.view.LayoutInflater;
import android.view.View;
import android.view.WindowManager;
import android.view.animation.AlphaAnimation;
import android.view.animation.Animation;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

/**
 * 系统级浮窗服务：在其它 App 之上显示一颗小星云（复用 index.html 的 ?overlay=1 模式）。
 * 需要 SYSTEM_ALERT_WINDOW 权限（首次由用户手动授予）。
 */
public class CiraOverlayService extends Service {

    public static final String ACTION_SHOW = "com.cira.runtime.action.OVERLAY_SHOW";
    public static final String ACTION_HIDE = "com.cira.runtime.action.OVERLAY_HIDE";

    private WindowManager wm;
    private View overlayView;

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) return START_NOT_STICKY;
        if (ACTION_HIDE.equals(intent.getAction())) {
            hide();
            stopSelf();
        } else if (ACTION_SHOW.equals(intent.getAction())) {
            show();
        }
        return START_NOT_STICKY;
    }

    private void show() {
        if (overlayView != null) return;
        if (!Settings.canDrawOverlays(this)) {
            Log.w("CiraOverlay", "SYSTEM_ALERT_WINDOW permission not granted");
            return;
        }

        wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                        ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                        : WindowManager.LayoutParams.TYPE_PHONE,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT);
        params.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
        params.x = 0;
        params.y = 200;  // 从底部上移，更居中
        params.width = 280;  // 增加宽度
        params.height = 280; // 增加高度

        overlayView = LayoutInflater.from(this).inflate(R.layout.overlay_window, null);
        WebView wv = overlayView.findViewById(R.id.overlay_web);
        wv.setWebViewClient(new WebViewClient());
        WebSettings ws = wv.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setAllowFileAccess(true);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            ws.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        }
        // 浮窗复用同一套星云：直接加载打包进 assets/public 的页面（?overlay=1）
        String base = "file:///android_asset/public/index.html?overlay=1";
        String coreUrl = com.cira.runtime.BuildConfig.CIRA_CORE_URL;
        if (coreUrl != null && !coreUrl.isEmpty()) base += "&api=" + Uri.encode(coreUrl);
        wv.loadUrl(base);

        wm.addView(overlayView, params);
        
        // 添加淡入动画
        AlphaAnimation fadeIn = new AlphaAnimation(0.0f, 1.0f);
        fadeIn.setDuration(300);
        overlayView.startAnimation(fadeIn);
        Log.d("CiraOverlay", "Overlay shown");
    }

    private void hide() {
        if (overlayView != null && wm != null) {
            // 添加淡出动画
            AlphaAnimation fadeOut = new AlphaAnimation(1.0f, 0.0f);
            fadeOut.setDuration(200);
            fadeOut.setAnimationListener(new Animation.AnimationListener() {
                @Override
                public void onAnimationStart(Animation animation) {}
                @Override
                public void onAnimationRepeat(Animation animation) {}
                @Override
                public void onAnimationEnd(Animation animation) {
                    wm.removeView(overlayView);
                    overlayView = null;
                    Log.d("CiraOverlay", "Overlay hidden");
                }
            });
            overlayView.startAnimation(fadeOut);
        }
    }

    @Override
    public void onDestroy() {
        hide();
        super.onDestroy();
    }
}
