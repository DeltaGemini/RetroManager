package com.retromanager.phone;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/** What the app remembers: where RetroManager and RetroArch's folder are, and the choices made here. */
final class Prefs {
    private final SharedPreferences prefs;
    // sha1 of each save as it was when the phone and the server last agreed: "<person>|<system>/<rom>"
    private final SharedPreferences synced;

    Prefs(Context context) {
        prefs = context.getSharedPreferences("app", Context.MODE_PRIVATE);
        synced = context.getSharedPreferences("synced", Context.MODE_PRIVATE);
    }

    /** RetroManager's address, without a slash at the end ("http://192.168.1.10:5000"), or null. */
    String server() { return prefs.getString("server", null); }
    void server(String address) { prefs.edit().putString("server", address).apply(); }

    /** The RetroArch folder the person chose, as the folder picker gave it, or null. */
    Uri tree() {
        String tree = prefs.getString("tree", null);
        return tree == null ? null : Uri.parse(tree);
    }
    void tree(Uri tree) { prefs.edit().putString("tree", tree.toString()).apply(); }

    /** The RetroArch app to start, if one was chosen over the first that's installed. */
    String retroArch() { return prefs.getString("retroarch", null); }
    void retroArch(String name) { prefs.edit().putString("retroarch", name).apply(); }

    /** Whose saves this phone keeps, with login off: null (not asked yet), "" (nobody) or a name. */
    String profile() { return prefs.getString("profile", null); }
    void profile(String name) { prefs.edit().putString("profile", name).apply(); }

    /** The server's save profiles as last seen, for choosing one in the settings. */
    JSONArray profiles() {
        try { return new JSONArray(prefs.getString("profiles", "[]")); } catch (JSONException e) { return new JSONArray(); }
    }
    void profiles(JSONArray names) { prefs.edit().putString("profiles", names.toString()).apply(); }

    /** What was chosen to play a system (its folder name) with: a player's id
     *  ("retroarch:snes9x", "app:azahar"), or null to let the app choose. */
    String core(String system) {
        String chosen = json("cores").optString(system, null);
        // (once it was the core's name alone)
        return chosen == null || chosen.isEmpty() || chosen.contains(":") ? chosen : "retroarch:" + chosen;
    }
    void core(String system, String core) {
        JSONObject cores = json("cores");
        try {
            if (core == null || core.isEmpty()) cores.remove(system); else cores.put(system, core);
        } catch (JSONException e) { return; }
        prefs.edit().putString("cores", cores.toString()).apply();
    }

    /** The games started from here lately, newest first, whose saves are looked at again
     *  when the app comes back: [{system, rom, profile, save, launch}]. */
    JSONArray watched() {
        try { return new JSONArray(prefs.getString("watched", "[]")); } catch (JSONException e) { return new JSONArray(); }
    }
    void watched(JSONArray games) { prefs.edit().putString("watched", games.toString()).apply(); }

    /** The RetroArch cores that didn't start a system's game when tried (so aren't installed, most likely). */
    java.util.Set<String> failed(String system) {
        java.util.Set<String> cores = new java.util.HashSet<>();
        JSONArray listed = json("failed").optJSONArray(system);
        for (int i = 0; listed != null && i < listed.length(); i++) cores.add(listed.optString(i));
        return cores;
    }
    void failed(String system, String core, boolean failed) {
        JSONObject all = json("failed");
        java.util.Set<String> cores = failed(system);
        if (failed ? !cores.add(core) : !cores.remove(core)) return;
        try { all.put(system, new JSONArray(cores)); } catch (JSONException e) { return; }
        prefs.edit().putString("failed", all.toString()).apply();
    }

    /** The game RetroArch was last started on, until it's been seen whether it began: {system, rom, path, core, at}. */
    JSONObject launched() {
        String launched = prefs.getString("launched", null);
        try { return launched == null ? null : new JSONObject(launched); } catch (JSONException e) { return null; }
    }
    void launched(JSONObject game) { prefs.edit().putString("launched", game == null ? null : game.toString()).apply(); }

    /** Whether RetroArch's history is gone by to tell that a game began (not, once the person says it's wrong). */
    boolean trustHistory() { return prefs.getBoolean("trustHistory", true); }
    void trustHistory(boolean trust) { prefs.edit().putBoolean("trustHistory", trust).apply(); }

