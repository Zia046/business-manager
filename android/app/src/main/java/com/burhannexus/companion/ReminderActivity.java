package com.burhannexus.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/**
 * Payment reminders for many customers. Step 1: tick the customers. Step 2: confirm. Step 3: one personalised
 * message after another is opened in the phone's SMS app; the user presses Send there each time.
 * Nothing is ever sent silently.
 */
public class ReminderActivity extends Activity {
    private final List<JSONObject> eligible = new ArrayList<>();
    private final List<CheckBox> boxes = new ArrayList<>();
    private final List<JSONObject> queue = new ArrayList<>();
    private int position = -1;              // -1 = still choosing
    private boolean composerOpened = false;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        setTitle("Send SMS Reminders");
        if (b != null) {
            ArrayList<String> ids = b.getStringArrayList("queue");
            if (ids != null) {
                for (String id : ids) {
                    JSONObject o = Store.customer(this, id);
                    if (o != null) queue.add(o);
                }
                position = Math.min(b.getInt("position", -1), queue.size());
            }
        }
        if (position >= 0 && !queue.isEmpty()) showQueue(); else showChooser();
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        if (position >= 0) {
            ArrayList<String> ids = new ArrayList<>();
            for (JSONObject o : queue) ids.add(o.optString("id"));
            out.putStringArrayList("queue", ids);
            out.putInt("position", position);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (composerOpened) {               // back from the SMS app: move on to the next customer
            composerOpened = false;
            position++;
            showQueue();
        }
    }

