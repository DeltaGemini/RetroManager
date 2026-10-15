package com.retromanager.phone;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import android.net.Uri;
import android.util.Log;
import android.webkit.CookieManager;
import android.webkit.MimeTypeMap;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * What lets the Console page open with no connection. Everything the page asks
 * the server for (the page itself, its scripts, the game lists, the pictures)
 * goes through here: it's fetched as usual and a copy is kept, and when the
 * server can't be reached the copy is given instead. So whatever has been
 * looked at before is there offline, as it was then.
 *
 * Pictures and other media are kept in the RetroArch folder's media folder,
 * under the same system/type/name as on the server, and one that's already
 * there (synced by something else, say) is used without asking the server.
 * Everything else is kept in the app's own storage.
 */
final class OfflineCache {
    private static final String TAG = "RetroManager";
    // Larger answers than this go straight through
    private static final long MAX_KEPT = 64L * 1024 * 1024;
    // A picture the app fetched itself is asked for again after this long
    private static final long MEDIA_REFRESH = 7L * 24 * 3600 * 1000;
    // How long the server is left alone after it couldn't be reached
    private static final long OFFLINE_FOR = 8000;
    private static final Object PASS = new Object();

    private final File kept;
    private final File temp;
    private final SQLiteOpenHelper index;
    private volatile String origin;
    private volatile Folder folder;
    private volatile long offlineUntil;

    OfflineCache(Context context) {
        kept = new File(context.getFilesDir(), "offline");
        temp = new File(context.getCacheDir(), "fetching");
        kept.mkdirs();
        temp.mkdirs();
        File[] left = temp.listFiles();
        if (left != null) for (File file : left) file.delete();
        index = new SQLiteOpenHelper(context, "offline.db", null, 1) {
            @Override public void onCreate(SQLiteDatabase db) {
                // file: "i:<name in the app's storage>" or "f:<path in the RetroArch folder>"
                db.execSQL("CREATE TABLE kept (url TEXT PRIMARY KEY, mime TEXT, charset TEXT, saved INTEGER, max_age INTEGER, file TEXT)");
            }
            @Override public void onUpgrade(SQLiteDatabase db, int from, int to) { }
        };
    }

    /** RetroManager's address ("http://192.168.1.10:5000") and the RetroArch folder. */
    void use(String server, Folder folder) {
        this.origin = server;
        this.folder = folder;
        this.offlineUntil = 0;
    }

    /** Whether the server couldn't be reached a moment ago. */
    boolean offline() {
        return System.currentTimeMillis() < offlineUntil;
    }

    void reached(boolean yes) {
        offlineUntil = yes ? 0 : System.currentTimeMillis() + OFFLINE_FOR;
    }

    /** The answer to give the page for a request, or null to let it ask the network itself. */
    WebResourceResponse intercept(WebResourceRequest request) {
        try {
            return answer(request);
        } catch (Exception e) {
            Log.w(TAG, "Couldn't answer " + request.getUrl(), e);
            return null;
        }
    }

