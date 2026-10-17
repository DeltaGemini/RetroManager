package com.retromanager.phone;

import android.net.Uri;
import android.os.SystemClock;
import android.util.Log;

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
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

import com.retromanager.phone.Player.Stop;

/**
 * A game's battery save and save states, kept in step between the phone and RetroManager,
 * whose they are when more than one person uses the phone, and the game's pictures kept on
 * the phone for when there's no connection. Player.java starts the game and hands over here.
 */
final class Saves {
    private static final String TAG = "RetroManager";
    private static final int MAX_SAVE = 16 * 1024 * 1024;
    private static final int WATCHED = 8;

    private final Player player;
    private final MainActivity app;
    private final Prefs prefs;
    private final OfflineCache cache;
    private final File known;

    Saves(Player player, MainActivity app, Prefs prefs, OfflineCache cache, File known) {
        this.player = player;
        this.app = app;
        this.prefs = prefs;
        this.cache = cache;
        this.known = known;
    }

    // --- Saves ---

    /** Whose save to play with: the signed-in person's; else the one chosen here
     *  ("shared" is the saves that are nobody's in particular, "" none at all).
     *  With no people on the server it's the shared ones without asking; with
     *  some, the person is asked once. */
    String profile(JSONObject info) {
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

    static String key(JSONObject game) {
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
        HttpURLConnection connection = player.open(saveAddress(game, null), "GET");
        try {
            int status = connection.getResponseCode();
            serverSaveModified = status == 200 ? connection.getLastModified() : 0;
            if (status == 404) return null;
            if (status != 200) throw new IOException("The server answered " + status + " for the save");
            try (InputStream in = connection.getInputStream()) {
                return Player.bytes(in, MAX_SAVE);
            }
        } finally {
            connection.disconnect();
        }
    }

    /** Sends the phone's save to the server (which backs up the one it replaces). */
    private boolean upload(JSONObject game, byte[] save) throws IOException {
        HttpURLConnection connection = player.open(saveAddress(game, UUID.randomUUID().toString()), "PUT");
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
                String sum = place == null ? null : OfflineCache.sha1(Player.read(folder, place));
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
        player.run(() -> {
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
            player.heading = "Save states: ";
            for (JSONObject game : games.values()) {
                if (player.cancelled) break;
                app.progress(player.heading + game.optString("name"), done++, games.size());
                // (only the person whose states these are on the phone)
                String whose = owner(folder, game, false);
                if (whose != null && !whose.equals(game.optString("profile"))) continue;
                try {
                    moved += states(folder, game, false);
                } catch (IOException e) {
                    if (Player.network(e)) throw new Stop("RetroManager can't be reached, so nothing could be brought in step.");
                    Log.w(TAG, "Save states of " + game.optString("rom"), e);
                }
            }
            app.say(games.isEmpty() ? "No game's save states are kept in step on this phone yet."
                    : "Save states of " + games.size() + (games.size() == 1 ? " game" : " games") + " are in step" + (moved > 0 ? " (" + moved + " sent)" : "") + ".");
        });
    }

    void changeHands(Folder folder, JSONObject game) throws Stop {
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
    void saveBefore(Folder folder, JSONObject game) throws IOException, Stop {
        String place = findSave(folder, game);
        byte[] phone = place == null ? null : Player.read(folder, place);
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
    int states(Folder folder, JSONObject game, boolean ask) throws IOException {
        JSONObject answer;
        try {
            answer = player.json("/api/play/phone-states" + stateAddress(game, null));
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
        HttpURLConnection connection = player.open("/api/play/phone-state" + stateAddress(game, name), "GET");
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
        HttpURLConnection connection = player.open("/api/play/phone-state" + stateAddress(game, name) + "&modified=" + entry.modified / 1000, "PUT");
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
     *  they're there with no connection (not its videos). It goes on player.behind the
     *  game. Done once, and again when the server's have changed: one the app
     *  fetched itself is fetched again if the server's is a different one now. */
    void fetchMedia(Folder folder, String system, String rom, JSONObject info) {
        JSONArray media = info.optJSONArray("media");
        JSONObject stamps = info.optJSONObject("media_stamps");
        String done = "media|" + system + "/" + rom, now = OfflineCache.sha1(String.valueOf(media) + stamps);
        if (media == null || cache.offline() || now.equals(prefs.synced(done))) return;
        player.behind.execute(() -> {
            try {
                for (int i = 0; i < media.length(); i++) {
                    String path = media.optString(i), place = "media/" + path;
                    String stamp = stamps == null ? "" : stamps.optString(path), got = prefs.synced("mstamp|" + path);
                    if (path.isEmpty()) continue;
                    if (folder.stat(place) != null && (got == null || stamp.isEmpty() || got.equals(stamp))) continue;
                    StringBuilder address = new StringBuilder("/api/media");
                    for (String part : path.split("/")) address.append('/').append(Uri.encode(part));
                    HttpURLConnection connection = player.open(address.toString(), "GET");
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

    void watch(JSONObject game) throws JSONException {
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
        if (player.busy || SystemClock.elapsedRealtime() - player.lookedAt < 5000) return;
        player.lookedAt = SystemClock.elapsedRealtime();
        player.worker.execute(() -> {
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
                for (int i = 0; i < plays.length(); i++) player.played(plays.optJSONObject(i).optString("system"), plays.optJSONObject(i).optString("rom"), plays.optJSONObject(i).optLong("at"));
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
                    byte[] phone = Player.read(folder, place);
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
}