    // ---------------- step 1: choose ----------------
    private void showChooser() {
        position = -1;
        eligible.clear();
        boxes.clear();
        LinearLayout page = Ui.page(this);
        JSONArray all = Store.customers(this);
        int noPhone = 0;
        for (int i = 0; i < all.length(); i++) {
            JSONObject o = all.optJSONObject(i);
            if (o == null || o.optDouble("balance", 0) <= 0) continue;
            if (o.optString("phone").isEmpty()) {
                noPhone++;
                continue;
            }
            eligible.add(o);
        }
        page.addView(Ui.text(this, "Choose who gets a payment reminder", 17, Ui.NAVY, true));
        page.addView(Ui.text(this, "Last Sync: " + Store.lastSyncText(this)
                + (noPhone > 0 ? "\n" + noPhone + " customer(s) have no mobile number and are not listed." : ""),
                13, Ui.MUTED, false), Ui.lp(this, 2));
        if (eligible.isEmpty()) {
            page.addView(Ui.text(this, "No customer with a pending balance and a mobile number.", 15, Ui.TEXT, false),
                    Ui.lp(this, 16));
            return;
        }
        final TextView chosen = Ui.text(this, "", 14, Ui.TEXT, true);
        final CheckBox all2 = new CheckBox(this);
        all2.setText("Select all (" + eligible.size() + ")");
        page.addView(all2, Ui.lp(this, 8));
        final Runnable recount = () -> {
            int n = 0;
            double sum = 0;
            for (int i = 0; i < boxes.size(); i++) {
                if (boxes.get(i).isChecked()) {
                    n++;
                    sum += eligible.get(i).optDouble("balance", 0);
                }
            }
            chosen.setText(n + " selected   |   " + Ui.money(sum));
        };
        for (JSONObject o : eligible) {
            LinearLayout card = Ui.card(this);
            CheckBox cb = new CheckBox(this);
            cb.setText(o.optString("name"));
            cb.setTextSize(15);
            cb.setTextColor(Ui.NAVY);
            cb.setOnCheckedChangeListener((v, on) -> recount.run());
            boxes.add(cb);
            card.addView(cb);
            LinearLayout line = Ui.row(this);
            line.addView(Ui.text(this, o.optString("phone"), 13, Ui.MUTED, false),
                    new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
            line.addView(Ui.text(this, Ui.money(o.optDouble("balance", 0)), 15, Ui.RED, true));
            card.addView(line);
            page.addView(card, Ui.lp(this, 6));
        }
        all2.setOnCheckedChangeListener((v, on) -> {
            for (CheckBox cb : boxes) cb.setChecked(on);
        });
        page.addView(chosen, Ui.lp(this, 12));
        Button next = Ui.button(this, "CONTINUE", Ui.RED);
        next.setOnClickListener(v -> confirm());
        page.addView(next, Ui.lp(this, 8));
        recount.run();
    }

    // ---------------- step 2: confirm ----------------
    private void confirm() {
        queue.clear();
        double sum = 0;
        StringBuilder names = new StringBuilder();
        for (int i = 0; i < boxes.size(); i++) {
            if (!boxes.get(i).isChecked()) continue;
            JSONObject o = eligible.get(i);
            queue.add(o);
            sum += o.optDouble("balance", 0);
            if (queue.size() <= 12) {
                names.append("\n• ").append(o.optString("name")).append("  ").append(o.optString("phone"))
                        .append("  ").append(Ui.money(o.optDouble("balance", 0)));
            }
        }
        if (queue.isEmpty()) {
            Ui.toast(this, "Select at least one customer");
            return;
        }
        if (Ui.messageFor(this, queue.get(0)) == null) return;          // template without ****: nothing is sent
        if (queue.size() > 12) names.append("\n… and ").append(queue.size() - 12).append(" more");
        new AlertDialog.Builder(this).setTitle("Send " + queue.size() + " reminder(s)?")
                .setMessage("Total outstanding: " + Ui.money(sum) + "\n" + names
                        + "\n\nEach customer gets a personal message with his own amount. Your SMS app opens for "
                        + "one customer at a time; press Send there, then come back for the next one.")
                .setPositiveButton("Start", (d, w) -> {
                    position = 0;
                    showQueue();
                })
                .setNegativeButton("Cancel", null).show();
    }

    // ---------------- step 3: one after another ----------------
    private void showQueue() {
        LinearLayout page = Ui.page(this);
        if (position >= queue.size()) {
            page.addView(Ui.text(this, "Finished", 20, Ui.GREEN, true));
            page.addView(Ui.text(this, "All " + queue.size() + " reminder(s) were opened in your SMS app.", 15,
                    Ui.TEXT, false), Ui.lp(this, 6));
            Button done = Ui.button(this, "DONE", Ui.NAVY);
            done.setOnClickListener(v -> finish());
            page.addView(done, Ui.lp(this, 16));
            position = -1;
            return;
        }
        final JSONObject o = queue.get(position);
        final String msg = Ui.messageFor(this, o);
        page.addView(Ui.text(this, "Reminder " + (position + 1) + " of " + queue.size(), 14, Ui.MUTED, true));
        LinearLayout card = Ui.card(this);
        card.addView(Ui.text(this, o.optString("name"), 19, Ui.NAVY, true));
        card.addView(Ui.text(this, o.optString("phone"), 14, Ui.MUTED, false));
        card.addView(Ui.text(this, "Outstanding: " + Ui.money(o.optDouble("balance", 0)), 16, Ui.RED, true),
                Ui.lp(this, 4));
        page.addView(card, Ui.lp(this, 8));
        LinearLayout preview = Ui.card(this);
        preview.addView(Ui.text(this, msg == null ? "" : msg, 15, Ui.TEXT, false));
        page.addView(preview, Ui.lp(this, 8));

        Button open = Ui.button(this, "OPEN SMS APP", Ui.RED);
        open.setEnabled(msg != null);
        open.setOnClickListener(v -> composerOpened = Ui.openSms(this, o.optString("phone"), msg));
        page.addView(open, Ui.lp(this, 12));
        LinearLayout row = Ui.row(this);
        Button skip = Ui.outlineButton(this, "Skip");
        skip.setOnClickListener(v -> {
            position++;
            showQueue();
        });
        Button stop = Ui.outlineButton(this, "Stop");
        stop.setOnClickListener(v -> finish());
        row.addView(skip, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        row.addView(Ui.gap(this, 10));
        row.addView(stop, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        page.addView(row, Ui.lp(this, 8));
        View hint = Ui.text(this, "After pressing Send in the SMS app, come back here: the next customer appears "
                + "automatically.", 13, Ui.MUTED, false);
        page.addView(hint, Ui.lp(this, 10));
    }
}
