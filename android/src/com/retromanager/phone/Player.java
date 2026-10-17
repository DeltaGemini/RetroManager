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

/**
 * Starting a game in the phone's RetroArch: asks RetroManager what the game
 * needs, fetches the files the phone's roms folder hasn't got, brings the
 * person's battery save over, and starts RetroArch on the game with the
 * system's core. When the app comes back, a save that changed goes to the server.
 *
 * With no connection, a game that's on the phone still starts: from what the
 * server said about it last time, or else from the system's cores as last seen.
 */
final class Player {
    private static final String TAG = "RetroManager";
    /** The RetroArch builds, the one from retroarch.com first. */
    static final String[] RETROARCH = {"com.retroarch.aarch64", "com.retroarch", "com.retroarch.ra32"};
    private static final String ACTIVITY = "com.retroarch.browser.retroactivity.RetroActivityFuture";
    private static final int MAX_SAVE = 16 * 1024 * 1024;
    private static final int WATCHED = 8;

    /** Something to tell the person instead of starting the game (no message: they cancelled). */
    private static final class Stop extends Exception {
        Stop(String message) { super(message); }
    }

    private final MainActivity app;
    private final Prefs prefs;
    private final OfflineCache cache;
    private final File known;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final ExecutorService behind = Executors.newSingleThreadExecutor();
    private volatile boolean cancelled;
    private volatile boolean busy;
    // What's put before the progress box's text while several games are fetched ("Game 2 of 9")
    private volatile String heading = "";
    private long lookedAt;

    Player(MainActivity app, Prefs prefs, OfflineCache cache) {
        this(app, app, prefs, cache);
    }

    /** Without the app on screen (SaveJob): only sendSavesNow is of use then. */
    Player(android.content.Context context, Prefs prefs, OfflineCache cache) {
        this(null, context, prefs, cache);
    }

    private Player(MainActivity app, android.content.Context context, Prefs prefs, OfflineCache cache) {
        this.app = app;
        this.prefs = prefs;
        this.cache = cache;
        this.known = new File(context.getFilesDir(), "games");
        known.mkdirs();
    }

    void play(String system, String rom) {
        run(() -> start(system, rom.startsWith("./") ? rom.substring(2) : rom, true));
    }

    /** Fetches a game to the phone (what play would, short of starting it). */
    void fetch(String system, String rom, String name) {
        run(() -> {
            start(system, rom.startsWith("./") ? rom.substring(2) : rom, false);
            app.say(name + " is on this phone.");
        });
    }

    /** Fetches several, one after another, after asking: [[system, rom], ...]. */
    void fetchAll(JSONArray games) {
        run(() -> {
            int count = games.length(), failed = 0;
            if (count == 0 || !app.confirm("Fetch " + count + (count == 1 ? " game" : " games") + " to this phone?",
                    "Each is fetched with its pictures, as playing it would. It goes on while the phone does other things, and what's left can be cancelled.", "Fetch")) return;
            String problem = null;
            for (int i = 0; i < count; i++) {
                JSONArray game = games.optJSONArray(i);
                String rom = game == null ? "" : game.optString(1);
                heading = "Game " + (i + 1) + " of " + count + "\n";
                try {
                    start(game.optString(0), rom.startsWith("./") ? rom.substring(2) : rom, false);
                } catch (Stop stop) {
                    if (stop.getMessage() == null) break;   // cancelled
                    failed++;
                    problem = stop.getMessage();
                }
            }
            heading = "";
            if (failed > 0) app.alert(failed + " of " + count + " weren't fetched", "The last one: " + problem);
            else if (!cancelled) app.say(count + (count == 1 ? " game is" : " games are") + " on this phone.");
        });
    }

    private interface Work {
        void run() throws Exception;
    }

    private void run(Work work) {
        if (busy) return;
        busy = true;
        cancelled = false;
        worker.execute(() -> {
            try {
                work.run();
            } catch (Stop stop) {
                if (stop.getMessage() != null) app.alert("Not done", stop.getMessage());
            } catch (Exception e) {
                Log.w(TAG, "Couldn't finish", e);
                app.alert("Not done", String.valueOf(e.getMessage()));
            } finally {
                heading = "";
                app.progress(null, 0, 0);
                app.fetching(false);
                busy = false;
            }
        });
    }

    /** Takes a game off the phone: its files in the roms folder (a disc's tracks
     *  with it), after asking. Nothing on the server is touched, and its save stays. */
    void remove(String system, String name, String rom) {
        if (busy) return;
        busy = true;
        String path = rom.startsWith("./") ? rom.substring(2) : rom;
        worker.execute(() -> {
            try {
                Folder folder = app.folder();
                if (folder == null) return;
                // The files it's made of, as the server (or its last answer) lists them; else the one file
                List<String> files = new ArrayList<>();
                try {
                    JSONArray listed = info(folder, system, path).optJSONArray("files");
                    for (int i = 0; listed != null && i < listed.length(); i++) files.add(listed.getJSONObject(i).getString("path"));
                } catch (Stop | JSONException e) {
                    // not known: the file alone
                }
                if (!files.contains(path)) files.add(path);
                List<String> there = new ArrayList<>();
                long total = 0;
                for (String file : files) {
                    Folder.Entry entry = folder.stat("roms/" + system + "/" + file);
                    if (entry == null || entry.folder) continue;
                    there.add("roms/" + system + "/" + file);
                    total += entry.size;
                }
                if (there.isEmpty()) {
                    app.say("It isn't on this phone.");
                    return;
                }
                // Something that keeps the folder in step with another device would carry the removal there, or bring the game back
                boolean synced = folder.stat("roms/" + system + "/.stfolder") != null || folder.stat(".stfolder") != null;
                if (!synced && folder.stat("roms/.stfolder") != null) {
                    // (the roms folder is: but its ignore list may leave all but a few systems out)
                    synced = true;
                    try (InputStream in = folder.read("roms/.stignore")) {
                        List<String> lines = Arrays.asList(new String(bytes(in, 1 << 20), StandardCharsets.UTF_8).split("\\s*\\n\\s*"));
                        boolean kept = false;
                        for (String line : lines) if (line.startsWith("!/" + system) || line.startsWith("!" + system)) kept = true;
                        if (lines.contains("/*") || lines.contains("*")) synced = kept;
                    } catch (IOException e) {
                        // no ignore list: all of it is kept in step
                    }
                }
                String message = (there.size() == 1 ? "Its file" : "Its " + there.size() + " files") + " (" + size(total) + ") will be deleted from this phone's roms folder. "
                        + "The game stays in RetroManager, and its save stays on the phone."
                        + (synced ? "\n\nThis folder is kept in step by Syncthing: depending on how that's set up, removing the game here may remove it from the other device too, or it may come back." : "");
                if (!app.confirm("Remove " + name + " from this phone?", message, "Remove from phone")) return;
                int failed = 0;
                for (String file : there) if (!folder.delete(file)) failed++;
                app.romsChanged();
                app.say(failed == 0 ? name + " is off this phone." : failed + " of its files couldn't be deleted.");
            } finally {
                busy = false;
            }
        });
    }

    void cancel() {
        cancelled = true;
    }

