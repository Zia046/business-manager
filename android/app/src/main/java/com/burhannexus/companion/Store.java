package com.burhannexus.companion;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.UUID;

/** Everything the app remembers: the pairing with the PC and the last data it received (kept when offline). */
public final class Store {
    private Store() {}

    private static final String PREFS = "bnbc", CACHE = "last_sync.json";
    private static JSONObject cached;

    static SharedPreferences prefs(Context c) {
        return c.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static String deviceId(Context c) {
        String id = prefs(c).getString("device_id", null);
        if (id == null) {
            id = UUID.randomUUID().toString().replace("-", "");
            prefs(c).edit().putString("device_id", id).apply();
        }
        return id;
    }

    public static boolean paired(Context c) {
        return prefs(c).getString("key", null) != null;
    }

    public static byte[] key(Context c) {
        String k = prefs(c).getString("key", null);
        return k == null ? null : Crypto.unb64(k);
    }

    public static void savePairing(Context c, byte[] key, String serverId, String shop, String host, int port) {
        prefs(c).edit().putString("key", Crypto.b64(key)).putString("server_id", serverId).putString("shop", shop)
                .putString("host", host).putInt("port", port).apply();
    }

    public static void forgetPairing(Context c) {
        prefs(c).edit().remove("key").remove("server_id").remove("host").remove("port").apply();
    }

    public static String serverId(Context c) { return prefs(c).getString("server_id", ""); }
    public static String shop(Context c) { return prefs(c).getString("shop", ""); }
    public static String host(Context c) { return prefs(c).getString("host", ""); }
    public static int port(Context c) { return prefs(c).getInt("port", Api.HTTP_PORT); }

    public static void saveAddress(Context c, String host, int port) {
        prefs(c).edit().putString("host", host).putInt("port", port).apply();
    }

    public static long lastSync(Context c) { return prefs(c).getLong("last_sync", 0); }

    public static String lastSyncText(Context c) {
        long t = lastSync(c);
        return t == 0 ? "Never" : new SimpleDateFormat("dd MMM yyyy, hh:mm a", Locale.US).format(new Date(t));
    }

    /** The answer of the last successful sync. Never deleted by a failed sync. */
    public static synchronized void saveData(Context c, JSONObject data) throws Exception {
        File tmp = new File(c.getFilesDir(), CACHE + ".tmp");
        try (FileOutputStream out = new FileOutputStream(tmp)) {
            out.write(data.toString().getBytes(StandardCharsets.UTF_8));
        }
        File real = new File(c.getFilesDir(), CACHE);
        if (!tmp.renameTo(real)) {
            real.delete();
            tmp.renameTo(real);
        }
        cached = data;
        prefs(c).edit().putLong("last_sync", System.currentTimeMillis())
                .putString("shop", data.optString("shop", shop(c))).apply();
    }

    public static synchronized JSONObject data(Context c) {
        if (cached != null) return cached;
        File f = new File(c.getFilesDir(), CACHE);
        if (!f.exists()) return new JSONObject();
        try (FileInputStream in = new FileInputStream(f)) {
            byte[] buf = new byte[(int) f.length()];
            int n = 0;
            while (n < buf.length) {
                int r = in.read(buf, n, buf.length - n);
                if (r < 0) break;
                n += r;
            }
            cached = new JSONObject(new String(buf, 0, n, StandardCharsets.UTF_8));
        } catch (Exception e) {
            cached = new JSONObject();
        }
        return cached;
    }

    public static JSONArray customers(Context c) {
        JSONArray a = data(c).optJSONArray("customers");
        return a == null ? new JSONArray() : a;
    }

    public static JSONObject customer(Context c, String id) {
        JSONArray a = customers(c);
        for (int i = 0; i < a.length(); i++) {
            JSONObject o = a.optJSONObject(i);
            if (o != null && id.equals(o.optString("id"))) return o;
        }
        return null;
    }

    public static JSONObject template(Context c) {
        JSONObject t = data(c).optJSONObject("template");
        return t == null ? new JSONObject() : t;
    }

    /** Put a newer template / business details into the cached data (after saving them on the PC). */
    public static synchronized void patch(Context c, String name, JSONObject value) {
        try {
            JSONObject d = data(c);
            d.put(name, value);
            File real = new File(c.getFilesDir(), CACHE);
            try (FileOutputStream out = new FileOutputStream(real)) {
                out.write(d.toString().getBytes(StandardCharsets.UTF_8));
            }
        } catch (Exception ignored) {
        }
    }
}