    /** The games with an icon on the home screen that starts them in RetroArch
     *  without the app (as `watched`): their saves are looked at when the app is next opened. */
    JSONArray pinned() {
        try { return new JSONArray(prefs.getString("pinned", "[]")); } catch (JSONException e) { return new JSONArray(); }
    }
    void pinned(JSONArray games) { prefs.edit().putString("pinned", games.toString()).apply(); }

    /** Whether the app writes the save folders into the override of each core it starts (Setup.pin). */
    boolean pinSaves() { return prefs.getBoolean("pinSaves", false); }
    void pinSaves(boolean pin) { prefs.edit().putBoolean("pinSaves", pin).apply(); }

    /** Games started with no connection, to tell RetroManager of when there is one: [{system, rom, at}]. */
    JSONArray plays() {
        try { return new JSONArray(prefs.getString("plays", "[]")); } catch (JSONException e) { return new JSONArray(); }
    }
    void plays(JSONArray games) { prefs.edit().putString("plays", games.toString()).apply(); }

    /** The newest version of the app the person has been told of (so they're told once). */
    long toldOf() { return prefs.getLong("toldOf", 0); }
    void toldOf(long version) { prefs.edit().putLong("toldOf", version).apply(); }

    String synced(String key) { return synced.getString(key, null); }

    /** What a marker's first part can be that isn't a person's name. */
    static final java.util.List<String> NOT_PEOPLE = java.util.Arrays.asList("got", "sum", "mstamp", "owner", "state", "media");

    /** The people a game ("system/rom") has been kept in step for here: the
     *  names its save's markers ("<person>|system/rom") and its save states'
     *  ("state|<person>|system/rom|<file>") are under. */
    java.util.List<String> syncedFor(String game) {
        java.util.Set<String> people = new java.util.LinkedHashSet<>();
        for (String key : synced.getAll().keySet()) {
            String[] parts = key.split("\\|");
            if (parts.length == 2 && parts[1].equals(game)) people.add(parts[0]);
            else if (parts.length == 4 && parts[0].equals("state") && parts[2].equals(game)) people.add(parts[1]);
        }
        people.removeAll(NOT_PEOPLE);
        return new java.util.ArrayList<>(people);
    }

    /** Whose the saves are that were on the phone before the app had anything
     *  to do with them (null until the person has said). */
    String unclaimed() { return prefs.getString("unclaimed", null); }

    void unclaimed(String person) { prefs.edit().putString("unclaimed", person).apply(); }

    /** Whether the saves on the phone have been gone through for that person (Player.claim) since it could. */
    /** Whose recent games the widget and the app icon's shortcuts show (who was signed in when they were fetched). */
    String recentFor() { return prefs.getString("recentFor", ""); }
    void recentFor(String person) { prefs.edit().putString("recentFor", person == null ? "" : person).apply(); }

    boolean claimed() { return prefs.getBoolean("claimed", false); }
    void claimed(boolean yes) { prefs.edit().putBoolean("claimed", yes).apply(); }

    /** What the last Player.claim changed, to put back (null: nothing to undo):
     *  {person, at, games, markers: {key: value it had}, owners: {key: value it had, or null}}. */
    JSONObject claimUndo() {
        String saved = prefs.getString("claimUndo", null);
        try { return saved == null ? null : new JSONObject(saved); } catch (JSONException e) { return null; }
    }
    void claimUndo(JSONObject undo) {
        if (undo == null) prefs.edit().remove("claimUndo").apply(); else prefs.edit().putString("claimUndo", undo.toString()).apply();
    }

    java.util.Set<String> syncedKeys() { return new java.util.TreeSet<>(synced.getAll().keySet()); }
    void forget(java.util.Collection<String> keys) {
        SharedPreferences.Editor edit = synced.edit();
        for (String key : keys) edit.remove(key);
        edit.apply();
    }
    void synced(String key, String sha) { synced.edit().putString(key, sha).apply(); }

    private JSONObject json(String key) {
        try { return new JSONObject(prefs.getString(key, "{}")); } catch (JSONException e) { return new JSONObject(); }
    }
}
