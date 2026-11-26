package com.burhannexus.companion.sync;

import java.util.List;
import java.util.Map;

/** Where the phone keeps its data: a copy of the computer's records, the outbox and a few settings. */
public interface SyncStore {
    String meta(String key);

    void setMeta(String key, String value);

    /** id -> fingerprint of every record of one kind. */
    Map<Long, String> fingerprints(String kind);

    void putRecord(String kind, long id, String fingerprint, String json);

    void deleteRecord(String kind, long id);

    String record(String kind, long id);

    /** All records of a kind (JSON text). */
    List<String> records(String kind);

    void addOp(Op op);

    void updateOp(Op op);

    /** All transactions in the order they were made. */
    List<Op> ops();

    /** Runs `work` as one database transaction: all of it is saved, or nothing. */
    void atomically(Runnable work);
}
