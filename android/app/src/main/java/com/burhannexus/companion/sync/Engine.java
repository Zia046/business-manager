package com.burhannexus.companion.sync;

import java.io.IOException;
import java.security.SecureRandom;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Date;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * The phone's business data and its two-way sync with the Windows Business Manager. Plain Java (no Android).
 *
 * Local first: every sale, purchase, return, payment, expense or new customer is saved on the phone at once as a
 * transaction in the outbox, and the screens show its effect straight away (stock, balances, history).
 *
 * Sync (automatic): 1. the outbox goes to the computer, which applies each transaction with its own business rules
 * and answers per transaction (saved / conflict); a transaction is never applied twice because its id is kept;
 * 2. the phone gets the computer's records that are new or changed since last time and drops the ones that are gone.
 * Step 2 is saved in one go, and only then are the computer-saved transactions taken out of the "still to add"
 * list, so a broken connection can never count a sale twice or lose one.
 */
public final class Engine {
    public interface Transport {
        /** One call to the computer. Returns the answer's data; throws IOException when it cannot be reached. */
        Object call(String op, Map<String, Object> args) throws Exception;
    }

    public interface Listener {
        void onState(String state);
    }

    public static final class Invalid extends Exception {
        public Invalid(String message) { super(message); }
    }

    // the status line of the app
    public static final String CONNECTED = "Connected – Auto Sync Active";
    public static final String OFFLINE = "Offline Mode – Changes Saved Locally";
    public static final String SYNCING = "Synchronizing Data...";
    public static final String COMPLETED = "Sync Completed";
    public static final String RETRY = "Sync Retry Pending";

    public static final String[] KINDS = {"product", "serial", "party", "invoice", "purchase", "return", "voucher",
            "expense", "meta"};
    private static final int FETCH_BATCH = 400, PUSH_BATCH = 50;

    public final SyncStore store;
    private final String deviceId;
    private final CopyOnWriteArrayList<Listener> listeners = new CopyOnWriteArrayList<>();
    private volatile String state = OFFLINE;
    private volatile String lastError = "";

    public Engine(SyncStore store, String deviceId) {
        this.store = store;
        this.deviceId = deviceId;
    }

    public void addListener(Listener l) { listeners.addIfAbsent(l); }
    public void removeListener(Listener l) { listeners.remove(l); }
    public String state() { return state; }
    public String lastError() { return lastError; }

    private void setState(String s) {
        state = s;
        for (Listener l : listeners) l.onState(s);
    }

    public static String now() {
        return new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(new Date());
    }

    // =====================================================================================================
    // sync
    // =====================================================================================================
    /** One full sync. Returns true when everything was exchanged. Never throws. */
    public synchronized boolean sync(Transport t) {
        setState(SYNCING);
        try {
            Map<String, Object> hello = Json.map(t.call("sync_hello", Json.of()));
            String series = Json.txt(hello.get("series"));
            store.setMeta("series", series);
            store.setMeta("shop", Json.txt(hello.get("shop")));
            long serverLast = Json.lng(hello.get("series_last"));
            String key = "counter_" + series;
            long mine = store.meta(key) == null ? 0 : Long.parseLong(store.meta(key));
            if (serverLast > mine) store.setMeta(key, String.valueOf(serverLast));   // e.g. after a reinstall

            push(t);
            pull(t);
            store.setMeta("last_sync", now());
            lastError = "";
            setState(COMPLETED);
            setState(CONNECTED);
            return true;
        } catch (IOException e) {
            lastError = "Computer not reachable";
            setState(hasUnsent() ? RETRY : OFFLINE);
            return false;
        } catch (Exception e) {
            lastError = e.getMessage() == null ? e.toString() : e.getMessage();
            setState(RETRY);
            return false;
        }
    }

    public boolean hasUnsent() {
        for (Op o : store.ops()) if (Op.PENDING.equals(o.status)) return true;
        return false;
    }