    private WebResourceResponse answer(WebResourceRequest request) {
        Uri uri = request.getUrl();
        String scheme = uri.getScheme();
        if (!"GET".equalsIgnoreCase(request.getMethod()) || scheme == null || !scheme.startsWith("http")) return null;
        // A part of a file (a video being played) isn't worth keeping
        for (String name : request.getRequestHeaders().keySet()) if ("range".equalsIgnoreCase(name)) return null;
        String url = uri.buildUpon().fragment(null).build().toString();
        String path = uri.getPath() == null ? "/" : uri.getPath();
        boolean ours = origin != null && (url.equals(origin) || url.startsWith(origin + "/"));
        // Games, saves and the browser emulator are fetched when they're wanted, not kept here
        if (ours && (path.startsWith("/api/rom") || path.startsWith("/api/phone/rom/") || path.startsWith("/api/play/") || path.startsWith("/emulatorjs/"))) return null;

        // The page wants what was said last time, at once (it asks the server as well)
        for (String name : request.getRequestHeaders().keySet()) {
            if (!"x-retromanager-kept".equalsIgnoreCase(name)) continue;
            Kept last = find(url);
            WebResourceResponse was = last == null ? null : open(last);
            return was != null ? was : new WebResourceResponse("text/plain", "utf-8", 504, "Not kept", new HashMap<>(), new ByteArrayInputStream(new byte[0]));
        }

        Folder folder = this.folder;
        String media = ours && folder != null && path.startsWith("/api/media/") ? "media/" + path.substring("/api/media/".length()) : null;
        Kept copy = find(url);
        long now = System.currentTimeMillis();
        if (media != null) {
            // The phone's own copy, unless it's one of ours that's due a fresh look
            if (copy == null || offline() || now - copy.saved < MEDIA_REFRESH) {
                WebResourceResponse local = fromFolder(folder, media);
                if (local != null) return local;
            }
        } else if (copy != null && copy.maxAge > 0 && now - copy.saved < copy.maxAge * 1000L) {
            WebResourceResponse fresh = open(copy);
            if (fresh != null) return fresh;
        }

        if (!offline()) {
            try {
                Object fetched = fetch(request, url, ours, media);
                return fetched == PASS ? null : (WebResourceResponse) fetched;
            } catch (IOException e) {
                if (ours) reached(false);
            }
        }

        WebResourceResponse old = copy == null ? null : open(copy);
        if (old == null && media != null) old = fromFolder(folder, media);
        // A small picture that was never fetched: the whole one, if the phone has it
        if (old == null && ours && folder != null && path.startsWith("/api/thumb/")) {
            int slash = path.indexOf('/', "/api/thumb/".length());
            if (slash > 0) old = fromFolder(folder, "media/" + path.substring(slash + 1));
        }
        if (old != null) return old;
        if (!ours) return null;
        return request.isForMainFrame() ? notKept() : new WebResourceResponse("text/plain", "utf-8", 503, "Offline", new HashMap<>(), new ByteArrayInputStream(new byte[0]));
    }

    // --- The network ---

    private Object fetch(WebResourceRequest request, String url, boolean ours, String media) throws IOException {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setConnectTimeout(3000);
        connection.setReadTimeout(30000);
        connection.setInstanceFollowRedirects(false);
        for (Map.Entry<String, String> header : request.getRequestHeaders().entrySet()) {
            String name = header.getKey().toLowerCase(Locale.ROOT);
            // Always the whole thing, uncompressed by the connection itself
            if (name.equals("if-none-match") || name.equals("if-modified-since") || name.equals("accept-encoding") || name.equals("cookie")) continue;
            connection.setRequestProperty(header.getKey(), header.getValue());
        }
        String cookies = CookieManager.getInstance().getCookie(url);
        if (cookies != null) connection.setRequestProperty("Cookie", cookies);

        int status = connection.getResponseCode();
        if (ours) reached(true);
        Map<String, String> headers = new HashMap<>();
        String control = null;
        for (Map.Entry<String, List<String>> header : connection.getHeaderFields().entrySet()) {
            if (header.getKey() == null) continue;
            String name = header.getKey().toLowerCase(Locale.ROOT);
            if (name.equals("set-cookie")) {
                for (String cookie : header.getValue()) CookieManager.getInstance().setCookie(url, cookie);
            } else if (name.equals("cache-control")) {
                control = String.join(", ", header.getValue()).toLowerCase(Locale.ROOT);
            } else if (!name.equals("content-encoding") && !name.equals("content-length") && !name.equals("transfer-encoding")
                    && !name.equals("content-type") && !name.equals("connection") && !name.equals("keep-alive")) {
                headers.put(header.getKey(), String.join(", ", header.getValue()));
            }
        }
        // The page follows a redirect itself (an answer given from here can't be one)
        if (status < 200 || (status >= 300 && status < 400)) {
            connection.disconnect();
            return PASS;
        }
        String type = connection.getContentType();
        String mime = type == null ? guessMime(url) : type.split(";")[0].trim();
        String charset = null;
        if (type != null && type.toLowerCase(Locale.ROOT).contains("charset=")) {
            charset = type.substring(type.toLowerCase(Locale.ROOT).indexOf("charset=") + 8).split(";")[0].trim().replace("\"", "");
        } else if (mime.startsWith("text/") || mime.contains("json") || mime.contains("javascript")) {
            charset = "utf-8";
        }
        InputStream body = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
        if (body == null) body = new ByteArrayInputStream(new byte[0]);
        String reason = connection.getResponseMessage();
        if (reason == null || reason.isEmpty()) reason = status < 400 ? "OK" : "Error";
        if (status == 200 && connection.getContentLengthLong() <= MAX_KEPT && (control == null || !control.contains("no-store"))) {
            try {
                body = new Keeping(body, url, mime, charset, maxAge(control), media);
            } catch (IOException e) {
                Log.w(TAG, "Not keeping " + url, e);
            }
        }
        return new WebResourceResponse(mime, charset, status, reason, headers, body);
    }

