package com.burhannexus.companion;

import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import android.net.ConnectivityManager;
import android.net.Network;

/** Sends what the phone saved and fetches what changed on the computer, also when the app is closed. */
public class SyncJob extends JobService {
    private static final int JOB_ID = 4782;
    private static volatile boolean watching;

    @Override
    public boolean onStartJob(JobParameters params) {
        if (!Store.paired(this)) return false;
        final Context c = getApplicationContext();
        new Thread(() -> {
            boolean ok = false;
            try {
                ok = Local.engine(c).sync(Local.transport(c));
            } catch (Throwable ignored) {
            }
            jobFinished(params, !ok && Local.engine(c).hasUnsent());
        }, "bn-sync-job").start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return true;
    }

    /** Every 15 minutes (the shortest Android allows) while there is a network; kept after a restart. */
    static void schedule(Context c) {
        JobScheduler js = (JobScheduler) c.getSystemService(Context.JOB_SCHEDULER_SERVICE);
        if (js == null) return;
        for (JobInfo j : js.getAllPendingJobs()) if (j.getId() == JOB_ID) return;
        js.schedule(new JobInfo.Builder(JOB_ID, new ComponentName(c, SyncJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPeriodic(15 * 60 * 1000L)
                .setPersisted(true)
                .build());
    }

    /** While the app runs: the moment Wi-Fi comes back, sync. */
    static void watchNetwork(Context c) {
        if (watching) return;
        ConnectivityManager cm = (ConnectivityManager) c.getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm == null) return;
        try {
            cm.registerDefaultNetworkCallback(new ConnectivityManager.NetworkCallback() {
                @Override
                public void onAvailable(Network network) {
                    Sync.later(c, 3000);
                }
            });
            watching = true;
        } catch (Exception ignored) {
        }
    }
}
