package com.retromanager.phone;

import android.appwidget.AppWidgetManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ShortcutInfo;
import android.content.pm.ShortcutManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.drawable.Icon;
import android.net.Uri;
import android.util.Log;
import android.webkit.CookieManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;

/** The games played most recently (RetroManager's "Continue playing", for the
 *  person signed in here), kept on the phone with a picture of each, for the
 *  home screen widget (RecentWidget), the app icon's shortcuts (long-press it)
 *  and the PLAY_RECENT intent. Fetched when the app opens, after a game, and
 *  when the widget asks; what was fetched last stays for when there's no
 *  connection. */
final class Recent {
    static final int COUNT = 5;
    private static final int SHORTCUTS = 4;
    static final String PLAY = "com.retromanager.phone.PLAY";
    private static final String TAG = "RetroManager";
    private static final String KEPT = "recent.json";

    private Recent() {}

    /** The games kept: [{system, rom, name}], newest first. */
    static JSONArray kept(Context context) {
        try {
            File file = new File(context.getFilesDir(), KEPT);
            if (!file.isFile()) return new JSONArray();
            byte[] data = java.nio.file.Files.readAllBytes(file.toPath());
            return new JSONArray(new String(data, "UTF-8"));
        } catch (Exception e) {
            return new JSONArray();
        }
    }

    /** A kept game's picture, or null. */
    static Bitmap picture(Context context, int index) {
        File file = new File(new File(context.getFilesDir(), "recent"), index + ".img");
        return file.isFile() ? BitmapFactory.decodeFile(file.getPath()) : null;
    }

    /** What starts a game: through the app, which brings its saves in step and fetches it if it must. */
    static Intent play(Context context, String system, String rom) {
        return new Intent(context, MainActivity.class).setAction(PLAY).putExtra("system", system).putExtra("rom", rom)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    }

    /** Asks RetroManager for the games, keeps them and their pictures, then
     *  draws the widgets and shortcuts again. Run off the main thread. Says
     *  whether the list was fetched (if not, the kept one is shown as it was). */
    static boolean refresh(Context context) {
        Prefs prefs = new Prefs(context);
        String server = prefs.server();
        boolean fetched = false;
        if (server != null) {
            try {
                // (a person's list is worked out the first time it's asked for: ask again for up to half a minute)
                JSONObject home = get(server, "/api/console/home");
                for (int tries = 0; home != null && home.optBoolean("pending") && tries < 8; tries++) {
                    Thread.sleep(4000);
                    home = get(server, "/api/console/home");
                }
                if (home != null && home.optBoolean("success") && !home.optBoolean("pending")) {
                    JSONArray games = home.optJSONArray("recent");
                    JSONArray keep = new JSONArray();
                    File pictures = new File(context.getFilesDir(), "recent");
                    pictures.mkdirs();
                    Folder folder = prefs.tree() != null && Folder.usable(prefs.tree()) ? new Folder(context, prefs.tree()) : null;
                    for (int i = 0; games != null && i < games.length() && keep.length() < COUNT; i++) {
                        JSONObject game = games.optJSONObject(i);
                        if (game == null) continue;
                        String rom = game.optString("path").replaceFirst("^(\\./)+", "");
                        String name = game.optString("name", rom);
                        keep.put(new JSONObject().put("system", game.optString("_system")).put("rom", rom).put("name", name));
                        String art = first(game, "box2d", "mix", "screenshot", "wheel");
                        Bitmap bitmap = art == null ? null : picture(folder, server, art);
                        File file = new File(pictures, (keep.length() - 1) + ".img");
                        if (bitmap != null) {
                            try (FileOutputStream out = new FileOutputStream(file)) {
                                bitmap.compress(Bitmap.CompressFormat.PNG, 100, out);
                            }
                        } else if (file.isFile()) {
                            file.delete();
                        }
                    }
                    try (FileOutputStream out = new FileOutputStream(new File(context.getFilesDir(), KEPT))) {
                        out.write(keep.toString().getBytes("UTF-8"));
                    }
                    fetched = true;
                }
            } catch (Exception e) {
                Log.w(TAG, "Couldn't fetch the recent games", e);
            }
        }
        drawn(context);
        return fetched;
    }