    private void push(Transport t) throws Exception {
        while (true) {
            List<Op> batch = new ArrayList<>();
            for (Op o : store.ops()) {
                if (Op.PENDING.equals(o.status)) batch.add(o);
                if (batch.size() >= PUSH_BATCH) break;
            }
            if (batch.isEmpty()) return;
            List<Object> payload = new ArrayList<>();
            for (Op o : batch) {
                payload.add(Json.of("op_id", o.opId, "kind", o.kind, "made_at", o.madeAt, "data", Json.read(o.data)));
            }
            List<Object> answers = Json.list(t.call("sync_push", Json.of("ops", payload)));
            Map<String, Map<String, Object>> byId = new HashMap<>();
            for (Object a : answers) byId.put(Json.txt(Json.map(a).get("op_id")), Json.map(a));
            boolean progress = false;
            for (Op o : batch) {
                Map<String, Object> a = byId.get(o.opId);
                if (a == null) continue;
                String st = Json.txt(a.get("status"));
                o.status = "applied".equals(st) ? Op.APPLIED : "dismissed".equals(st) ? Op.DISMISSED : Op.CONFLICT;
                o.message = Json.txt(a.get("message"));
                o.docType = Json.txt(a.get("doc_type"));
                o.docId = Json.lng(a.get("doc_id"));
                if (!Json.txt(a.get("doc_no")).isEmpty()) o.docNo = Json.txt(a.get("doc_no"));
                store.updateOp(o);
                progress = true;
            }
            if (!progress) throw new Exception("The computer did not answer for the sent transactions");
        }
    }

    private void pull(Transport t) throws Exception {
        Map<String, Object> man = Json.map(t.call("sync_manifest", Json.of()));
        Map<String, Map<Long, String>> remote = new HashMap<>();
        Map<String, List<Object>> want = new LinkedHashMap<>();
        for (String k : KINDS) {
            Map<Long, String> r = new HashMap<>();
            for (Object pair : Json.list(man.get(k))) {
                List<Object> p = Json.list(pair);
                r.put(Json.lng(p.get(0)), Json.txt(p.get(1)));
            }
            remote.put(k, r);
            Map<Long, String> mine = store.fingerprints(k);
            List<Object> ids = new ArrayList<>();
            for (Map.Entry<Long, String> e : r.entrySet()) {
                if (!e.getValue().equals(mine.get(e.getKey()))) ids.add(e.getKey());
            }
            want.put(k, ids);
        }
        // fetch everything first, keep it aside, then save it all in one go
        final Map<String, List<Map<String, Object>>> got = new HashMap<>();
        while (true) {
            Map<String, Object> ask = new LinkedHashMap<>();
            int n = 0;
            for (String k : KINDS) {
                List<Object> ids = want.get(k);
                if (ids.isEmpty() || n >= FETCH_BATCH) continue;
                int take = Math.min(ids.size(), FETCH_BATCH - n);
                ask.put(k, new ArrayList<>(ids.subList(0, take)));
                ids.subList(0, take).clear();
                n += take;
            }
            if (n == 0) break;
            Map<String, Object> ans = Json.map(t.call("sync_fetch", Json.of("want", ask)));
            for (Map.Entry<String, Object> e : ans.entrySet()) {
                List<Map<String, Object>> list = got.computeIfAbsent(e.getKey(), x -> new ArrayList<>());
                for (Object r : Json.list(e.getValue())) list.add(Json.map(r));
            }
        }
        store.atomically(() -> {
            for (Map.Entry<String, List<Map<String, Object>>> e : got.entrySet()) {
                for (Map<String, Object> r : e.getValue()) {
                    String fp = Json.txt(r.remove("_fp"));
                    store.putRecord(e.getKey(), Json.lng(r.get("id")), fp, Json.write(r));
                }
            }
            for (String k : KINDS) {
                Map<Long, String> r = remote.get(k);
                for (Long id : new ArrayList<>(store.fingerprints(k).keySet())) {
                    if (!r.containsKey(id)) store.deleteRecord(k, id);      // gone on the computer
                }
            }
            for (Op o : store.ops()) {                                       // now part of our copy
                if (Op.APPLIED.equals(o.status)) {
                    o.status = Op.DONE;
                    store.updateOp(o);
                }
            }
        });
    }

