package com.retromanager.phone;

import android.net.Uri;
import android.os.Build;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Giving RetroArch on one phone the setup it has on another.
 *
 * RetroArch's main settings file is out of any app's reach, but what's in its
 * config folder isn't: each core's overrides (settings that apply while that
 * core runs), its options, remaps and shader presets, with the overlays those
 * name. One phone's are sent to RetroManager (save) and fetched on another
 * (apply).
 *
 * Where saves go is one of RetroArch's main settings, so it can't be copied;
 * but a core's override can say it. With "the same save folders on every
 * phone" on, the app writes the save folders into the override of each core it
 * starts (pin): saves/<system>/ and states/<system>/ in the RetroArch folder,
 * whatever that phone's RetroArch is set to itself.
 */
final class Setup {
    private static final String TAG = "RetroManager";
    private static final long MAX_FILE = 32L * 1024 * 1024;
    private static final int MAX_FILES = 3000;
    private static final Pattern OVERLAY = Pattern.compile("(?m)^\\s*input_overlay\\s*=\\s*\"([^\"]+)\"");
    private static final Pattern SETTING = Pattern.compile("^\\s*([A-Za-z0-9_]+)\\s*=.*$");
    // Text files, in which another phone's paths are put right
    private static final String[] TEXT = {".cfg", ".opt", ".slangp", ".glslp", ".cgp", ".rmp", ".cht"};

    private final MainActivity app;
    private final Prefs prefs;
    private final Player player;

    Setup(MainActivity app, Prefs prefs, Player player) {
        this.app = app;
        this.prefs = prefs;
        this.player = player;
    }

    private static void walk(Folder folder, String rel, int depth, List<String> found) {
        for (Folder.Entry entry : folder.list(rel)) {
            if (entry.name.startsWith(".") || found.size() >= MAX_FILES) continue;
            if (entry.folder) {
                if (depth < 6) walk(folder, rel + "/" + entry.name, depth + 1, found);
            } else if (entry.size <= MAX_FILE) {
                found.add(rel + "/" + entry.name);
            }
        }
    }

    private static String text(Folder folder, String rel) throws IOException {
        try (InputStream in = folder.read(rel)) {
            return new String(Player.bytes(in, 4 << 20), StandardCharsets.UTF_8);
        }
    }

    /** This phone's setup: everything in config, and the overlays its overrides name (their folders). */
    private List<String> files(Folder folder) {
        List<String> found = new ArrayList<>();
        walk(folder, "config", 0, found);
        String base = folder.path() + "/";
        List<String> overlays = new ArrayList<>();
        for (String rel : new ArrayList<>(found)) {
            if (!rel.endsWith(".cfg")) continue;
            try {
                Matcher named = OVERLAY.matcher(text(folder, rel));
                while (named.find()) {
                    String path = named.group(1);
                    // (one of RetroArch's own, in its private storage, is the same on every phone)
                    if (!path.startsWith(base) || path.lastIndexOf('/') <= base.length()) continue;
                    String in = path.substring(base.length(), path.lastIndexOf('/'));
                    if (!overlays.contains(in) && !in.startsWith("config")) overlays.add(in);
                }
            } catch (IOException e) {
                // not read: nothing named
            }
        }
        for (String in : overlays) walk(folder, in, 3, found);
        return found;
    }

