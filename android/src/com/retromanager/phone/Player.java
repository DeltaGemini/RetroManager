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
    static final String TAG = "RetroManager";
    /** The RetroArch builds, the one from retroarch.com first. */
    static final String[] RETROARCH = {"com.retroarch.aarch64", "com.retroarch", "com.retroarch.ra32"};
    static final String ACTIVITY = "com.retroarch.browser.retroactivity.RetroActivityFuture";
    private static final int MAX_SAVE = 16 * 1024 * 1024;
    private static final int WATCHED = 8;

    /** Something to tell the person instead of starting the game (no message: they cancelled). */
    static final class Stop extends Exception {
        Stop(String message) { super(message); }
    }

    private final MainActivity app;
    final Launcher launcher;
    private final Prefs prefs;
    private final OfflineCache cache;
    private final File known;
    final ExecutorService worker = Executors.newSingleThreadExecutor();
    final ExecutorService behind = Executors.newSingleThreadExecutor();
    volatile boolean cancelled;
    volatile boolean busy;
    // What's put before the progress box's text while several games are fetched ("Game 2 of 9")
    volatile String heading = "";
    long lookedAt;

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
        this.saves = new Saves(this, app, prefs, cache, known);
        this.launcher = new Launcher(this, app, prefs);
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

    interface Work {
        void run() throws Exception;
    }

    void run(Work work) {
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
            launcher.nothingPlays(system, info.optString("name", system), players);
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
            launcher.launch(launcher.retroArch(), player.optString("core"), folder.path(launchRel));
        } else {
            launcher.launch(player, folder, launchRel);
        }
        played(system, rom, System.currentTimeMillis() / 1000);
    }

    // --- What the game needs ---

    JSONObject info(Folder folder, String system, String rom) throws Stop {
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

    /** What to start a system's games with, or null if nothing on the phone will (Decide.choose). */
    JSONObject choose(History history, String system, String rom, JSONArray players) {
        boolean retroArch = launcher.retroArch() != null;
        // (a game can have its own, over its system's)
        String chosen = rom == null ? null : prefs.core(system + "/" + rom);
        if (chosen == null) chosen = prefs.core(system);
        List<Decide.Option> options = new ArrayList<>();
        for (int i = 0; i < players.length(); i++) {
            JSONObject player = players.optJSONObject(i);
            options.add(player == null ? new Decide.Option("", "", "", "")
                    : new Decide.Option(player.optString("id"), player.optString("kind"), player.optString("core"), player.optString("package")));
        }
        String pick = Decide.choose(options, chosen, retroArch ? history.coreFor(system) : null, prefs.failed(system), retroArch, this::has, history::used);
        if (pick == null) return null;
        return pick.startsWith("core:") ? core(pick.substring("core:".length())) : players.optJSONObject(Integer.parseInt(pick));
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

    /** Whether a game's file on the phone is an older copy of RetroManager's, to fetch again (Decide.freshness). */
    private boolean replaced(String system, JSONObject file, Folder.Entry there) {
        String key = "got|" + system + "/" + file.optString("path");
        Decide.Freshness fresh = Decide.freshness(prefs.synced(key), file.optString("stamp", ""), file.optLong("size"),
                file.optLong("modified"), there.size, there.modified, prefs.updateGames());
        if (fresh.note != null) prefs.synced(key, fresh.note);
        return fresh.fetch;
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
    void played(String system, String rom, long at) {
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
    static boolean network(IOException e) {
        return e instanceof java.net.SocketException || e instanceof java.net.SocketTimeoutException || e instanceof java.net.UnknownHostException;
    }

    // --- Saves, whose save is on the phone, save states and pictures: Saves.java ---

    final Saves saves;

    private String profile(JSONObject info) { return saves.profile(info); }
    private void changeHands(Folder folder, JSONObject game) throws Stop { saves.changeHands(folder, game); }
    private void saveBefore(Folder folder, JSONObject game) throws IOException, Stop { saves.saveBefore(folder, game); }
    private int states(Folder folder, JSONObject game, boolean ask) throws IOException { return saves.states(folder, game, ask); }
    private void watch(JSONObject game) throws JSONException { saves.watch(game); }
    private void fetchMedia(Folder folder, String system, String rom, JSONObject info) { saves.fetchMedia(folder, system, rom, info); }
    int claim(Folder folder, String person, boolean apply) { return saves.claim(folder, person, apply); }
    int undoClaim() { return saves.undoClaim(); }
    void syncAllStates() { saves.syncAllStates(); }
    void sendSaves() { saves.sendSaves(); }
    List<String> sendSavesNow(Folder folder) { return saves.sendSavesNow(folder); }

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

    static byte[] read(Folder folder, String place) throws IOException {
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
