package com.retromanager.phone;

import android.content.ComponentName;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Environment;
import android.os.StatFs;
import android.os.SystemClock;
import android.provider.Settings;
import android.util.Log;
import android.webkit.CookieManager;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Starting a game in RetroArch (or saying why nothing on the phone plays it), and, back in the
 *  app, whether it began. Part of Player (`owner`), which decides what a game is started with. */
final class Launcher {
    private final Player owner;
    private final MainActivity app;   // (null without the app on screen: SaveJob's Player)
    private final Prefs prefs;

    Launcher(Player owner, MainActivity app, Prefs prefs) {
        this.owner = owner;
        this.app = app;
        this.prefs = prefs;
    }

    /** The RetroArch builds on this phone. */
    List<String> installed() {
        List<String> found = new ArrayList<>();
        for (String name : Player.RETROARCH) {
            try {
                app.getPackageManager().getApplicationInfo(name, 0);
                found.add(name);
            } catch (PackageManager.NameNotFoundException e) {
                // not this one
            }
        }
        return found;
    }

    String retroArch() {
        List<String> found = installed();
        return found.contains(prefs.retroArch()) ? prefs.retroArch() : found.isEmpty() ? null : found.get(0);
    }

    /** Starts RetroArch on a game, the way other frontends do: its own activity,
     *  told the game's path, the core's file and where its settings are. */
    void launch(String retroArch, String core, String rom) throws Player.Stop {
        Intent intent = retroArchIntent(retroArch, core, rom);
        if (intent == null) throw new Player.Stop("RetroArch isn't installed on this phone.");
        Log.i(Player.TAG, "Starting " + rom + " with " + core + " in " + retroArch);
        String problem = app.start(intent);
        if (problem != null) throw new Player.Stop("RetroArch couldn't be started: " + problem);
    }

    /** What starts RetroArch on a game with a core (null if RetroArch isn't installed). */
    private Intent retroArchIntent(String retroArch, String core, String rom) {
        ApplicationInfo installed;
        try {
            installed = retroArch == null ? null : app.getPackageManager().getApplicationInfo(retroArch, 0);
        } catch (PackageManager.NameNotFoundException e) {
            installed = null;
        }
        if (installed == null) return null;
        String storage = Environment.getExternalStorageDirectory().getAbsolutePath();
        Intent intent = new Intent(Intent.ACTION_MAIN);
        intent.setComponent(new ComponentName(retroArch, Player.ACTIVITY));
        intent.putExtra("ROM", rom);
        intent.putExtra("LIBRETRO", "/data/data/" + retroArch + "/cores/" + core + "_libretro_android.so");
        intent.putExtra("CONFIGFILE", storage + "/Android/data/" + retroArch + "/files/retroarch.cfg");
        intent.putExtra("IME", Settings.Secure.getString(app.getContentResolver(), Settings.Secure.DEFAULT_INPUT_METHOD));
        intent.putExtra("DATADIR", installed.dataDir);
        intent.putExtra("APK", installed.sourceDir);
        intent.putExtra("SDCARD", storage);
        intent.putExtra("EXTERNAL", storage + "/Android/data/" + retroArch + "/files");
        // A game already running there is replaced by this one
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        return intent;
    }

    /** For a game's icon on the home screen: what starts the game in RetroArch
     *  straight away, without the app opening first. Null when that can't be
     *  (the game isn't on the phone yet, or it's played in an emulator of its
     *  own, which has to be handed the game by the app): the icon opens the app
     *  then. Since the app isn't there to carry the game's save, the game is
     *  remembered, and its save and save states go to the server the next time
     *  the app is opened. Not from the main thread: the server may be asked. */
    Intent direct(String system, String rom) {
        Folder folder = app.folder();
        String path = rom.startsWith("./") ? rom.substring(2) : rom, launch = "roms/" + system + "/" + path;
        if (folder == null || folder.stat(launch) == null) return null;
        try {
            JSONObject info = owner.info(folder, system, path);
            JSONObject player = info.optBoolean("playable") ? owner.choose(new History(folder), system, path, Player.players(info)) : null;
            if (player == null || !"core".equals(player.optString("kind"))) return null;
            Intent intent = retroArchIntent(retroArch(), player.optString("core"), folder.path(launch));
            if (intent == null) return null;
            // Whose save it is: the signed-in person's, or the one chosen here (not asked for now)
            String profile = !info.isNull("me") && !info.optString("me").isEmpty() ? info.optString("me") : prefs.profile();
            if (profile != null && !profile.isEmpty() && !info.isNull("save")) {
                JSONObject game = new JSONObject().put("system", system).put("rom", path).put("profile", profile).put("save", info.optString("save"))
                        .put("launch", launch).put("core", player.optString("core")).put("name", info.optString("name", path));
                JSONArray pinned = new JSONArray().put(game), before = prefs.pinned();
                for (int i = 0; i < before.length() && pinned.length() < 40; i++) {
                    if (before.optJSONObject(i) != null && !Saves.key(before.optJSONObject(i)).equals(Saves.key(game))) pinned.put(before.optJSONObject(i));
                }
                prefs.pinned(pinned);
            }
            return intent;
        } catch (Player.Stop | JSONException e) {
            return null;
        }
    }

