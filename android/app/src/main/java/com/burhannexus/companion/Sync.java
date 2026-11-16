package com.burhannexus.companion;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;

import org.json.JSONObject;

import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** One sync at a time, in the background. Screens listen and redraw when the state changes. */
public final class Sync {
    private Sync() {}

    public interface Listener {
        void onSyncState();
    }

    public interface Job {
        Object run() throws Exception;
    }

    public interface Done {
        void done(Object result, Api.ApiException error);
    }

    public static final int IDLE = 0, RUNNING = 1;
    public static volatile int state = IDLE;
    public static volatile boolean online = false;          // did the last attempt reach the PC?
    public static volatile String message = "";            // why the last attempt failed ("" = it worked)

    private static final ExecutorService pool = Executors.newSingleThreadExecutor();
    private static final Handler main = new Handler(Looper.getMainLooper());
    private static final CopyOnWriteArrayList<Listener> listeners = new CopyOnWriteArrayList<>();

    public static void addListener(Listener l) { listeners.addIfAbsent(l); }
    public static void removeListener(Listener l) { listeners.remove(l); }

    private static void notifyListeners() {
        main.post(() -> {
            for (Listener l : listeners) l.onSyncState();
        });
    }

    /** Fetch everything from the PC. A failure changes only the status; the saved data stays as it is. */
    public static void now(Context context) {
        final Context c = context.getApplicationContext();
        if (!Store.paired(c) || state == RUNNING) return;
        state = RUNNING;
        notifyListeners();
        pool.execute(() -> {
            try {
                Object data = Api.call(c, "sync", null);
                Store.saveData(c, (JSONObject) data);
                online = true;
                message = "";
            } catch (Api.ApiException e) {
                online = false;
                message = e.getMessage();
                if ("not_paired".equals(e.code)) message = "This phone was removed on the computer. Pair again.";
            } catch (Exception e) {
                online = false;
                message = "Sync failed";
            }
            state = IDLE;
            notifyListeners();
        });
    }

    /** Any other background call (pairing, saving the template...). The answer comes back on the main thread. */
    public static void background(Job job, Done done) {
        pool.execute(() -> {
            Object result = null;
            Api.ApiException error = null;
            try {
                result = job.run();
            } catch (Api.ApiException e) {
                error = e;
            } catch (Exception e) {
                error = new Api.ApiException("error", e.getMessage() == null ? "Something went wrong" : e.getMessage());
            }
            final Object r = result;
            final Api.ApiException err = error;
            main.post(() -> done.done(r, err));
        });
    }
}
