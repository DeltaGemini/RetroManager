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

/** What the page can ask of the app (window.RMApp in frontend/common/header.js): playing and
 *  fetching games, the phone's settings, what's on the phone, and so on. MainActivity puts it
 *  on the page; the work is done there. */
final class Bridge {
    private final MainActivity app;

    Bridge(MainActivity app) {
        this.app = app;
    }

    /** Starts a game in RetroArch, fetching it first if the phone hasn't got it. */
    /** The page says who's signed in, each time it loads: someone else, and the
     *  widget and app icon's games played last are theirs at once. */
    @JavascriptInterface public void signedIn(String person) {
        String now = person == null ? "" : person;
        if (now.equals(app.prefs.recentFor())) return;
        app.prefs.recentFor(now);
        app.recentAt = System.currentTimeMillis();
        new Thread(() -> Recent.refresh(app)).start();
    }

    @JavascriptInterface public void play(String system, String rom) {
        if (system == null || rom == null || system.contains("/") || system.startsWith(".")) return;
        app.player.play(system, rom);
    }

    /** The answer to a question the page drew for the app (window.RMDialog): the option's
     *  place, 0 or 1 for a button, or -1 for "put away"; and what was typed, if it asked. */
    @JavascriptInterface public void dialogAnswer(String id, int index, String text) {
        app.runOnUiThread(() -> {
            MainActivity.Answer answer = app.asked.remove(id);
            if (answer != null) answer.answer(index, text);
        });
    }

    /** Cancel, pressed on the page's "fetching" box. */
    @JavascriptInterface public void cancelFetch() {
        app.player.cancel();
    }

    // --- The page's own "This phone" panel (common/header.js) ---

    /** What the panel shows: {server, folder, retroArch, retroArchs, profile, profiles, kept, version}. */
    @JavascriptInterface public String settingsInfo() {
        try {
            String mine;
            try {
                mine = app.getPackageManager().getPackageInfo(app.getPackageName(), 0).versionName;
            } catch (Exception e) {
                mine = "?";
            }
            return new JSONObject().put("server", app.prefs.server()).put("folder", app.folder == null ? JSONObject.NULL : app.folder.path())
                    .put("retroArch", app.player.retroArch() == null ? JSONObject.NULL : app.player.retroArch()).put("retroArchs", new JSONArray(app.player.installed()))
                    .put("profile", app.prefs.profile() == null ? JSONObject.NULL : app.prefs.profile()).put("profiles", app.prefs.profiles())
                    .put("kept", Player.size(app.cache.size())).put("version", mine).put("pinSaves", app.prefs.pinSaves()).put("updateGames", app.prefs.updateGames()).put("failedCores", app.failedCores())
                    .put("unclaimed", app.prefs.unclaimed() == null ? JSONObject.NULL : app.prefs.unclaimed())
                    .put("claimUndo", app.prefs.claimUndo() == null ? JSONObject.NULL : new JSONObject()
                            .put("person", app.prefs.claimUndo().optString("person")).put("games", app.prefs.claimUndo().optInt("games"))
                            .put("at", app.prefs.claimUndo().optLong("at"))).toString();
        } catch (org.json.JSONException e) {
            return "{}";
        }
    }

