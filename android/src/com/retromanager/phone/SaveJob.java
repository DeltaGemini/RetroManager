package com.retromanager.phone;

import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import android.util.Log;

import java.util.List;

/**
 * Sends changed saves and save states to RetroManager every so often while the
 * app isn't open, when there's a connection: a game left with the Home button,
 * or started from its icon on the home screen, doesn't bring the app back to
 * the front, which is when it otherwise looks. What it does is Player's
 * (sendSavesNow): the same rules, so a save the server has changed too is
 * left for the person to choose between the next time the game starts.
 */
public class SaveJob extends JobService {
    private static final int ID = 1;
    private static final long EVERY = 30 * 60 * 1000L;

    static void schedule(Context context) {
        JobScheduler jobs = context.getSystemService(JobScheduler.class);
        if (jobs == null || jobs.getPendingJob(ID) != null) return;
        jobs.schedule(new JobInfo.Builder(ID, new ComponentName(context, SaveJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPeriodic(EVERY)
                .build());
    }

    @Override public boolean onStartJob(JobParameters params) {
        new Thread(() -> {
            try {
                Prefs prefs = new Prefs(this);
                if (prefs.server() != null && prefs.tree() != null && Folder.usable(prefs.tree())) {
                    OfflineCache cache = new OfflineCache(this);
                    Folder folder = new Folder(this, prefs.tree());
                    cache.use(prefs.server(), folder);
                    List<String> sent = new Player(this, prefs, cache).sendSavesNow(folder);
                    if (!sent.isEmpty()) Log.i("RetroManager", "Sent while the app was closed: " + sent);
                }
            } catch (RuntimeException e) {
                Log.w("RetroManager", "Couldn't look at the saves in the background", e);
            }
            jobFinished(params, false);
        }, "save-job").start();
        return true;
    }

    @Override public boolean onStopJob(JobParameters params) {
        return false;
    }
}
