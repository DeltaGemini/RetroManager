package com.retromanager.phone;

import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageInstaller;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.util.Log;
import android.webkit.CookieManager;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/** Updates the app from inside it: fetches the newer build RetroManager has
 *  (/app/RetroManager.apk, put there by android/build.sh) straight into an
 *  Android install session, and Android asks the person to confirm it, over
 *  this one (it's signed with the same key, so everything here is kept).
 *  The first time, Android wants RetroManager allowed to install apps: the
 *  settings for that open, and the update goes on when the person comes back. */
class Updater {
    private static final String TAG = "RetroManager";
    private static final String DONE = "com.retromanager.phone.UPDATE_DONE";

    private final MainActivity activity;
    private boolean receiving;
    // An update waiting on "install unknown apps" being allowed: the server it's from, or null
    private String waiting;
    private volatile boolean busy;

    Updater(MainActivity activity) {
        this.activity = activity;
    }

    /** Fetches and installs the newer build (from a thread of its own). */
    void install(String server) {
        if (server == null || busy) return;
        if (Build.VERSION.SDK_INT >= 26 && !activity.getPackageManager().canRequestPackageInstalls()) {
            waiting = server;
            activity.say("Allow RetroManager to install apps, then come back: the update carries on.");
            activity.runOnUiThread(() -> {
                try {
                    activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                            Uri.parse("package:" + activity.getPackageName())));
                } catch (Exception e) {
                    activity.say("Allow RetroManager to install unknown apps in the phone's settings, then try again.");
                }
            });
            return;
        }
        busy = true;
        new Thread(() -> {
            PackageInstaller installer = activity.getPackageManager().getPackageInstaller();
            int session = -1;
            try {
                HttpURLConnection connection = (HttpURLConnection) new URL(server + "/app/RetroManager.apk").openConnection();
                String cookie = CookieManager.getInstance().getCookie(server);
                if (cookie != null) connection.setRequestProperty("Cookie", cookie);
                connection.setConnectTimeout(8000);
                connection.setReadTimeout(30000);
                if (connection.getResponseCode() != 200) throw new java.io.IOException("RetroManager said " + connection.getResponseCode());
                long length = connection.getContentLengthLong();
                PackageInstaller.SessionParams params = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                params.setAppPackageName(activity.getPackageName());
                if (length > 0) params.setSize(length);
                session = installer.createSession(params);
                try (PackageInstaller.Session open = installer.openSession(session)) {
                    try (InputStream in = connection.getInputStream(); OutputStream out = open.openWrite("RetroManager.apk", 0, length > 0 ? length : -1)) {
                        byte[] buffer = new byte[64 * 1024];
                        long done = 0;
                        for (int read; (read = in.read(buffer)) > 0; ) {
                            out.write(buffer, 0, read);
                            done += read;
                            activity.progress("Fetching the new version", done, length);
                        }
                        open.fsync(out);
                    }
                    listen();
                    Intent finished = new Intent(DONE).setPackage(activity.getPackageName());
                    PendingIntent pending = PendingIntent.getBroadcast(activity, session, finished,
                            PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0));
                    open.commit(pending.getIntentSender());
                }
                activity.progress(null, 0, 0);
            } catch (Exception e) {
                Log.w(TAG, "The update couldn't be fetched", e);
                if (session >= 0) try { installer.abandonSession(session); } catch (Exception ignored) { }
                activity.progress(null, 0, 0);
                activity.say("The new version couldn't be fetched: " + e.getMessage());
                busy = false;
            }
        }).start();
    }

    /** Back in the app: an update that was waiting on the permission goes on. */
    void resumed() {
        if (waiting == null) return;
        if (Build.VERSION.SDK_INT >= 26 && !activity.getPackageManager().canRequestPackageInstalls()) return;
        String server = waiting;
        waiting = null;
        install(server);
    }

    /** Android's answers about the install: to ask the person, done, or why not. */
    private void listen() {
        if (receiving) return;
        receiving = true;
        BroadcastReceiver receiver = new BroadcastReceiver() {
            @Override public void onReceive(Context context, Intent intent) {
                int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
                if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
                    Intent confirm = Build.VERSION.SDK_INT >= 33
                            ? intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent.class)
                            : legacyIntent(intent);
                    if (confirm != null) activity.startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                    return;
                }
                busy = false;
                // (on success Android replaces the app, so there's no one here to tell)
                if (status != PackageInstaller.STATUS_SUCCESS) {
                    String why = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
                    if (status == PackageInstaller.STATUS_FAILURE_ABORTED) activity.say("The update wasn't installed.");
                    else activity.say("The update didn't install" + (why == null ? "." : ": " + why));
                }
            }
        };
        IntentFilter filter = new IntentFilter(DONE);
        if (Build.VERSION.SDK_INT >= 33) activity.registerReceiver(receiver, filter, Context.RECEIVER_NOT_EXPORTED);
        else activity.registerReceiver(receiver, filter);
    }

    @SuppressWarnings("deprecation")
    private static Intent legacyIntent(Intent intent) {
        return intent.getParcelableExtra(Intent.EXTRA_INTENT);
    }
}
