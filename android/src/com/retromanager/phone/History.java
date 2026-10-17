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

    /** The path RetroArch's history has for a game started at this path with this core: the
     *  entry with the same file name, else the newest with that core; null if there's neither. */
    String recorded(String path, String core) {
        String name = path.substring(path.lastIndexOf('/') + 1);
        for (String[] game : played) {
            String file = game[0].replaceAll("#.*$", "");
            if (file.substring(file.lastIndexOf('/') + 1).equalsIgnoreCase(name)) return game[0];
        }
        for (String[] game : played) if (game[1].equals(core)) return game[0];
        return null;
    }

    /** Whether a game is in it with that core: it began. */
    boolean began(String path, String core) {
        for (String[] game : played) if (game[1].equals(core) && game[0].regionMatches(true, 0, path, 0, path.length())) return true;
        return false;
    }
}
