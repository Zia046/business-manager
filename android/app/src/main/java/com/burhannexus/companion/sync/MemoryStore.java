package com.burhannexus.companion.sync;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/** In-memory SyncStore (used by the desktop tests; the app uses SqliteStore). */
public final class MemoryStore implements SyncStore {
    private final Map<String, String> meta = new HashMap<>();
    private final Map<String, TreeMap<Long, String[]>> recs = new HashMap<>();
    private final LinkedHashMap<String, Op> ops = new LinkedHashMap<>();
    private long seq;

    public synchronized String meta(String key) { return meta.get(key); }
    public synchronized void setMeta(String key, String value) { meta.put(key, value); }

    private TreeMap<Long, String[]> kind(String k) {
        return recs.computeIfAbsent(k, x -> new TreeMap<>());
    }

    public synchronized Map<Long, String> fingerprints(String k) {
        Map<Long, String> out = new HashMap<>();
        for (Map.Entry<Long, String[]> e : kind(k).entrySet()) out.put(e.getKey(), e.getValue()[0]);
        return out;
    }

    public synchronized void putRecord(String k, long id, String fp, String json) { kind(k).put(id, new String[] {fp, json}); }
    public synchronized void deleteRecord(String k, long id) { kind(k).remove(id); }

    public synchronized String record(String k, long id) {
        String[] r = kind(k).get(id);
        return r == null ? null : r[1];
    }

    public synchronized List<String> records(String k) {
        List<String> out = new ArrayList<>();
        for (String[] r : kind(k).values()) out.add(r[1]);
        return out;
    }

    public synchronized void addOp(Op op) {
        op.seq = ++seq;
        ops.put(op.opId, copy(op));
    }

    public synchronized void updateOp(Op op) { ops.put(op.opId, copy(op)); }

    public synchronized List<Op> ops() {
        List<Op> out = new ArrayList<>();
        for (Op o : ops.values()) out.add(copy(o));
        return out;
    }

    public synchronized void atomically(Runnable work) { work.run(); }

    private static Op copy(Op o) {
        Op c = new Op();
        c.opId = o.opId; c.kind = o.kind; c.madeAt = o.madeAt; c.data = o.data; c.status = o.status;
        c.message = o.message; c.docType = o.docType; c.docNo = o.docNo; c.seq = o.seq; c.docId = o.docId;
        return c;
    }
}
