package com.retromanager.phone;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/** What RetroArch's own history (in its folder) says: the core each game was
 *  last played with. It's the only sight the app has of RetroArch's cores:
 *  one that's in there is installed. */
final class History {
    private final String roms;
    private final List<String[]> played = new ArrayList<>();   // {game's path, core}, newest first

    History(Folder folder) {
        roms = folder == null ? null : folder.path("roms") + "/";
        try (InputStream in = folder == null ? null : folder.read("playlists/builtin/content_history.lpl")) {
            JSONArray items = new JSONObject(new String(Player.bytes(in, 8 << 20), StandardCharsets.UTF_8)).optJSONArray("items");
            for (int i = 0; items != null && i < items.length(); i++) {
                JSONObject item = items.optJSONObject(i);
                String core = item == null ? null : Decide.coreOf(item.optString("core_path"));
                if (core != null) played.add(new String[]{item.optString("path"), core});
            }
        } catch (IOException | JSONException | NullPointerException e) {
            // No history to go by
        }
    }

    // (what it says: Decide.java, where it's tested)
    String coreFor(String system) { return Decide.coreFor(played, roms, system); }

    List<String> cores() { return Decide.cores(played); }

    boolean used(String core) { return Decide.used(played, core); }

    String recorded(String path, String core) { return Decide.recorded(played, path, core); }

    boolean began(String path, String core) { return Decide.began(played, path, core); }
}
