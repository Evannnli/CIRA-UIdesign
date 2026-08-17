package com.cira.runtime;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * 开机自启：重启后台唤醒服务。
 * 注意：仅系统广播不够——小米/HyperOS 还需用户在"自启动管理"里允许本应用，见构建说明。
 */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            Intent svc = new Intent(context, CiraForegroundService.class);
            svc.setAction(CiraForegroundService.ACTION_START);
            context.startForegroundService(svc);
        }
    }
}
