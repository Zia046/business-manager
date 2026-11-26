package com.burhannexus.companion.sync;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * The phone's own database (SQLite, in the app's private storage). It keeps working with the computer switched
 * off, and survives the app being closed and the phone being restarted.
 *   records - the phone's copy of the computer's records (products, stock, IMEIs, customers, bills ...)
 *   outbox  - every transaction made on the phone and what happened to it on the computer
 *   meta    - small settings (invoice series and counter, last sync ...)
 */
public final class SqliteStore extends SQLiteOpenHelper implements SyncStore {
    public SqliteStore(Context c) {
        super(c.getApplicationContext(), "business.db", null, 1);
        setWriteAheadLoggingEnabled(true);
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE records (kind TEXT NOT NULL, id INTEGER NOT NULL, fp TEXT NOT NULL, json TEXT NOT NULL, "
                + "PRIMARY KEY (kind, id))");
        db.execSQL("CREATE TABLE outbox (op_id TEXT PRIMARY KEY, seq INTEGER NOT NULL, kind TEXT NOT NULL, "
                + "made_at TEXT NOT NULL, data TEXT NOT NULL, status TEXT NOT NULL, message TEXT, doc_type TEXT, "
                + "doc_id INTEGER, doc_no TEXT)");
        db.execSQL("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)");
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldV, int newV) {
        // version 1 is the first one; later versions add tables/columns here, never drop data
    }

    public synchronized String meta(String key) {
        try (Cursor c = getReadableDatabase().rawQuery("SELECT value FROM meta WHERE key=?", new String[] {key})) {
            return c.moveToFirst() ? c.getString(0) : null;
        }
    }

    public synchronized void setMeta(String key, String value) {
        ContentValues v = new ContentValues();
        v.put("key", key);
        v.put("value", value);
        getWritableDatabase().insertWithOnConflict("meta", null, v, SQLiteDatabase.CONFLICT_REPLACE);
    }

    public synchronized Map<Long, String> fingerprints(String kind) {
        Map<Long, String> out = new HashMap<>();
        try (Cursor c = getReadableDatabase().rawQuery("SELECT id, fp FROM records WHERE kind=?", new String[] {kind})) {
            while (c.moveToNext()) out.put(c.getLong(0), c.getString(1));
        }
        return out;
    }

    public synchronized void putRecord(String kind, long id, String fp, String json) {
        ContentValues v = new ContentValues();
        v.put("kind", kind);
        v.put("id", id);
        v.put("fp", fp);
        v.put("json", json);
        getWritableDatabase().insertWithOnConflict("records", null, v, SQLiteDatabase.CONFLICT_REPLACE);
    }

    public synchronized void deleteRecord(String kind, long id) {
        getWritableDatabase().delete("records", "kind=? AND id=?", new String[] {kind, String.valueOf(id)});
    }

    public synchronized String record(String kind, long id) {
        try (Cursor c = getReadableDatabase().rawQuery("SELECT json FROM records WHERE kind=? AND id=?",
                new String[] {kind, String.valueOf(id)})) {
            return c.moveToFirst() ? c.getString(0) : null;
        }
    }

    public synchronized List<String> records(String kind) {
        List<String> out = new ArrayList<>();
        try (Cursor c = getReadableDatabase().rawQuery("SELECT json FROM records WHERE kind=? ORDER BY id",
                new String[] {kind})) {
            while (c.moveToNext()) out.add(c.getString(0));
        }
        return out;
    }

    private static ContentValues values(Op o) {
        ContentValues v = new ContentValues();
        v.put("op_id", o.opId);
        v.put("seq", o.seq);
        v.put("kind", o.kind);
        v.put("made_at", o.madeAt);
        v.put("data", o.data);
        v.put("status", o.status);
        v.put("message", o.message);
        v.put("doc_type", o.docType);
        v.put("doc_id", o.docId);
        v.put("doc_no", o.docNo);
        return v;
    }

    public synchronized void addOp(Op o) {
        try (Cursor c = getReadableDatabase().rawQuery("SELECT COALESCE(MAX(seq),0) FROM outbox", null)) {
            c.moveToFirst();
            o.seq = c.getLong(0) + 1;
        }
        getWritableDatabase().insertOrThrow("outbox", null, values(o));
    }

    public synchronized void updateOp(Op o) {
        getWritableDatabase().update("outbox", values(o), "op_id=?", new String[] {o.opId});
    }

    public synchronized List<Op> ops() {
        List<Op> out = new ArrayList<>();
        try (Cursor c = getReadableDatabase().rawQuery("SELECT op_id, seq, kind, made_at, data, status, message, doc_type, "
                + "doc_id, doc_no FROM outbox ORDER BY seq", null)) {
            while (c.moveToNext()) {
                Op o = new Op();
                o.opId = c.getString(0);
                o.seq = c.getLong(1);
                o.kind = c.getString(2);
                o.madeAt = c.getString(3);
                o.data = c.getString(4);
                o.status = c.getString(5);
                o.message = c.isNull(6) ? "" : c.getString(6);
                o.docType = c.isNull(7) ? "" : c.getString(7);
                o.docId = c.isNull(8) ? 0 : c.getLong(8);
                o.docNo = c.isNull(9) ? "" : c.getString(9);
                out.add(o);
            }
        }
        return out;
    }

    public synchronized void atomically(Runnable work) {
        SQLiteDatabase db = getWritableDatabase();
        db.beginTransaction();
        try {
            work.run();
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }
}