    /** Starts a game in an emulator of its own, as the server describes it: its
     *  activity, asked to open the game, which it's handed as a document it may read. */
    void launch(JSONObject player, Folder folder, String rel) throws Player.Stop {
        if (folder.stat(rel) == null) throw new Player.Stop("The game's file isn't in the roms folder.");
        // A game that has to be installed in the emulator is started on the installed copy
        JSONObject titles = player.optJSONObject("titles");
        JSONArray formats = titles == null ? null : titles.optJSONArray("extensions");
        for (int i = 0; formats != null && i < formats.length(); i++) {
            if (!rel.toLowerCase(Locale.ROOT).endsWith(formats.optString(i))) continue;
            String installed = installedTitle(folder, rel, titles.optJSONArray("folders"));
            if (installed == null) {
                app.progress(null, 0, 0);
                int picked = app.choose("This game has to be installed in " + player.optString("name") + " first",
                        new String[]{"Open " + player.optString("name") + " (Install CIA file, then play it from here)"});
                Intent open = picked == 0 ? app.getPackageManager().getLaunchIntentForPackage(player.optString("package")) : null;
                if (open != null) app.start(open);
                throw new Player.Stop(null);
            }
            rel = installed;
            break;
        }
        Intent intent = new Intent(player.optString("action", Intent.ACTION_VIEW));
        intent.setComponent(new ComponentName(player.optString("package"), player.optString("activity")));
        if ("document".equals(player.optString("data"))) {
            intent.setDataAndType(folder.document(rel), player.optString("type", "application/octet-stream"));
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } else if ("path".equals(player.optString("data"))) {
            intent.setData(Uri.fromFile(new File(folder.path(rel))));
        }
        // Named values it's given: "{document}" is the game as a document, "{path}" its path
        JSONObject extras = player.optJSONObject("extras");
        for (java.util.Iterator<String> names = extras == null ? null : extras.keys(); names != null && names.hasNext(); ) {
            String name = names.next(), value = extras.optString(name);
            if (value.contains("{document}")) {
                // (clipped to the intent as well, which is what lets the emulator read it)
                intent.setClipData(android.content.ClipData.newRawUri("game", folder.document(rel)));
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            }
            intent.putExtra(name, value.replace("{document}", folder.document(rel).toString()).replace("{path}", folder.path(rel)));
        }
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        Log.i(Player.TAG, "Starting " + rel + " in " + player.optString("name"));
        String problem = app.start(intent);
        if (problem != null) throw new Player.Stop(player.optString("name") + " couldn't be started: " + problem);
    }

    /** Where a 3DS .cia is once installed in the emulator: the largest .app of
     *  its title, in the emulator's own SD card folder. A .cia names its title in
     *  its ticket; an update's or an add-on's is the game's own with another
     *  first half, so those start the game. Null if it isn't installed (or the
     *  emulator's folder isn't inside the RetroArch folder, where the app can look). */
    private String installedTitle(Folder folder, String rel, JSONArray folders) {
        String low;
        try (InputStream in = folder.read(rel)) {
            java.io.DataInputStream data = new java.io.DataInputStream(in);
            byte[] header = new byte[0x20];
            data.readFully(header);
            java.nio.ByteBuffer sizes = java.nio.ByteBuffer.wrap(header).order(java.nio.ByteOrder.LITTLE_ENDIAN);
            long ticket = (sizes.getInt(0) + 63L) / 64 * 64 + (sizes.getInt(8) + 63L) / 64 * 64;
            // (the title's id is 0x1DC into the ticket: 8 bytes, of which the game's own are the last 4)
            long skip = ticket + 0x1DC + 4 - header.length;
            if (skip < 0 || skip > (1 << 20)) return null;
            while (skip > 0) {
                int n = data.skipBytes((int) skip);
                if (n <= 0) return null;
                skip -= n;
            }
            low = String.format("%08x", data.readInt());
        } catch (IOException e) {
            return null;
        }
        for (int i = 0; folders != null && i < folders.length(); i++) {
            String cards = folders.optString(i) + "/sdmc/Nintendo 3DS";
            for (Folder.Entry first : folder.list(cards)) {
                for (Folder.Entry second : first.folder ? folder.list(cards + "/" + first.name) : new ArrayList<Folder.Entry>()) {
                    String content = cards + "/" + first.name + "/" + second.name + "/title/00040000/" + low + "/content";
                    Folder.Entry largest = null;
                    for (Folder.Entry file : folder.list(content)) {
                        if (!file.folder && file.name.toLowerCase(Locale.ROOT).endsWith(".app") && (largest == null || file.size > largest.size)) largest = file;
                    }
                    if (largest != null) return content + "/" + largest.name;
                }
            }
        }
        return null;
    }

