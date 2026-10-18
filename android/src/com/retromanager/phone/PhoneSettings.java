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

/** This phone's settings (📱 in the page's header): what's set, the emulators for each system, and
 *  what's in the phone's roms folder. */
final class PhoneSettings {
    private final MainActivity app;

    PhoneSettings(MainActivity app) { this.app = app; }

    /** What's in the phone's roms folder, system by system, with how much room it takes. */
    private void storage() {
        Folder folder = app.folder;
        if (folder == null) return;
        app.say("Looking through the roms folder…");
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
                String label = app.player.systemEntry(system.name).optString("label", system.name);
                labels.add(label + ": " + files.size() + (files.size() == 1 ? " file, " : " files, ") + Player.size(size));
            }
            String free;
            try {
                free = ", " + Player.size(new android.os.StatFs(folder.path()).getAvailableBytes()) + " free";
            } catch (Exception e) {
                free = "";
            }
            String title = "On this phone: " + Player.size(total) + free;
            app.runOnUiThread(() -> {
                if (app.isFinishing() || app.isDestroyed()) return;
                new AlertDialog.Builder(app).setTitle(title).setItems(labels.toArray(new String[0]), (dialog, which) -> {
                    List<Object[]> files = all.get(which);
                    String[] rows = new String[Math.min(files.size(), 300)];
                    for (int i = 0; i < rows.length; i++) rows[i] = Player.size((Long) files.get(i)[1]) + "  " + files.get(i)[0];
                    // (largest first; pressing one offers to take that game off the phone)
                    new AlertDialog.Builder(app).setTitle(labels.get(which)).setItems(rows, (d, row) -> {
                        String path = (String) files.get(row)[0];
                        app.player.remove(names.get(which), path.substring(path.lastIndexOf('/') + 1), path);
                    }).setPositiveButton("Close", null).show();
                }).setPositiveButton("Close", null).show();
            });
        }).start();
    }

    static void sizes(Folder folder, String base, String inside, int depth, List<Object[]> found) {
        for (Folder.Entry entry : folder.list(inside.isEmpty() ? base : base + "/" + inside)) {
            String path = inside.isEmpty() ? entry.name : inside + "/" + entry.name;
            if (entry.name.startsWith(".")) continue;
            if (!entry.folder) found.add(new Object[]{path, entry.size});
            else if (depth < 3) sizes(folder, base, path, depth + 1, found);
        }
    }


    void settings() {
        if (app.isFinishing() || app.isDestroyed()) return;
        List<String> labels = new ArrayList<>();
        List<Runnable> actions = new ArrayList<>();
        labels.add("RetroManager: " + app.prefs.server());
        actions.add(() -> app.askServer(null, null));
        labels.add("RetroArch folder: " + (app.folder == null ? "not chosen" : app.folder.path()));
        actions.add(app::askFolder);
        List<String> installed = app.player.launcher.installed();
        labels.add("RetroArch app: " + (installed.isEmpty() ? "not installed" : app.player.launcher.retroArch()));
        actions.add(() -> {
            if (installed.isEmpty()) app.alert("RetroArch isn't installed", "Install RetroArch from retroarch.com, and its cores from inside it.");
            else new AlertDialog.Builder(app).setTitle("RetroArch app")
                    .setItems(installed.toArray(new String[0]), (dialog, which) -> app.prefs.retroArch(installed.get(which))).show();
        });
        JSONArray profiles = app.prefs.profiles();
        if (profiles.length() > 0) {
            String profile = app.prefs.profile();
            labels.add("Saves (with login off): " + (profile == null ? "asked at the first game" : profile.isEmpty() ? "stay on this phone" : profile + "'s"));
            actions.add(() -> {
                String[] options = new String[profiles.length() + 1];
                options[0] = "Nobody: saves stay on this phone";
                for (int i = 0; i < profiles.length(); i++) options[i + 1] = profiles.optString(i);
                new AlertDialog.Builder(app).setTitle("Whose saves does this phone play with?")
                        .setItems(options, (dialog, which) -> app.prefs.profile(which == 0 ? "" : options[which])).show();
            });
        }
        labels.add("Emulators…");
        actions.add(this::emulators);
        labels.add("Games on this phone…");
        actions.add(this::storage);
        labels.add("Forget the pages kept for offline (" + Player.size(app.cache.size()) + ")");
        actions.add(() -> {
            app.cache.clear();
            app.say("Forgotten. Pictures in the media folder stay.");
        });
        String mine;
        try {
            mine = app.getPackageManager().getPackageInfo(app.getPackageName(), 0).versionName;
        } catch (Exception e) {
            mine = "?";
        }
        labels.add("App version " + mine + ": look for a newer one");
        actions.add(() -> app.updater.checkUpdate(true));
        labels.add("Reload");
        actions.add(() -> {
            app.cache.reached(true);
            app.web.reload();
        });
        new AlertDialog.Builder(app).setTitle("This phone").setItems(labels.toArray(new String[0]), (dialog, which) -> actions.get(which).run())
                .setPositiveButton("Close", null).show();
    }

    /** What plays each system's games: RetroArch with one of its cores, or an emulator of its own. */
    private void emulators() {
        JSONArray systems = app.player.systems();
        if (systems.length() == 0) {
            app.alert("Emulators", "The list of systems comes from RetroManager, which hasn't been reached yet.");
            return;
        }
        History history = new History(app.folder);
        String[] labels = new String[systems.length()];
        for (int i = 0; i < labels.length; i++) {
            JSONObject system = systems.optJSONObject(i);
            JSONObject plays = app.player.choose(history, system.optString("name"), null, Player.players(system));
            labels[i] = system.optString("label") + ": " + (plays == null ? "nothing yet" : plays.optString("name"))
                    + (plays != null && app.prefs.core(system.optString("name")) != null ? " (chosen)" : "");
        }
        new AlertDialog.Builder(app).setTitle("Emulators").setItems(labels, (dialog, which) -> emulators(systems.optJSONObject(which).optString("name"), null, null))
                .setPositiveButton("Close", null).show();
    }

    /** One system's, or with `rom` one game's own: everything that could play it,
     *  with what's known of each on this phone. */
    void emulators(String name) {
        emulators(name, null, null);
    }

    void emulators(String name, String rom, String title) {
        app.runOnUiThread(() -> {
            if (app.isFinishing() || app.isDestroyed()) return;
            JSONObject system = app.player.systemEntry(name);
            JSONArray players = Player.players(system);
            History history = new History(app.folder);
            java.util.Set<String> failed = app.prefs.failed(name);
            // What's chosen is kept for the system, or for the one game
            String key = rom == null ? name : name + "/" + rom;
            List<String> labels = new ArrayList<>();
            List<Runnable> actions = new ArrayList<>();
            labels.add(rom == null ? "Automatic" : "As " + system.optString("label", name) + " is played");
            actions.add(() -> app.prefs.core(key, null));
            for (int i = 0; i < players.length(); i++) {
                JSONObject one = players.optJSONObject(i);
                if ("core".equals(one.optString("kind"))) {
                    String core = one.optString("core");
                    labels.add(one.optString("name") + (failed.contains(core) ? " (didn't start when tried)" : history.used(core) ? " (installed)" : ""));
                    actions.add(() -> {
                        app.prefs.failed(name, core, false);
                        app.prefs.core(key, one.optString("id"));
                    });
                } else if (app.player.has(one.optString("package"))) {
                    labels.add(one.optString("name") + " (installed; keeps its own saves)");
                    actions.add(() -> app.prefs.core(key, one.optString("id")));
                } else {
                    labels.add("Get " + one.optString("name") + " (not installed)");
                    actions.add(() -> app.start(new Intent(Intent.ACTION_VIEW, Uri.parse(one.optString("get"))).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)));
                }
            }
            labels.add("Another RetroArch core…");
            actions.add(() -> typeCore(name, key, title != null ? title : system.optString("label", name)));
            String chosen = app.prefs.core(key);
            try {
                app.ask(app.spec("choose", (title != null ? title : system.optString("label", name)) + (chosen == null ? "" : ": " + chosen.replace("retroarch:", "RetroArch: ").replace("app:", "")), null)
                        .put("options", new JSONArray(labels)), (index, text) -> {
                    if (index < 0) return;
                    actions.get(index).run();
                    // (the page marks the systems nothing plays)
                    app.tellPage();
                });
            } catch (org.json.JSONException e) {
                // nothing to ask with
            }
        });
    }

    private void typeCore(String name, String key, String label) {
        try {
            app.ask(app.spec("input", label, "The core's file name in RetroArch, without \"_libretro_android.so\".").put("hint", "snes9x").put("yes", "Use"), (index, text) -> {
                String core = index != 0 || text == null ? "" : text.trim().replace("_libretro_android.so", "");
                if (core.isEmpty()) return;
                app.prefs.failed(name, core, false);
                app.prefs.core(key, "retroarch:" + core);
                app.tellPage();
            });
        } catch (org.json.JSONException e) {
            // nothing to ask with
        }
    }
}
