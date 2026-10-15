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

/**
 * RetroManager's Console page as a phone's game launcher. The page is the
 * server's own, shown in a WebView; what the app adds is `RMApp` on the page,
 * whose play() starts a game in the phone's RetroArch (Player), and copies of
 * what the page loads so it opens with no connection (OfflineCache).
 *
 * The first time, it asks for RetroManager's address and for RetroArch's
 * folder, where the games (roms/), pictures (media/) and saves (saves/) are.
 */
public class MainActivity extends Activity {
    private static final int PICK_FOLDER = 1;
    private static final int PICK_FILES = 3;
    private android.webkit.ValueCallback<Uri[]> picking;
    private static final String PLAY = "com.retromanager.phone.PLAY";
    private static final String VERSION = "1.0";

    private Prefs prefs;
    private OfflineCache cache;
    private Player player;
    private Setup setup;
    private WebView web;
    private volatile Folder folder;
    private AlertDialog progress;
    private TextView progressText;
    private ProgressBar progressBar;
    // Each system's game files on the phone, as the page was last told (see RMApp.localRoms)
    private final Map<String, String> roms = new HashMap<>();
    private String allRoms;
    private boolean fetching;
    private final java.util.concurrent.ExecutorService lister = java.util.concurrent.Executors.newSingleThreadExecutor();
    private volatile long probed;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = new Prefs(this);
        cache = new OfflineCache(this);
        player = new Player(this, prefs, cache);
        setup = new Setup(this, prefs, player);
        SaveJob.schedule(this);

