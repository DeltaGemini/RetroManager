package com.retromanager.phone;

import java.util.List;
import java.util.Set;
import java.util.function.Predicate;

/** The app's decisions that are plain logic, apart from Android, so they can be tested on
 *  any computer (android/test.sh, android/tests/DecideTest.java): whether a game's file on
 *  the phone is an older copy of RetroManager's, and what to start a game with. */
final class Decide {
    private Decide() {}

    /** What to do about a game's file that's on the phone. */
    static final class Freshness {
        final boolean fetch;   // an older copy: fetch RetroManager's again
        final String note;     // the server's stamp to note for it now (it's the same), or null
        Freshness(boolean fetch, String note) { this.fetch = fetch; this.note = note; }
    }

    /** Whether a file on the phone is an older copy of RetroManager's (an updated ROM is often
     *  the same size). The app notes ("got") the server's date and size ("stamp", "mtime-size")
     *  of each file it fetches. One it noted only the size of (an older app), or didn't fetch
     *  (copied there, or put there by Syncthing, which keeps a file's date), is older if its
     *  size differs or the server's is dated after it. One that isn't the app's is only fetched
     *  again with keepUpToDate, and from then on is the app's; without it, one changed on the
     *  phone since it was fetched stays.
     *  got: what was noted (null: not fetched by the app); stamp: the server's ("" if it gave none);
     *  times in ms (0: not known). */
    static Freshness freshness(String got, String stamp, long serverSize, long serverModified,
                               long phoneSize, long phoneModified, boolean keepUpToDate) {
        boolean newer = serverSize != phoneSize || (serverModified > 0 && phoneModified > 0 && serverModified > phoneModified + 2000);
        if (got != null && got.contains("-")) {
            if (stamp.isEmpty() || got.equals(stamp)) return new Freshness(false, null);
            // (changed on the phone since it was fetched: the phone's own now, unless games are kept up to date)
            return new Freshness(keepUpToDate || got.endsWith("-" + phoneSize), null);
        }
        boolean ours = got != null && got.equals(String.valueOf(phoneSize));
        if (!ours && !keepUpToDate) return new Freshness(false, null);
        // (the same: noted, so the next change is seen)
        return new Freshness(newer, !newer && !stamp.isEmpty() ? stamp : null);
    }

    /** Something that can play a system's games: a RetroArch core, or an emulator app of its own. */
    static final class Option {
        final String id, kind, core, pkg;   // kind: "core" or "app"
        Option(String id, String kind, String core, String pkg) { this.id = id; this.kind = kind; this.core = core; this.pkg = pkg; }
        boolean isCore() { return "core".equals(kind); }
    }

    /** What to start a game with: one of the options (its index), a core the server doesn't list
     *  ("core:<name>": typed in, or the one RetroArch last played the system with), or null if
     *  nothing on the phone will. In order: the one chosen here (for the game, else its system);
     *  the core RetroArch last played the system with; an emulator of its own that's installed;
     *  a core RetroArch has played anything with (so it's there); a core not tried yet.
     *  A core that didn't start a game when tried is passed over, unless RetroArch's history shows
     *  it playing something (another system's games, say): then it's installed, and whatever kept
     *  that game out of the history wasn't the core's absence. */
    static String choose(List<Option> options, String chosen, String lastCore, Set<String> failed,
                         boolean retroArch, Predicate<String> appInstalled, Predicate<String> coreUsed) {
        if (chosen != null) {
            for (int i = 0; i < options.size(); i++) {
                Option option = options.get(i);
                if (chosen.equals(option.id) && (option.isCore() ? retroArch : appInstalled.test(option.pkg))) return String.valueOf(i);
            }
            if (chosen.startsWith("retroarch:") && retroArch) return "core:" + chosen.substring("retroarch:".length());
        }
        Predicate<String> passedOver = core -> failed.contains(core) && !coreUsed.test(core);
        if (retroArch && lastCore != null && !passedOver.test(lastCore)) return "core:" + lastCore;
        for (int i = 0; i < options.size(); i++) {
            Option option = options.get(i);
            if (!option.isCore() && appInstalled.test(option.pkg)) return String.valueOf(i);
        }
        if (!retroArch) return null;
        int untried = -1;
        for (int i = 0; i < options.size(); i++) {
            Option option = options.get(i);
            if (!option.isCore() || passedOver.test(option.core)) continue;
            if (coreUsed.test(option.core)) return String.valueOf(i);
            if (untried < 0) untried = i;
        }
        return untried < 0 ? null : String.valueOf(untried);
    }
}
