package com.burhannexus.companion;

import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.burhannexus.companion.sync.Json;

import org.json.JSONObject;

import java.util.HashMap;
import java.util.Map;

/** Dashboard: worked out on the phone from its own database, so it is right offline too. */
public class MainActivity extends BaseActivity {
    private TextView shop, hint;
    private final Map<String, TextView[]> stats = new HashMap<>();

    @Override
    protected String screenKey() {
        return "home";
    }

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        setTitle("Burhan Nexus");
        LinearLayout page = Ui.page(this);
        shop = Ui.text(this, "", 20, Ui.NAVY, true);
        page.addView(shop);
        hint = Ui.text(this, "", 13, Ui.RED, false);
        page.addView(hint, Ui.lp(this, 2));

        // quick actions
        String[][] quick = {{"New Sale", "new:sale"}, {"Receive Payment", "money:receipt"},
                {"New Purchase", "new:purchase"}, {"New Expense", "money:expense"}};
        int[] qc = {Ui.RED, Ui.GREEN, Ui.NAVY, Ui.GOLD};
        for (int i = 0; i < quick.length; i += 2) {
            LinearLayout row = Ui.row(this);
            row.addView(action(quick[i][0], quick[i][1], qc[i]), half());
            row.addView(Ui.gap(this, 10));
            row.addView(action(quick[i + 1][0], quick[i + 1][1], qc[i + 1]), half());
            page.addView(row, Ui.lp(this, 10));
        }

        String[][] cards = {
                {"today_sales", "Today's Sales", "list:invoice"}, {"month_sales", "This Month", "list:invoice"},
                {"receivable", "Customers Owe", "list:customer"}, {"payable", "We Owe Suppliers", "list:supplier"},
                {"cash", "Cash in Hand", "biz:finance"}, {"stock_value", "Stock Value", "list:product"},
                {"phones_in_stock", "Phones in Stock", "list:phone"}, {"low_stock", "Low Stock Items", "list:low"}};
        int[] colors = {Ui.GREEN, Ui.TEAL, Ui.RED, Ui.ORANGE, Ui.GOLD, Ui.NAVY, Ui.CYAN, Ui.PURPLE};
        page.addView(Ui.text(this, "Today", 17, Ui.NAVY, true), Ui.lp(this, 18));
        for (int i = 0; i < cards.length; i += 2) {
            LinearLayout row = Ui.row(this);
            row.addView(stat(cards[i], colors[i]), half());
            row.addView(Ui.gap(this, 10));
            row.addView(stat(cards[i + 1], colors[i + 1]), half());
            page.addView(row, Ui.lp(this, 10));
        }
        Button pending = Ui.outlineButton(this, "Sync & Conflicts");
        pending.setOnClickListener(v -> open(this, "list:sync"));
        page.addView(pending, Ui.lp(this, 14));
        stats.put("pending_button", new TextView[] {pending});

        TextView ver = Ui.text(this, "App version " + App.BuildConfigInfo.version(this), 12, Ui.MUTED, false);
        ver.setGravity(Gravity.CENTER);
        page.addView(ver, Ui.lp(this, 14));
    }

    private Button action(String label, String key, int color) {
        Button b = Ui.button(this, label, color);
        b.setOnClickListener(v -> open(this, key));
        return b;
    }

    private LinearLayout stat(String[] spec, int color) {
        TextView value = new TextView(this), note = new TextView(this);
        LinearLayout c = Ui.statCard(this, color, spec[1], value, note);
        c.setClickable(true);
        c.setOnClickListener(v -> open(this, spec[2]));
        stats.put(spec[0], new TextView[] {value, note});
        return c;
    }

    private LinearLayout.LayoutParams half() {
        return new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1);
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
        render();
    }

    @Override
    protected void onDataChanged() {
        render();
    }

    private void set(String key, String value, String note) {
        TextView[] t = stats.get(key);
        if (t == null) return;
        t[0].setText(value);
        if (t.length > 1) t[1].setText(note);
    }

    private void render() {
        String name = Json.txt(Local.engine(this).meta().get("shop"));
        if (name.isEmpty() || "null".equals(name)) name = Store.shop(this);
        shop.setText(name.isEmpty() ? "Burhan Nexus" : name);
        if (!Store.paired(this)) {
            hint.setText("Pair this phone with the Business Manager computer: menu ☰ > Connection with Computer.");
        } else if (Local.engine(this).series() == null) {
            hint.setText("Waiting for the first sync with the computer (same Wi-Fi)…");
        } else {
            hint.setText("");
        }
        Map<String, Object> d = Local.engine(this).dashboard();
        set("today_sales", Ui.money(Json.num(d.get("today_sales"))), Json.lng(d.get("today_invoices")) + " bills today");
        set("month_sales", Ui.money(Json.num(d.get("month_sales"))), "sales this month");
        set("receivable", Ui.money(Json.num(d.get("receivable"))), "to receive");
        set("payable", Ui.money(Json.num(d.get("payable"))), "to pay");
        set("cash", Ui.money(Json.num(d.get("cash"))), "as of last sync");
        set("stock_value", Ui.money(Json.num(d.get("stock_value"))), "at cost");
        set("phones_in_stock", String.valueOf(Json.lng(d.get("phones_in_stock"))), "with IMEI");
        set("low_stock", String.valueOf(Json.lng(d.get("low_stock"))), "items to re-order");
        long unsent = Json.lng(d.get("unsent")), conflicts = Json.lng(d.get("conflicts"));
        TextView[] pb = stats.get("pending_button");
        if (pb != null) pb[0].setText("Sync & Conflicts" + (unsent > 0 ? "  ·  " + unsent + " waiting" : "")
                + (conflicts > 0 ? "  ·  " + conflicts + " need attention" : ""));
    }
}