        web = new WebView(this);
        web.setBackgroundColor(0xff0a0e27);
        setContentView(web, new ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setUserAgentString(settings.getUserAgentString() + " RetroManagerApp/" + VERSION);
        CookieManager.getInstance().setAcceptCookie(true);
        web.addJavascriptInterface(new Bridge(), "RMApp");
        web.setWebChromeClient(new WebChromeClient() {
            // "Choose files", on the Add games page: the phone's own file picker
            @Override public boolean onShowFileChooser(WebView view, android.webkit.ValueCallback<Uri[]> chosen, FileChooserParams params) {
                if (picking != null) picking.onReceiveValue(null);
                picking = chosen;
                Intent pick = new Intent(Intent.ACTION_GET_CONTENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*");
                // (games come in every kind of file, so none is left out)
                pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                try {
                    startActivityForResult(pick, PICK_FILES);
                } catch (Exception e) {
                    picking = null;
                    chosen.onReceiveValue(null);
                    alert("No file picker", "This phone has nothing to choose files with.");
                }
                return true;
            }
        });
        web.setWebViewClient(new WebViewClient() {
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return cache.intercept(request);
            }

            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap icon) {
                // (the page that was showing them has gone)
                forgetAsked();
            }

            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                // Only RetroManager's own pages open here (they're the ones given RMApp)
                String url = request.getUrl().toString(), server = prefs.server();
                if (server != null && (url.equals(server) || url.startsWith(server + "/"))) {
                    // The Console page is the app's only view: a link to the Library comes back to it
                    String path = request.getUrl().getPath();
                    // (except for one of its tools, such as Profiles and login, which the header's profile button opens)
                    boolean tool = request.getUrl().getQueryParameter("tool") != null;
                    if (request.isForMainFrame() && !tool && (path == null || path.isEmpty() || path.equals("/"))) {
                        view.loadUrl(server + "/console");
                        return true;
                    }
                    return false;
                }
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, request.getUrl()));
                } catch (Exception e) {
                    say("Nothing on this phone opens " + url);
                }
                return true;
            }
        });
        // (over https the page has a service worker, whose requests don't come through the WebViewClient)
        ServiceWorkerController.getInstance().setServiceWorkerClient(new ServiceWorkerClient() {
            @Override public WebResourceResponse shouldInterceptRequest(WebResourceRequest request) {
                return cache.intercept(request);
            }
        });

        if (prefs.tree() != null && Folder.usable(prefs.tree())) folder = new Folder(this, prefs.tree());
        if (prefs.server() == null) askServer(null, null);
        else if (folder == null) askFolder();
        else open();
        // (not when the app is only being brought back from the recent apps)
        if (state == null && (getIntent().getFlags() & Intent.FLAG_ACTIVITY_LAUNCHED_FROM_HISTORY) == 0) {
            playFrom(getIntent());
            sharedToUs(getIntent());
        }
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        playFrom(intent);
        sharedToUs(intent);
    }

    /** The files an intent carries: the one it names, or the several clipped to it. */
    private static List<Uri> shared(Intent intent) {
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
    private void sharedToUs(Intent intent) {
        String action = intent == null ? null : intent.getAction();
        if (!Intent.ACTION_SEND.equals(action) && !Intent.ACTION_SEND_MULTIPLE.equals(action)) return;
        List<Uri> files = shared(intent);
        intent.setAction(Intent.ACTION_MAIN);
        String server = prefs.server();
        if (files.isEmpty() || server == null) {
            if (server == null) say("Set RetroManager up first.");
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
                    try (android.database.Cursor cursor = getContentResolver().query(files.get(i), new String[]{android.provider.OpenableColumns.DISPLAY_NAME, android.provider.OpenableColumns.SIZE}, null, null, null)) {
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
                        try (java.io.InputStream in = getContentResolver().openInputStream(files.get(i))) {
                            if (in == null) throw new java.io.IOException(name + " couldn't be opened");
                            int n;
                            while ((n = in.read(buffer)) >= 0) {
                                out.write(buffer, 0, n);
                                done += n;
                                long now = android.os.SystemClock.elapsedRealtime();
                                if (now - last > 200) {
                                    last = now;
                                    progress("Sending " + name + " to RetroManager", done, total);
                                }
                            }
                        }
                        out.write("\r\n".getBytes(java.nio.charset.StandardCharsets.UTF_8));
                    }
                    out.write(end);
                }
                int status = connection.getResponseCode();
                progress(null, 0, 0);
                if (status >= 400) {
                    alert("Not sent", "RetroManager answered " + status + ".");
                    return;
                }
                // (it answers with where its Add games page is, with how many it took)
                String where = connection.getHeaderField("Location");
                String page = where == null ? "/import?shared=" + files.size() : where.startsWith("http") ? where.substring(where.indexOf('/', 8)) : where;
                runOnUiThread(() -> web.loadUrl(server + page));
            } catch (Exception e) {
                progress(null, 0, 0);
                alert("Not sent", "The files couldn't be sent to RetroManager: " + e.getMessage());
            } finally {
                if (connection != null) connection.disconnect();
            }
        }).start();
    }

    /** A game's icon on the home screen was pressed (see Bridge.pin): the game starts. */
    private void playFrom(Intent intent) {
        if (intent == null || !PLAY.equals(intent.getAction()) || prefs.server() == null || folder == null) return;
        String system = intent.getStringExtra("system"), rom = intent.getStringExtra("rom");
        // (once: turning the phone, or coming back to the app, isn't pressing it again)
        intent.setAction(Intent.ACTION_MAIN);
        if (system != null && rom != null) player.play(system, rom);
    }

    /** A game's picture as a home screen icon: the whole picture in the middle,
     *  over itself filling the square and darkened, so no shape of icon cuts into it. */
    private Icon icon(String picture) {
        Bitmap art = null;
        Folder folder = this.folder;
        if (picture != null && !picture.isEmpty()) {
            // The phone's own copy, or else the server's small one
            try (java.io.InputStream in = folder.read("media/" + picture)) {
                art = BitmapFactory.decodeStream(in);
            } catch (Exception e) {
                // not on the phone
            }
            if (art == null) {
                try {
                    StringBuilder address = new StringBuilder(prefs.server() + "/api/thumb/480");
                    for (String part : picture.split("/")) address.append('/').append(Uri.encode(part));
                    HttpURLConnection connection = (HttpURLConnection) new URL(address.toString()).openConnection();
                    connection.setConnectTimeout(4000);
                    connection.setReadTimeout(15000);
                    String cookies = CookieManager.getInstance().getCookie(address.toString());
                    if (cookies != null) connection.setRequestProperty("Cookie", cookies);
                    try (java.io.InputStream in = connection.getInputStream()) {
                        art = BitmapFactory.decodeStream(in);
                    } finally {
                        connection.disconnect();
                    }
                } catch (Exception e) {
                    // no picture: the app's own icon
                }
            }
        }
        if (art == null) return Icon.createWithResource(this, getApplicationInfo().icon);
        // (a picture straight off a card can be huge)
        while (art.getWidth() > 2000 || art.getHeight() > 2000) art = Bitmap.createScaledBitmap(art, art.getWidth() / 2, art.getHeight() / 2, true);
        int size = 432;
        Bitmap icon = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(icon);
        Paint paint = new Paint(Paint.FILTER_BITMAP_FLAG | Paint.ANTI_ALIAS_FLAG);
        float cover = Math.max(size / (float) art.getWidth(), size / (float) art.getHeight());
        RectF behind = new RectF((size - art.getWidth() * cover) / 2, (size - art.getHeight() * cover) / 2, (size + art.getWidth() * cover) / 2, (size + art.getHeight() * cover) / 2);
        canvas.drawColor(0xff0a0e27);
        canvas.drawBitmap(art, null, behind, paint);
        canvas.drawColor(0xb0000000);
        // An adaptive icon shows its middle two thirds for certain: the picture fits in a little more
        float inside = size * 0.70f, fit = Math.min(inside / art.getWidth(), inside / art.getHeight());
        canvas.drawBitmap(art, null, new RectF((size - art.getWidth() * fit) / 2, (size - art.getHeight() * fit) / 2, (size + art.getWidth() * fit) / 2, (size + art.getHeight() * fit) / 2), paint);
        return Icon.createWithAdaptiveBitmap(icon);
    }

    @Override protected void onResume() {
        super.onResume();
        web.onResume();
        // Back from RetroArch, most likely: did the game begin there, and has its save changed
        player.checkLaunch();
        player.sendSaves();
        // (and the roms folder may have changed meanwhile: something else may keep it in step)
        romsChanged();
    }

    @Override protected void onPause() {
        stick = null;
        padRepeat.removeCallbacks(stickAgain);
        web.onPause();
        CookieManager.getInstance().flush();
        super.onPause();
    }

    @Override protected void onDestroy() {
        if (progress != null) progress.dismiss();
        web.destroy();
        super.onDestroy();
    }

    // --- A controller ---
    // A page inside the app isn't given a controller's presses, so they're passed
    // to it (RMPad, in the Console): the D-pad or stick chooses, A opens or plays,
    // B goes back, X is the game's page, L1 and R1 a page up and down.

    private final android.os.Handler padRepeat = new android.os.Handler(android.os.Looper.getMainLooper());
    private String stick;
    private final Runnable stickAgain = new Runnable() {
        @Override public void run() {
            if (stick == null) return;
            pad(stick);
            padRepeat.postDelayed(this, 110);
        }
    };

    private static String padKey(int code) {
        switch (code) {
            case android.view.KeyEvent.KEYCODE_DPAD_UP: return "ArrowUp";
            case android.view.KeyEvent.KEYCODE_DPAD_DOWN: return "ArrowDown";
            case android.view.KeyEvent.KEYCODE_DPAD_LEFT: return "ArrowLeft";
            case android.view.KeyEvent.KEYCODE_DPAD_RIGHT: return "ArrowRight";
            case android.view.KeyEvent.KEYCODE_DPAD_CENTER:
            case android.view.KeyEvent.KEYCODE_BUTTON_A:
            case android.view.KeyEvent.KEYCODE_BUTTON_START: return "Enter";
            case android.view.KeyEvent.KEYCODE_BUTTON_B: return "Escape";
            case android.view.KeyEvent.KEYCODE_BUTTON_X: return "e";
            case android.view.KeyEvent.KEYCODE_BUTTON_L1: return "PageUp";
            case android.view.KeyEvent.KEYCODE_BUTTON_R1: return "PageDown";
            default: return null;
        }
    }

    private static boolean fromPad(int source) {
        return (source & android.view.InputDevice.SOURCE_GAMEPAD) == android.view.InputDevice.SOURCE_GAMEPAD
                || (source & android.view.InputDevice.SOURCE_JOYSTICK) == android.view.InputDevice.SOURCE_JOYSTICK
                || (source & android.view.InputDevice.SOURCE_DPAD) == android.view.InputDevice.SOURCE_DPAD;
    }

    private void pad(String key) {
        if (!isFinishing() && !isDestroyed()) web.evaluateJavascript("window.RMPad&&window.RMPad('" + key + "')", null);
    }

    @Override public boolean dispatchKeyEvent(android.view.KeyEvent event) {
        String key = fromPad(event.getSource()) ? padKey(event.getKeyCode()) : null;
        if (key == null) return super.dispatchKeyEvent(event);
        // (held down, only the ones that move carry on)
        if (event.getAction() == android.view.KeyEvent.ACTION_DOWN && (event.getRepeatCount() == 0 || key.startsWith("Arrow") || key.startsWith("Page"))) pad(key);
        return true;
    }

    @Override public boolean dispatchGenericMotionEvent(android.view.MotionEvent event) {
        if ((event.getSource() & android.view.InputDevice.SOURCE_JOYSTICK) != android.view.InputDevice.SOURCE_JOYSTICK
                || event.getAction() != android.view.MotionEvent.ACTION_MOVE) return super.dispatchGenericMotionEvent(event);
        // The D-pad of many controllers is a "hat"; the left stick does the same
        float x = event.getAxisValue(android.view.MotionEvent.AXIS_HAT_X), y = event.getAxisValue(android.view.MotionEvent.AXIS_HAT_Y);
        if (Math.abs(x) < 0.5f && Math.abs(y) < 0.5f) {
            x = event.getAxisValue(android.view.MotionEvent.AXIS_X);
            y = event.getAxisValue(android.view.MotionEvent.AXIS_Y);
        }
        String now = Math.abs(x) > 0.6f && Math.abs(x) >= Math.abs(y) ? (x < 0 ? "ArrowLeft" : "ArrowRight")
                : Math.abs(y) > 0.6f ? (y < 0 ? "ArrowUp" : "ArrowDown") : null;
        if (now == null ? stick != null : !now.equals(stick)) {
            stick = now;
            padRepeat.removeCallbacks(stickAgain);
            if (now != null) {
                pad(now);
                padRepeat.postDelayed(stickAgain, 380);
            }
        }
        return true;
    }

    @SuppressWarnings("deprecation")
    @Override public void onBackPressed() {
        // The page says where Back goes (a game's page to its list, the list to
        // the systems, a popup away): only when it has nowhere does the app go
        // back a page, or close
        web.evaluateJavascript("(function(){try{return !!(window.RMBack&&window.RMBack())}catch(e){return false}})()", handled -> {
            if ("true".equals(handled) || isFinishing() || isDestroyed()) return;
            if (web.canGoBack()) web.goBack();
            else finish();
        });
    }

    private void open() {
        cache.use(prefs.server(), folder);
        // (once, where whose the phone's saves are was said before the app went through them all)
        if (prefs.unclaimed() != null && !prefs.claimed() && folder != null) {
            Folder here = folder;
            new Thread(() -> player.claim(here, prefs.unclaimed())).start();
        }
        player.refreshCores();
        checkUpdate(false);
        refreshShortcuts();
        romsChanged();
        web.clearHistory();
        web.loadUrl(prefs.server() + "/console");
    }

    Setup setup() {
        return setup;
    }

    Folder folder() {
        return folder;
    }

    // --- What the page can ask for ---

    private final class Bridge {
        /** Starts a game in RetroArch, fetching it first if the phone hasn't got it. */
        @JavascriptInterface public void play(String system, String rom) {
            if (system == null || rom == null || system.contains("/") || system.startsWith(".")) return;
            player.play(system, rom);
        }

        /** The answer to a question the page drew for the app (window.RMDialog): the option's
         *  place, 0 or 1 for a button, or -1 for "put away"; and what was typed, if it asked. */
        @JavascriptInterface public void dialogAnswer(String id, int index, String text) {
            runOnUiThread(() -> {
                Answer answer = asked.remove(id);
                if (answer != null) answer.answer(index, text);
            });
        }

        /** Cancel, pressed on the page's "fetching" box. */
        @JavascriptInterface public void cancelFetch() {
            player.cancel();
        }

        // --- The page's own "This phone" panel (common/header.js) ---

        /** What the panel shows: {server, folder, retroArch, retroArchs, profile, profiles, kept, version}. */
        @JavascriptInterface public String settingsInfo() {
            try {
                String mine;
                try {
                    mine = getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
                } catch (Exception e) {
                    mine = "?";
                }
                return new JSONObject().put("server", prefs.server()).put("folder", folder == null ? JSONObject.NULL : folder.path())
                        .put("retroArch", player.retroArch() == null ? JSONObject.NULL : player.retroArch()).put("retroArchs", new JSONArray(player.installed()))
                        .put("profile", prefs.profile() == null ? JSONObject.NULL : prefs.profile()).put("profiles", prefs.profiles())
                        .put("kept", Player.size(cache.size())).put("version", mine).put("pinSaves", prefs.pinSaves())
                        .put("unclaimed", prefs.unclaimed() == null ? JSONObject.NULL : prefs.unclaimed()).toString();
            } catch (org.json.JSONException e) {
                return "{}";
            }
        }

        /** One of the panel's actions: "server", "folder", "retroarch" (value: the app), "profile" (value: the
         *  name, or "" for nobody), "forget", "update", "reload", "open" (value: an address, for the browser). */
        @JavascriptInterface public void setting(String what, String value) {
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed() || what == null) return;
                switch (what) {
                    case "server": askServer(null, null); break;
                    case "folder": askFolder(); break;
                    case "retroarch": if (player.installed().contains(value)) prefs.retroArch(value); break;
                    case "profile": prefs.profile(value == null ? "" : value); break;
                    case "unclaimed":
                        if (value == null || value.isEmpty()) break;
                        prefs.unclaimed(value);
                        tellPage();
                        new Thread(() -> say(player.claim(folder(), value) + " games' saves on this phone are taken to be " + value + "'s")).start();
                        break;
                    case "forget":
                        try {
                            ask(spec("confirm", "Forget the pages kept for offline?", "The pages and game lists kept for when there's no connection are forgotten, and kept again as they're opened. Pictures in the media folder stay.").put("yes", "Forget"), (index, text) -> {
                                if (index != 0) return;
                                cache.clear();
                                say("Forgotten.");
                                tellPage();
                            });
                        } catch (org.json.JSONException e) {
                            // nothing to ask with
                        }
                        break;
                    case "update": checkUpdate(true); break;
                    // RetroArch's setup (Setup.java): "save" this phone's, "apply" the kept one, "check", and "pin" (value: on or off)
                    case "setup-save": setup.save(); break;
                    case "setup-apply": setup.apply(); break;
                    case "setup-check": setup.check(); break;
                    case "setup-pin": prefs.pinSaves("on".equals(value)); break;
                    case "reload":
                        cache.reached(true);
                        web.reload();
                        break;
                    case "open":
                        if (value != null && value.matches("(?i)^https?://.*")) start(new Intent(Intent.ACTION_VIEW, Uri.parse(value)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                        break;
                    default: break;
                }
                tellPage();
            });
        }

        /** What plays each system, for the panel: [{name, label, plays, chosen, options: [{id, label, note, get}]}]. */
        @JavascriptInterface public String emulatorsInfo() {
            JSONArray out = new JSONArray(), systems = player.systems();
            Player.History history = player.new History(folder);
            try {
                for (int i = 0; i < systems.length(); i++) {
                    JSONObject system = systems.optJSONObject(i);
                    String name = system.optString("name");
                    JSONArray players = Player.players(system), options = new JSONArray();
                    java.util.Set<String> failed = prefs.failed(name);
                    for (int j = 0; j < players.length(); j++) {
                        JSONObject one = players.optJSONObject(j);
                        JSONObject option = new JSONObject().put("id", one.optString("id")).put("label", one.optString("name"));
                        if ("core".equals(one.optString("kind"))) {
                            option.put("note", failed.contains(one.optString("core")) ? "didn't start when tried" : history.used(one.optString("core")) ? "installed" : "");
                        } else if (player.has(one.optString("package"))) {
                            option.put("note", "installed · keeps its own saves");
                        } else {
                            option.put("note", "not installed").put("get", one.optString("get"));
                        }
                        options.put(option);
                    }
                    JSONObject plays = player.choose(history, name, null, players);
                    out.put(new JSONObject().put("name", name).put("label", system.optString("label", name))
                            .put("plays", plays == null ? JSONObject.NULL : plays.optString("name"))
                            .put("chosen", prefs.core(name) == null ? JSONObject.NULL : prefs.core(name)).put("options", options));
                }
            } catch (org.json.JSONException e) {
                // as far as it got
            }
            return out.toString();
        }

        /** What a system is played with: a player's id, "retroarch:<core>" for one typed in, or "" to let the app choose. */
        @JavascriptInterface public void setEmulator(String system, String id) {
            if (system == null || system.contains("/")) return;
            if (id != null && id.startsWith("retroarch:")) prefs.failed(system, id.substring("retroarch:".length()), false);
            prefs.core(system, id == null || id.isEmpty() ? null : id);
            tellPage();
        }

        /** Looks through the roms folder for the panel, which is sent the answer when it's ready
         *  ("retromanager:phone-storage": {total, free, systems: [{name, label, size, files: [[path, size]]}]}). */
        @JavascriptInterface public void scanStorage() {
            Folder folder = MainActivity.this.folder;
            if (folder == null) return;
            new Thread(() -> {
                try {
                    JSONArray systems = new JSONArray();
                    long total = 0;
                    for (Folder.Entry system : folder.list("roms")) {
                        if (!system.folder || system.name.startsWith(".")) continue;
                        List<Object[]> files = new ArrayList<>();
                        sizes(folder, "roms/" + system.name, "", 0, files);
                        if (files.isEmpty()) continue;
                        files.sort((a, b) -> Long.compare((Long) b[1], (Long) a[1]));
                        long size = 0;
                        JSONArray listed = new JSONArray();
                        for (Object[] file : files) {
                            size += (Long) file[1];
                            if (listed.length() < 400) listed.put(new JSONArray().put(file[0]).put(Player.size((Long) file[1])));
                        }
                        total += size;
                        systems.put(new JSONObject().put("name", system.name).put("label", player.systemEntry(system.name).optString("label", system.name))
                                .put("count", files.size()).put("size", Player.size(size)).put("bytes", size).put("files", listed));
                    }
                    String free;
                    try {
                        free = Player.size(new android.os.StatFs(folder.path()).getAvailableBytes());
                    } catch (Exception e) {
                        free = "";
                    }
                    String found = new JSONObject().put("total", Player.size(total)).put("free", free).put("systems", systems).toString();
                    runOnUiThread(() -> {
                        if (!isFinishing() && !isDestroyed())
                            web.evaluateJavascript("window.dispatchEvent(new CustomEvent('retromanager:phone-storage', { detail: " + found + " }))", null);
                    });
                } catch (org.json.JSONException e) {
                    // nothing to show
                }
            }).start();
        }

        /** Fetches a game to the phone without starting it. */
        @JavascriptInterface public void fetch(String system, String rom, String name) {
            if (system == null || rom == null || system.contains("/") || system.startsWith(".")) return;
            player.fetch(system, rom, name == null || name.isEmpty() ? rom : name);
        }

        /** Fetches several, after asking: a JSON list of [system, rom]. */
        @JavascriptInterface public void fetchAll(String games) {
            try {
                player.fetchAll(new JSONArray(games));
            } catch (org.json.JSONException e) {
                // nothing to fetch
            }
        }

        /** Asks what this one game is played with (over what its system is). */
        @JavascriptInterface public void chooseEmulator(String system, String rom, String name) {
            if (system == null || rom == null || system.contains("/") || system.startsWith(".")) return;
            emulators(system, rom.startsWith("./") ? rom.substring(2) : rom, name);
        }

        /** Takes a game off the phone (its files in the roms folder), after asking. The server's copy isn't touched. */
        @JavascriptInterface public void removeLocal(String system, String rom, String name) {
            if (system == null || rom == null || system.contains("/") || system.startsWith(".")) return;
            player.remove(system, name == null || name.isEmpty() ? rom : name, rom);
        }

        /** A system's game files on the phone: a JSON list of paths in its roms folder. */
        @JavascriptInterface public String localRoms(String system) {
            Folder folder = MainActivity.this.folder;
            if (folder == null || system == null || system.contains("/") || system.startsWith(".")) return "[]";
            synchronized (roms) {
                String listed = roms.get(system);
                if (listed == null) {
                    JSONArray found = new JSONArray();
                    list(folder, "roms/" + system, "", 0, found);
                    listed = found.toString();
                    roms.put(system, listed);
                }
                return listed;
            }
        }

        /** Every system's game files on the phone: a JSON object of system folder -> paths in it.
         *  It's the list as last worked out, given at once; the page is told
         *  ("retromanager:phone-roms") when a fresh look finds it has changed. */
        @JavascriptInterface public String localSystems() {
            synchronized (roms) {
                if (allRoms == null) {
                    try (java.io.InputStream in = new java.io.FileInputStream(romsFile())) {
                        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
                        OfflineCache.copy(in, out);
                        allRoms = out.toString("UTF-8");
                    } catch (java.io.IOException e) {
                        allRoms = "{}";
                    }
                }
                return allRoms;
            }
        }

        /** The systems nothing on this phone plays yet: a JSON list of their folders. */
        @JavascriptInterface public String unplayable() {
            return player.unplayable();
        }

        /** Whether RetroManager can't be reached. The page asks every few seconds,
         *  which is also what has the server looked for again. */
        @JavascriptInterface public boolean offline() {
            long now = android.os.SystemClock.elapsedRealtime();
            String server = prefs.server();
            if (server != null && now - probed > 5000) {
                probed = now;
                new Thread(() -> {
                    try {
                        HttpURLConnection connection = (HttpURLConnection) new URL(server + "/api/health").openConnection();
                        connection.setConnectTimeout(3000);
                        connection.setReadTimeout(3000);
                        connection.getResponseCode();
                        connection.disconnect();
                        cache.reached(true);
                    } catch (Exception e) {
                        cache.reached(false);
                    }
                }).start();
            }
            return cache.offline();
        }

        /** Puts a game on the phone's home screen, as an icon that starts it:
         *  `picture` is its media path ("snes/box2d/Game.png"), for the icon. */
        @JavascriptInterface public void pin(String system, String rom, String name, String picture) {
            if (system == null || rom == null || system.contains("/") || system.startsWith(".")) return;
            ShortcutManager shortcuts = getSystemService(ShortcutManager.class);
            if (shortcuts == null || !shortcuts.isRequestPinShortcutSupported()) {
                alert("Home screen", "This phone's home screen doesn't take icons from apps.");
                return;
            }
            new Thread(() -> {
                String label = name == null || name.isEmpty() ? rom : name;
                // Straight into RetroArch where that can be; otherwise through the app, which fetches the game or hands it to its emulator
                Intent play = player.direct(system, rom);
                if (play == null) play = new Intent(MainActivity.this, MainActivity.class).setAction(PLAY).putExtra("system", system).putExtra("rom", rom);
                ShortcutInfo shortcut = new ShortcutInfo.Builder(MainActivity.this, "game:" + system + "/" + rom)
                        .setShortLabel(label).setLongLabel(label).setIcon(icon(picture)).setIntent(play).build();
                try {
                    // (the phone asks before it adds it)
                    if (!shortcuts.requestPinShortcut(shortcut, null)) say("The home screen wouldn't take it.");
                } catch (Exception e) {
                    say("Couldn't add it: " + e.getMessage());
                }
            }).start();
        }

        /** "Offline", pressed: looks for RetroManager again now. If it still isn't there, offers
         *  to start Tailscale, which is how it's reached away from home. */
        @JavascriptInterface public void checkOnline() {
            new Thread(() -> {
                if (reachable()) {
                    backOnline("RetroManager is back.");
                    return;
                }
                boolean tailscale = player.has(TAILSCALE);
                runOnUiThread(() -> {
                    try {
                        JSONObject spec = spec("confirm", "RetroManager still can't be reached",
                                tailscale ? "Away from home it's reached over Tailscale, which may be off. Start it?"
                                        : "The phone isn't on RetroManager's network. Away from home it needs a VPN to it, such as Tailscale.")
                                .put("yes", tailscale ? "Start Tailscale" : "OK");
                        if (tailscale) spec.put("other", "Open Tailscale");
                        ask(spec, (index, text) -> {
                            if (!tailscale || index < 0) return;
                            if (index == 1) {
                                Intent open = getPackageManager().getLaunchIntentForPackage(TAILSCALE);
                                if (open != null) start(open);
                                return;
                            }
                            // Tailscale connects when it's sent this (it's how other apps switch it on)
                            try {
                                sendBroadcast(new Intent(TAILSCALE + ".CONNECT_VPN").setClassName(TAILSCALE, TAILSCALE + ".IPNReceiver"));
                            } catch (Exception e) {
                                say("Tailscale couldn't be started from here: open it instead.");
                                return;
                            }
                            say("Starting Tailscale…");
                            new Thread(() -> {
                                // (it takes a few seconds to come up)
                                for (int tries = 0; tries < 6; tries++) {
                                    try { Thread.sleep(2500); } catch (InterruptedException e) { return; }
                                    if (reachable()) {
                                        backOnline("Connected: RetroManager is back.");
                                        return;
                                    }
                                }
                                say("Still no RetroManager. Open Tailscale to see whether it connected.");
                            }).start();
                        });
                    } catch (org.json.JSONException e) {
                        // nothing to ask with
                    }
                });
            }).start();
        }

        /** Opens the whole of RetroManager (the Library and the rest) in the phone's browser. */
        @JavascriptInterface public void openBrowser() {
            String server = prefs.server();
            if (server == null) return;
            String problem = start(new Intent(Intent.ACTION_VIEW, Uri.parse(server + "/")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            if (problem != null) say("No browser opened: " + problem);
        }

        @JavascriptInterface public String version() {
            return VERSION;
        }

        @JavascriptInterface public void openSettings() {
            runOnUiThread(MainActivity.this::settings);
        }
    }

    private static void list(Folder folder, String base, String inside, int depth, JSONArray found) {
        for (Folder.Entry entry : folder.list(inside.isEmpty() ? base : base + "/" + inside)) {
            String path = inside.isEmpty() ? entry.name : inside + "/" + entry.name;
            if (!entry.folder) found.put(path);
            else if (depth < 3) list(folder, base, path, depth + 1, found);
        }
    }

    private java.io.File romsFile() {
        return new java.io.File(getFilesDir(), "roms.json");
    }

    /** The roms folder may have changed (a game arrived, or the app came back):
     *  its files are listed again, off the page's own thread since a big folder
     *  takes a moment, and the page is told if the list is a different one. */
    void romsChanged() {
        Folder folder = this.folder;
        if (folder == null) return;
        lister.execute(() -> {
            JSONObject all = new JSONObject();
            for (Folder.Entry system : folder.list("roms")) {
                if (!system.folder || system.name.startsWith(".")) continue;
                JSONArray found = new JSONArray();
                list(folder, "roms/" + system.name, "", 0, found);
                try { all.put(system.name, found); } catch (org.json.JSONException e) { /* not a name JSON takes */ }
            }
            String listed = all.toString();
            synchronized (roms) {
                roms.clear();
                if (listed.equals(allRoms)) return;
                allRoms = listed;
                try (java.io.OutputStream out = new java.io.FileOutputStream(romsFile())) {
                    out.write(listed.getBytes(java.nio.charset.StandardCharsets.UTF_8));
                } catch (java.io.IOException e) { /* listed again next time */ }
            }
            runOnUiThread(() -> {
                if (!isFinishing() && !isDestroyed()) web.evaluateJavascript("window.dispatchEvent(new Event('retromanager:phone-roms'))", null);
            });
        });
    }

    // --- What Player shows ---

    // --- Asking and telling ---
    // Every question, message and progress box is drawn by the page when one of
    // RetroManager's is showing (window.RMDialog, in common/header.js), so it has
    // the page's colours. When none is (setting up, or a page that couldn't be
    // reached), the phone's own boxes are used.

    private interface Answer {
        /** `index`: the option, or 0 for the main button and 1 for the other one; -1 if it was put away. */
        void answer(int index, String text);
    }

    private final Map<String, Answer> asked = new HashMap<>();
    private int dialogs;

    /** Shows a question (UI thread): {kind: "choose" | "confirm" | "alert" | "input", title, message,
     *  options, yes, other, cancel (false: it can't be put away), value, hint}. */
    private void ask(JSONObject spec, Answer answer) {
        if (isFinishing() || isDestroyed()) {
            answer.answer(-1, null);
            return;
        }
        String id = String.valueOf(++dialogs);
        try {
            spec.put("id", id);
        } catch (org.json.JSONException e) {
            answer.answer(-1, null);
            return;
        }
        asked.put(id, answer);
        web.evaluateJavascript("!!(window.RMDialog && window.RMDialog.show(" + spec + "))", shown -> {
            if ("true".equals(shown)) return;
            if (asked.remove(id) != null) askHere(spec, answer);
        });
    }

    /** The page's questions are put away when it goes (their answers would never come). */
    private void forgetAsked() {
        List<Answer> waiting = new ArrayList<>(asked.values());
        asked.clear();
        for (Answer answer : waiting) answer.answer(-1, null);
        progressOn = 0;
    }

    /** The same question in one of the phone's own boxes. */
    private void askHere(JSONObject spec, Answer answer) {
        if (isFinishing() || isDestroyed()) {
            answer.answer(-1, null);
            return;
        }
        boolean[] done = {false};
        Answer once = (index, text) -> {
            if (done[0]) return;
            done[0] = true;
            answer.answer(index, text);
        };
        String kind = spec.optString("kind");
        AlertDialog.Builder box = new AlertDialog.Builder(this).setTitle(spec.optString("title"));
        if (!spec.optString("message").isEmpty()) box.setMessage(spec.optString("message"));
        boolean cancel = spec.optBoolean("cancel", true);
        box.setCancelable(cancel);
        EditText typed = null;
        if (kind.equals("choose")) {
            JSONArray options = spec.optJSONArray("options");
            String[] labels = new String[options == null ? 0 : options.length()];
            for (int i = 0; i < labels.length; i++) labels[i] = options.optString(i);
            box.setMessage(null).setItems(labels, (dialog, which) -> once.answer(which, null));
        } else if (kind.equals("input")) {
            typed = new EditText(this);
            typed.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
            typed.setHint(spec.optString("hint"));
            typed.setText(spec.optString("value"));
            typed.setSelection(typed.getText().length());
            FrameLayout frame = new FrameLayout(this);
            int pad = (int) (20 * getResources().getDisplayMetrics().density);
            frame.setPadding(pad, pad / 2, pad, 0);
            frame.addView(typed);
            box.setView(frame);
        }
        EditText field = typed;
        if (!kind.equals("choose")) box.setPositiveButton(spec.optString("yes", "OK"), (dialog, which) -> once.answer(0, field == null ? null : field.getText().toString()));
        if (!spec.optString("other").isEmpty()) box.setNeutralButton(spec.optString("other"), (dialog, which) -> once.answer(1, field == null ? null : field.getText().toString()));
        if (cancel && !kind.equals("alert")) box.setNegativeButton("Cancel", null);
        box.setOnDismissListener(dialog -> once.answer(-1, null));
        box.show();
    }

    private static JSONObject spec(String kind, String title, String message) {
        try {
            return new JSONObject().put("kind", kind).put("title", title).put("message", message == null ? "" : message);
        } catch (org.json.JSONException e) {
            throw new IllegalStateException(e);
        }
    }

    // The "fetching" box: 0 not up, 1 the page's, 2 the phone's own, 3 asking the page whether it can
    private int progressOn;
    private String progressNow;
    private long progressDone, progressTotal;

    /** The "fetching" box: its text and how far along it is (no text: put it away). */
    void progress(String text, long done, long total) {
        runOnUiThread(() -> {
            if (isFinishing() || isDestroyed()) return;
            progressNow = text;
            progressDone = done;
            progressTotal = total;
            if (text == null) {
                if (progressOn == 1) web.evaluateJavascript("window.RMDialog && window.RMDialog.progress(null)", null);
                if (progress != null) progress.dismiss();
                progress = null;
                if (progressOn != 3) progressOn = 0;
                return;
            }
            if (progressOn == 0) {
                progressOn = 3;
                web.evaluateJavascript("!!(window.RMDialog && window.RMDialog.progress(" + progressSpec() + "))", shown -> {
                    progressOn = "true".equals(shown) ? 1 : 2;
                    // (it may have finished, or moved on, while the page was asked)
                    progress(progressNow, progressDone, progressTotal);
                });
            } else if (progressOn == 1) {
                web.evaluateJavascript("window.RMDialog && window.RMDialog.progress(" + progressSpec() + ")", null);
            } else if (progressOn == 2) {
                progressHere(text, done, total);
            }
        });
    }

    private String progressSpec() {
        try {
            return new JSONObject().put("text", progressNow).put("done", progressDone).put("total", progressTotal)
                    .put("amount", progressTotal > 0 ? Player.size(progressDone) + " of " + Player.size(progressTotal) : "").toString();
        } catch (org.json.JSONException e) {
            return "null";
        }
    }

    private void progressHere(String text, long done, long total) {
        if (progress == null) {
            LinearLayout box = new LinearLayout(this);
            box.setOrientation(LinearLayout.VERTICAL);
            int pad = (int) (22 * getResources().getDisplayMetrics().density);
            box.setPadding(pad, pad, pad, pad / 2);
            progressText = new TextView(this);
            progressText.setTextSize(15);
            progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
            progressBar.setMax(1000);
            box.addView(progressText);
            LinearLayout.LayoutParams below = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            below.topMargin = pad / 2;
            box.addView(progressBar, below);
            progress = new AlertDialog.Builder(this).setView(box).setCancelable(false)
                    .setNegativeButton("Cancel", (dialog, which) -> player.cancel()).create();
            progress.show();
        }
        progressText.setText(total > 0 ? text + "\n" + Player.size(done) + " of " + Player.size(total) : text);
        progressBar.setIndeterminate(total <= 0);
        if (total > 0) progressBar.setProgress((int) (done * 1000 / total));
    }

    void alert(String title, String message) {
        runOnUiThread(() -> ask(spec("alert", title, message), (index, text) -> { }));
    }

    void say(String message) {
        runOnUiThread(() -> Toast.makeText(this, message, Toast.LENGTH_LONG).show());
    }

    /** Asks the person to pick one (from Player's own thread, which waits): its place in the list, or -1. */
    int choose(String title, String[] options) {
        int[] picked = {-1};
        CountDownLatch answered = new CountDownLatch(1);
        runOnUiThread(() -> {
            try {
                ask(spec("choose", title, null).put("options", new JSONArray(java.util.Arrays.asList(options))), (index, text) -> {
                    picked[0] = index;
                    answered.countDown();
                });
            } catch (org.json.JSONException e) {
                answered.countDown();
            }
        });
        try {
            answered.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        return picked[0];
    }

    /** Asks yes or no (from Player's own thread, which waits). */
    boolean confirm(String title, String message, String yes) {
        boolean[] agreed = {false};
        CountDownLatch answered = new CountDownLatch(1);
        runOnUiThread(() -> {
            try {
                ask(spec("confirm", title, message).put("yes", yes), (index, text) -> {
                    agreed[0] = index == 0;
                    answered.countDown();
                });
            } catch (org.json.JSONException e) {
                answered.countDown();
            }
        });
        try {
            answered.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        return agreed[0];
    }

    /** While games are being fetched, a notification keeps the app going when it isn't in front (FetchService). */
    void fetching(boolean on) {
        runOnUiThread(() -> {
            if (on == fetching) return;
            fetching = on;
            try {
                Intent service = new Intent(this, FetchService.class);
                if (!on) {
                    stopService(service);
                    return;
                }
                if (android.os.Build.VERSION.SDK_INT >= 33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != android.content.pm.PackageManager.PERMISSION_GRANTED)
                    requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 2);
                startForegroundService(service);
            } catch (Exception e) {
                // The fetch goes on all the same, while the app is in front
                android.util.Log.w("RetroManager", "No notification for the fetch", e);
            }
        });
    }

    /** What's in the phone's roms folder, system by system, with how much room it takes. */
    private void storage() {
        Folder folder = this.folder;
        if (folder == null) return;
        say("Looking through the roms folder…");
        new Thread(() -> {
            List<String> names = new ArrayList<>(), labels = new ArrayList<>();
            List<List<Object[]>> all = new ArrayList<>();
            long total = 0;
            for (Folder.Entry system : folder.list("roms")) {
                if (!system.folder || system.name.startsWith(".")) continue;
                List<Object[]> files = new ArrayList<>();
                sizes(folder, "roms/" + system.name, "", 0, files);
                if (files.isEmpty()) continue;
                long size = 0;
                for (Object[] file : files) size += (Long) file[1];
                total += size;
                files.sort((a, b) -> Long.compare((Long) b[1], (Long) a[1]));
                names.add(system.name);
                all.add(files);
                String label = player.systemEntry(system.name).optString("label", system.name);
                labels.add(label + ": " + files.size() + (files.size() == 1 ? " file, " : " files, ") + Player.size(size));
            }
            String free;
            try {
                free = ", " + Player.size(new android.os.StatFs(folder.path()).getAvailableBytes()) + " free";
            } catch (Exception e) {
                free = "";
            }
            String title = "On this phone: " + Player.size(total) + free;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                new AlertDialog.Builder(this).setTitle(title).setItems(labels.toArray(new String[0]), (dialog, which) -> {
                    List<Object[]> files = all.get(which);
                    String[] rows = new String[Math.min(files.size(), 300)];
                    for (int i = 0; i < rows.length; i++) rows[i] = Player.size((Long) files.get(i)[1]) + "  " + files.get(i)[0];
                    // (largest first; pressing one offers to take that game off the phone)
                    new AlertDialog.Builder(this).setTitle(labels.get(which)).setItems(rows, (d, row) -> {
                        String path = (String) files.get(row)[0];
                        player.remove(names.get(which), path.substring(path.lastIndexOf('/') + 1), path);
                    }).setPositiveButton("Close", null).show();
                }).setPositiveButton("Close", null).show();
            });
        }).start();
    }

    private static void sizes(Folder folder, String base, String inside, int depth, List<Object[]> found) {
        for (Folder.Entry entry : folder.list(inside.isEmpty() ? base : base + "/" + inside)) {
            String path = inside.isEmpty() ? entry.name : inside + "/" + entry.name;
            if (entry.name.startsWith(".")) continue;
            if (!entry.folder) found.add(new Object[]{path, entry.size});
            else if (depth < 3) sizes(folder, base, path, depth + 1, found);
        }
    }

    private long version() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).getLongVersionCode();
        } catch (Exception e) {
            return 0;
        }
    }

    /** Whether RetroManager has a newer build of this app (android/build.sh puts
     *  it there, with its number in /app/version.json): says so once for each,
     *  or every time when asked (`asked`). */
    private void checkUpdate(boolean asked) {
        String server = prefs.server();
        if (server == null) return;
        new Thread(() -> {
            long newest = 0;
            String name = "";
            try {
                HttpURLConnection connection = (HttpURLConnection) new URL(server + "/app/version.json").openConnection();
                connection.setConnectTimeout(4000);
                connection.setReadTimeout(4000);
                if (connection.getResponseCode() == 200) {
                    try (java.io.InputStream in = connection.getInputStream()) {
                        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
                        OfflineCache.copy(in, out);
                        JSONObject described = new JSONObject(out.toString("UTF-8"));
                        newest = described.optLong("code");
                        name = described.optString("name");
                    }
                }
                connection.disconnect();
            } catch (Exception e) {
                if (asked) say("RetroManager couldn't be asked.");
                return;
            }
            long found = newest;
            String called = name;
            if (found <= version()) {
                if (asked) say("This is the newest version.");
                return;
            }
            if (!asked && found == prefs.toldOf()) return;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                try {
                    ask(spec("confirm", "A newer version of this app is ready", "Version " + called + ". It downloads in the phone's browser: open it from there to install it over this one.").put("yes", "Get it"), (index, text) -> {
                        if (index == 0) start(new Intent(Intent.ACTION_VIEW, Uri.parse(server + "/app/RetroManager.apk")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                        else prefs.toldOf(found);
                    });
                } catch (org.json.JSONException e) {
                    // nothing to ask with
                }
            });
        }).start();
    }

    private static final String TAILSCALE = "com.tailscale.ipn";

    /** Whether RetroManager answers now (not from the main thread). */
    private boolean reachable() {
        String server = prefs.server();
        if (server == null) return false;
        try {
            HttpURLConnection connection = (HttpURLConnection) new URL(server + "/api/health").openConnection();
            connection.setConnectTimeout(3000);
            connection.setReadTimeout(3000);
            connection.getResponseCode();
            connection.disconnect();
            cache.reached(true);
            return true;
        } catch (Exception e) {
            cache.reached(false);
            return false;
        }
    }

    /** RetroManager is there again: the page is loaded afresh, since what's showing is the phone's kept copy. */
    private void backOnline(String message) {
        say(message);
        runOnUiThread(() -> {
            if (!isFinishing() && !isDestroyed()) web.reload();
        });
    }

    /** The home screen's game icons are pointed straight at RetroArch where they
     *  can be: one added before its game was on the phone, or before icons did
     *  that, opens the app until then. Each keeps its name and picture. */
    private void refreshShortcuts() {
        new Thread(() -> {
            try {
                ShortcutManager shortcuts = getSystemService(ShortcutManager.class);
                List<ShortcutInfo> changed = new ArrayList<>();
                for (ShortcutInfo pinned : shortcuts == null ? new ArrayList<ShortcutInfo>() : shortcuts.getPinnedShortcuts()) {
                    String id = pinned.getId();
                    int slash = id.indexOf('/');
                    if (!id.startsWith("game:") || slash < 0) continue;
                    Intent play = player.direct(id.substring(5, slash), id.substring(slash + 1));
                    if (play != null) changed.add(new ShortcutInfo.Builder(this, id).setIntent(play).build());
                }
                if (!changed.isEmpty()) shortcuts.updateShortcuts(changed);
            } catch (Exception e) {
                android.util.Log.w("RetroManager", "Couldn't bring the home screen's icons up to date", e);
            }
        }).start();
    }

    /** Starts another app: null if it started, else why it didn't. */
    String start(Intent intent) {
        try {
            startActivity(intent);
            return null;
        } catch (Exception e) {
            return e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
        }
    }

    // --- Setting up ---

    /** Asks for RetroManager's address: `problem` is what was wrong with `typed`, the last try. */
    private void askServer(String problem, String typed) {
        try {
            JSONObject spec = spec("input", "Where is RetroManager?", problem != null ? problem : "The address you open RetroManager at in a browser.")
                    .put("value", typed != null ? typed : prefs.server() == null ? "http://" : prefs.server()).put("hint", "http://192.168.1.10:5000")
                    .put("yes", "Connect").put("cancel", prefs.server() != null);
            if (problem != null) spec.put("other", "Use it anyway");
            ask(spec, (index, text) -> {
                if (index >= 0 && text != null) checkServer(text, index == 1);
            });
        } catch (org.json.JSONException e) {
            // nothing to ask with
        }
    }

    private void checkServer(String typed, boolean anyway) {
        String address = typed.trim();
        while (address.endsWith("/")) address = address.substring(0, address.length() - 1);
        if (!address.matches("(?i)^https?://.*")) address = "http://" + address;
        if (address.matches("(?i)^https?://$")) {
            askServer("Type the address first.", null);
            return;
        }
        String server = address;
        if (anyway) {
            useServer(server);
            return;
        }
        new Thread(() -> {
            String problem = null;
            try {
                HttpURLConnection connection = (HttpURLConnection) new URL(server + "/api/health").openConnection();
                connection.setConnectTimeout(5000);
                connection.setReadTimeout(5000);
                if (connection.getResponseCode() != 200) problem = "Something answered at " + server + ", but it doesn't look like RetroManager.";
                connection.disconnect();
            } catch (Exception e) {
                problem = "Nothing answered at " + server + " (" + e.getMessage() + "). Is the phone on the same network?";
            }
            String found = problem;
            runOnUiThread(() -> {
                if (isFinishing() || isDestroyed()) return;
                if (found == null) useServer(server);
                else askServer(found, server);
            });
        }).start();
    }

    private void useServer(String server) {
        if (!server.equals(prefs.server())) cache.clear();
        prefs.server(server);
        if (folder == null) askFolder();
        else open();
    }

    private void askFolder() {
        try {
            ask(spec("confirm", "Where is RetroArch's folder?", "Choose the RetroArch folder on this phone (usually \"RetroArch\" in the phone's storage). Games are kept in its roms folder, pictures in media, and RetroArch's own saves folder is used.\n\nOn the next screen, open that folder and press \"Use this folder\".")
                    .put("yes", "Choose").put("cancel", folder != null), (index, text) -> {
                if (index != 0) return;
                Intent pick = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
                pick.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
                pick.putExtra(DocumentsContract.EXTRA_INITIAL_URI, DocumentsContract.buildDocumentUri(Folder.STORAGE, "primary:RetroArch"));
                try {
                    startActivityForResult(pick, PICK_FOLDER);
                } catch (Exception e) {
                    alert("No folder picker", "This phone has nothing to choose a folder with.");
                }
            });
        } catch (org.json.JSONException e) {
            // nothing to ask with
        }
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == PICK_FILES) {
            List<Uri> files = result == RESULT_OK && data != null ? shared(data) : new ArrayList<>();
            if (picking != null) picking.onReceiveValue(files.isEmpty() ? null : files.toArray(new Uri[0]));
            picking = null;
            return;
        }
        if (request != PICK_FOLDER) return;
        Uri tree = result == RESULT_OK && data != null ? data.getData() : null;
        if (tree == null) {
            if (folder == null) askFolder();
            return;
        }
        if (!Folder.usable(tree)) {
            new AlertDialog.Builder(this).setTitle("Not that one")
                    .setMessage("RetroArch needs the folder to be on the phone's own storage or its SD card.")
                    .setPositiveButton("Choose again", (dialog, which) -> askFolder()).setCancelable(folder != null).show();
            return;
        }
        getContentResolver().takePersistableUriPermission(tree, Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
        prefs.tree(tree);
        folder = new Folder(this, tree);
        // (another folder's games aren't this one's)
        synchronized (roms) {
            roms.clear();
            allRoms = "{}";
        }
        if (prefs.server() == null) askServer(null, null);
        else open();
    }

    // --- This phone's settings (📱 in the page's header) ---

    private void settings() {
        if (isFinishing() || isDestroyed()) return;
        List<String> labels = new ArrayList<>();
        List<Runnable> actions = new ArrayList<>();
        labels.add("RetroManager: " + prefs.server());
        actions.add(() -> askServer(null, null));
        labels.add("RetroArch folder: " + (folder == null ? "not chosen" : folder.path()));
        actions.add(this::askFolder);
        List<String> installed = player.installed();
        labels.add("RetroArch app: " + (installed.isEmpty() ? "not installed" : player.retroArch()));
        actions.add(() -> {
            if (installed.isEmpty()) alert("RetroArch isn't installed", "Install RetroArch from retroarch.com, and its cores from inside it.");
            else new AlertDialog.Builder(this).setTitle("RetroArch app")
                    .setItems(installed.toArray(new String[0]), (dialog, which) -> prefs.retroArch(installed.get(which))).show();
        });
        JSONArray profiles = prefs.profiles();
        if (profiles.length() > 0) {
            String profile = prefs.profile();
            labels.add("Saves (with login off): " + (profile == null ? "asked at the first game" : profile.isEmpty() ? "stay on this phone" : profile + "'s"));
            actions.add(() -> {
                String[] options = new String[profiles.length() + 1];
                options[0] = "Nobody: saves stay on this phone";
                for (int i = 0; i < profiles.length(); i++) options[i + 1] = profiles.optString(i);
                new AlertDialog.Builder(this).setTitle("Whose saves does this phone play with?")
                        .setItems(options, (dialog, which) -> prefs.profile(which == 0 ? "" : options[which])).show();
            });
        }
        labels.add("Emulators…");
        actions.add(this::emulators);
        labels.add("Games on this phone…");
        actions.add(this::storage);
        labels.add("Forget the pages kept for offline (" + Player.size(cache.size()) + ")");
        actions.add(() -> {
            cache.clear();
            say("Forgotten. Pictures in the media folder stay.");
        });
        String mine;
        try {
            mine = getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception e) {
            mine = "?";
        }
        labels.add("App version " + mine + ": look for a newer one");
        actions.add(() -> checkUpdate(true));
        labels.add("Reload");
        actions.add(() -> {
            cache.reached(true);
            web.reload();
        });
        new AlertDialog.Builder(this).setTitle("This phone").setItems(labels.toArray(new String[0]), (dialog, which) -> actions.get(which).run())
                .setPositiveButton("Close", null).show();
    }

    /** What plays each system's games: RetroArch with one of its cores, or an emulator of its own. */
    private void emulators() {
        JSONArray systems = player.systems();
        if (systems.length() == 0) {
            alert("Emulators", "The list of systems comes from RetroManager, which hasn't been reached yet.");
            return;
        }
        Player.History history = player.new History(folder);
        String[] labels = new String[systems.length()];
        for (int i = 0; i < labels.length; i++) {
            JSONObject system = systems.optJSONObject(i);
            JSONObject plays = player.choose(history, system.optString("name"), null, Player.players(system));
            labels[i] = system.optString("label") + ": " + (plays == null ? "nothing yet" : plays.optString("name"))
                    + (plays != null && prefs.core(system.optString("name")) != null ? " (chosen)" : "");
        }
        new AlertDialog.Builder(this).setTitle("Emulators").setItems(labels, (dialog, which) -> emulators(systems.optJSONObject(which).optString("name"), null, null))
                .setPositiveButton("Close", null).show();
    }

    /** One system's, or with `rom` one game's own: everything that could play it,
     *  with what's known of each on this phone. */
    void emulators(String name) {
        emulators(name, null, null);
    }

    void emulators(String name, String rom, String title) {
        runOnUiThread(() -> {
            if (isFinishing() || isDestroyed()) return;
            JSONObject system = player.systemEntry(name);
            JSONArray players = Player.players(system);
            Player.History history = player.new History(folder);
            java.util.Set<String> failed = prefs.failed(name);
            // What's chosen is kept for the system, or for the one game
            String key = rom == null ? name : name + "/" + rom;
            List<String> labels = new ArrayList<>();
            List<Runnable> actions = new ArrayList<>();
            labels.add(rom == null ? "Automatic" : "As " + system.optString("label", name) + " is played");
            actions.add(() -> prefs.core(key, null));
            for (int i = 0; i < players.length(); i++) {
                JSONObject one = players.optJSONObject(i);
                if ("core".equals(one.optString("kind"))) {
                    String core = one.optString("core");
                    labels.add(one.optString("name") + (failed.contains(core) ? " (didn't start when tried)" : history.used(core) ? " (installed)" : ""));
                    actions.add(() -> {
                        prefs.failed(name, core, false);
                        prefs.core(key, one.optString("id"));
                    });
                } else if (player.has(one.optString("package"))) {
                    labels.add(one.optString("name") + " (installed; keeps its own saves)");
                    actions.add(() -> prefs.core(key, one.optString("id")));
                } else {
                    labels.add("Get " + one.optString("name") + " (not installed)");
                    actions.add(() -> start(new Intent(Intent.ACTION_VIEW, Uri.parse(one.optString("get"))).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)));
                }
            }
            labels.add("Another RetroArch core…");
            actions.add(() -> typeCore(name, key, title != null ? title : system.optString("label", name)));
            String chosen = prefs.core(key);
            try {
                ask(spec("choose", (title != null ? title : system.optString("label", name)) + (chosen == null ? "" : ": " + chosen.replace("retroarch:", "RetroArch: ").replace("app:", "")), null)
                        .put("options", new JSONArray(labels)), (index, text) -> {
                    if (index < 0) return;
                    actions.get(index).run();
                    // (the page marks the systems nothing plays)
                    tellPage();
                });
            } catch (org.json.JSONException e) {
                // nothing to ask with
            }
        });
    }

    private void typeCore(String name, String key, String label) {
        try {
            ask(spec("input", label, "The core's file name in RetroArch, without \"_libretro_android.so\".").put("hint", "snes9x").put("yes", "Use"), (index, text) -> {
                String core = index != 0 || text == null ? "" : text.trim().replace("_libretro_android.so", "");
                if (core.isEmpty()) return;
                prefs.failed(name, core, false);
                prefs.core(key, "retroarch:" + core);
                tellPage();
            });
        } catch (org.json.JSONException e) {
            // nothing to ask with
        }
    }

    /** Tells the page that what the phone has, or can play, may have changed. */
    void tellPage() {
        runOnUiThread(() -> {
            if (!isFinishing() && !isDestroyed()) web.evaluateJavascript("window.dispatchEvent(new Event('retromanager:phone-roms'))", null);
        });
    }
}