    /** Sends this phone's setup to RetroManager, in place of the one kept there. From a thread of its own. */
    void save() {
        new Thread(() -> {
            Folder folder = app.folder();
            if (folder == null) return;
            try {
                app.progress("Looking through RetroArch's config folder…", 0, 0);
                List<String> files = files(folder);
                app.progress(null, 0, 0);
                if (files.isEmpty()) {
                    app.alert("Nothing to save", "RetroArch's config folder is empty: there's no setup on this phone yet.");
                    return;
                }
                JSONObject kept = player.json("/api/phone/setup");
                String instead = kept.optBoolean("saved") ? "\n\nIt replaces the one saved from " + kept.optString("device") + " on " + day(kept.optLong("at")) + "." : "";
                if (!app.confirm("Save this phone's RetroArch setup?", files.size() + " files: each core's overrides, options, remaps and shader presets, and the overlays they use. "
                        + "Another phone can then be given the same." + instead, "Save")) return;
                JSONArray sent = new JSONArray();
                for (int i = 0; i < files.size(); i++) {
                    String rel = files.get(i);
                    app.progress("Saving " + rel.substring(rel.lastIndexOf('/') + 1), i, files.size());
                    Folder.Entry entry = folder.stat(rel);
                    if (entry == null) continue;
                    HttpURLConnection connection = player.open("/api/phone/setup/file?path=" + Uri.encode(rel), "PUT");
                    try {
                        connection.setDoOutput(true);
                        connection.setRequestProperty("Content-Type", "application/octet-stream");
                        connection.setFixedLengthStreamingMode(entry.size);
                        try (InputStream in = folder.read(rel); OutputStream out = connection.getOutputStream()) {
                            OfflineCache.copy(in, out);
                        }
                        if (connection.getResponseCode() == 200) sent.put(rel);
                        else if (connection.getResponseCode() == 401 || connection.getResponseCode() == 403)
                            throw new IOException("only an admin can save the setup");
                    } finally {
                        connection.disconnect();
                    }
                }
                byte[] body = new JSONObject().put("device", Build.MODEL).put("base", folder.path())
                        .put("package", String.valueOf(player.retroArch())).put("files", sent).toString().getBytes(StandardCharsets.UTF_8);
                HttpURLConnection connection = player.open("/api/phone/setup", "POST");
                try {
                    connection.setDoOutput(true);
                    connection.setRequestProperty("Content-Type", "application/json");
                    connection.setFixedLengthStreamingMode(body.length);
                    try (OutputStream out = connection.getOutputStream()) {
                        out.write(body);
                    }
                    if (connection.getResponseCode() != 200) throw new IOException("RetroManager answered " + connection.getResponseCode());
                } finally {
                    connection.disconnect();
                }
                app.progress(null, 0, 0);
                app.alert("Saved", sent.length() + " files are kept in RetroManager. On another phone: 📱 This phone › RetroArch setup › Apply.");
                app.tellPage();
            } catch (IOException | JSONException e) {
                app.progress(null, 0, 0);
                app.alert("Not saved", "The setup couldn't be saved: " + e.getMessage());
            }
        }).start();
    }

    /** Fetches the setup kept in RetroManager into this phone's RetroArch folder.
     *  A file that's there already and differs is copied to "RetroManager backups"
     *  first. Paths that name the other phone's folders are put right. */
    void apply() {
        new Thread(() -> {
            Folder folder = app.folder();
            if (folder == null) return;
            try {
                JSONObject kept = player.json("/api/phone/setup");
                JSONArray files = kept.optJSONArray("files");
                if (!kept.optBoolean("saved") || files == null || files.length() == 0) {
                    app.alert("No setup saved", "Save one from a phone that's set up as you like it first: 📱 This phone › RetroArch setup › Save.");
                    return;
                }
                if (!app.confirm("Apply the setup from " + kept.optString("device") + "?", "Saved on " + day(kept.optLong("at")) + ": " + files.length()
                        + " files go into this phone's RetroArch folder (each core's overrides, options and shader presets, and their overlays). "
                        + "A file of this phone's that differs is kept in RetroArch/RetroManager backups first.\n\nClose RetroArch before applying.", "Apply")) return;
                String base = folder.path(), theirs = kept.optString("base");
                String mine = String.valueOf(player.retroArch()), other = kept.optString("package");
                String backups = "RetroManager backups/setup-" + new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(new Date());
                int written = 0, same = 0, backed = 0;
                for (int i = 0; i < files.length(); i++) {
                    String rel = files.getJSONObject(i).getString("path");
                    app.progress("Applying " + rel.substring(rel.lastIndexOf('/') + 1), i, files.length());
                    HttpURLConnection connection = player.open("/api/phone/setup/file?path=" + Uri.encode(rel), "GET");
                    byte[] data;
                    try {
                        if (connection.getResponseCode() != 200) continue;
                        try (InputStream in = connection.getInputStream()) {
                            data = Player.bytes(in, (int) MAX_FILE);
                        }
                    } finally {
                        connection.disconnect();
                    }
                    boolean isText = false;
                    for (String ending : TEXT) isText |= rel.toLowerCase(Locale.ROOT).endsWith(ending);
                    if (isText) {
                        // The other phone's RetroArch folder, and its app's own storage, are this phone's here
                        String contents = new String(data, StandardCharsets.UTF_8);
                        if (!theirs.isEmpty() && !theirs.equals(base)) contents = contents.replace(theirs + "/", base + "/");
                        if (!other.isEmpty() && !other.equals("null") && !mine.equals("null") && !other.equals(mine)) {
                            contents = contents.replace("/data/user/0/" + other + "/", "/data/user/0/" + mine + "/")
                                    .replace("/data/data/" + other + "/", "/data/data/" + mine + "/");
                        }
                        data = contents.getBytes(StandardCharsets.UTF_8);
                    }
                    if (folder.stat(rel) != null) {
                        byte[] here;
                        try (InputStream in = folder.read(rel)) {
                            here = Player.bytes(in, (int) MAX_FILE);
                        } catch (IOException e) {
                            here = null;
                        }
                        if (here != null && java.util.Arrays.equals(here, data)) {
                            same++;
                            continue;
                        }
                        if (here != null) {
                            try (OutputStream out = folder.write(backups + "/" + rel)) {
                                out.write(here);
                            }
                            backed++;
                        }
                    }
                    try (OutputStream out = folder.write(rel)) {
                        out.write(data);
                    }
                    written++;
                }
                app.progress(null, 0, 0);
                app.alert("Applied", written + (written == 1 ? " file" : " files") + " written" + (same > 0 ? ", " + same + " already the same" : "")
                        + (backed > 0 ? ". " + backed + " of this phone's own were kept in RetroArch/" + backups : "") + ".");
            } catch (IOException | JSONException e) {
                app.progress(null, 0, 0);
                app.alert("Not applied", "The setup couldn't be fetched: " + e.getMessage());
            }
        }).start();
    }