    /** Nothing on the phone plays the game: says so, with what can be done about it. */
    void nothingPlays(String system, String name, JSONArray players) {
        List<String> options = new ArrayList<>();
        List<Runnable> actions = new ArrayList<>();
        List<String> cores = new ArrayList<>();
        for (int i = 0; i < players.length(); i++) {
            JSONObject player = players.optJSONObject(i);
            if ("core".equals(player.optString("kind"))) cores.add(player.optString("core"));
            else if (!player.optString("get").isEmpty()) {
                options.add("Get " + player.optString("name"));
                actions.add(() -> app.start(new Intent(Intent.ACTION_VIEW, Uri.parse(player.optString("get"))).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)));
            }
        }
        String retroArch = retroArch();
        if (!cores.isEmpty() && retroArch != null) {
            options.add("Open RetroArch, to install a core (" + String.join(" or ", cores.subList(0, Math.min(2, cores.size()))) + ")");
            actions.add(() -> {
                app.say("In RetroArch: Main Menu → Online Updater → Core Downloader");
                Intent open = app.getPackageManager().getLaunchIntentForPackage(retroArch);
                if (open != null) app.start(open);
            });
        } else if (!cores.isEmpty()) {
            options.add("Get RetroArch");
            actions.add(() -> app.start(new Intent(Intent.ACTION_VIEW, Uri.parse("https://www.retroarch.com/?page=platforms")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)));
        }
        options.add("Choose what plays it…");
        actions.add(() -> app.phone.emulators(system));
        int picked = app.choose("Nothing on this phone plays " + name + " yet", options.toArray(new String[0]));
        if (picked >= 0) actions.get(picked).run();
    }

    /** When the app comes back from RetroArch: whether the game it was started
     *  on began, going by RetroArch's history. If it isn't there, the core most
     *  likely isn't installed: it's passed over from now on, and the person is
     *  asked what to try instead. */
    void checkLaunch() {
        JSONObject launched = prefs.launched();
        if (launched == null || System.currentTimeMillis() - launched.optLong("at") < 4000) return;
        prefs.launched(null);
        owner.worker.execute(() -> {
            Folder folder = app.folder();
            String system = launched.optString("system"), core = launched.optString("core");
            if (folder == null) return;
            History seen = new History(folder);
            boolean began = seen.began(launched.optString("path"), core);
            Decide.Launch verdict = Decide.launch(prefs.trustHistory(), began, seen.used(core));
            if (verdict == Decide.Launch.UNKNOWN) return;
            // (noted for Check this phone: what RetroArch's history has beside what it was given)
            try {
                String recorded = seen.recorded(launched.optString("path"), core);
                prefs.launchChecked(new JSONObject(launched.toString()).put("began", began).put("recorded", recorded == null ? JSONObject.NULL : recorded));
            } catch (JSONException e) {
                // Not noted
            }
            if (verdict == Decide.Launch.STARTED) {
                prefs.failed(system, core, false);
                return;
            }
            prefs.failed(system, core, true);
            app.romsChanged();
            JSONArray players = Player.players(owner.systemEntry(system));
            History history = new History(folder);
            List<String> options = new ArrayList<>();
            List<Runnable> actions = new ArrayList<>();
            JSONObject next = owner.choose(history, system, launched.optString("rom"), players);
            if (next != null) {
                options.add("Try " + next.optString("name"));
                actions.add(() -> {
                    prefs.core(system, next.optString("id"));
                    owner.play(system, launched.optString("rom"));
                });
            }
            String retroArch = retroArch();
            if (retroArch != null) {
                options.add("Open RetroArch, to install " + core);
                actions.add(() -> {
                    prefs.failed(system, core, false);
                    app.say("In RetroArch: Main Menu → Online Updater → Core Downloader");
                    Intent open = app.getPackageManager().getLaunchIntentForPackage(retroArch);
                    if (open != null) app.start(open);
                });
            }
            options.add("Choose what plays it…");
            actions.add(() -> app.phone.emulators(system));
            options.add("It did start: don't ask again");
            actions.add(() -> {
                prefs.trustHistory(false);
                prefs.failed(system, core, false);
                app.romsChanged();
            });
            int picked = app.choose("That doesn't seem to have started in RetroArch with " + core, options.toArray(new String[0]));
            if (picked >= 0) actions.get(picked).run();
        });
    }
}
