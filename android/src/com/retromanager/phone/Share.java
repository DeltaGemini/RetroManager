package com.retromanager.phone;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.ShortcutInfo;
import android.content.pm.ShortcutManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.drawable.Icon;
import android.net.Uri;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.text.InputType;
import android.view.Gravity;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.ServiceWorkerClient;
import android.webkit.ServiceWorkerController;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;
import org.json.JSONArray;
import org.json.JSONObject;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;

/** Files shared to the app from another (a game downloaded in the browser, say): they're sent to
 *  RetroManager, which stages them, and its Add games page opens on them, as sharing to the
 *  installed web app does. */
final class Share {
    private final MainActivity app;

    Share(MainActivity app) { this.app = app; }

    /** The files an intent carries: the one it names, or the several clipped to it. */
    static List<Uri> shared(Intent intent) {
        List<Uri> files = new ArrayList<>();
        if (intent.getClipData() != null) {
            for (int i = 0; i < intent.getClipData().getItemCount(); i++) {
                Uri file = intent.getClipData().getItemAt(i).getUri();
                if (file != null && !files.contains(file)) files.add(file);
            }
        }
        Uri one = intent.getData() != null ? intent.getData() : (Uri) intent.getParcelableExtra(Intent.EXTRA_STREAM);
        if (one != null && !files.contains(one)) files.add(one);
        List<Uri> several = intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
        if (several != null) for (Uri file : several) if (file != null && !files.contains(file)) files.add(file);
        return files;
    }

    /** Files shared to the app from another (a game downloaded in the browser,
     *  say): they're sent to RetroManager, which stages them, and its Add games
     *  page opens on them, as sharing to the installed web app does. */
    void sharedToUs(Intent intent) {
        String action = intent == null ? null : intent.getAction();
        if (!Intent.ACTION_SEND.equals(action) && !Intent.ACTION_SEND_MULTIPLE.equals(action)) return;
        List<Uri> files = shared(intent);
        intent.setAction(Intent.ACTION_MAIN);
        String server = app.prefs.server();
        if (files.isEmpty() || server == null) {
            if (server == null) app.say("Set RetroManager up first.");
            return;
        }
        new Thread(() -> {
            String boundary = "----RetroManager" + System.nanoTime();
            HttpURLConnection connection = null;
            try {
                // Each file's name and size, to say how far along it is
                String[] names = new String[files.size()];
                long[] sizes = new long[files.size()];
                long total = 0;
                for (int i = 0; i < files.size(); i++) {
                    names[i] = "file" + (i + 1);
                    try (android.database.Cursor cursor = app.getContentResolver().query(files.get(i), new String[]{android.provider.OpenableColumns.DISPLAY_NAME, android.provider.OpenableColumns.SIZE}, null, null, null)) {
                        if (cursor != null && cursor.moveToFirst()) {
                            if (!cursor.isNull(0)) names[i] = cursor.getString(0);
                            if (!cursor.isNull(1)) sizes[i] = cursor.getLong(1);
                        }
                    } catch (Exception e) {
                        // a name of our own, and no size
                    }
                    total += sizes[i];
                }
                connection = (HttpURLConnection) new URL(server + "/share").openConnection();
                connection.setRequestMethod("POST");
                connection.setDoOutput(true);
                connection.setInstanceFollowRedirects(false);
                connection.setConnectTimeout(5000);
                connection.setReadTimeout(120000);
                // Each file's lines before it, and the length of it all when every size is known
                // (which every server takes; without one it goes in chunks)
                byte[][] heads = new byte[files.size()][];
                byte[] end = ("--" + boundary + "--\r\n").getBytes(java.nio.charset.StandardCharsets.UTF_8);
                long length = end.length;
                boolean sized = true;
                for (int i = 0; i < files.size(); i++) {
                    String name = names[i].replace("\"", "'").replace("\r", " ").replace("\n", " ");
                    heads[i] = ("--" + boundary + "\r\nContent-Disposition: form-data; name=\"roms\"; filename=\"" + name + "\"\r\nContent-Type: application/octet-stream\r\n\r\n").getBytes(java.nio.charset.StandardCharsets.UTF_8);
                    length += heads[i].length + sizes[i] + 2;
                    if (sizes[i] <= 0) sized = false;
                }
                if (sized) connection.setFixedLengthStreamingMode(length);
                else connection.setChunkedStreamingMode(256 * 1024);
                connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
                String cookies = CookieManager.getInstance().getCookie(server + "/share");
                if (cookies != null) connection.setRequestProperty("Cookie", cookies);
                long done = 0, last = 0;
                byte[] buffer = new byte[256 * 1024];
                try (java.io.OutputStream out = connection.getOutputStream()) {
                    for (int i = 0; i < files.size(); i++) {
                        String name = names[i];
                        out.write(heads[i]);
                        try (java.io.InputStream in = app.getContentResolver().openInputStream(files.get(i))) {
                            if (in == null) throw new java.io.IOException(name + " couldn't be opened");
                            int n;
                            while ((n = in.read(buffer)) >= 0) {
                                out.write(buffer, 0, n);
                                done += n;
                                long now = android.os.SystemClock.elapsedRealtime();
                                if (now - last > 200) {
                                    last = now;
                                    app.progress("Sending " + name + " to RetroManager", done, total);
                                }
                            }
                        }
                        out.write("\r\n".getBytes(java.nio.charset.StandardCharsets.UTF_8));
                    }
                    out.write(end);
                }
                int status = connection.getResponseCode();
                app.progress(null, 0, 0);
                if (status >= 400) {
                    app.alert("Not sent", "RetroManager answered " + status + ".");
                    return;
                }
                // (it answers with where its Add games page is, with how many it took)
                String where = connection.getHeaderField("Location");
                String page = where == null ? "/import?shared=" + files.size() : where.startsWith("http") ? where.substring(where.indexOf('/', 8)) : where;
                app.runOnUiThread(() -> app.web.loadUrl(server + page));
            } catch (Exception e) {
                app.progress(null, 0, 0);
                app.alert("Not sent", "The files couldn't be sent to RetroManager: " + e.getMessage());
            } finally {
                if (connection != null) connection.disconnect();
            }
        }).start();
    }
}