    /** The save folders, as a core's override says them: by system, in the RetroArch folder. */
    private static Map<String, String> pinned(String base) {
        Map<String, String> settings = new LinkedHashMap<>();
        settings.put("savefile_directory", base + "/saves");
        settings.put("savestate_directory", base + "/states");
        settings.put("sort_savefiles_by_content_enable", "true");
        settings.put("sort_savestates_by_content_enable", "true");
        settings.put("sort_savefiles_enable", "false");
        settings.put("sort_savestates_enable", "false");
        settings.put("savefiles_in_content_dir", "false");
        settings.put("savestates_in_content_dir", "false");
        return settings;
    }

    /** Before a game starts in a core: makes the core's override say where saves
     *  go, keeping whatever else the override says. Nothing is written when it
     *  already does, or when RetroArch's name for the core's folder isn't known. */
    void pin(Folder folder, JSONObject core) {
        String name = core.optString("folder");
        if (!prefs.pinSaves() || name.isEmpty() || name.equals("null")) return;
        String rel = "config/" + name + "/" + name + ".cfg";
        try {
            Map<String, String> wanted = pinned(folder.path());
            String before = folder.stat(rel) == null ? "" : text(folder, rel);
            StringBuilder after = new StringBuilder();
            List<String> said = new ArrayList<>();
            for (String line : before.split("\n", -1)) {
                Matcher setting = SETTING.matcher(line);
                if (setting.matches() && wanted.containsKey(setting.group(1))) {
                    after.append(setting.group(1)).append(" = \"").append(wanted.get(setting.group(1))).append("\"\n");
                    said.add(setting.group(1));
                } else if (!line.isEmpty()) {
                    after.append(line).append("\n");
                }
            }
            for (Map.Entry<String, String> setting : wanted.entrySet()) {
                if (!said.contains(setting.getKey())) after.append(setting.getKey()).append(" = \"").append(setting.getValue()).append("\"\n");
            }
            if (after.toString().equals(before.endsWith("\n") || before.isEmpty() ? before : before + "\n")) return;
            // (RetroArch only takes a save folder that's there)
            folder.folders("saves");
            folder.folders("states");
            try (OutputStream out = folder.write(rel)) {
                out.write(after.toString().getBytes(StandardCharsets.UTF_8));
            }
            Log.i(TAG, "Save folders written to " + rel);
        } catch (IOException e) {
            Log.w(TAG, "Couldn't write the save folders to " + rel, e);
        }
    }

