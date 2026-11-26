package com.burhannexus.companion.sync;

/** One transaction made on the phone, waiting for (or done with) the computer. */
public final class Op {
    public static final String PENDING = "pending";     // saved on the phone, not yet on the computer
    public static final String APPLIED = "applied";     // the computer saved it; its effect is not in our copy yet
    public static final String DONE = "done";           // in our copy of the computer's records
    public static final String CONFLICT = "conflict";   // the computer could not save it: the owner decides
    public static final String DISMISSED = "dismissed"; // the owner dealt with it on the computer

    public String opId, kind, madeAt, data, status = PENDING, message = "", docType = "", docNo = "";
    public long seq, docId;

    /** Still has to be added to what the screens show (the computer's copy does not contain it yet). */
    public boolean counts() {
        return PENDING.equals(status) || APPLIED.equals(status);
    }
}
