package com.burhannexus.companion;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.net.ConnectivityManager;
import android.net.Network;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

/** Home dashboard: the figures from the last sync, the connection status and SYNC NOW. */
public class MainActivity extends Activity implements Sync.Listener {
    private static final long AUTO_SYNC_MS = 60_000;

    private TextView shop, status, lastSync, total, totalNote, customers, customersNote, recovered, recoveredNote,
            overdue, overdueNote, hint;
    private Button syncButton;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            Sync.now(MainActivity.this);
            handler.postDelayed(this, AUTO_SYNC_MS);
        }
    };
    private ConnectivityManager.NetworkCallback networkCallback;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        setTitle("Burhan Nexus – Business Companion");
        LinearLayout page = Ui.page(this);

        LinearLayout head = Ui.row(this);
        shop = Ui.text(this, "", 20, Ui.NAVY, true);
        head.addView(shop, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        status = Ui.chip(this, "", Ui.MUTED);
        head.addView(status);
        page.addView(head);
        lastSync = Ui.text(this, "", 13, Ui.MUTED, false);
        page.addView(lastSync, Ui.lp(this, 2));

        total = new TextView(this);
        totalNote = new TextView(this);
        page.addView(Ui.statCard(this, Ui.RED, "Total Outstanding", total, totalNote), Ui.lp(this, 12));

        LinearLayout r1 = Ui.row(this);
        customers = new TextView(this);
        customersNote = new TextView(this);
        overdue = new TextView(this);
        overdueNote = new TextView(this);
        r1.addView(Ui.statCard(this, Ui.NAVY, "Customers with Outstanding", customers, customersNote), half());
        r1.addView(Ui.gap(this, 10));
        r1.addView(Ui.statCard(this, Ui.ORANGE, "Overdue Payments", overdue, overdueNote), half());
        page.addView(r1, Ui.lp(this, 10));

        recovered = new TextView(this);
        recoveredNote = new TextView(this);
        page.addView(Ui.statCard(this, Ui.GREEN, "Today's Recoveries", recovered, recoveredNote), Ui.lp(this, 10));

        syncButton = Ui.button(this, "SYNC NOW", Ui.RED);
        syncButton.setOnClickListener(v -> {
            if (!Store.paired(this)) {
                startActivity(new Intent(this, ConnectActivity.class));
            } else {
                Sync.now(this);
            }
        });
        page.addView(syncButton, Ui.lp(this, 14));
        hint = Ui.text(this, "", 13, Ui.RED, false);
        hint.setGravity(Gravity.CENTER);
        page.addView(hint, Ui.lp(this, 4));

        // business figures: one small tile per section, the details open on their own page
        page.addView(Ui.text(this, "Business", 17, Ui.NAVY, true), Ui.lp(this, 18));
        String[][] tiles = {
                {BusinessActivity.STOCK, "📦"}, {BusinessActivity.MOBILES, "📱"},
                {BusinessActivity.SALES, "🧾"}, {BusinessActivity.PURCHASES, "🛒"},
                {BusinessActivity.FINANCE, "💰"}, {BusinessActivity.ACTIVITY, "🕘"}};
        int[] colors = {Ui.TEAL, Ui.CYAN, Ui.GREEN, Ui.NAVY, Ui.GOLD, Ui.PURPLE};
        for (int i = 0; i < tiles.length; i += 2) {
            LinearLayout row = Ui.row(this);
            row.addView(tile(tiles[i][0], tiles[i][1], colors[i]), half());
            row.addView(Ui.gap(this, 10));
            row.addView(tile(tiles[i + 1][0], tiles[i + 1][1], colors[i + 1]), half());
            page.addView(row, Ui.lp(this, 10));
        }

        page.addView(nav("Outstanding Customers", OutstandingActivity.class), Ui.lp(this, 18));
        page.addView(nav("Send SMS Reminders", ReminderActivity.class), Ui.lp(this, 8));
        page.addView(nav("SMS Template Settings", TemplateActivity.class), Ui.lp(this, 8));
        page.addView(nav("Connection with Computer", ConnectActivity.class), Ui.lp(this, 8));
        TextView ver = Ui.text(this, "App version " + App.BuildConfigInfo.version(this), 12, Ui.MUTED, false);
        ver.setGravity(Gravity.CENTER);
        page.addView(ver, Ui.lp(this, 14));
    }

    private final java.util.Map<String, TextView> tileValues = new java.util.HashMap<>();

    private LinearLayout tile(String section, String icon, int color) {
        LinearLayout t = Ui.column(this);
        t.setBackground(Ui.outline(this, android.graphics.Color.WHITE, Ui.LINE));
        int p = Ui.dp(this, 12);
        t.setPadding(p, p, p, p);
        LinearLayout top = Ui.row(this);
        TextView ic = Ui.text(this, icon, 18, color, false);
        top.addView(ic);
        top.addView(Ui.gap(this, 6));
        top.addView(Ui.text(this, BusinessActivity.title(section), 13, Ui.MUTED, true),
                new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        t.addView(top);
        TextView v = Ui.text(this, "-", 17, color, true);
        t.addView(v, Ui.lp(this, 4));
        tileValues.put(section, v);
        t.setClickable(true);
        t.setOnClickListener(x -> startActivity(new Intent(this, BusinessActivity.class).putExtra("section", section)));
        return t;
    }

    private void renderTiles() {
        JSONObject o = Store.data(this).optJSONObject("overview");
        if (o == null) o = new JSONObject();
        JSONObject st = o.optJSONObject("stock"), mo = o.optJSONObject("mobiles"), sa = o.optJSONObject("sales"),
                pu = o.optJSONObject("purchases"), fi = o.optJSONObject("finance"), ac = o.optJSONObject("activity");
        setTile(BusinessActivity.STOCK, st == null ? null : Ui.money(st.optDouble("purchase_value")) + " stock");
        setTile(BusinessActivity.MOBILES, mo == null ? null : mo.optInt("total") + " phones");
        setTile(BusinessActivity.SALES, sa == null ? null : Ui.money(sa.optDouble("today_total")) + " today");
        setTile(BusinessActivity.PURCHASES, pu == null ? null : Ui.money(pu.optDouble("today_total")) + " today");
        setTile(BusinessActivity.FINANCE, fi == null ? null : Ui.money(fi.optDouble("cash_in_hand")) + " cash");
        JSONArray recent = ac == null ? null : ac.optJSONArray("sales");
        setTile(BusinessActivity.ACTIVITY, ac == null ? null
                : recent != null && recent.length() > 0 ? "Last sale " + recent.optJSONObject(0).optString("date") : "Open");
    }

    private void setTile(String section, String value) {
        TextView v = tileValues.get(section);
        if (v != null) v.setText(value == null ? "Sync to see" : value);
    }

    private LinearLayout.LayoutParams half() {
        return new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1);
    }

    private Button nav(String label, Class<?> target) {
        Button b = Ui.outlineButton(this, label);
        b.setOnClickListener(v -> startActivity(new Intent(this, target)));
        return b;
    }

    @Override
    protected void onResume() {
        super.onResume();
        String crash = App.takeCrash(this);
        if (crash != null) {                                  // the app closed last time: show why
            final String text = crash;
            new android.app.AlertDialog.Builder(this).setTitle("The app closed because of an error")
                    .setMessage("Please send a screenshot of this to the developer.\n\n"
                            + (text.length() > 2500 ? text.substring(0, 2500) : text))
                    .setPositiveButton("Copy", (d, w) -> {
                        android.content.ClipboardManager cb = (android.content.ClipboardManager)
                                getSystemService(Context.CLIPBOARD_SERVICE);
                        cb.setPrimaryClip(android.content.ClipData.newPlainText("error", text));
                        Ui.toast(this, "Copied. Paste it in WhatsApp to the developer.");
                    })
                    .setNegativeButton("Close", null).show();
        }
        Sync.addListener(this);
        render();
        handler.removeCallbacks(tick);
        handler.post(tick);                                   // sync now, then every minute while the app is open
        try {                                                 // and at once when Wi-Fi comes back
            ConnectivityManager cm = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
            networkCallback = new ConnectivityManager.NetworkCallback() {
                @Override
                public void onAvailable(Network network) {
                    handler.postDelayed(() -> Sync.now(MainActivity.this), 1500);
                }
            };
            cm.registerDefaultNetworkCallback(networkCallback);
        } catch (Exception ignored) {
            networkCallback = null;
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        Sync.removeListener(this);
        handler.removeCallbacks(tick);
        if (networkCallback != null) {
            try {
                ((ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE))
                        .unregisterNetworkCallback(networkCallback);
            } catch (Exception ignored) {
            }
            networkCallback = null;
        }
    }

    @Override
    public void onSyncState() {
        render();
    }

    private void render() {
        boolean paired = Store.paired(this);
        JSONObject s = Store.data(this).optJSONObject("summary");
        if (s == null) s = new JSONObject();
        String name = Store.shop(this);
        shop.setText(name.isEmpty() ? "Burhan Nexus" : name);
        lastSync.setText("Last Sync: " + Store.lastSyncText(this));
        renderTiles();
        total.setText(Ui.money(s.optDouble("total_outstanding", 0)));
        totalNote.setText("PKR, customers and cash loans");
        customers.setText(String.valueOf(s.optInt("customers", 0)));
        customersNote.setText("with a pending balance");
        overdue.setText(String.valueOf(s.optInt("overdue_count", 0)));
        overdueNote.setText(Ui.money(s.optDouble("overdue_amount", 0)));
        recovered.setText(Ui.money(s.optDouble("today_recoveries", 0)));
        recoveredNote.setText("received today (as of last sync)");

        String label;
        int color;
        if (!paired) {
            label = "NOT PAIRED";
            color = Ui.MUTED;
        } else if (Sync.state == Sync.RUNNING) {
            label = "SYNCING…";
            color = Ui.CYAN;
        } else if (Sync.online) {
            label = "ONLINE";
            color = Ui.GREEN;
        } else {
            label = "OFFLINE";
            color = Ui.ORANGE;
        }
        status.setText(label);
        status.setBackground(Ui.box(color, Ui.dp(this, 9)));
        syncButton.setText(!paired ? "PAIR WITH COMPUTER" : Sync.state == Sync.RUNNING ? "SYNCING…" : "SYNC NOW");
        syncButton.setEnabled(Sync.state != Sync.RUNNING);
        if (!paired) {
            hint.setText("Pair this phone with your Business Manager computer to see your data.");
        } else if (Sync.state != Sync.RUNNING && !Sync.online && !Sync.message.isEmpty()) {
            hint.setText("Offline: " + Sync.message + ". Showing the data of the last sync.");
        } else {
            hint.setText("");
        }
    }
}
