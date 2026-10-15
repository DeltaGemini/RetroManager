package com.retromanager.phone;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;

/**
 * Keeps the app going while games are being fetched and it isn't in front:
 * Android lets an app with a notification up carry on. The fetching itself is
 * Player's; this is only the notification, there for as long as it lasts.
 */
public class FetchService extends Service {
    @Override public IBinder onBind(Intent intent) {
        return null;
    }

    @Override public int onStartCommand(Intent intent, int flags, int id) {
        NotificationManager notifications = getSystemService(NotificationManager.class);
        notifications.createNotificationChannel(new NotificationChannel("fetch", "Fetching games", NotificationManager.IMPORTANCE_LOW));
        Notification notification = new Notification.Builder(this, "fetch")
                .setContentTitle("RetroManager")
                .setContentText("Fetching games to this phone")
                .setSmallIcon(android.R.drawable.stat_sys_download)
                .setOngoing(true)
                .setContentIntent(PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE))
                .build();
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        else startForeground(1, notification);
        return START_NOT_STICKY;
    }
}
