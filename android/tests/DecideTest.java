package com.retromanager.phone;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** The tests of the app's plain decisions (Decide.java), on any computer with Java:
 *  android/test.sh. Each case is a situation the app meets. */
public final class DecideTest {
    private static int run, failed;

    private static void check(String what, Object got, Object wanted) {
        run++;
        if (wanted == null ? got != null : !wanted.equals(got)) {
            failed++;
            System.out.println("FAIL " + what + ": got " + got + ", wanted " + wanted);
        }
    }

    private static String fresh(String got, String stamp, long serverSize, long serverModified, long phoneSize, long phoneModified, boolean keep) {
        Decide.Freshness f = Decide.freshness(got, stamp, serverSize, serverModified, phoneSize, phoneModified, keep);
        return (f.fetch ? "fetch" : "keep") + (f.note != null ? " note " + f.note : "");
    }

    private static void freshness() {
        long day = 86_400_000L;
        // Fetched by this app, which noted the server's date and size
        check("the same as fetched", fresh("1000-500", "1000-500", 500, 1_000_000, 500, 5_000_000, false), "keep");
        check("replaced on the server, the same size", fresh("1000-500", "2000-500", 500, 2_000_000, 500, 5_000_000, false), "fetch");
        check("changed on the phone since, not kept up to date", fresh("1000-500", "2000-500", 500, 2_000_000, 600, 5_000_000, false), "keep");
        check("changed on the phone since, kept up to date", fresh("1000-500", "2000-500", 500, 2_000_000, 600, 5_000_000, true), "fetch");
        check("a server that gives no stamp", fresh("1000-500", "", 500, 0, 500, 5_000_000, true), "keep");
        // Fetched by an older app, which noted only the size: an updated ROM the same size
        // (HeartGold replaced on the server after the phone fetched it)
        check("older app, replaced since, the same size", fresh("500", "9000-500", 500, 9 * day, 500, 2 * day, false), "fetch");
        check("older app, not replaced since", fresh("500", "1000-500", 500, day, 500, 2 * day, false), "keep note 1000-500");
        check("older app, another size", fresh("500", "1000-600", 600, day, 500, 2 * day, false), "fetch");
        // Not fetched by the app (copied, or by Syncthing, which keeps the file's date)
        check("not the app's, not kept up to date", fresh(null, "1000-500", 500, day, 500, day, false), "keep");
        check("Syncthing's copy, unchanged", fresh(null, "1000-500", 500, day, 500, day, true), "keep note 1000-500");
        check("Syncthing's copy, a second apart", fresh(null, "1000-500", 500, day + 1000, 500, day, true), "keep note 1000-500");
        check("not the app's, replaced on the server", fresh(null, "9000-500", 500, 9 * day, 500, day, true), "fetch");
        check("not the app's, another size", fresh(null, "1000-700", 700, day, 500, day, true), "fetch");
    }

    private static Decide.Option core(String name) { return new Decide.Option("retroarch:" + name, "core", name, ""); }
    private static Decide.Option app(String key, String pkg) { return new Decide.Option("app:" + key, "app", "", pkg); }

    private static String choose(List<Decide.Option> options, String chosen, String last, Set<String> failed, boolean retroArch,
                                 Set<String> apps, Set<String> used) {
        return Decide.choose(options, chosen, last, failed, retroArch, apps::contains, used::contains);
    }

    private static Set<String> set(String... items) { return new HashSet<>(Arrays.asList(items)); }

    private static void choosing() {
        List<Decide.Option> gba = Arrays.asList(core("mgba"), core("vba_next"), core("gpsp"));
        Set<String> none = Collections.emptySet();
        // Every GBA core marked as not starting a game, though mGBA plays the Game Boy's: mGBA
        check("a core marked failed that plays another system", choose(gba, null, null, set("mgba", "vba_next", "gpsp"), true, none, set("mgba")), "0");
        check("every core failed and none ever played: nothing", choose(gba, null, null, set("mgba", "vba_next", "gpsp"), true, none, none), null);
        check("one failed, one played elsewhere", choose(gba, null, null, set("mgba"), true, none, set("gpsp")), "2");
        check("nothing known: the first", choose(gba, null, null, none, true, none, none), "0");
        check("the one chosen", choose(gba, "retroarch:gpsp", null, none, true, none, none), "2");
        check("one typed in, not listed", choose(gba, "retroarch:mgba_new", null, none, true, none, none), "core:mgba_new");
        check("RetroArch's last for the system", choose(gba, null, "vba_next", none, true, none, none), "core:vba_next");
        check("no RetroArch: nothing", choose(gba, null, null, none, false, none, none), null);
        List<Decide.Option> threeDs = Arrays.asList(app("azahar", "org.azahar_emu.azahar"), core("citra"));
        check("an emulator of its own, installed", choose(threeDs, null, null, none, true, set("org.azahar_emu.azahar"), none), "0");
        check("an emulator of its own, not installed", choose(threeDs, null, null, none, true, none, none), "1");
        check("chosen but not installed: the next best", choose(threeDs, "app:azahar", null, none, true, none, none), "1");
    }