    /** One of the panel's actions: "server", "folder", "retroarch" (value: the app), "profile" (value: the
     *  name, or "" for nobody), "forget", "update", "reload", "open" (value: an address, for the browser). */
    @JavascriptInterface public void setting(String what, String value) {
        app.runOnUiThread(() -> {
            if (app.isFinishing() || app.isDestroyed() || what == null) return;
            switch (what) {
                case "server": app.askServer(null, null); break;
                case "folder": app.askFolder(); break;
                case "retroarch": if (app.player.installed().contains(value)) app.prefs.retroArch(value); break;
                case "profile": app.prefs.profile(value == null ? "" : value); break;
                case "unclaimed":
                    // (choosing the one already chosen does nothing; another asks first)
                    if (value == null || value.isEmpty() || value.equals(app.prefs.unclaimed())) break;
                    new Thread(() -> {
                        int others = app.player.claim(app.folder(), value, false);
                        String[] options = others > 0
                                ? new String[]{"Just the unsorted ones", "Also take over the " + others + " game" + (others == 1 ? "" : "s") + " noted as someone else's"}
                                : new String[]{"Make it " + value};
                        int picked = app.choose("Unsorted saves are " + value + "'s?",
                                "Saves on this phone that RetroManager hasn't sorted out yet (the ones that were here before the app) will count as " + value + "'s."
                                        + (others > 0 ? " " + others + " game" + (others == 1 ? "'s save is" : "s' saves are") + " noted as someone else's: they stay theirs, unless you take them over too." : ""),
                                options);
                        if (picked < 0) { app.tellPage(); return; }
                        app.prefs.unclaimed(value);
                        if (picked == 1) {
                            int taken = app.player.claim(app.folder(), value, true);
                            app.say(taken + " game" + (taken == 1 ? "'s save" : "s' saves") + " on this phone are now " + value + "'s. Undo it in these settings if that was a slip.");
                        } else {
                            app.say("Unsorted saves are " + value + "'s. Nobody else's were touched.");
                        }
                        app.tellPage();
                    }).start();
                    break;
                case "undo-claim":
                    new Thread(() -> {
                        JSONObject undo = app.prefs.claimUndo();
                        if (undo == null || !app.confirm("Undo taking over saves?", "The " + undo.optInt("games") + " games' saves taken to be "
                                + undo.optString("person") + "'s go back to whose they were before.", "Undo it")) return;
                        int back = app.player.undoClaim();
                        app.say(back + " game" + (back == 1 ? "'s save" : "s' saves") + " back to whose they were.");
                        app.tellPage();
                    }).start();
                    break;
                case "forget":
                    try {
                        app.ask(app.spec("confirm", "Forget the pages kept for offline?", "The pages and game lists kept for when there's no connection are forgotten, and kept again as they're opened. Pictures in the media folder stay.").put("yes", "Forget"), (index, text) -> {
                            if (index != 0) return;
                            app.cache.clear();
                            app.say("Forgotten.");
                            app.tellPage();
                        });
                    } catch (org.json.JSONException e) {
                        // nothing to ask with
                    }
                    break;
                case "update": app.checkUpdate(true); break;
                // RetroArch's setup (Setup.java): "save" this phone's, "apply" the kept one, "check", and "pin" (value: on or off)
                case "setup-save": app.setup.save(); break;
                case "setup-apply": app.setup.apply(); break;
                case "setup-check": app.setup.check(); break;
                case "setup-pin": app.prefs.pinSaves("on".equals(value)); break;
                case "update-games": app.prefs.updateGames("on".equals(value)); break;
                case "clear-failed": app.prefs.clearFailed(); app.romsChanged(); app.say("Every core will be tried again"); break;
                case "sync-states": app.player.syncAllStates(); break;
                case "reload":
                    app.cache.reached(true);
                    app.web.reload();
                    break;
                case "open":
                    if (value != null && value.matches("(?i)^https?://.*")) app.start(new Intent(Intent.ACTION_VIEW, Uri.parse(value)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                    break;
                default: break;
            }
            app.tellPage();
        });
    }

    /** What plays each system, for the panel: [{name, label, plays, chosen, options: [{id, label, note, get}]}]. */
    @JavascriptInterface public String emulatorsInfo() {
        JSONArray out = new JSONArray(), systems = app.player.systems();
        History history = new History(app.folder);
        try {
            for (int i = 0; i < systems.length(); i++) {
                JSONObject system = systems.optJSONObject(i);
                String name = system.optString("name");
                JSONArray players = Player.players(system), options = new JSONArray();
                java.util.Set<String> failed = app.prefs.failed(name);
                for (int j = 0; j < players.length(); j++) {
                    JSONObject one = players.optJSONObject(j);
                    JSONObject option = new JSONObject().put("id", one.optString("id")).put("label", one.optString("name"));
                    if ("core".equals(one.optString("kind"))) {
                        option.put("note", failed.contains(one.optString("core")) ? "didn't start when tried" : history.used(one.optString("core")) ? "installed" : "");
                    } else if (app.player.has(one.optString("package"))) {
                        option.put("note", "installed · keeps its own saves");
                    } else {
                        option.put("note", "not installed").put("get", one.optString("get"));
                    }
                    options.put(option);
                }
                JSONObject plays = app.player.choose(history, name, null, players);
                out.put(new JSONObject().put("name", name).put("label", system.optString("label", name))
                        .put("plays", plays == null ? JSONObject.NULL : plays.optString("name"))
                        .put("chosen", app.prefs.core(name) == null ? JSONObject.NULL : app.prefs.core(name)).put("options", options));
            }
        } catch (org.json.JSONException e) {
            // as far as it got
        }
        return out.toString();
    }

    /** What a system is played with: a player's id, "retroarch:<core>" for one typed in, or "" to let the app choose. */
    @JavascriptInterface public void setEmulator(String system, String id) {
        if (system == null || system.contains("/")) return;
        if (id != null && id.startsWith("retroarch:")) app.prefs.failed(system, id.substring("retroarch:".length()), false);
        app.prefs.core(system, id == null || id.isEmpty() ? null : id);
        app.tellPage();
    }

    /** Looks through the roms folder for the panel, which is sent the answer when it's ready
     *  ("retromanager:phone-storage": {total, free, systems: [{name, label, size, files: [[path, size]]}]}). */
    @JavascriptInterface public void scanStorage() {
        Folder folder = app.folder;
        if (folder == null) return;
        new Thread(() -> {
            try {
                JSONArray systems = new JSONArray();
                long total = 0;
                for (Folder.Entry system : folder.list("roms")) {
                    if (!system.folder || system.name.startsWith(".")) continue;
                    List<Object[]> files = new ArrayList<>();
                    app.sizes(folder, "roms/" + system.name, "", 0, files);
                    if (files.isEmpty()) continue;
                    files.sort((a, b) -> Long.compare((Long) b[1], (Long) a[1]));
                    long size = 0;
                    JSONArray listed = new JSONArray();
                    for (Object[] file : files) {
                        size += (Long) file[1];
                        if (listed.length() < 400) listed.put(new JSONArray().put(file[0]).put(Player.size((Long) file[1])));
                    }
                    total += size;
                    systems.put(new JSONObject().put("name", system.name).put("label", app.player.systemEntry(system.name).optString("label", system.name))
                            .put("count", files.size()).put("size", Player.size(size)).put("bytes", size).put("files", listed));
                }
                String free;
                try {
                    free = Player.size(new android.os.StatFs(folder.path()).getAvailableBytes());
                } catch (Exception e) {
                    free = "";
                }
                String found = new JSONObject().put("total", Player.size(total)).put("free", free).put("systems", systems).toString();
                app.runOnUiThread(() -> {
                    if (!app.isFinishing() && !app.isDestroyed())
                        app.web.evaluateJavascript("window.dispatchEvent(new CustomEvent('retromanager:phone-storage', { detail: " + found + " }))", null);
                });
            } catch (org.json.JSONException e) {
                // nothing to show
            }
        }).start();
    }

    /** Fetches a game to the phone without starting it. */
    @JavascriptInterface public void fetch(String system, String rom, String name) {
        if (system == null || rom == null || system.contains("/") || system.startsWith(".")) return;
        app.player.fetch(system, rom, name == null || name.isEmpty() ? rom : name);
    }

    /** Fetches several, after asking: a JSON list of [system, rom]. */
    @JavascriptInterface public void fetchAll(String games) {
        try {
            app.player.fetchAll(new JSONArray(games));
        } catch (org.json.JSONException e) {
            // nothing to fetch
        }
    }

    /** Asks what this one game is played with (over what its system is). */
    @JavascriptInterface public void chooseEmulator(String system, String rom, String name) {
        if (system == null || rom == null || system.contains("/") || system.startsWith(".")) return;
        app.emulators(system, rom.startsWith("./") ? rom.substring(2) : rom, name);
    }

    /** Takes a game off the phone (its files in the roms folder), after asking. The server's copy isn't touched. */
    @JavascriptInterface public void removeLocal(String system, String rom, String name) {
        if (system == null || rom == null || system.contains("/") || system.startsWith(".")) return;
        app.player.remove(system, name == null || name.isEmpty() ? rom : name, rom);
    }

    /** A system's game files on the phone: a JSON list of paths in its roms folder. */
    @JavascriptInterface public String localRoms(String system) {
        Folder folder = app.folder;
        if (folder == null || system == null || system.contains("/") || system.startsWith(".")) return "[]";
        synchronized (app.roms) {
            String listed = app.roms.get(system);
            if (listed == null) {
                JSONArray found = new JSONArray();
                app.list(folder, "roms/" + system, "", 0, found);
                listed = found.toString();
                app.roms.put(system, listed);
            }
            return listed;
        }
    }

    /** Every system's game files on the phone: a JSON object of system folder -> paths in it.
     *  It's the list as last worked out, given at once; the page is told
     *  ("retromanager:phone-roms") when a fresh look finds it has changed. */
    @JavascriptInterface public String localSystems() {
        synchronized (app.roms) {
            if (app.allRoms == null) {
                try (java.io.InputStream in = new java.io.FileInputStream(app.romsFile())) {
                    java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
                    OfflineCache.copy(in, out);
                    app.allRoms = out.toString("UTF-8");
                } catch (java.io.IOException e) {
                    app.allRoms = "{}";
                }
            }
            return app.allRoms;
        }
    }

    /** The systems nothing on this phone plays yet: a JSON list of their folders. */
    @JavascriptInterface public String unplayable() {
        return app.player.unplayable();
    }

    /** Whether RetroManager can't be reached. The page asks every few seconds,
     *  which is also what has the server looked for again. */
    @JavascriptInterface public boolean offline() {
        long now = android.os.SystemClock.elapsedRealtime();
        String server = app.prefs.server();
        if (server != null && now - app.probed > 5000) {
            app.probed = now;
            new Thread(() -> {
                try {
                    HttpURLConnection connection = (HttpURLConnection) new URL(server + "/api/health").openConnection();
                    connection.setConnectTimeout(3000);
                    connection.setReadTimeout(3000);
                    connection.getResponseCode();
                    connection.disconnect();
                    app.cache.reached(true);
                } catch (Exception e) {
                    app.cache.reached(false);
                }
            }).start();
        }
        return app.cache.offline();
    }

    /** Puts a game on the phone's home screen, as an icon that starts it:
     *  `picture` is its media path ("snes/box2d/Game.png"), for the icon. */
    @JavascriptInterface public void pin(String system, String rom, String name, String picture) {
        if (system == null || rom == null || system.contains("/") || system.startsWith(".")) return;
        ShortcutManager shortcuts = app.getSystemService(ShortcutManager.class);
        if (shortcuts == null || !shortcuts.isRequestPinShortcutSupported()) {
            app.alert("Home screen", "This phone's home screen doesn't take icons from apps.");
            return;
        }
        new Thread(() -> {
            String label = name == null || name.isEmpty() ? rom : name;
            // Straight into RetroArch where that can be; otherwise through the app, which fetches the game or hands it to its emulator
            Intent play = app.player.direct(system, rom);
            if (play == null) play = new Intent(app, MainActivity.class).setAction(app.PLAY).putExtra("system", system).putExtra("rom", rom);
            ShortcutInfo shortcut = new ShortcutInfo.Builder(app, "game:" + system + "/" + rom)
                    .setShortLabel(label).setLongLabel(label).setIcon(app.icon(picture)).setIntent(play).build();
            try {
                // (the phone asks before it adds it)
                if (!shortcuts.requestPinShortcut(shortcut, null)) app.say("The home screen wouldn't take it.");
            } catch (Exception e) {
                app.say("Couldn't add it: " + e.getMessage());
            }
        }).start();
    }

    /** "Offline", pressed: looks for RetroManager again now. If it still isn't there, offers
     *  to start Tailscale, which is how it's reached away from home. */
    @JavascriptInterface public void checkOnline() {
        new Thread(() -> {
            if (app.reachable()) {
                app.backOnline("RetroManager is back.");
                return;
            }
            boolean tailscale = app.player.has(app.TAILSCALE);
            app.runOnUiThread(() -> {
                try {
                    JSONObject spec = app.spec("confirm", "RetroManager still can't be reached",
                            tailscale ? "Away from home it's reached over Tailscale, which may be off. Start it?"
                                    : "The phone isn't on RetroManager's network. Away from home it needs a VPN to it, such as Tailscale.")
                            .put("yes", tailscale ? "Start Tailscale" : "OK");
                    if (tailscale) spec.put("other", "Open Tailscale");
                    app.ask(spec, (index, text) -> {
                        if (!tailscale || index < 0) return;
                        if (index == 1) {
                            Intent open = app.getPackageManager().getLaunchIntentForPackage(app.TAILSCALE);
                            if (open != null) app.start(open);
                            return;
                        }
                        // Tailscale connects when it's sent this (it's how other apps switch it on)
                        try {
                            app.sendBroadcast(new Intent(app.TAILSCALE + ".CONNECT_VPN").setClassName(app.TAILSCALE, app.TAILSCALE + ".IPNReceiver"));
                        } catch (Exception e) {
                            app.say("Tailscale couldn't be started from here: open it instead.");
                            return;
                        }
                        app.say("Starting Tailscale…");
                        new Thread(() -> {
                            // (it takes a few seconds to come up)
                            for (int tries = 0; tries < 6; tries++) {
                                try { Thread.sleep(2500); } catch (InterruptedException e) { return; }
                                if (app.reachable()) {
                                    app.backOnline("Connected: RetroManager is back.");
                                    return;
                                }
                            }
                            app.say("Still no RetroManager. Open Tailscale to see whether it connected.");
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
        String server = app.prefs.server();
        if (server == null) return;
        String problem = app.start(new Intent(Intent.ACTION_VIEW, Uri.parse(server + "/")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        if (problem != null) app.say("No browser opened: " + problem);
    }

    @JavascriptInterface public String version() {
        return app.VERSION;
    }

    @JavascriptInterface public void openSettings() {
        app.runOnUiThread(app::settings);
    }
}