    private static long maxAge(String control) {
        if (control == null || control.contains("no-cache")) return 0;
        int at = control.indexOf("max-age=");
        if (at < 0) return 0;
        int end = at + 8;
        while (end < control.length() && Character.isDigit(control.charAt(end))) end++;
        try {
            return Long.parseLong(control.substring(at + 8, end));
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    private static String guessMime(String name) {
        int query = name.indexOf('?');
        if (query >= 0) name = name.substring(0, query);
        int dot = name.lastIndexOf('.');
        String mime = dot < 0 ? null : MimeTypeMap.getSingleton().getMimeTypeFromExtension(name.substring(dot + 1).toLowerCase(Locale.ROOT));
        return mime == null ? "application/octet-stream" : mime;
    }

    /** Passes an answer on to the page while writing it to a file, which is kept once all of it has gone by. */
    private final class Keeping extends FilterInputStream {
        private final String url, mime, charset, media;
        private final long maxAge;
        private final File file;
        private OutputStream out;
        private long size;
        private boolean done;

        Keeping(InputStream in, String url, String mime, String charset, long maxAge, String media) throws IOException {
            super(in);
            this.url = url;
            this.mime = mime;
            this.charset = charset;
            this.maxAge = maxAge;
            this.media = media;
            this.file = File.createTempFile("get", null, temp);
            this.out = new FileOutputStream(file);
        }

        @Override public int read() throws IOException {
            byte[] one = new byte[1];
            int n = read(one, 0, 1);
            return n < 0 ? -1 : one[0] & 0xff;
        }

        @Override public int read(byte[] buffer, int offset, int count) throws IOException {
            int n;
            try {
                n = in.read(buffer, offset, count);
            } catch (IOException e) {
                drop();
                throw e;
            }
            if (n < 0) finish();
            else if (out != null) {
                size += n;
                try {
                    if (size > MAX_KEPT) drop(); else out.write(buffer, offset, n);
                } catch (IOException e) {
                    drop();
                }
            }
            return n;
        }

        @Override public long skip(long count) throws IOException {
            drop();
            return in.skip(count);
        }

        @Override public boolean markSupported() { return false; }

        @Override public void close() throws IOException {
            drop();
            in.close();
        }

        private void drop() {
            if (out == null) return;
            try { out.close(); } catch (IOException e) { /* nothing to keep anyway */ }
            out = null;
            if (!done) file.delete();
        }

        private void finish() {
            if (out == null || done) return;
            done = true;
            try {
                out.close();
                out = null;
                String where;
                Folder folder = OfflineCache.this.folder;
                if (media != null && folder != null) {
                    try (InputStream from = new FileInputStream(file); OutputStream to = folder.write(media)) {
                        copy(from, to);
                    }
                    file.delete();
                    where = "f:" + Folder.clean(media);
                } else {
                    String name = sha1(url);
                    File target = new File(kept, name);
                    if (!file.renameTo(target)) throw new IOException("Couldn't keep " + url);
                    where = "i:" + name;
                }
                ContentValues row = new ContentValues();
                row.put("url", url);
                row.put("mime", mime);
                row.put("charset", charset);
                row.put("saved", System.currentTimeMillis());
                row.put("max_age", maxAge);
                row.put("file", where);
                index.getWritableDatabase().insertWithOnConflict("kept", null, row, SQLiteDatabase.CONFLICT_REPLACE);
            } catch (Exception e) {
                Log.w(TAG, "Couldn't keep " + url, e);
                file.delete();
            }
        }
    }

    // --- The copies ---

    private static final class Kept {
        String url, mime, charset, file;
        long saved, maxAge;
    }

    private Kept find(String url) {
        try (Cursor cursor = index.getReadableDatabase().rawQuery("SELECT mime, charset, saved, max_age, file FROM kept WHERE url = ?", new String[]{url})) {
            if (!cursor.moveToFirst()) return null;
            Kept copy = new Kept();
            copy.url = url;
            copy.mime = cursor.getString(0);
            copy.charset = cursor.getString(1);
            copy.saved = cursor.getLong(2);
            copy.maxAge = cursor.getLong(3);
            copy.file = cursor.getString(4);
            return copy;
        } catch (Exception e) {
            return null;
        }
    }

    private WebResourceResponse open(Kept copy) {
        try {
            Folder folder = this.folder;
            InputStream body;
            if (copy.file.startsWith("f:")) {
                if (folder == null) return null;
                body = folder.read(copy.file.substring(2));
            } else {
                body = new FileInputStream(new File(kept, copy.file.substring(2)));
            }
            return new WebResourceResponse(copy.mime, copy.charset, 200, "OK", keptHeaders(), body);
        } catch (IOException e) {
            // The file has gone: forget it
            try { index.getWritableDatabase().delete("kept", "url = ?", new String[]{copy.url}); } catch (Exception ignored) { }
            return null;
        }
    }

    private static WebResourceResponse fromFolder(Folder folder, String rel) {
        Folder.Entry entry = folder.stat(rel);
        if (entry == null || entry.folder) return null;
        try {
            return new WebResourceResponse(guessMime(rel), null, 200, "OK", keptHeaders(), folder.read(rel));
        } catch (IOException e) {
            return null;
        }
    }

    private static Map<String, String> keptHeaders() {
        Map<String, String> headers = new HashMap<>();
        // (the scripts a page loads from a CDN are asked for with crossorigin)
        headers.put("Access-Control-Allow-Origin", "*");
        return headers;
    }

    private WebResourceResponse notKept() {
        String page = "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
                + "<title>RetroManager</title><style>body{margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;"
                + "background:#0a0e27;color:#e8e8f0;font-family:sans-serif;text-align:center;padding:24px;box-sizing:border-box}"
                + "p{color:#a0a8c8;max-width:28em;line-height:1.5;margin:0}button{padding:10px 18px;border-radius:6px;border:1px solid #3a4270;background:#1a2040;color:#e8e8f0;font-size:15px}</style></head>"
                + "<body><h2 style=\"margin:0\">RetroManager can't be reached</h2>"
                + "<p>This page hasn't been opened on this phone before, so there's no copy of it to show. Pages you've opened while connected stay available.</p>"
                + "<div style=\"display:flex;gap:10px\"><button onclick=\"location.reload()\">Try again</button><button onclick=\"RMApp.openSettings()\">This phone</button></div></body></html>";
        return new WebResourceResponse("text/html", "utf-8", new ByteArrayInputStream(page.getBytes(StandardCharsets.UTF_8)));
    }

    /** How much the app's own storage holds for offline (not the media folder). */
    long size() {
        long total = 0;
        File[] files = kept.listFiles();
        if (files != null) for (File file : files) total += file.length();
        return total;
    }

    /** Forgets everything kept, except the media folder's files, which stay where they are. */
    void clear() {
        try { index.getWritableDatabase().delete("kept", null, null); } catch (Exception e) { Log.w(TAG, "Couldn't clear the index", e); }
        File[] files = kept.listFiles();
        if (files != null) for (File file : files) file.delete();
    }

    static void copy(InputStream from, OutputStream to) throws IOException {
        byte[] buffer = new byte[64 * 1024];
        int n;
        while ((n = from.read(buffer)) >= 0) to.write(buffer, 0, n);
    }

    static String sha1(String text) {
        return sha1(text.getBytes(StandardCharsets.UTF_8));
    }

    static String sha1(byte[] bytes) {
        try {
            StringBuilder out = new StringBuilder();
            for (byte b : MessageDigest.getInstance("SHA-1").digest(bytes)) out.append(String.format("%02x", b));
            return out.toString();
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}
