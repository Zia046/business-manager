import com.burhannexus.companion.Crypto;
import com.burhannexus.companion.sync.Engine;
import com.burhannexus.companion.sync.Json;
import com.burhannexus.companion.sync.MemoryStore;
import com.burhannexus.companion.sync.Op;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Runs the Android app's sync engine on a desktop JVM against the real Windows program (tests/test_core.py drives it).
 * One command per line on stdin, one JSON answer per line on stdout.
 */
public class SyncHarness {
    static String host;
    static int port;
    static byte[] key;
    static String deviceId;
    static boolean offline;
    static String breakAfter;          // cut the connection right after this call reached the computer

    static Map<String, Object> http(String path, String body) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL("http", host, port, path).openConnection();
        c.setConnectTimeout(3000);
        c.setReadTimeout(20000);
        if (body != null) {
            byte[] b = body.getBytes(StandardCharsets.UTF_8);
            c.setRequestMethod("POST");
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            try (OutputStream o = c.getOutputStream()) { o.write(b); }
        }
        int st = c.getResponseCode();
        InputStream in = st >= 400 ? c.getErrorStream() : c.getInputStream();
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        byte[] chunk = new byte[8192];
        int n;
        while ((n = in.read(chunk)) > 0) buf.write(chunk, 0, n);
        Map<String, Object> o = Json.obj(new String(buf.toByteArray(), StandardCharsets.UTF_8));
        if (st >= 400) throw new IOException("HTTP " + st + " " + o.get("message"));
        return o;
    }

    static Engine.Transport transport = (op, args) -> {
        if (offline) throw new IOException("offline");
        String[] sealed = Crypto.seal(key, deviceId, Json.write(Json.of("op", op, "args", args)).getBytes(StandardCharsets.UTF_8));
        Map<String, Object> ans = http("/api", Json.write(Json.of("d", deviceId, "n", sealed[0], "c", sealed[1])));
        if (op.equals(breakAfter)) {
            breakAfter = null;
            throw new IOException("connection broken after " + op);
        }
        Map<String, Object> out = Json.obj(new String(Crypto.open(key, deviceId, Json.txt(ans.get("n")), Json.txt(ans.get("c"))),
                StandardCharsets.UTF_8));
        if (!Boolean.TRUE.equals(out.get("ok"))) throw new Exception(Json.txt(out.get("message")));
        return out.get("data");
    };

    public static void main(String[] a) throws Exception {
        System.setOut(new java.io.PrintStream(new java.io.FileOutputStream(java.io.FileDescriptor.out), true, "UTF-8"));
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        MemoryStore store = new MemoryStore();
        Engine engine = null;
        String line;
        while ((line = in.readLine()) != null) {
            String[] p = line.split(" ", 2);
            Object out;
            try {
                switch (p[0]) {
                    case "pair": {                       // pair <host> <port> <code> <deviceId>
                        String[] x = p[1].split(" ");
                        host = x[0]; port = Integer.parseInt(x[1]); deviceId = x[3];
                        Map<String, Object> hello = http("/hello", null);
                        KeyPair kp = Crypto.newKeyPair();
                        key = Crypto.sessionKey(Crypto.sharedSecret(kp.getPrivate(), Crypto.unb64(Json.txt(hello.get("pub")))), x[2], deviceId);
                        http("/pair", Json.write(Json.of("device_id", deviceId, "name", "Harness", "pub",
                                Crypto.b64(kp.getPublic().getEncoded()), "proof", Crypto.proof(key, "pair|" + deviceId))));
                        engine = new Engine(store, deviceId);
                        out = "paired";
                        break;
                    }
                    case "sync": out = engine.sync(transport) + " " + engine.state() + " " + engine.lastError(); break;
                    case "offline": offline = Boolean.parseBoolean(p[1]); out = offline; break;
                    case "break_after": breakAfter = p[1]; out = p[1]; break;
                    case "restart": engine = new Engine(store, deviceId); out = "restarted"; break;   // app closed and opened
                    case "record": {
                        String[] x = p[1].split(" ", 2);
                        Op op = engine.record(x[0], Json.obj(x[1]));
                        out = Json.of("op_id", op.opId, "no", op.docNo);
                        break;
                    }
                    case "dashboard": out = engine.dashboard(); break;
                    case "products": out = new ArrayList<>(engine.products().values()); break;
                    case "parties": out = new ArrayList<>(engine.parties(p[1]).values()); break;
                    case "phones": out = engine.phonesInStock(Long.parseLong(p[1])); break;
                    case "docs": out = engine.documents(p[1]); break;
                    case "ops": {
                        List<Object> l = new ArrayList<>();
                        for (Op o : store.ops()) l.add(Json.of("op_id", o.opId, "kind", o.kind, "status", o.status,
                                "message", o.message, "doc_no", o.docNo));
                        out = l;
                        break;
                    }
                    case "state": out = engine.state(); break;
                    default: out = "unknown command";
                }
                System.out.println(Json.write(Json.of("ok", true, "out", out)));
            } catch (Engine.Invalid e) {
                System.out.println(Json.write(Json.of("ok", false, "invalid", e.getMessage())));
            } catch (Exception e) {
                System.out.println(Json.write(Json.of("ok", false, "error", String.valueOf(e))));
            }
            System.out.flush();
        }
    }
}