    private static String[] entry(String path, String core) { return new String[]{path, core}; }

    private static void history() {
        String roms = "/storage/emulated/0/RetroArch/roms/";
        List<String[]> played = Arrays.asList(   // newest first
            entry(roms + "gb/Tetris (World).gb", "mgba"),
            entry(roms + "GBA/Golden Sun.zip#Golden Sun (USA).gba", "mgba"),
            entry("content://com.android.externalstorage.documents/tree/primary%3ARetroArch/roms/snes/Earthbound.sfc", "snes9x"),
            entry(roms + "gba/Advance Wars.gba", "vba_next"));
        check("a core's file", Decide.coreOf("/data/user/0/com.retroarch.aarch64/cores/mgba_libretro_android.so"), "mgba");
        check("not a core's file", Decide.coreOf("/data/user/0/com.retroarch/cores/readme.txt"), null);
        check("no core", Decide.coreOf(""), null);
        check("the last core for a system, its folder in another case", Decide.coreFor(played, roms, "gba"), "mgba");
        check("no game of the system", Decide.coreFor(played, roms, "n64"), null);
        check("cores, newest first, once each", Decide.cores(played), Arrays.asList("mgba", "snes9x", "vba_next"));
        check("a core used for another system", Decide.used(played, "mgba"), true);
        check("a core never used", Decide.used(played, "gpsp"), false);
        check("began: a zip, its entry naming the file inside", Decide.began(played, roms + "gba/Golden Sun.zip", "mgba"), true);
        check("began: in the history with another core", Decide.began(played, roms + "gba/Advance Wars.gba", "mgba"), false);
        check("began: not in the history", Decide.began(played, roms + "gba/Mother 3.gba", "mgba"), false);
        check("recorded: the same file under another folder name",
            Decide.recorded(played, "/storage/emulated/0/RetroArch/roms/snes/Earthbound.sfc", "snes9x"), played.get(2)[0]);
        check("recorded: otherwise the newest with the core", Decide.recorded(played, roms + "gba/Mother 3.gba", "vba_next"), played.get(3)[0]);
        check("recorded: neither", Decide.recorded(played, roms + "gba/Mother 3.gba", "gpsp"), null);
    }

    private static void launching() {
        check("in the history: started", Decide.launch(true, true, true), Decide.Launch.STARTED);
        // The GBA case: not in the history in time, but mGBA has played Game Boy games, so it's installed
        check("not in it, but the core plays other games: started", Decide.launch(true, false, true), Decide.Launch.STARTED);
        check("not in it, the core never seen: failed", Decide.launch(true, false, false), Decide.Launch.FAILED);
        check("the history isn't trusted: not judged", Decide.launch(false, false, false), Decide.Launch.UNKNOWN);
    }

    private static void stick() {
        check("the hat pressed left", Decide.stickKey(-1f, 0f, 0f, 0f), "ArrowLeft");
        check("the hat pressed down", Decide.stickKey(0f, 1f, 0.9f, 0f), "ArrowDown");   // (the hat over the stick)
        check("the stick pushed up, the hat at rest", Decide.stickKey(0f, 0f, 0.1f, -0.8f), "ArrowUp");
        check("the stick mostly sideways", Decide.stickKey(0f, 0f, 0.8f, 0.7f), "ArrowRight");
        check("the stick nudged, not pushed", Decide.stickKey(0f, 0f, 0.4f, 0.5f), null);
    }

    public static void main(String[] args) {
        freshness();
        choosing();
        history();
        launching();
        stick();
        System.out.println(failed == 0 ? "Decide: " + run + " checks passed" : "Decide: " + failed + " of " + run + " checks failed");
        System.exit(failed == 0 ? 0 : 1);
    }
}
