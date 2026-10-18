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
    static final String PLAY = Recent.PLAY, PLAY_RECENT = "com.retromanager.phone.PLAY_RECENT";
    // When the recent games (widget, app icon shortcuts) were last asked for
    long recentAt;
    static final String VERSION = "1.0";

    Prefs prefs;
    OfflineCache cache;
    Player player;
    Setup setup;
    Updater updater;
    final Share share = new Share(this);
    final PhoneSettings phone = new PhoneSettings(this);
    WebView web;
    volatile Folder folder;
    private AlertDialog progress;
    private TextView progressText;
    private ProgressBar progressBar;
    // Each system's game files on the phone, as the page was last told (see RMApp.localRoms)
    final Map<String, String> roms = new HashMap<>();
    String allRoms;
    private boolean fetching;
    private final java.util.concurrent.ExecutorService lister = java.util.concurrent.Executors.newSingleThreadExecutor();
    volatile long probed;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = new Prefs(this);
        cache = new OfflineCache(this);
        player = new Player(this, prefs, cache);
        updater = new Updater(this);
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
        web.addJavascriptInterface(new Bridge(this), "RMApp");
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
            share.sharedToUs(getIntent());
        }
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        playFrom(intent);
        share.sharedToUs(intent);
    }

    /** A game's icon on the home screen was pressed (see Bridge.pin): the game starts. */
    private void playFrom(Intent intent) {
        if (intent == null || prefs.server() == null || folder == null) return;
        String system = intent.getStringExtra("system"), rom = intent.getStringExtra("rom");
        if (PLAY_RECENT.equals(intent.getAction())) {
            // The nth game played most recently (1: the last), as the widget has them
            int n = Math.max(1, intent.getIntExtra("n", 1));
            JSONObject game = Recent.kept(this).optJSONObject(n - 1);
            if (game == null) {
                say("There's no game " + n + " in the ones played recently.");
                intent.setAction(Intent.ACTION_MAIN);
                return;
            }
            system = game.optString("system");
            rom = game.optString("rom");
        } else if (!PLAY.equals(intent.getAction())) {
            return;
        }
        // (once: turning the phone, or coming back to the app, isn't pressing it again)
        intent.setAction(Intent.ACTION_MAIN);
        if (system != null && rom != null) player.play(system, rom);
    }

    /** A game's picture as a home screen icon: the whole picture in the middle,
     *  over itself filling the square and darkened, so no shape of icon cuts into it. */
    Icon icon(String picture) {
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
        player.launcher.checkLaunch();
        player.sendSaves();
        // (and the roms folder may have changed meanwhile: something else may keep it in step)
        romsChanged();
        // Back from allowing RetroManager to install apps: the update goes on
        updater.resumed();
        // The widget's and app icon's recent games: back from a game, they may have changed
        // (not more than once a minute: this happens each time the app comes back)
        if (prefs.server() != null && System.currentTimeMillis() - recentAt > 60_000) {
            recentAt = System.currentTimeMillis();
            new Thread(() -> Recent.refresh(this)).start();
        }
    }

    @Override protected void onPause() {
        pads.stop();
        web.onPause();
        CookieManager.getInstance().flush();
        super.onPause();
    }

    @Override protected void onDestroy() {
        if (progress != null) progress.dismiss();
        web.destroy();
        super.onDestroy();
    }

    // --- A controller: Pad.java passes its presses to the page ---

    private final Pad pads = new Pad(this);

    @Override public boolean dispatchKeyEvent(android.view.KeyEvent event) {
        return pads.key(event) || super.dispatchKeyEvent(event);
    }

    @Override public boolean dispatchGenericMotionEvent(android.view.MotionEvent event) {
        return pads.motion(event) || super.dispatchGenericMotionEvent(event);
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
            new Thread(() -> player.claim(here, prefs.unclaimed(), true)).start();
        }
        player.refreshCores();
        updater.checkUpdate(false);
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

    // (What the page can ask for: Bridge.java)


    static void list(Folder folder, String base, String inside, int depth, JSONArray found) {
        for (Folder.Entry entry : folder.list(inside.isEmpty() ? base : base + "/" + inside)) {
            String path = inside.isEmpty() ? entry.name : inside + "/" + entry.name;
            if (!entry.folder) found.put(path);
            else if (depth < 3) list(folder, base, path, depth + 1, found);
        }
    }

    java.io.File romsFile() {
        return new java.io.File(getFilesDir(), "roms.json");
    }

    /** The roms folder may have changed (a game arrived, or the app came back):
     *  its files are listed again, off the page's own thread since a big folder
     *  takes a moment, and the page is told if the list is a different one. */
    /** How many cores are marked as not starting a game, on every system (Check this phone, and clearing them). */
    int failedCores() {
        JSONObject all = prefs.allFailed();
        int n = 0;
        for (java.util.Iterator<String> it = all.keys(); it.hasNext(); ) {
            JSONArray cores = all.optJSONArray(it.next());
            n += cores == null ? 0 : cores.length();
        }
        return n;
    }

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

    interface Answer {
        /** `index`: the option, or 0 for the main button and 1 for the other one; -1 if it was put away. */
        void answer(int index, String text);
    }

    final Map<String, Answer> asked = new HashMap<>();
    private int dialogs;

    /** Shows a question (UI thread): {kind: "choose" | "confirm" | "alert" | "input", title, message,
     *  options, yes, other, cancel (false: it can't be put away), value, hint}. */
    void ask(JSONObject spec, Answer answer) {
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

    static JSONObject spec(String kind, String title, String message) {
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
        return choose(title, null, options);
    }

    /** The same, with a line saying what the choice does. */
    int choose(String title, String message, String[] options) {
        int[] picked = {-1};
        CountDownLatch answered = new CountDownLatch(1);
        runOnUiThread(() -> {
            try {
                ask(spec("choose", title, message).put("options", new JSONArray(java.util.Arrays.asList(options))), (index, text) -> {
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

    static final String TAILSCALE = "com.tailscale.ipn";

    /** Whether RetroManager answers now (not from the main thread). */
    boolean reachable() {
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
    void backOnline(String message) {
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
                    Intent play = player.launcher.direct(id.substring(5, slash), id.substring(slash + 1));
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
    void askServer(String problem, String typed) {
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

    void askFolder() {
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
            List<Uri> files = result == RESULT_OK && data != null ? Share.shared(data) : new ArrayList<>();
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

    /** Tells the page that what the phone has, or can play, may have changed. */
    void tellPage() {
        runOnUiThread(() -> {
            if (!isFinishing() && !isDestroyed()) web.evaluateJavascript("window.dispatchEvent(new Event('retromanager:phone-roms'))", null);
        });
    }
}