    /** How RetroArch is set up on this phone, as far as the app can see, in words. */
    void check() {
        new Thread(() -> {
            Folder folder = app.folder();
            StringBuilder said = new StringBuilder();
            String retroArch = player.retroArch();
            said.append(retroArch == null ? "✗ RetroArch isn't installed.\n" : "✓ RetroArch: " + retroArch + "\n");
            if (folder == null) {
                said.append("✗ RetroArch's folder hasn't been chosen.\n");
            } else {
                said.append("✓ Folder: ").append(folder.path()).append("\n");
                for (String needed : new String[]{"roms", "saves", "states", "system", "config"}) {
                    Folder.Entry there = folder.stat(needed);
                    said.append(there != null && there.folder ? "✓ " : "✗ no ").append(needed).append(" folder\n");
                }
                // Where RetroArch has been putting saves: loose in the folder, or sorted into folders
                int loose = 0, sorted = 0;
                for (Folder.Entry entry : folder.list("saves")) {
                    if (entry.folder && !entry.name.equals("RetroManager backups")) sorted += folder.list("saves/" + entry.name).size();
                    else if (!entry.folder) loose++;
                }
                said.append("\nSaves: ").append(loose + sorted == 0 ? "none yet" : sorted + " in folders (by system or core), " + loose + " loose").append("\n");
                List<String> cores = new History(folder).cores();
                said.append("Cores RetroArch has played with: ").append(cores.isEmpty() ? "none yet" : String.join(", ", cores)).append("\n");
                // Cores passed over because a game started with them didn't show in RetroArch's history
                JSONObject failed = prefs.allFailed();
                List<String> marked = new ArrayList<>();
                for (java.util.Iterator<String> it = failed.keys(); it.hasNext(); ) {
                    String system = it.next();
                    JSONArray list = failed.optJSONArray(system);
                    List<String> names = new ArrayList<>();
                    for (int i = 0; list != null && i < list.length(); i++) names.add(list.optString(i));
                    if (!names.isEmpty()) marked.add(system + ": " + String.join(", ", names));
                }
                said.append("Cores marked as not starting a game: ").append(marked.isEmpty() ? "none" : String.join("; ", marked)).append("\n");
                // The last games started from the app, and whether RetroArch's history has them where they were started
                JSONArray launches = prefs.launches();
                if (launches.length() > 0) {
                    said.append("\nGames started lately (✓ in RetroArch's history):\n");
                    for (int i = 0; i < launches.length(); i++) {
                        JSONObject launch = launches.optJSONObject(i);
                        if (launch == null) continue;
                        said.append(launch.optBoolean("began") ? "✓ " : "✗ ").append(launch.optString("system")).append("/").append(launch.optString("rom"))
                                .append(" with ").append(launch.optString("core")).append(", ").append(day(launch.optLong("at") / 1000)).append("\n");
                        if (!launch.optBoolean("began")) {
                            said.append("   given: ").append(launch.optString("path")).append("\n   history has: ")
                                    .append(launch.isNull("recorded") ? "nothing for it" : launch.optString("recorded")).append("\n");
                        }
                    }
                }
                List<String> overrides = new ArrayList<>();
                for (Folder.Entry core : folder.list("config")) {
                    if (core.folder && folder.stat("config/" + core.name + "/" + core.name + ".cfg") != null) overrides.add(core.name);
                }
                said.append("Cores with overrides: ").append(overrides.isEmpty() ? "none" : String.join(", ", overrides)).append("\n");
            }
            said.append("\nThe same save folders on every phone: ").append(prefs.pinSaves() ? "on" : "off").append("\n");
            try {
                JSONObject kept = player.json("/api/phone/setup");
                said.append(kept.optBoolean("saved") ? "Setup kept in RetroManager: from " + kept.optString("device") + ", " + day(kept.optLong("at")) + ", "
                        + (kept.optJSONArray("files") == null ? 0 : kept.optJSONArray("files").length()) + " files" : "No setup is kept in RetroManager yet.");
            } catch (IOException | JSONException e) {
                said.append("RetroManager couldn't be asked whether a setup is kept.");
            }
            app.alert("RetroArch on this phone", said.toString());
        }).start();
    }

    private static String day(long seconds) {
        return seconds <= 0 ? "an unknown date" : new SimpleDateFormat("d MMM yyyy, HH:mm", Locale.getDefault()).format(new Date(seconds * 1000));
    }
}
