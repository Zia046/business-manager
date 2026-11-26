package com.burhannexus.companion;

import android.content.Context;

import com.burhannexus.companion.sync.Engine;
import com.burhannexus.companion.sync.Json;
import com.burhannexus.companion.sync.SqliteStore;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;

/** The phone's business data (one Engine for the whole app) and how it reaches the computer. */
public final class Local {
    private Local() {}

    private static Engine engine;

    public static synchronized Engine engine(Context c) {
        if (engine == null) engine = new Engine(new SqliteStore(c), Store.deviceId(c));
        return engine;
    }

    /** The encrypted connection to the paired computer (finds it on the Wi-Fi by itself). */
    public static Engine.Transport transport(Context context) {
        final Context c = context.getApplicationContext();
        return (op, args) -> {
            Object data;
            try {
                data = Api.call(c, op, new JSONObject(Json.write(args)));
            } catch (Api.ApiException e) {
                if ("offline".equals(e.code)) throw new IOException(e.getMessage());
                throw e;
            }
            if (data == null || data == JSONObject.NULL) return null;
            if (data instanceof JSONObject || data instanceof JSONArray) return Json.read(data.toString());
            return Json.read(JSONObject.quote(String.valueOf(data)));
        };
    }
}