    /** The widgets and the app icon's shortcuts, from what's kept. */
    static void drawn(Context context) {
        AppWidgetManager widgets = AppWidgetManager.getInstance(context);
        int[] ids = widgets.getAppWidgetIds(new ComponentName(context, RecentWidget.class));
        if (ids.length > 0) RecentWidget.draw(context, widgets, ids);
        shortcuts(context);
    }

    private static void shortcuts(Context context) {
        try {
            ShortcutManager manager = context.getSystemService(ShortcutManager.class);
            if (manager == null) return;
            JSONArray games = kept(context);
            List<ShortcutInfo> list = new ArrayList<>();
            // (four: most home screens show no more, and would leave out one of the five, the newest even)
            int most = Math.min(SHORTCUTS, manager.getMaxShortcutCountPerActivity());
            for (int i = 0; i < games.length() && list.size() < most; i++) {
                JSONObject game = games.optJSONObject(i);
                String name = game.optString("name");
                Bitmap art = picture(context, i);
                ShortcutInfo.Builder shortcut = new ShortcutInfo.Builder(context, "recent:" + i)
                        .setShortLabel(name.length() > 24 ? name.substring(0, 23) + "…" : name).setLongLabel(name)
                        .setIntent(play(context, game.optString("system"), game.optString("rom")).setAction(PLAY))
                        .setRank(i);
                if (art != null) shortcut.setIcon(Icon.createWithBitmap(square(art)));
                list.add(shortcut.build());
            }
            manager.setDynamicShortcuts(list);
        } catch (Exception e) {
            Log.w(TAG, "Couldn't set the app icon's shortcuts", e);
        }
    }

    /** A picture on a square, for an icon. */
    private static Bitmap square(Bitmap art) {
        int size = Math.max(art.getWidth(), art.getHeight());
        Bitmap out = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        new android.graphics.Canvas(out).drawBitmap(art, (size - art.getWidth()) / 2f, (size - art.getHeight()) / 2f, null);
        return out;
    }

    private static String first(JSONObject game, String... fields) {
        for (String field : fields) {
            String value = game.optString(field, "");
            if (!value.isEmpty() && !"null".equals(value)) return value;
        }
        return null;
    }

    /** A game's picture: the phone's own copy, or the server's small one. */
    private static Bitmap picture(Folder folder, String server, String path) {
        if (folder != null) {
            try (InputStream in = folder.read("media/" + path)) {
                Bitmap art = BitmapFactory.decodeStream(in);
                if (art != null) return shrunk(art);
            } catch (Exception e) {
                // not on the phone
            }
        }
        try {
            StringBuilder address = new StringBuilder(server + "/api/thumb/320");
            for (String part : path.split("/")) address.append('/').append(Uri.encode(part));
            HttpURLConnection connection = open(server, address.toString());
            try (InputStream in = connection.getInputStream()) {
                Bitmap art = BitmapFactory.decodeStream(in);
                return art == null ? null : shrunk(art);
            }
        } catch (Exception e) {
            return null;
        }
    }

    /** No bigger than the widget needs (it's handed over whole each time it's drawn). */
    private static Bitmap shrunk(Bitmap art) {
        int longest = Math.max(art.getWidth(), art.getHeight());
        if (longest <= 240) return art;
        float scale = 240f / longest;
        return Bitmap.createScaledBitmap(art, Math.round(art.getWidth() * scale), Math.round(art.getHeight() * scale), true);
    }

    private static HttpURLConnection open(String server, String address) throws java.io.IOException {
        HttpURLConnection connection = (HttpURLConnection) new URL(address).openConnection();
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(15000);
        // (as the person signed in to the app's page)
        String cookies = CookieManager.getInstance().getCookie(server);
        if (cookies != null) connection.setRequestProperty("Cookie", cookies);
        return connection;
    }

    private static JSONObject get(String server, String path) throws Exception {
        HttpURLConnection connection = open(server, server + path);
        if (connection.getResponseCode() != 200) return null;
        try (InputStream in = connection.getInputStream()) {
            java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
            OfflineCache.copy(in, out);
            return new JSONObject(out.toString("UTF-8"));
        }
    }
}