    /** Makes a game ready on the phone (its files, the system's BIOS, its pictures) and, with `launch`, starts it. */
    private void start(String system, String rom, boolean launch) throws Exception {
        Folder folder = app.folder();
        if (folder == null) throw new Stop("Choose RetroArch's folder first (📱 This phone).");
        app.progress(heading + "Looking the game up…", 0, 0);
        JSONObject info = info(folder, system, rom);
        if (!info.optBoolean("playable")) throw new Stop(info.optString("error", "This game can't be played on the phone."));
        // What plays it, before anything is fetched: with nothing to, there's no point
        JSONArray players = players(info);
        JSONObject player = choose(new History(folder), system, rom, players);
        if (player == null && launch) {
            app.progress(null, 0, 0);
            nothingPlays(system, info.optString("name", system), players);
            return;
        }

        fetch(folder, system, info.getJSONArray("files"));
        bios(folder, system, info.optJSONArray("bios"));
        app.romsChanged();
        fetchMedia(folder, system, rom, info);
        if (!launch) return;

        String launchRel = "roms/" + system + "/" + rom;
        boolean core = "core".equals(player.optString("kind"));
        // (an emulator of its own keeps its saves to itself: only RetroArch's are carried)
        String saveName = !core || info.isNull("save") ? null : info.optString("save");
        String profile = saveName == null ? "" : profile(info);
        if (!profile.isEmpty()) {
            app.progress("Checking " + (profile.equals("shared") ? "the shared save" : profile + "'s save") + "…", 0, 0);
            JSONObject game = new JSONObject().put("system", system).put("rom", rom).put("profile", profile).put("save", saveName).put("launch", launchRel)
                    .put("core", player.optString("core")).put("name", info.optString("name", rom));
            // (someone else's save on the phone is put by first, and this person's own brought back)
            changeHands(folder, game);
            try {
                saveBefore(folder, game);
                app.progress("Checking " + (profile.equals("shared") ? "the shared save states" : profile + "'s save states") + "…", 0, 0);
                states(folder, game, true);
            } catch (IOException e) {
                // No connection: the phone's own save is played, and goes up later
                if (network(e)) cache.reached(false);
                else app.say("Couldn't check the saves: " + e.getMessage());
            }
            watch(game);
        }

        if (core) {
            // (with "the same save folders on every phone": the core's override says where saves go)
            app.setup().pin(folder, player);
            prefs.launched(new JSONObject().put("system", system).put("rom", rom).put("path", folder.path(launchRel))
                    .put("core", player.optString("core")).put("at", System.currentTimeMillis()));
            launch(retroArch(), player.optString("core"), folder.path(launchRel));
        } else {
            launch(player, folder, launchRel);
        }
        played(system, rom, System.currentTimeMillis() / 1000);
    }

    // --- What the game needs ---

    private JSONObject info(Folder folder, String system, String rom) throws Stop {
        File file = new File(known, OfflineCache.sha1(system + "/" + rom) + ".json");
        try {
            JSONObject info = json("/api/phone/info?system=" + Uri.encode(system) + "&rom=" + Uri.encode(rom));
            if (!info.optBoolean("success")) throw new Stop(info.optString("error", "The server couldn't say what this game needs."));
            if (info.optBoolean("playable")) {
                try (OutputStream out = new FileOutputStream(file)) {
                    out.write(info.toString().getBytes(StandardCharsets.UTF_8));
                }
                if (info.optJSONArray("profiles") != null) prefs.profiles(info.optJSONArray("profiles"));
            }
            return info;
        } catch (IOException | JSONException e) {
            cache.reached(false);
        }
        try (InputStream in = new FileInputStream(file)) {
            return new JSONObject(new String(bytes(in, 1 << 20), StandardCharsets.UTF_8));
        } catch (IOException | JSONException e) {
            // Never started from here: it can still be, if the file is on the phone
        }
        Folder.Entry there = folder.stat("roms/" + system + "/" + rom);
        JSONArray cores = players(systemEntry(system));
        if (there == null || there.folder) throw new Stop("RetroManager can't be reached, and this game isn't on the phone.");
        if (cores.length() == 0) throw new Stop("RetroManager can't be reached, and the phone doesn't know yet what plays " + system + ".");
        try {
            String name = rom.substring(rom.lastIndexOf('/') + 1);
            int dot = name.lastIndexOf('.');
            return new JSONObject().put("playable", true).put("players", cores)
                    .put("files", new JSONArray().put(new JSONObject().put("path", rom).put("size", there.size)))
                    .put("save", (dot > 0 ? name.substring(0, dot) : name) + ".srm");
        } catch (JSONException e) {
            throw new Stop(e.getMessage());
        }
    }

    // --- What plays it ---

    /** What RetroArch's own history (in its folder) says: the core each game was
     *  last played with. It's the only sight the app has of RetroArch's cores:
     *  one that's in there is installed. */
    final class History {
        private final String roms;
        private final List<String[]> played = new ArrayList<>();   // {game's path, core}, newest first

        History(Folder folder) {
            roms = folder == null ? null : folder.path("roms") + "/";
            try (InputStream in = folder == null ? null : folder.read("playlists/builtin/content_history.lpl")) {
                JSONArray items = new JSONObject(new String(bytes(in, 8 << 20), StandardCharsets.UTF_8)).optJSONArray("items");
                for (int i = 0; items != null && i < items.length(); i++) {
                    JSONObject item = items.optJSONObject(i);
                    String file = item == null ? "" : item.optString("core_path");
                    file = file.substring(file.lastIndexOf('/') + 1);
                    if (file.endsWith("_libretro_android.so")) played.add(new String[]{item.optString("path"), file.substring(0, file.length() - "_libretro_android.so".length())});
                }
            } catch (IOException | JSONException | NullPointerException e) {
                // No history to go by
            }
        }

        /** The core a system's games were last played with, or null. */
        String coreFor(String system) {
            String folder = roms + system + "/";
            for (String[] game : played) if (game[0].regionMatches(true, 0, folder, 0, folder.length())) return game[1];
            return null;
        }

        /** Every core it names, most recent first. */
        List<String> cores() {
            List<String> cores = new ArrayList<>();
            for (String[] game : played) if (!cores.contains(game[1])) cores.add(game[1]);
            return cores;
        }

        boolean used(String core) {
            for (String[] game : played) if (game[1].equals(core)) return true;
            return false;
        }

        /** Whether a game is in it with that core: it began. */
        boolean began(String path, String core) {
            for (String[] game : played) if (game[1].equals(core) && game[0].regionMatches(true, 0, path, 0, path.length())) return true;
            return false;
        }
    }

    /** What can play a game or a system, from what the server said of it:
     *  [{id, kind: "core" | "app", name, ...}] (backend/systems.py: phone_players). */
    static JSONArray players(JSONObject described) {
        JSONArray players = described.optJSONArray("players");
        if (players != null) return players;
        // (an answer kept from before the server listed them: RetroArch's cores alone)
        players = new JSONArray();
        JSONArray cores = described.optJSONArray("cores");
        for (int i = 0; cores != null && i < cores.length(); i++) players.put(core(cores.optString(i)));
        return players;
    }

    private static JSONObject core(String name) {
        try {
            return new JSONObject().put("id", "retroarch:" + name).put("kind", "core").put("core", name).put("name", "RetroArch: " + name);
        } catch (JSONException e) {
            throw new IllegalStateException(e);
        }
    }

    boolean has(String name) {
        try {
            app.getPackageManager().getApplicationInfo(name, 0);
            return true;
        } catch (PackageManager.NameNotFoundException e) {
            return false;
        }
    }

    /** What to start a system's games with, or null if nothing on the phone will:
     *  the one chosen here, for the game or else for its system; else the core
     *  RetroArch last played the system with;
     *  else an emulator of its own that's installed; else a core RetroArch has
     *  played anything with (so it's there); else a core that hasn't been tried.
     *  A core that didn't start a game when tried is passed over. */
    JSONObject choose(History history, String system, String rom, JSONArray players) {
        boolean retroArch = retroArch() != null;
        java.util.Set<String> failed = prefs.failed(system);
        // (a game can have its own, over its system's)
        String chosen = rom == null ? null : prefs.core(system + "/" + rom);
        if (chosen == null) chosen = prefs.core(system);
        if (chosen != null) {
            for (int i = 0; i < players.length(); i++) {
                JSONObject player = players.optJSONObject(i);
                if (chosen.equals(player.optString("id")) && ("core".equals(player.optString("kind")) ? retroArch : has(player.optString("package")))) return player;
            }
            // (a core typed in here, which the server doesn't list)
            if (chosen.startsWith("retroarch:") && retroArch) return core(chosen.substring("retroarch:".length()));
        }
        String last = retroArch ? history.coreFor(system) : null;
        if (last != null && !failed.contains(last)) return core(last);
        for (int i = 0; i < players.length(); i++) {
            JSONObject player = players.optJSONObject(i);
            if ("app".equals(player.optString("kind")) && has(player.optString("package"))) return player;
        }
        if (!retroArch) return null;
        JSONObject untried = null;
        for (int i = 0; i < players.length(); i++) {
            JSONObject player = players.optJSONObject(i);
            if (!"core".equals(player.optString("kind")) || failed.contains(player.optString("core"))) continue;
            if (history.used(player.optString("core"))) return player;
            if (untried == null) untried = player;
        }
        return untried;
    }