    // =====================================================================================================
    // records as the screens see them: the computer's copy + what is still on its way
    // =====================================================================================================
    public List<Map<String, Object>> list(String kind) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (String s : store.records(kind)) out.add(Json.obj(s));
        return out;
    }

    public Map<String, Object> get(String kind, long id) {
        String s = store.record(kind, id);
        return s == null ? null : Json.obj(s);
    }

    public Map<String, Object> meta() {
        String s = store.record("meta", 1);
        return s == null ? new LinkedHashMap<>() : Json.obj(s);
    }

    public List<Op> unfinished() {
        List<Op> out = new ArrayList<>();
        for (Op o : store.ops()) if (o.counts()) out.add(o);
        return out;
    }

    public List<Op> conflicts() {
        List<Op> out = new ArrayList<>();
        for (Op o : store.ops()) if (Op.CONFLICT.equals(o.status)) out.add(o);
        return out;
    }

    /** "123" for a computer record, "op:<id>" for one made on this phone and not yet on the computer. */
    public static Object ref(String key) {
        if (key != null && key.startsWith("op:")) return Json.of("op", key.substring(3));
        return Long.parseLong(key);
    }

    public static String key(Object ref) {
        if (ref instanceof Map) return "op:" + Json.txt(Json.map(ref).get("op"));
        return String.valueOf(Json.lng(ref));
    }

    /** Products with the stock the phone should show now. */
    public Map<String, Map<String, Object>> products() {
        Map<String, Map<String, Object>> out = new LinkedHashMap<>();
        for (Map<String, Object> p : list("product")) out.put(String.valueOf(Json.lng(p.get("id"))), p);
        for (Op o : unfinished()) {
            Map<String, Object> d = Json.obj(o.data);
            double sign = stockSign(o.kind);
            if (sign == 0) continue;
            for (Object it : Json.list(d.get("items"))) {
                Map<String, Object> line = Json.map(it);
                Map<String, Object> p = out.get(key(line.get("product_id")));
                if (p != null) p.put("qty", Json.num(p.get("qty")) + sign * Json.num(line.get("qty")));
            }
        }
        return out;
    }

    private static double stockSign(String kind) {
        switch (kind) {
            case "sale": case "purchase_return": return -1;
            case "purchase": case "sale_return": return 1;
            default: return 0;
        }
    }

    /** IMEIs of one phone model that are in the shop now (computer's list, minus/plus what is on its way). */
    public List<Map<String, Object>> phonesInStock(long productId) {
        Set<String> gone = new HashSet<>();
        List<Map<String, Object>> extra = new ArrayList<>();
        for (Op o : unfinished()) {
            Map<String, Object> d = Json.obj(o.data);
            for (Object it : Json.list(d.get("items"))) {
                Map<String, Object> line = Json.map(it);
                if (!key(line.get("product_id")).equals(String.valueOf(productId))) continue;
                if ("sale".equals(o.kind) || "purchase_return".equals(o.kind)) {
                    gone.add(Json.txt(line.get("serial")));
                } else if ("sale_return".equals(o.kind)) {
                    extra.add(Json.of("serial", Json.txt(line.get("serial")), "imei2", line.get("serial2"),
                            "product_id", productId, "status", "in_stock"));
                } else if ("purchase".equals(o.kind)) {
                    for (Object s : Json.list(line.get("serials"))) {
                        List<Object> pair = Json.list(s);
                        extra.add(Json.of("serial", Json.txt(pair.get(0)), "imei2", pair.size() > 1 ? pair.get(1) : null,
                                "product_id", productId, "status", "in_stock"));
                    }
                }
            }
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> s : list("serial")) {
            if (Json.lng(s.get("product_id")) == productId && "in_stock".equals(s.get("status"))
                    && !gone.contains(Json.txt(s.get("serial")))) out.add(s);
        }
        for (Map<String, Object> s : extra) if (!gone.contains(Json.txt(s.get("serial")))) out.add(s);
        return out;
    }

    /** Was this IMEI sold (on the computer or on the phone) and not returned yet? */
    public boolean isSold(String imei) {
        for (Op o : unfinished()) {
            Map<String, Object> d = Json.obj(o.data);
            for (Object it : Json.list(d.get("items"))) {
                if (imei.equals(Json.txt(Json.map(it).get("serial")))) {
                    if ("sale".equals(o.kind)) return true;
                    if ("sale_return".equals(o.kind)) return false;
                }
            }
        }
        for (Map<String, Object> s : list("serial")) {
            if (imei.equals(Json.txt(s.get("serial"))) || imei.equals(Json.txt(s.get("imei2"))))
                return "sold".equals(s.get("status"));
        }
        return false;
    }

    private boolean imeiKnown(String imei) {
        for (Map<String, Object> s : list("serial")) {
            if (imei.equals(Json.txt(s.get("serial"))) || imei.equals(Json.txt(s.get("imei2")))) return true;
        }
        for (Op o : unfinished()) {
            if (!"purchase".equals(o.kind)) continue;
            for (Object it : Json.list(Json.obj(o.data).get("items"))) {
                for (Object s : Json.list(Json.map(it).get("serials"))) {
                    for (Object x : Json.list(s)) if (imei.equals(Json.txt(x))) return true;
                }
            }
        }
        return false;
    }

    /** Customers or suppliers with the balance the phone should show now; also the ones made on the phone. */
    public Map<String, Map<String, Object>> parties(String kind) {
        Map<String, Map<String, Object>> out = new LinkedHashMap<>();
        for (Map<String, Object> p : list("party")) {
            if (kind.equals(p.get("kind")) && Json.num(p.get("active")) != 0) {
                out.put(String.valueOf(Json.lng(p.get("id"))), p);
            }
        }
        for (Op o : unfinished()) {
            Map<String, Object> d = Json.obj(o.data);
            if (("customer_add".equals(o.kind) && "customer".equals(kind))
                    || ("supplier_add".equals(o.kind) && "supplier".equals(kind))) {
                out.put("op:" + o.opId, Json.of("id", "op:" + o.opId, "kind", kind, "name", d.get("name"),
                        "phone", d.get("phone"), "address", d.get("address"), "balance", 0.0, "is_walkin", 0,
                        "pending", true));
                continue;
            }
            double change = balanceChange(o.kind, d, kind);
            if (change == 0) continue;
            Map<String, Object> p = out.get(key(d.get("party_id")));
            if (p != null) p.put("balance", Json.num(p.get("balance")) + change);
        }
        return out;
    }

    private static double balanceChange(String opKind, Map<String, Object> d, String partyKind) {
        double total = total(opKind, d);
        if ("customer".equals(partyKind)) {
            switch (opKind) {
                case "sale": return total - Json.num(d.get("paid"));
                case "receipt": return -Json.num(d.get("amount"));
                case "sale_return": return -(total - Json.num(d.get("refunded")));
                default: return 0;
            }
        }
        switch (opKind) {
            case "purchase": return total - Json.num(d.get("paid"));
            case "supplier_payment": return -Json.num(d.get("amount"));
            case "purchase_return": return -(total - Json.num(d.get("received")));
            default: return 0;
        }
    }

    /** The document total, worked out exactly like the computer does (line = qty x price - line discount). */
    public static double total(String kind, Map<String, Object> d) {
        double sub = 0;
        for (Object it : Json.list(d.get("items"))) {
            Map<String, Object> l = Json.map(it);
            sub += round2(Json.num(l.get("qty")) * Json.num(l.get("price")) - Json.num(l.get("discount")));
        }
        if ("sale".equals(kind)) sub -= Json.num(d.get("discount"));
        return round2(sub);
    }

    public static double round2(double v) {
        return Math.round(v * 100.0) / 100.0;
    }

    /** Documents of one type for history screens, newest first: the computer's ones and the phone's unsent ones. */
    public List<Map<String, Object>> documents(String docKind) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> r : list(docKind)) {
            r.put("sync", "synced");
            out.add(r);
        }
        for (Op o : store.ops()) {
            if (!o.counts() && !Op.CONFLICT.equals(o.status)) continue;
            String dk = docKindOf(o.kind);
            if (!docKind.equals(dk)) continue;
            Map<String, Object> d = Json.obj(o.data);
            Map<String, Object> r = new LinkedHashMap<>(d);
            r.put("id", "op:" + o.opId);
            r.put("no", !o.docNo.isEmpty() ? o.docNo : Json.txt(d.get("no")).isEmpty() ? "(new)" : d.get("no"));
            r.put("date", o.madeAt);
            r.put("total", "voucher".equals(dk) || "expense".equals(dk) ? Json.num(d.get("amount")) : total(o.kind, d));
            r.put("party", partyName(d.get("party_id")));
            r.put("op_kind", o.kind);
            r.put("status", "active");
            r.put("sync", Op.CONFLICT.equals(o.status) ? "conflict" : "pending");
            r.put("message", o.message);
            if ("return".equals(dk)) r.put("kind", "sale_return".equals(o.kind) ? "sale" : "purchase");
            if ("voucher".equals(dk)) r.put("kind", "receipt".equals(o.kind) ? "receipt" : "payment");
            List<Object> lines = new ArrayList<>();
            Map<String, Map<String, Object>> prods = productNames();
            for (Object it : Json.list(d.get("items"))) {
                Map<String, Object> l = new LinkedHashMap<>(Json.map(it));
                Map<String, Object> p = prods.get(key(l.get("product_id")));
                l.put("name", p == null ? "?" : p.get("name"));
                lines.add(l);
            }
            r.put("lines", lines);
            out.add(r);
        }
        Collections.sort(out, (a, b) -> Json.txt(b.get("date")).compareTo(Json.txt(a.get("date"))));
        return out;
    }

    private static String docKindOf(String opKind) {
        switch (opKind) {
            case "sale": return "invoice";
            case "purchase": return "purchase";
            case "sale_return": case "purchase_return": return "return";
            case "receipt": case "supplier_payment": return "voucher";
            case "expense": return "expense";
            default: return "";
        }
    }

    private Map<String, Map<String, Object>> productNames() {
        Map<String, Map<String, Object>> m = new HashMap<>();
        for (Map<String, Object> p : list("product")) m.put(String.valueOf(Json.lng(p.get("id"))), p);
        return m;
    }

    public String partyName(Object ref) {
        if (ref == null) return "";
        String k = key(ref);
        for (String kind : new String[] {"customer", "supplier"}) {
            Map<String, Object> p = parties(kind).get(k);
            if (p != null) return Json.txt(p.get("name"));
        }
        return "";
    }

    /** Dashboard figures worked out on the phone from its data (correct also while offline). */
    public Map<String, Object> dashboard() {
        String today = now().substring(0, 10), month = today.substring(0, 7);
        double todaySales = 0, monthSales = 0, stockValue = 0, receivable = 0, payable = 0;
        int todayCount = 0, low = 0, phones = 0;
        for (Map<String, Object> inv : documents("invoice")) {
            if ("cancelled".equals(inv.get("status")) || "conflict".equals(inv.get("sync"))) continue;
            String date = Json.txt(inv.get("date"));
            double t = Json.num(inv.get("total"));
            if (date.startsWith(today)) { todaySales += t; todayCount++; }
            if (date.startsWith(month)) monthSales += t;
        }
        for (Map<String, Object> p : products().values()) {
            if (Json.num(p.get("active")) == 0) continue;
            double q = Json.num(p.get("qty"));
            stockValue += Math.max(q, 0) * Json.num(p.get("avg_cost"));
            boolean phone = Json.num(p.get("track_serial")) != 0;
            if (phone) phones += (int) Math.max(q, 0);
            else if (q <= Json.num(p.get("low_stock_level"))) low++;
        }
        for (Map<String, Object> c : parties("customer").values()) receivable += Math.max(Json.num(c.get("balance")), 0);
        for (Map<String, Object> s : parties("supplier").values()) payable += Math.max(Json.num(s.get("balance")), 0);
        double cash = Json.num(Json.map(meta().get("dashboard")).get("cash"));
        for (Op o : unfinished()) {
            Map<String, Object> d = Json.obj(o.data);
            switch (o.kind) {
                case "sale": cash += Json.num(d.get("paid")); break;
                case "receipt": cash += Json.num(d.get("amount")); break;
                case "purchase_return": cash += Json.num(d.get("received")); break;
                case "purchase": cash -= Json.num(d.get("paid")); break;
                case "supplier_payment": case "expense": cash -= Json.num(d.get("amount")); break;
                case "sale_return": cash -= Json.num(d.get("refunded")); break;
                default:
            }
        }
        return Json.of("today_sales", round2(todaySales), "today_invoices", todayCount, "month_sales", round2(monthSales),
                "stock_value", round2(stockValue), "receivable", round2(receivable), "payable", round2(payable),
                "low_stock", low, "phones_in_stock", phones, "cash", round2(cash),
                "unsent", unfinishedCount(Op.PENDING), "conflicts", conflicts().size());
    }

    private int unfinishedCount(String status) {
        int n = 0;
        for (Op o : store.ops()) if (status.equals(o.status)) n++;
        return n;
    }

    // =====================================================================================================
    // new transactions (checked with the same rules the computer uses, then saved in the outbox)
    // =====================================================================================================
    private static final SecureRandom RNG = new SecureRandom();

    private String newId() {
        String dev = deviceId.length() > 10 ? deviceId.substring(0, 10) : deviceId;
        return dev + "-" + Long.toString(System.currentTimeMillis(), 36) + "-" + Long.toString(Math.abs(RNG.nextLong()), 36);
    }

    public String series() {
        return store.meta("series");
    }

    /** Checks and saves one transaction. `data` uses refs (Long or {"op": id}) for customers/suppliers/products. */
    public synchronized Op record(String kind, Map<String, Object> data) throws Invalid {
        check(kind, data);
        final Op op = new Op();
        op.opId = newId();
        op.kind = kind;
        op.madeAt = now();
        final String[] counterKey = {null};
        final long[] counterVal = {0};
        if ("sale".equals(kind)) {
            String series = series();
            if (series == null || series.isEmpty()) {
                throw new Invalid("Connect to the computer once before the first sale (to get this phone's invoice numbers).");
            }
            counterKey[0] = "counter_" + series;
            String c = store.meta(counterKey[0]);
            counterVal[0] = (c == null ? 0 : Long.parseLong(c)) + 1;
            data.put("no", String.format(Locale.US, "%s-%05d", series, counterVal[0]));
            op.docNo = Json.txt(data.get("no"));
        }
        op.data = Json.write(data);
        store.atomically(() -> {
            store.addOp(op);
            if (counterKey[0] != null) store.setMeta(counterKey[0], String.valueOf(counterVal[0]));
        });
        return op;
    }

    private void check(String kind, Map<String, Object> d) throws Invalid {
        switch (kind) {
            case "customer_add": case "supplier_add":
                if (Json.txt(d.get("name")).trim().isEmpty()) throw new Invalid("Name is required");
                return;
            case "expense":
                if (Json.txt(d.get("category")).trim().isEmpty()) throw new Invalid("Write the expense category");
                if (Json.num(d.get("amount")) <= 0) throw new Invalid("Amount must be more than zero");
                return;
            case "receipt": case "supplier_payment": {
                party(d, "receipt".equals(kind) ? "customer" : "supplier");
                if (Json.num(d.get("amount")) <= 0) throw new Invalid("Amount must be more than zero");
                return;
            }
            default:
        }
        boolean customer = "sale".equals(kind) || "sale_return".equals(kind);
        Map<String, Object> party = party(d, customer ? "customer" : "supplier");
        List<Object> items = Json.list(d.get("items"));
        if (items.isEmpty()) throw new Invalid("Add at least one product");
        Map<String, Map<String, Object>> prods = products();
        Map<String, Double> wantQty = new HashMap<>();
        Set<String> imeis = new HashSet<>();
        for (Object it : items) {
            Map<String, Object> l = Json.map(it);
            Map<String, Object> p = prods.get(key(l.get("product_id")));
            if (p == null) throw new Invalid("Product not found");
            String name = Json.txt(p.get("name"));
            double qty = Json.num(l.get("qty")), price = Json.num(l.get("price")), disc = Json.num(l.get("discount"));
            if (qty <= 0 || price < 0 || disc < 0) throw new Invalid("Quantity must be positive; price/discount cannot be negative");
            if (qty * price - disc < -0.004) throw new Invalid("Line discount is larger than the line amount");
            boolean phone = Json.num(p.get("track_serial")) != 0;
            long pid = Json.lng(p.get("id"));
            if (phone && "purchase".equals(kind)) {
                List<Object> serials = Json.list(l.get("serials"));
                if (serials.size() != (int) qty) throw new Invalid("'" + name + "': enter one IMEI for each phone (" + (int) qty + ")");
                boolean dbl = "double".equals(p.get("imei_mode"));
                for (Object s : serials) {
                    List<Object> pair = Json.list(s);
                    String i1 = Json.txt(pair.get(0)), i2 = pair.size() > 1 ? Json.txt(pair.get(1)) : "";
                    imei(i1, name);
                    if (dbl) {
                        imei(i2, name);
                        if (i1.equals(i2)) throw new Invalid("IMEI 1 and IMEI 2 cannot be the same");
                    } else if (!i2.isEmpty()) {
                        throw new Invalid("'" + name + "' has a single IMEI - leave IMEI 2 empty");
                    }
                    for (String x : dbl ? new String[] {i1, i2} : new String[] {i1}) {
                        if (!imeis.add(x) || imeiKnown(x)) throw new Invalid("IMEI " + x + " is already in your records");
                    }
                }
            } else if (phone) {
                if (qty != 1) throw new Invalid("'" + name + "': one phone per line, with its IMEI");
                String i1 = Json.txt(l.get("serial"));
                imei(i1, name);
                if (!imeis.add(i1)) throw new Invalid("IMEI " + i1 + " is twice on this bill");
                boolean inShop = false;
                for (Map<String, Object> s : phonesInStock(pid)) {
                    if (i1.equals(Json.txt(s.get("serial"))) || i1.equals(Json.txt(s.get("imei2")))) inShop = true;
                }
                if ("sale_return".equals(kind)) {
                    if (!isSold(i1)) throw new Invalid("This phone (IMEI " + i1 + ") was not sold, so it cannot be returned");
                } else if (!inShop) {
                    throw new Invalid("This phone (IMEI " + i1 + ") is not in stock");
                }
            }
            if ("sale".equals(kind) || "purchase_return".equals(kind)) {
                String k = key(l.get("product_id"));
                double want = wantQty.getOrDefault(k, 0.0) + qty;
                wantQty.put(k, want);
                if (want > Json.num(p.get("qty")) + 1e-9) {
                    throw new Invalid("Not enough stock for '" + name + "' (available " + fmt(Json.num(p.get("qty"))) + ")");
                }
            }
        }
        double total = total(kind, d);
        if ("sale".equals(kind)) {
            double disc = Json.num(d.get("discount")), paid = round2(Json.num(d.get("paid")));
            if (disc < 0 || total < 0) throw new Invalid("Invalid invoice discount");
            if (paid < 0 || paid > total + 0.004) throw new Invalid("Paid amount must be between 0 and the invoice total");
            if (Json.num(party.get("is_walkin")) != 0 && Math.abs(paid - total) > 0.004) {
                throw new Invalid("Walk-in customer must pay in full. Select a saved customer for credit.");
            }
        }
        String cash = "sale_return".equals(kind) ? "refunded" : "purchase_return".equals(kind) ? "received"
                : "purchase".equals(kind) ? "paid" : null;
        if (cash != null) {
            double v = Json.num(d.get(cash));
            if (v < 0 || v > total + 0.004) throw new Invalid("Amount paid back cannot be more than the total");
        }
    }

    private Map<String, Object> party(Map<String, Object> d, String kind) throws Invalid {
        Object ref = d.get("party_id");
        Map<String, Object> p = ref == null ? null : parties(kind).get(key(ref));
        if (p == null) throw new Invalid("customer".equals(kind) ? "Select the customer" : "Select the supplier");
        if ("receipt".equals(kind) && Json.num(p.get("is_walkin")) != 0) throw new Invalid("Select a saved customer");
        return p;
    }

    private static void imei(String s, String name) throws Invalid {
        if (!s.matches("[0-9]{10,100}")) throw new Invalid("'" + name + "': IMEI must be digits only, at least 10");
    }

    private static String fmt(double v) {
        return v == Math.rint(v) ? String.valueOf((long) v) : String.valueOf(v);
    }
}
