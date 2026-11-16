package com.burhannexus.companion;

import android.content.Context;
import android.os.Build;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InterfaceAddress;
import java.net.NetworkInterface;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Talks to the Windows Business Manager on the same Wi-Fi. Never call from the main thread. */
public final class Api {
    private Api() {}

    public static final int HTTP_PORT = 47820, DISCOVERY_PORT = 47821;
    private static final String ASK = "BNBC_DISCOVER_1";

    public static class ApiException extends Exception {
        public final String code;
        public ApiException(String code, String message) {
            super(message);
            this.code = code;
        }
    }

    public static class Server {
        public String host, serverId, shop;
        public int port;
    }

    // ---------------- plain HTTP ----------------
    private static JSONObject http(String method, String host, int port, String path, JSONObject body,
                                   int connectMs, int readMs) throws Exception {
        HttpURLConnection con = (HttpURLConnection) new URL("http", host, port, path).openConnection();
        try {
            con.setConnectTimeout(connectMs);
            con.setReadTimeout(readMs);
            con.setRequestMethod(method);
            con.setUseCaches(false);
            if (body != null) {
                byte[] data = body.toString().getBytes(StandardCharsets.UTF_8);
                con.setDoOutput(true);
                con.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                con.setFixedLengthStreamingMode(data.length);
                try (OutputStream out = con.getOutputStream()) {
                    out.write(data);
                }
            }
            int status = con.getResponseCode();
            InputStream in = status >= 400 ? con.getErrorStream() : con.getInputStream();
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            if (in != null) {
                byte[] chunk = new byte[8192];
                int n;
                while ((n = in.read(chunk)) > 0) buf.write(chunk, 0, n);
                in.close();
            }
            JSONObject obj = new JSONObject(new String(buf.toByteArray(), StandardCharsets.UTF_8));
            if (status >= 400) {
                throw new ApiException(obj.optString("error", "server"), obj.optString("message", "Error " + status));
            }
            return obj;
        } finally {
            con.disconnect();
        }
    }

    public static Server hello(String host, int port, int connectMs) throws Exception {
        JSONObject o = http("GET", host, port, "/hello", null, connectMs, 4000);
        if (!"BNBC".equals(o.optString("app"))) throw new ApiException("not_bm", "Not a Business Manager");
        Server s = new Server();
        s.host = host;
        s.port = o.optInt("port", port);
        s.serverId = o.optString("server_id");
        s.shop = o.optString("shop");
        return s;
    }