    /** The systems nothing on the phone plays yet, for the page to mark: a JSON list of their folders. */
    String unplayable() {
        JSONArray none = new JSONArray(), systems = systems();
        History history = new History(app.folder());
        for (int i = 0; i < systems.length(); i++) {
            JSONObject system = systems.optJSONObject(i);
            if (system != null && choose(history, system.optString("name"), null, players(system)) == null) none.put(system.optString("name"));
        }
        return none.toString();
    }

    /** Nothing on the phone plays the game: says so, with what can be done about it. */
    private void nothingPlays(String system, String name, JSONArray players) {
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
        actions.add(() -> app.emulators(system));
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
        worker.execute(() -> {
            Folder folder = app.folder();
            String system = launched.optString("system"), core = launched.optString("core");
            if (folder == null || !prefs.trustHistory()) return;
            if (new History(folder).began(launched.optString("path"), core)) {
                prefs.failed(system, core, false);
                return;
            }
            prefs.failed(system, core, true);
            app.romsChanged();
            JSONArray players = players(systemEntry(system));
            History history = new History(folder);
            List<String> options = new ArrayList<>();
            List<Runnable> actions = new ArrayList<>();
            JSONObject next = choose(history, system, launched.optString("rom"), players);
            if (next != null) {
                options.add("Try " + next.optString("name"));
                actions.add(() -> {
                    prefs.core(system, next.optString("id"));
                    play(system, launched.optString("rom"));
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
            actions.add(() -> app.emulators(system));
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

    /** A system as the server last described it ({name, label, players}), or one with nothing known. */
    JSONObject systemEntry(String system) {
        JSONArray systems = systems();
        for (int i = 0; i < systems.length(); i++) {
            JSONObject entry = systems.optJSONObject(i);
            if (entry != null && system.equals(entry.optString("name"))) return entry;
        }
        return new JSONObject();
    }

    /** The library's systems with their cores, as last fetched: [{name, label, cores}]. */
    JSONArray systems() {
        try (InputStream in = new FileInputStream(new File(known, "cores.json"))) {
            return new JSONArray(new String(bytes(in, 1 << 20), StandardCharsets.UTF_8));
        } catch (IOException | JSONException e) {
            return new JSONArray();
        }
    }

    /** Fetches the systems and their cores, to have them when there's no connection. */
    void refreshCores() {
        worker.execute(() -> {
            try {
                JSONObject answer = json("/api/phone/cores");
                if (!answer.optBoolean("success")) return;
                try (OutputStream out = new FileOutputStream(new File(known, "cores.json"))) {
                    out.write(answer.getJSONArray("systems").toString().getBytes(StandardCharsets.UTF_8));
                }
            } catch (IOException | JSONException e) {
                // Next time
            }
        });
    }

    private void fetch(Folder folder, String system, JSONArray files) throws Exception {
        List<JSONObject> missing = new ArrayList<>();
        long total = 0;
        for (int i = 0; i < files.length(); i++) {
            JSONObject file = files.getJSONObject(i);
            Folder.Entry there = folder.stat("roms/" + system + "/" + file.getString("path"));
            if (there != null) {
                if (cache.offline() || !replaced(system, file, there)) continue;
                file.put("again", true);
            }
            missing.add(file);
            total += file.optLong("size");
        }
        if (missing.isEmpty()) return;
        if (cache.offline()) throw new Stop("This game isn't on the phone yet, and RetroManager can't be reached to fetch it.");
        try {
            StatFs room = new StatFs(Environment.getExternalStorageDirectory().getPath());
            if (folder.path().startsWith(Environment.getExternalStorageDirectory().getPath()) && room.getAvailableBytes() < total + (64L << 20))
                throw new Stop("There isn't room on the phone for this game (" + size(total) + ").");
        } catch (IllegalArgumentException e) {
            // Can't tell: try anyway
        }
        // (kept going while the phone does other things)
        app.fetching(true);
        long done = 0;
        for (JSONObject file : missing) {
            String path = file.getString("path");
            StringBuilder address = new StringBuilder("/api/phone/rom/" + Uri.encode(system));
            for (String part : path.split("/")) address.append('/').append(Uri.encode(part));
            fetchFile(folder, address.toString(), "roms/" + system + "/" + path, file.optLong("size"), done, total, file.optBoolean("again"));
            done += file.optLong("size");
            prefs.synced("got|" + system + "/" + path, file.optString("stamp", String.valueOf(file.optLong("size"))));
        }
    }

    /** Whether a game's file on the phone is an older copy of RetroManager's, to fetch again (an updated
     *  ROM, which is often the same size). The app notes the server's date and size ("stamp") of each
     *  file it fetches. One it noted only the size of (an older app), or didn't fetch (copied there, or
     *  put there by Syncthing, which keeps a file's date), is older if its size differs or the server's
     *  is dated after it. One that isn't the app's is only fetched again with "Keep games up to date" on,
     *  and from then on is the app's; with it off, one changed on the phone since it was fetched stays. */
    private boolean replaced(String system, JSONObject file, Folder.Entry there) {
        String key = "got|" + system + "/" + file.optString("path");
        String got = prefs.synced(key), stamp = file.optString("stamp", "");
        long size = file.optLong("size");
        boolean newer = size != there.size || (file.optLong("modified") > 0 && there.modified > 0 && file.optLong("modified") > there.modified + 2000);
        if (got != null && got.contains("-")) {
            if (stamp.isEmpty() || got.equals(stamp)) return false;
            // (changed on the phone since it was fetched: the phone's own now, unless games are kept up to date)
            return prefs.updateGames() || got.endsWith("-" + there.size);
        }
        boolean ours = got != null && got.equals(String.valueOf(there.size));
        if (!ours && !prefs.updateGames()) return false;
        if (!newer && !stamp.isEmpty()) prefs.synced(key, stamp);   // the same: noted, so the next change is seen
        return newer;
    }

    /** Fetches one file to a place in the RetroArch folder. While it arrives it
     *  has the name of a Syncthing temporary file, which Syncthing never sends on
     *  (in case the folder is one it keeps in step). If the connection drops, what
     *  arrived is kept and the next try carries on from there. */
    private void fetchFile(Folder folder, String address, String target, long expected, long before, long total) throws Stop {
        fetchFile(folder, address, target, expected, before, total, false);
    }

    /** (fresh: a newer copy of a file that's there, so a part left from fetching the old one isn't carried on) */
    private void fetchFile(Folder folder, String address, String target, long expected, long before, long total, boolean fresh) throws Stop {
        String file = target.substring(target.lastIndexOf('/') + 1), name = Folder.clean(file);
        String partial = target.substring(0, target.length() - file.length()) + ".syncthing." + name + ".tmp";
        if (fresh) folder.delete(partial);
        Folder.Entry part = folder.stat(partial);
        long have = part == null ? 0 : part.size;
        if (have > 0 && expected > 0 && have >= expected) {
            folder.delete(partial);
            have = 0;
        }
        HttpURLConnection connection = null;
        try {
            connection = open(address, "GET");
            connection.setRequestProperty("Accept-Encoding", "identity");
            if (have > 0) connection.setRequestProperty("Range", "bytes=" + have + "-");
            int status = connection.getResponseCode();
            if (status == 200) have = 0;   // (the whole of it, from the start)
            else if (status != 206) throw new Stop("The server wouldn't send " + name + " (" + status + ").");
            long last = 0, done = have;
            byte[] buffer = new byte[256 * 1024];
            try (InputStream in = connection.getInputStream(); OutputStream out = have > 0 ? folder.append(partial) : folder.write(partial)) {
                int n;
                while ((n = in.read(buffer)) >= 0) {
                    if (cancelled) throw new Stop(null);
                    out.write(buffer, 0, n);
                    done += n;
                    long now = SystemClock.elapsedRealtime();
                    if (now - last > 200) {
                        last = now;
                        app.progress(heading + "Fetching " + name, before + done, total);
                    }
                }
            }
            if (expected > 0 && done != expected) throw new IOException("only " + size(done) + " of " + size(expected) + " arrived");
            if (!folder.rename(partial, name)) throw new Stop("Couldn't put " + name + " in its folder.");
        } catch (Stop stop) {
            if (stop.getMessage() == null) folder.delete(partial);
            throw stop;
        } catch (IOException e) {
            if (network(e)) cache.reached(false);
            throw new Stop("Fetching " + name + " stopped (" + e.getMessage() + "). It carries on from where it got to the next time.");
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    /** The system's BIOS files, which RetroArch looks for in its system folder: the ones that aren't there are fetched. */
    private void bios(Folder folder, String system, JSONArray files) throws Stop {
        for (int i = 0; files != null && i < files.length() && !cache.offline(); i++) {
            JSONObject file = files.optJSONObject(i);
            String name = file.optString("name");
            if (name.isEmpty() || folder.stat("system/" + name) != null) continue;
            fetchFile(folder, "/api/phone/bios/" + Uri.encode(system) + "/" + Uri.encode(name), "system/" + name, file.optLong("size"), 0, file.optLong("size"));
        }
    }

    /** Tells RetroManager a game was started here, for its "Continue playing".
     *  With no connection it's kept, and told when there is one (sendSaves). */
    private void played(String system, String rom, long at) {
        try {
            HttpURLConnection connection = open("/api/phone/played", "POST");
            try {
                byte[] body = new JSONObject().put("system", system).put("rom", rom).put("at", at).toString().getBytes(StandardCharsets.UTF_8);
                connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type", "application/json");
                connection.setFixedLengthStreamingMode(body.length);
                try (OutputStream out = connection.getOutputStream()) {
                    out.write(body);
                }
                connection.getResponseCode();
            } finally {
                connection.disconnect();
            }
        } catch (IOException e) {
            try {
                prefs.plays(prefs.plays().put(new JSONObject().put("system", system).put("rom", rom).put("at", at)));
            } catch (JSONException ignored) { }
        } catch (JSONException e) {
            // nothing to tell
        }
    }

    /** Whether an error is the connection's (rather than the phone's storage). */
    private static boolean network(IOException e) {
        return e instanceof java.net.SocketException || e instanceof java.net.SocketTimeoutException || e instanceof java.net.UnknownHostException;
    }

    // --- Saves ---

    /** Whose save to play with: the signed-in person's; else the one chosen here
     *  ("shared" is the saves that are nobody's in particular, "" none at all).
     *  With no people on the server it's the shared ones without asking; with
     *  some, the person is asked once. */
    private String profile(JSONObject info) {
        if (!info.isNull("me") && !info.optString("me").isEmpty()) return info.optString("me");
        JSONArray profiles = info.optJSONArray("profiles");
        boolean shared = info.optBoolean("shared_saves");
        List<String> names = new ArrayList<>();
        for (int i = 0; profiles != null && i < profiles.length(); i++) names.add(profiles.optString(i));
        String chosen = prefs.profile();
        if (chosen != null && (chosen.isEmpty() || names.contains(chosen) || (chosen.equals("shared") && shared))) return chosen;
        if (names.isEmpty()) return shared ? "shared" : "";
        if (cache.offline()) return "";
        List<String> options = new ArrayList<>(), values = new ArrayList<>();
        if (shared) {
            options.add("Everyone's: the shared saves");
            values.add("shared");
        }
        options.addAll(names);
        values.addAll(names);
        options.add("Nobody: saves stay on this phone");
        values.add("");
        int picked = app.choose("Whose saves does this phone play with?", options.toArray(new String[0]));
        if (picked < 0) return "";
        prefs.profile(values.get(picked));
        return prefs.profile();
    }

    /** Where RetroArch keeps the game's battery save, wherever its settings put
     *  it: in saves, in a folder of saves (sorted by core or by system), or beside
     *  the game. The newest if there are several; null if there's none. */
    private String findSave(Folder folder, JSONObject game) {
        String name = game.optString("save"), launch = game.optString("launch");
        List<String> places = new ArrayList<>();
        places.add("saves/" + name);
        for (Folder.Entry entry : folder.list("saves")) if (entry.folder && !entry.name.equals(PEOPLE)) places.add("saves/" + entry.name + "/" + name);
        places.add(launch.substring(0, launch.lastIndexOf('/') + 1) + name);
        String found = null;
        long newest = -1;
        for (String place : places) {
            Folder.Entry entry = folder.stat(place);
            if (entry != null && !entry.folder && entry.size > 0 && entry.modified > newest) {
                found = place;
                newest = entry.modified;
            }
        }
        return found;
    }

    private static String key(JSONObject game) {
        return game.optString("profile") + "|" + game.optString("system") + "/" + game.optString("rom");
    }

    private String saveAddress(JSONObject game, String session) {
        return "/api/play/save?system=" + Uri.encode(game.optString("system")) + "&rom=" + Uri.encode(game.optString("rom"))
                + "&profile=" + Uri.encode(game.optString("profile")) + (session == null ? "" : "&session=" + session);
    }

    /** The person's save on the server, or null if they have none. */
    /** When the save serverSave last fetched was written on the server (0 if it didn't say). */
    private long serverSaveModified;

    private byte[] serverSave(JSONObject game) throws IOException {
        HttpURLConnection connection = open(saveAddress(game, null), "GET");
        try {
            int status = connection.getResponseCode();
            serverSaveModified = status == 200 ? connection.getLastModified() : 0;
            if (status == 404) return null;
            if (status != 200) throw new IOException("The server answered " + status + " for the save");
            try (InputStream in = connection.getInputStream()) {
                return bytes(in, MAX_SAVE);
            }
        } finally {
            connection.disconnect();
        }
    }

    /** Sends the phone's save to the server (which backs up the one it replaces). */
    private boolean upload(JSONObject game, byte[] save) throws IOException {
        HttpURLConnection connection = open(saveAddress(game, UUID.randomUUID().toString()), "PUT");
        try {
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/octet-stream");
            connection.setFixedLengthStreamingMode(save.length);
            try (OutputStream out = connection.getOutputStream()) {
                out.write(save);
            }
            int status = connection.getResponseCode();
            if (status == 200) prefs.synced(key(game), OfflineCache.sha1(save));
            // (409: a save that's all empty cells, which the server won't replace a real one with)
            return status == 200;
        } finally {
            connection.disconnect();
        }
    }

    private void keep(Folder folder, String place, byte[] save, JSONObject game) throws IOException {
        try (OutputStream out = folder.write(place)) {
            out.write(save);
        }
        prefs.synced(key(game), OfflineCache.sha1(save));
    }

    // --- Whose save is on the phone ---
    // RetroArch keeps one save (and one set of save states) for a game, whoever
    // plays. So that one person's doesn't become another's when the person
    // using the app changes, the app notes whose are on the phone; when a game
    // is started by someone else, theirs are put by in a folder of their own
    // ("RetroManager people/<name>/" in saves and in states) and the new
    // person's brought back from theirs, to be kept in step with the server as
    // ever. Nothing is sent for anyone but the person whose it is.

    private static final String PEOPLE = "RetroManager people";

    private static String gameOf(JSONObject game) {
        return game.optString("system") + "/" + game.optString("rom");
    }

    /** Who it can't be told for yet (the person hasn't said whose the phone's own saves are). */
    private static final String UNSAID = "?";

    /** Whose save is on the phone for this game: as noted, else whoever it has
     *  been kept in step for here (the one it still matches, if several). A
     *  save or state the app has never had anything to do with is whoever's the
     *  person has said such saves are: asked for now with `ask`, else UNSAID.
     *  null if there's nothing of anybody's there yet. */
    private String owner(Folder folder, JSONObject game, boolean ask) throws Stop {
        String noted = prefs.synced("owner|" + gameOf(game));
        if (noted != null) return noted;
        List<String> people = prefs.syncedFor(gameOf(game));
        if (people.contains(game.optString("profile"))) return game.optString("profile");
        if (people.size() == 1) return people.get(0);
        String place = findSave(folder, game);
        if (people.size() > 1) {
            try {
                String sum = place == null ? null : OfflineCache.sha1(read(folder, place));
                for (String person : people) if (sum != null && sum.equals(prefs.synced(person + "|" + gameOf(game)))) return person;
            } catch (IOException e) {
                // can't tell
            }
        }
        if (place == null && phoneStates(folder, game).isEmpty()) return null;
        // Something's there that the app didn't put there and has never sent: with
        // more than one person on the server, it isn't taken to be whoever asks first
        JSONArray known = prefs.profiles();
        if (known.length() < 2) return null;
        if (prefs.unclaimed() == null) {
            if (!ask || app == null) return UNSAID;
            String[] names = new String[known.length()];
            for (int i = 0; i < names.length; i++) names[i] = known.optString(i);
            int picked = app.choose("Whose are the saves that were already on this phone?", names);
            if (picked < 0) throw new Stop(null);
            prefs.unclaimed(names[picked]);
        }
        return prefs.unclaimed();
    }

    /** Takes the saves on the phone now to be this person's: every game noted
     *  as someone else's, or kept in step here for someone else, is noted as
     *  theirs, and the other's markers for it forgotten (it may have been this
     *  person's save sent as the other's, before the app kept them apart).
     *  Not a game this person has a save put by for: there the one on the
     *  phone really is someone else's. Returns how many games changed hands
     *  (with apply false, how many would, and nothing changes). What it changes
     *  is kept, so undoClaim can put it back. */
    int claim(Folder folder, String person, boolean apply) {
        if (folder == null || person == null || person.isEmpty()) return 0;
        java.util.Map<String, List<String>> games = new java.util.TreeMap<>();   // game -> the markers that say otherwise
        for (String key : prefs.syncedKeys()) {
            String[] parts = key.split("\\|");
            String game = null;
            if (parts.length == 2 && parts[0].equals("owner")) {
                if (!person.equals(prefs.synced(key))) game = parts[1];
            } else if (parts.length == 2 && !parts[0].equals(person) && !Prefs.NOT_PEOPLE.contains(parts[0])) {
                game = parts[1];
            } else if (parts.length == 4 && parts[0].equals("state") && !parts[1].equals(person)) {
                game = parts[2];
            }
            if (game == null) continue;
            if (!games.containsKey(game)) games.put(game, new ArrayList<>());
            if (!parts[0].equals("owner")) games.get(game).add(key);
        }
        int changed = 0;
        JSONObject markers = new JSONObject(), owners = new JSONObject();
        for (java.util.Map.Entry<String, List<String>> game : games.entrySet()) {
            int slash = game.getKey().indexOf('/');
            if (slash < 0) continue;
            String system = game.getKey().substring(0, slash), file = game.getKey().substring(game.getKey().lastIndexOf('/') + 1);
            String stem = (file.contains(".") ? file.substring(0, file.lastIndexOf('.')) : file) + ".";
            boolean putBy = false;
            for (String kind : new String[]{"saves", "states"}) {
                for (Folder.Entry entry : folder.list(kind + "/" + PEOPLE + "/" + person + "/" + system)) putBy |= !entry.folder && entry.name.startsWith(stem);
            }
            if (putBy) continue;
            changed++;
            if (!apply) continue;
            try {
                for (String key : game.getValue()) markers.put(key, prefs.synced(key));
                String owner = prefs.synced("owner|" + game.getKey());
                owners.put("owner|" + game.getKey(), owner == null ? JSONObject.NULL : owner);
            } catch (org.json.JSONException e) {
                Log.w(TAG, "Couldn't note how " + game.getKey() + " was, to undo", e);
            }
            prefs.forget(game.getValue());
            prefs.synced("owner|" + game.getKey(), person);
            Log.i(TAG, game.getKey() + ": the save on the phone taken to be " + person + "'s");
        }
        if (!apply) return changed;
        if (changed > 0) {
            try {
                prefs.claimUndo(new JSONObject().put("person", person).put("at", System.currentTimeMillis())
                        .put("games", changed).put("markers", markers).put("owners", owners));
            } catch (org.json.JSONException e) {
                Log.w(TAG, "Couldn't keep the undo", e);
            }
        }
        prefs.claimed(true);
        return changed;
    }

    /** Puts back what the last claim changed: whose each game's save was, and
     *  the markers it forgot. Returns how many games went back. */
    int undoClaim() {
        JSONObject undo = prefs.claimUndo();
        if (undo == null) return 0;
        JSONObject markers = undo.optJSONObject("markers"), owners = undo.optJSONObject("owners");
        java.util.List<String> drop = new ArrayList<>();
        for (java.util.Iterator<String> keys = owners == null ? java.util.Collections.emptyIterator() : owners.keys(); keys.hasNext(); ) {
            String key = keys.next();
            if (owners.isNull(key)) drop.add(key); else prefs.synced(key, owners.optString(key));
        }
        prefs.forget(drop);
        for (java.util.Iterator<String> keys = markers == null ? java.util.Collections.emptyIterator() : markers.keys(); keys.hasNext(); ) {
            String key = keys.next();
            if (!markers.isNull(key)) prefs.synced(key, markers.optString(key));
        }
        prefs.claimUndo(null);
        Log.i(TAG, "Undid taking " + undo.optInt("games") + " games' saves to be " + undo.optString("person") + "'s");
        return owners == null ? 0 : owners.length();
    }

    private static void move(Folder folder, String from, String to) throws IOException {
        try (InputStream in = folder.read(from); OutputStream out = folder.write(to)) {
            OfflineCache.copy(in, out);
        }
        if (!folder.delete(from)) throw new IOException("Couldn't move " + from);
    }

    /** Where a save or state that isn't on the phone yet goes: by system if RetroArch sorts them so. */
    private static String home(Folder folder, String kind, JSONObject game) {
        Folder.Entry sorted = folder.stat(kind + "/" + game.optString("system"));
        return sorted != null && sorted.folder ? kind + "/" + game.optString("system") : kind;
    }

    /** Before a game starts: if the save and save states on the phone are
     *  someone else's, they're put by for them and this person's brought back. */
    /** A state the server no longer has, moved to states/RetroManager backups/ (its picture goes: RetroArch makes it again). */
    private void retireState(Folder folder, String place, String name) {
        try {
            move(folder, place, "states/RetroManager backups/" + new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(new Date()) + " " + name);
            folder.delete(place + ".png");
            Log.i(TAG, "Put by, as the server has it no more: " + place);
        } catch (IOException e) {
            Log.w(TAG, "Couldn't put by " + place, e);
        }
    }

    /** Every game whose save states have been kept in step here, brought in step
     *  now (each person's, where the phone's are that person's): the server's
     *  new and changed ones fetched, the phone's sent, and the ones the server
     *  has put by put by here too. A state changed on both sides is left for
     *  when the game is next started, where the person chooses. */
    void syncAllStates() {
        run(() -> {
            Folder folder = app.folder();
            if (folder == null) throw new Stop("Choose the RetroArch folder first.");
            java.util.Map<String, JSONObject> games = new java.util.TreeMap<>();
            for (String marker : prefs.syncedKeys()) {
                String[] parts = marker.split("\\|");
                if (parts.length != 4 || !parts[0].equals("state") || !parts[2].contains("/")) continue;
                String system = parts[2].substring(0, parts[2].indexOf('/')), rom = parts[2].substring(parts[2].indexOf('/') + 1);
                String stem = rom.contains(".") ? rom.substring(rom.lastIndexOf('/') + 1, rom.lastIndexOf('.')) : rom;
                games.put(parts[1] + "|" + parts[2], new JSONObject().put("system", system).put("rom", rom).put("profile", parts[1])
                        .put("save", stem + ".srm").put("name", stem));
            }
            int done = 0, moved = 0;
            heading = "Save states: ";
            for (JSONObject game : games.values()) {
                if (cancelled) break;
                app.progress(heading + game.optString("name"), done++, games.size());
                // (only the person whose states these are on the phone)
                String whose = owner(folder, game, false);
                if (whose != null && !whose.equals(game.optString("profile"))) continue;
                try {
                    moved += states(folder, game, false);
                } catch (IOException e) {
                    if (network(e)) throw new Stop("RetroManager can't be reached, so nothing could be brought in step.");
                    Log.w(TAG, "Save states of " + game.optString("rom"), e);
                }
            }
            app.say(games.isEmpty() ? "No game's save states are kept in step on this phone yet."
                    : "Save states of " + games.size() + (games.size() == 1 ? " game" : " games") + " are in step" + (moved > 0 ? " (" + moved + " sent)" : "") + ".");
        });
    }

    private void changeHands(Folder folder, JSONObject game) throws Stop {
        String now = game.optString("profile"), was = owner(folder, game, true), name = game.optString("save");
        if (was == null || was.equals(now)) {
            prefs.synced("owner|" + gameOf(game), now);
            return;
        }
        String stem = name.contains(".") ? name.substring(0, name.lastIndexOf('.')) : name;
        try {
            // Theirs put by (the newest, if RetroArch has left it in more than one place)
            String place = findSave(folder, game);
            if (place != null) move(folder, place, "saves/" + PEOPLE + "/" + was + "/" + game.optString("system") + "/" + name);
            for (int i = 0; i < 4 && (place = findSave(folder, game)) != null; i++) folder.delete(place);
            for (java.util.Map.Entry<String, String> state : phoneStates(folder, game).entrySet()) {
                move(folder, state.getValue(), "states/" + PEOPLE + "/" + was + "/" + game.optString("system") + "/" + state.getKey());
                folder.delete(state.getValue() + ".png");   // (its picture, which RetroArch makes again)
            }
            // This person's brought back, if they've played it here before
            String mine = "saves/" + PEOPLE + "/" + now + "/" + game.optString("system") + "/" + name;
            if (folder.stat(mine) != null) move(folder, mine, home(folder, "saves", game) + "/" + name);
            for (Folder.Entry file : folder.list("states/" + PEOPLE + "/" + now + "/" + game.optString("system"))) {
                if (file.folder || !file.name.startsWith(stem + ".state")) continue;
                move(folder, "states/" + PEOPLE + "/" + now + "/" + game.optString("system") + "/" + file.name, home(folder, "states", game) + "/" + file.name);
            }
        } catch (IOException e) {
            // Better not to start than to play (and send) one person's save as another's
            throw new Stop("Couldn't put " + was + "'s save by to play " + now + "'s: " + e.getMessage());
        }
        prefs.synced("owner|" + gameOf(game), now);
        Log.i(TAG, gameOf(game) + ": " + was + "'s save put by, " + now + "'s in use");
    }

    /** Before the game starts: whichever of the phone's save and the server's has
     *  changed since they last matched replaces the other. If both have, the person says which. */
    private void saveBefore(Folder folder, JSONObject game) throws IOException, Stop {
        String place = findSave(folder, game);
        byte[] phone = place == null ? null : read(folder, place);
        byte[] server = serverSave(game);
        String last = prefs.synced(key(game));
        String name = game.optString("save"), profile = game.optString("profile");
        if (server == null) {
            if (phone != null) upload(game, phone);
            return;
        }
        if (phone == null) {
            // RetroArch sorts saves into folders by system if it's set to: follow that if it has
            Folder.Entry sorted = folder.stat("saves/" + game.optString("system"));
            keep(folder, (sorted != null && sorted.folder ? "saves/" + game.optString("system") + "/" : "saves/") + name, server, game);
            return;
        }
        if (Arrays.equals(phone, server)) {
            prefs.synced(key(game), OfflineCache.sha1(phone));
            return;
        }
        boolean phoneChanged = !OfflineCache.sha1(phone).equals(last), serverChanged = !OfflineCache.sha1(server).equals(last);
        if (phoneChanged && serverChanged) {
            Folder.Entry entry = folder.stat(place);
            SimpleDateFormat format = new SimpleDateFormat("d MMM, HH:mm", Locale.getDefault());
            String when = entry == null || entry.modified == 0 ? "" : " (" + format.format(new Date(entry.modified)) + ")";
            String serverWhen = serverSaveModified == 0 ? "" : " (" + format.format(new Date(serverSaveModified)) + ")";
            String theirs = profile.equals("shared") ? "the shared one" : profile + "'s";
            int picked = app.choose("This phone's save and " + theirs + " on the server are different",
                    new String[]{"Play the phone's save" + when, "Play " + theirs + " from the server" + serverWhen});
            if (picked < 0) throw new Stop(null);
            serverChanged = picked == 1;
        }
        if (serverChanged) {
            // The phone's goes in a folder of its own first
            keep(folder, "saves/RetroManager backups/" + new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(new Date()) + " " + name, phone, game);
            keep(folder, place, server, game);
        } else {
            upload(game, phone);
        }
    }

    // --- Save states ---
    // RetroArch's own, per slot ("<rom>.state", ".state1"..., ".state.auto"),
    // kept the same here and on the server for the person. Each is compared
    // with how it was when the two last matched, as the battery save is.

    private static final long MAX_STATE = 64L * 1024 * 1024;

    /** The phone's states for a game, wherever RetroArch's settings put them
     *  (in states, or a folder of it by core or by system): {name: place}, the newest of a name. */
    private java.util.Map<String, String> phoneStates(Folder folder, JSONObject game) {
        String save = game.optString("save"), stem = save.contains(".") ? save.substring(0, save.lastIndexOf('.')) : save;
        List<String> places = new ArrayList<>();
        places.add("states");
        for (Folder.Entry entry : folder.list("states")) if (entry.folder && !entry.name.equals("RetroManager backups") && !entry.name.equals(PEOPLE)) places.add("states/" + entry.name);
        java.util.Map<String, String> found = new java.util.TreeMap<>();
        java.util.Map<String, Long> dates = new java.util.HashMap<>();
        for (String place : places) {
            for (Folder.Entry file : folder.list(place)) {
                if (file.folder || file.size == 0 || file.size > MAX_STATE || !file.name.startsWith(stem + ".state")) continue;
                if (!file.name.substring(stem.length()).matches("\\.state(\\d{0,2}|\\.auto)")) continue;
                if (dates.containsKey(file.name) && dates.get(file.name) >= file.modified) continue;
                found.put(file.name, place + "/" + file.name);
                dates.put(file.name, file.modified);
            }
        }
        return found;
    }

    /** A file's sha1, worked out again only when its size or date has changed. */
    private String sum(Folder folder, String place) throws IOException {
        Folder.Entry entry = folder.stat(place);
        if (entry == null) throw new IOException(place + " has gone");
        String stamp = entry.size + ":" + entry.modified + ":", known = prefs.synced("sum|" + place);
        if (known != null && known.startsWith(stamp)) return known.substring(stamp.length());
        try (InputStream in = folder.read(place)) {
            java.security.MessageDigest digest = java.security.MessageDigest.getInstance("SHA-1");
            byte[] buffer = new byte[256 * 1024];
            int n;
            while ((n = in.read(buffer)) >= 0) digest.update(buffer, 0, n);
            StringBuilder sha = new StringBuilder();
            for (byte b : digest.digest()) sha.append(String.format("%02x", b));
            prefs.synced("sum|" + place, stamp + sha);
            return sha.toString();
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IOException(e);
        }
    }

    /** Whether any of a game's states on the phone isn't as it was when last carried. */
    private boolean statesChanged(Folder folder, JSONObject game) {
        try {
            for (java.util.Map.Entry<String, String> state : phoneStates(folder, game).entrySet()) {
                if (!sum(folder, state.getValue()).equals(prefs.synced("state|" + key(game) + "|" + state.getKey()))) return true;
            }
        } catch (IOException e) {
            // looked at again next time
        }
        return false;
    }

    private String stateAddress(JSONObject game, String name) {
        return "?system=" + Uri.encode(game.optString("system")) + "&rom=" + Uri.encode(game.optString("rom"))
                + "&profile=" + Uri.encode(game.optString("profile")) + (name == null ? "&core=" + Uri.encode(game.optString("core")) : "&name=" + Uri.encode(name));
    }

    private static String when(long millis) {
        return millis <= 0 ? "date unknown" : new SimpleDateFormat("d MMM yyyy, HH:mm", Locale.getDefault()).format(new Date(millis));
    }

    /** Brings a game's states on the phone and on the server into step, slot by
     *  slot: whichever side has changed since they last matched replaces the
     *  other. Where both have, the person is shown each one's date and says which
     *  to keep (`ask`; without it those are left for the next time the game starts).
     *  A state made by another core than the phone plays the game with isn't
     *  fetched. Returns how many went to the server. */
    private int states(Folder folder, JSONObject game, boolean ask) throws IOException {
        JSONObject answer;
        try {
            answer = json("/api/play/phone-states" + stateAddress(game, null));
        } catch (JSONException e) {
            return 0;   // a server from before it carried them
        }
        JSONArray listed = answer.optJSONArray("states");
        if (!answer.optBoolean("success") || listed == null) return 0;
        java.util.Map<String, JSONObject> server = new java.util.TreeMap<>();
        for (int i = 0; i < listed.length(); i++) server.put(listed.optJSONObject(i).optString("name"), listed.optJSONObject(i));
        java.util.Map<String, String> phone = phoneStates(folder, game);
        java.util.Set<String> names = new java.util.TreeSet<>(server.keySet());
        names.addAll(phone.keySet());
        // Where a state that's only on the server goes: beside the phone's others, else by system if RetroArch sorts them so
        String home = phone.isEmpty() ? null : phone.values().iterator().next();
        home = home != null ? home.substring(0, home.lastIndexOf('/')) : folder.stat("states/" + game.optString("system")) != null ? "states/" + game.optString("system") : "states";
        int sent = 0;
        for (String name : names) {
            String key = "state|" + key(game) + "|" + name, last = prefs.synced(key);
            String place = phone.get(name);
            JSONObject theirs = server.get(name);
            if (theirs == null) {
                if (sum(folder, place).equals(last)) {
                    // The server had it, and it hasn't changed here since, but the server's gone
                    // (thinned out or numbered again there): put by here too, not kept in step
                    retireState(folder, place, name);
                    prefs.forget(java.util.Collections.singletonList(key));
                    continue;
                }
                // Only here: new, or changed since the server had it
                if (sendState(folder, game, name, place, key)) sent++;
                continue;
            }
            boolean fits = theirs.isNull("fits") || theirs.optBoolean("fits");
            if (place == null) {
                if (fits && theirs.optLong("size") <= MAX_STATE) fetchState(folder, game, name, home + "/" + name, key);
                continue;
            }
            String mine = sum(folder, place);
            if (mine.equals(theirs.optString("sha1"))) {
                prefs.synced(key, mine);
                continue;
            }
            boolean phoneChanged = !mine.equals(last), serverChanged = !theirs.optString("sha1").equals(last);
            if (phoneChanged && serverChanged) {
                if (!ask) continue;
                Folder.Entry entry = folder.stat(place);
                int picked = app.choose(game.optString("name") + ": " + theirs.optString("label", name).toLowerCase(Locale.ROOT) + " is different on the phone and on the server",
                        new String[]{"Keep the phone's: " + when(entry == null ? 0 : entry.modified),
                                "Keep " + (game.optString("profile").equals("shared") ? "the shared one" : game.optString("profile") + "'s") + " from the server: " + when(theirs.optLong("modified") * 1000)
                                        + (fits ? "" : " (made with " + theirs.optString("made_by") + ", which this phone doesn't play it with)"),
                                "Leave both as they are"});
                if (picked != 0 && picked != 1) continue;
                serverChanged = picked == 1;
            }
            if (serverChanged) {
                if (!fits) continue;
                // The phone's goes in a folder of its own first
                try (InputStream in = folder.read(place); OutputStream out = folder.write("states/RetroManager backups/" + new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(new Date()) + " " + name)) {
                    OfflineCache.copy(in, out);
                }
                fetchState(folder, game, name, place, key);
            } else if (sendState(folder, game, name, place, key)) {
                sent++;
            }
        }
        return sent;
    }

    private void fetchState(Folder folder, JSONObject game, String name, String place, String key) throws IOException {
        HttpURLConnection connection = open("/api/play/phone-state" + stateAddress(game, name), "GET");
        try {
            if (connection.getResponseCode() != 200) return;
            try (InputStream in = connection.getInputStream(); OutputStream out = folder.write(place)) {
                OfflineCache.copy(in, out);
            }
            prefs.synced(key, sum(folder, place));
        } finally {
            connection.disconnect();
        }
    }

    private boolean sendState(Folder folder, JSONObject game, String name, String place, String key) throws IOException {
        Folder.Entry entry = folder.stat(place);
        if (entry == null || entry.size > MAX_STATE) return false;
        HttpURLConnection connection = open("/api/play/phone-state" + stateAddress(game, name) + "&modified=" + entry.modified / 1000, "PUT");
        try {
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/octet-stream");
            connection.setFixedLengthStreamingMode(entry.size);
            try (InputStream in = folder.read(place); OutputStream out = connection.getOutputStream()) {
                OfflineCache.copy(in, out);
            }
            if (connection.getResponseCode() != 200) return false;
            prefs.synced(key, sum(folder, place));
            return true;
        } finally {
            connection.disconnect();
        }
    }

    // --- Pictures ---

    /** A game's pictures and manual, fetched to the phone's media folder so
     *  they're there with no connection (not its videos). It goes on behind the
     *  game. Done once, and again when the server's have changed: one the app
     *  fetched itself is fetched again if the server's is a different one now. */
    private void fetchMedia(Folder folder, String system, String rom, JSONObject info) {
        JSONArray media = info.optJSONArray("media");
        JSONObject stamps = info.optJSONObject("media_stamps");
        String done = "media|" + system + "/" + rom, now = OfflineCache.sha1(String.valueOf(media) + stamps);
        if (media == null || cache.offline() || now.equals(prefs.synced(done))) return;
        behind.execute(() -> {
            try {
                for (int i = 0; i < media.length(); i++) {
                    String path = media.optString(i), place = "media/" + path;
                    String stamp = stamps == null ? "" : stamps.optString(path), got = prefs.synced("mstamp|" + path);
                    if (path.isEmpty()) continue;
                    if (folder.stat(place) != null && (got == null || stamp.isEmpty() || got.equals(stamp))) continue;
                    StringBuilder address = new StringBuilder("/api/media");
                    for (String part : path.split("/")) address.append('/').append(Uri.encode(part));
                    HttpURLConnection connection = open(address.toString(), "GET");
                    try {
                        if (connection.getResponseCode() != 200) continue;
                        String partial = place.substring(0, place.lastIndexOf('/') + 1) + ".syncthing." + Folder.clean(path.substring(path.lastIndexOf('/') + 1)) + ".tmp";
                        try (InputStream in = connection.getInputStream(); OutputStream out = folder.write(partial)) {
                            OfflineCache.copy(in, out);
                        }
                        if (!folder.rename(partial, path.substring(path.lastIndexOf('/') + 1))) folder.delete(partial);
                        else prefs.synced("mstamp|" + path, stamp.isEmpty() ? "-" : stamp);
                    } finally {
                        connection.disconnect();
                    }
                }
                prefs.synced(done, now);
            } catch (IOException e) {
                // the rest another time
            }
        });
    }

    private void watch(JSONObject game) throws JSONException {
        JSONArray games = new JSONArray().put(game), before = prefs.watched();
        for (int i = 0; i < before.length() && games.length() < WATCHED; i++) {
            JSONObject other = before.optJSONObject(i);
            if (other != null && !key(other).equals(key(game))) games.put(other);
        }
        prefs.watched(games);
    }

    /** When the app comes back to the front: the saves of the games started from
     *  here lately go to the server if they've changed, as long as the server's
     *  hasn't changed too (then it's asked about the next time the game starts). */
    void sendSaves() {
        if (busy || SystemClock.elapsedRealtime() - lookedAt < 5000) return;
        lookedAt = SystemClock.elapsedRealtime();
        worker.execute(() -> {
            List<String> sent = sendSavesNow(app.folder());
            if (!sent.isEmpty()) app.say(sent.size() == 1 ? "Save sent to RetroManager: " + sent.get(0) : sent.size() + " saves sent to RetroManager");
        });
    }

    private static final Object SENDING = new Object();

    /** What sendSaves does, on the thread it's called from: also SaveJob's, every
     *  so often while the app isn't open (a game started from the home screen
     *  never passes through it). Returns what was sent. */
    List<String> sendSavesNow(Folder folder) {
        List<String> sent = new ArrayList<>();
        if (folder == null || prefs.server() == null) return sent;
        synchronized (SENDING) {
            // The games started from here lately, and the ones with an icon on the home screen
            // (which start without the app, so this is when their saves are looked at)
            JSONArray games = prefs.watched(), pinned = prefs.pinned();
            for (int i = 0; i < pinned.length(); i++) {
                boolean there = false;
                for (int j = 0; j < games.length() && !there; j++) there = games.optJSONObject(j) != null && pinned.optJSONObject(i) != null && key(games.optJSONObject(j)).equals(key(pinned.optJSONObject(i)));
                if (!there && pinned.optJSONObject(i) != null) games.put(pinned.optJSONObject(i));
            }
            // What was started with no connection is told now
            JSONArray plays = prefs.plays();
            if (plays.length() > 0 && !cache.offline()) {
                prefs.plays(new JSONArray());
                for (int i = 0; i < plays.length(); i++) played(plays.optJSONObject(i).optString("system"), plays.optJSONObject(i).optString("rom"), plays.optJSONObject(i).optLong("at"));
            }
            try {
                for (int i = 0; i < games.length(); i++) {
                    JSONObject game = games.optJSONObject(i);
                    if (game == null) continue;
                    // What's on the phone may be someone else's by now: then this person's is the one put by for them
                    String whose;
                    try {
                        whose = owner(folder, game, false);
                    } catch (Stop stop) {
                        continue;
                    }
                    boolean theirs = whose == null || whose.equals(game.optString("profile"));
                    // Its save states: the changed ones the server hasn't a newer one of
                    if (theirs && statesChanged(folder, game) && states(folder, game, false) > 0) sent.add(game.optString("name", game.optString("save")) + "'s save states");
                    String place = theirs ? findSave(folder, game) : "saves/" + PEOPLE + "/" + game.optString("profile") + "/" + game.optString("system") + "/" + game.optString("save");
                    if (place == null || folder.stat(place) == null) continue;
                    byte[] phone = read(folder, place);
                    String last = prefs.synced(key(game));
                    if (OfflineCache.sha1(phone).equals(last)) continue;
                    byte[] server = serverSave(game);
                    if (server != null && Arrays.equals(server, phone)) prefs.synced(key(game), OfflineCache.sha1(phone));
                    else if ((server == null || OfflineCache.sha1(server).equals(last)) && upload(game, phone)) sent.add(game.optString("save"));
                }
                cache.reached(true);
            } catch (IOException e) {
                // No connection: they'll go when there is one
            }
        }
        return sent;
    }

    // --- RetroArch ---

    /** The RetroArch builds on this phone. */
    List<String> installed() {
        List<String> found = new ArrayList<>();
        for (String name : RETROARCH) {
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
    private void launch(String retroArch, String core, String rom) throws Stop {
        Intent intent = retroArchIntent(retroArch, core, rom);
        if (intent == null) throw new Stop("RetroArch isn't installed on this phone.");
        Log.i(TAG, "Starting " + rom + " with " + core + " in " + retroArch);
        String problem = app.start(intent);
        if (problem != null) throw new Stop("RetroArch couldn't be started: " + problem);
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
        intent.setComponent(new ComponentName(retroArch, ACTIVITY));
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
            JSONObject info = info(folder, system, path);
            JSONObject player = info.optBoolean("playable") ? choose(new History(folder), system, path, players(info)) : null;
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
                    if (before.optJSONObject(i) != null && !key(before.optJSONObject(i)).equals(key(game))) pinned.put(before.optJSONObject(i));
                }
                prefs.pinned(pinned);
            }
            return intent;
        } catch (Stop | JSONException e) {
            return null;
        }
    }

    /** Starts a game in an emulator of its own, as the server describes it: its
     *  activity, asked to open the game, which it's handed as a document it may read. */
    private void launch(JSONObject player, Folder folder, String rel) throws Stop {
        if (folder.stat(rel) == null) throw new Stop("The game's file isn't in the roms folder.");
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
                throw new Stop(null);
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
        Log.i(TAG, "Starting " + rel + " in " + player.optString("name"));
        String problem = app.start(intent);
        if (problem != null) throw new Stop(player.optString("name") + " couldn't be started: " + problem);
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

    // --- Talking to the server ---

    HttpURLConnection open(String address, String method) throws IOException {
        String server = prefs.server();
        if (server == null) throw new IOException("No server set");
        HttpURLConnection connection = (HttpURLConnection) new URL(server + address).openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(4000);
        connection.setReadTimeout(30000);
        String cookies = CookieManager.getInstance().getCookie(server + address);
        if (cookies != null) connection.setRequestProperty("Cookie", cookies);
        return connection;
    }

    JSONObject json(String address) throws IOException, JSONException {
        HttpURLConnection connection = open(address, "GET");
        try {
            int status = connection.getResponseCode();
            InputStream body = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
            String text = body == null ? "" : new String(bytes(body, 4 << 20), StandardCharsets.UTF_8);
            cache.reached(true);
            if (status == 401) return new JSONObject().put("success", false).put("error", "Sign in first.");
            return new JSONObject(text);
        } finally {
            connection.disconnect();
        }
    }

    private static byte[] read(Folder folder, String place) throws IOException {
        try (InputStream in = folder.read(place)) {
            return bytes(in, MAX_SAVE);
        }
    }

    static byte[] bytes(InputStream in, int most) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[64 * 1024];
        int n;
        while ((n = in.read(buffer)) >= 0) {
            out.write(buffer, 0, n);
            if (out.size() > most) throw new IOException("Larger than expected");
        }
        return out.toByteArray();
    }

    static String size(long bytes) {
        return bytes < 1 << 20 ? Math.max(1, bytes >> 10) + " KB" : bytes < 1 << 30 ? String.format(Locale.US, "%.1f MB", bytes / 1048576.0) : String.format(Locale.US, "%.2f GB", bytes / 1073741824.0);
    }
}
