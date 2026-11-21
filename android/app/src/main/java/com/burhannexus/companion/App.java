package com.burhannexus.companion;

import android.app.Application;
import android.content.Context;
import android.os.Build;

import java.io.File;
import java.io.FileOutputStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;

/** If the app ever closes because of an error, the error is saved and shown on the next start (for a screenshot). */
public class App extends Application {
    static final String CRASH_FILE = "last_error.txt";

    @Override
    public void onCreate() {
        super.onCreate();
        final Thread.UncaughtExceptionHandler previous = Thread.getDefaultUncaughtExceptionHandler();
        final Context c = getApplicationContext();
        Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
            try {
                StringWriter sw = new StringWriter();
                error.printStackTrace(new PrintWriter(sw));
                String text = "App " + BuildConfigInfo.version(c) + ", Android " + Build.VERSION.RELEASE + " (API "
                        + Build.VERSION.SDK_INT + "), " + Build.MANUFACTURER + " " + Build.MODEL + "\n\n" + sw;
                try (FileOutputStream out = new FileOutputStream(new File(c.getFilesDir(), CRASH_FILE))) {
                    out.write(text.getBytes(StandardCharsets.UTF_8));
                }
            } catch (Throwable ignored) {
            }
            if (previous != null) previous.uncaughtException(thread, error);
        });
    }

    /** The saved error text, or null. Reading it deletes it. */
    static String takeCrash(Context c) {
        File f = new File(c.getFilesDir(), CRASH_FILE);
        if (!f.exists()) return null;
        try {
            byte[] b = java.nio.file.Files.readAllBytes(f.toPath());
            return new String(b, StandardCharsets.UTF_8);
        } catch (Exception e) {
            return null;
        } finally {
            f.delete();
        }
    }

    static final class BuildConfigInfo {
        static String version(Context c) {
            try {
                return c.getPackageManager().getPackageInfo(c.getPackageName(), 0).versionName;
            } catch (Exception e) {
                return "?";
            }
        }
    }
}