    // ---------------- discovery: shout on the Wi-Fi, the PC answers ----------------
    private static Set<InetAddress> broadcastAddresses() {
        Set<InetAddress> out = new LinkedHashSet<>();
        try {
            out.add(InetAddress.getByName("255.255.255.255"));
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InterfaceAddress ia : ni.getInterfaceAddresses()) {
                    if (ia.getBroadcast() != null) out.add(ia.getBroadcast());
                }
            }
        } catch (Exception ignored) {
        }
        return out;
    }

    /** Every Business Manager that answers on this network within about 2.5 seconds. */
    public static List<Server> discover() {
        Map<String, Server> found = new LinkedHashMap<>();
        try (DatagramSocket sock = new DatagramSocket()) {
            sock.setBroadcast(true);
            sock.setSoTimeout(400);
            byte[] ask = ASK.getBytes(StandardCharsets.UTF_8);
            long end = System.currentTimeMillis() + 2500;
            long nextSend = 0;
            byte[] buf = new byte[1024];
            while (System.currentTimeMillis() < end) {
                if (System.currentTimeMillis() >= nextSend) {
                    for (InetAddress a : broadcastAddresses()) {
                        try {
                            sock.send(new DatagramPacket(ask, ask.length, a, DISCOVERY_PORT));
                        } catch (Exception ignored) {
                        }
                    }
                    nextSend = System.currentTimeMillis() + 800;
                }
                try {
                    DatagramPacket p = new DatagramPacket(buf, buf.length);
                    sock.receive(p);
                    JSONObject o = new JSONObject(new String(p.getData(), 0, p.getLength(), StandardCharsets.UTF_8));
                    if (!"BNBC".equals(o.optString("app"))) continue;
                    Server s = new Server();
                    s.host = p.getAddress().getHostAddress();
                    s.port = o.optInt("port", HTTP_PORT);
                    s.serverId = o.optString("server_id");
                    s.shop = o.optString("shop");
                    found.put(s.serverId, s);
                } catch (SocketTimeoutException ignored) {
                } catch (Exception ignored) {
                }
            }
        } catch (Exception ignored) {
        }
        return new ArrayList<>(found.values());
    }

    /** Where the paired PC is now: the last known address if it still answers, otherwise search the Wi-Fi. */
    private static Server locate(Context c) throws Exception {
        String wanted = Store.serverId(c), host = Store.host(c);
        if (!host.isEmpty()) {
            try {
                Server s = hello(host, Store.port(c), 1500);
                if (s.serverId.equals(wanted)) return s;
            } catch (Exception ignored) {       // the PC has another address now, or is off
            }
        }
        for (Server s : discover()) {
            if (s.serverId.equals(wanted)) {
                Store.saveAddress(c, s.host, s.port);
                return s;
            }
        }
        throw new ApiException("offline", "Computer not found on this Wi-Fi");
    }

    // ---------------- pairing ----------------
    public static void pair(Context c, Server s, String code) throws Exception {
        JSONObject hello = http("GET", s.host, s.port, "/hello", null, 3000, 5000);
        String deviceId = Store.deviceId(c);
        KeyPair kp = Crypto.newKeyPair();
        byte[] shared = Crypto.sharedSecret(kp.getPrivate(), Crypto.unb64(hello.getString("pub")));
        byte[] key = Crypto.sessionKey(shared, code, deviceId);
        JSONObject body = new JSONObject();
        body.put("device_id", deviceId);
        body.put("name", (Build.MANUFACTURER + " " + Build.MODEL).trim());
        body.put("pub", Crypto.b64(kp.getPublic().getEncoded()));
        body.put("proof", Crypto.proof(key, "pair|" + deviceId));
        JSONObject ans = http("POST", s.host, s.port, "/pair", body, 3000, 8000);
        String serverId = ans.optString("server_id");
        if (!Crypto.proof(key, "ok|" + serverId).equals(ans.optString("proof"))) {
            throw new ApiException("wrong_code", "The computer's answer could not be verified. Try again.");
        }
        Store.savePairing(c, key, serverId, ans.optString("shop", s.shop), s.host, s.port);
    }

    // ---------------- encrypted calls ----------------
    /** Returns the "data" of the answer. Throws ApiException("offline" | "not_paired" | "conflict" | "invalid"...). */
    public static Object call(Context c, String op, JSONObject args) throws Exception {
        byte[] key = Store.key(c);
        if (key == null) throw new ApiException("not_paired", "Not paired with a computer yet");
        Server s = locate(c);
        String deviceId = Store.deviceId(c);
        JSONObject req = new JSONObject();
        req.put("op", op);
        req.put("args", args == null ? new JSONObject() : args);
        String[] sealed = Crypto.seal(key, deviceId, req.toString().getBytes(StandardCharsets.UTF_8));
        JSONObject env = new JSONObject();
        env.put("d", deviceId);
        env.put("n", sealed[0]);
        env.put("c", sealed[1]);
        JSONObject ans;
        try {
            ans = http("POST", s.host, s.port, "/api", env, 3000, 20000);
        } catch (ApiException e) {
            throw e;
        } catch (Exception e) {
            throw new ApiException("offline", "Could not reach the computer");
        }
        JSONObject out = new JSONObject(new String(
                Crypto.open(key, deviceId, ans.getString("n"), ans.getString("c")), StandardCharsets.UTF_8));
        if (!out.optBoolean("ok")) {
            ApiException e = new ApiException(out.optString("error", "invalid"), out.optString("message", "Error"));
            if ("conflict".equals(e.code) && out.optJSONObject("data") != null) {
                Store.patch(c, "template", out.optJSONObject("data"));
            }
            throw e;
        }
        return out.opt("data");
    }
}
