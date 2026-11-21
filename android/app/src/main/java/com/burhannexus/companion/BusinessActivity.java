package com.burhannexus.companion;

import android.app.Activity;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * One section of the business figures sent by the PC at the last sync: stock, mobiles in hand, sales, purchases,
 * money, activity. Every page says when the figures were taken and shows OFFLINE when the PC was not reached.
 */
public class BusinessActivity extends Activity implements Sync.Listener {
    public static final String STOCK = "stock", MOBILES = "mobiles", SALES = "sales", PURCHASES = "purchases",
            FINANCE = "finance", ACTIVITY = "activity";
    private static final int MOBILE_ROWS = 150;

    private String section;
    private LinearLayout phonesBox;
    private EditText phoneSearch;

    public static String title(String section) {
        switch (section) {
            case STOCK: return "Stock Position";
            case MOBILES: return "Mobile in Hand";
            case SALES: return "Sales Overview";
            case PURCHASES: return "Purchase Overview";
            case FINANCE: return "Financial Overview";
            default: return "Recent Activity";
        }
    }

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        section = String.valueOf(getIntent().getStringExtra("section"));
        setTitle(title(section));
    }

    @Override
    protected void onResume() {
        super.onResume();
        Sync.addListener(this);
        render();
    }

    @Override
    protected void onPause() {
        super.onPause();
        Sync.removeListener(this);
    }

    @Override
    public void onSyncState() {
        if (Sync.state == Sync.IDLE) render();
    }

    // ---------------- page ----------------
    private void render() {
        LinearLayout page = Ui.page(this);
        LinearLayout head = Ui.row(this);
        head.addView(Ui.text(this, title(section), 19, Ui.NAVY, true),
                new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        boolean live = Sync.online && Sync.state == Sync.IDLE;
        head.addView(Ui.chip(this, live ? "UPDATED" : "OFFLINE", live ? Ui.GREEN : Ui.ORANGE));
        page.addView(head);
        page.addView(Ui.text(this, (live ? "Figures from the computer at " : "Not connected. Figures from the last sync: ")
                + Store.lastSyncText(this), 13, live ? Ui.MUTED : Ui.ORANGE, false), Ui.lp(this, 2));
        Button sync = Ui.outlineButton(this, Sync.state == Sync.RUNNING ? "Syncing…" : "Refresh / Sync now");
        sync.setEnabled(Sync.state != Sync.RUNNING && Store.paired(this));
        sync.setOnClickListener(v -> Sync.now(this));
        page.addView(sync, Ui.lp(this, 8));

        JSONObject all = Store.data(this).optJSONObject("overview");
        JSONObject d = all == null ? null : all.optJSONObject(section);
        if (d == null) {
            page.addView(Ui.text(this, "No figures yet. Press Refresh while this phone and the computer are on the same "
                    + "Wi-Fi. (Business Manager on the computer must be the newest version.)", 15, Ui.TEXT, false),
                    Ui.lp(this, 16));
            return;
        }
        switch (section) {
            case STOCK: stock(page, d); break;
            case MOBILES: mobiles(page, d); break;
            case SALES: sales(page, d); break;
            case PURCHASES: purchases(page, d); break;
            case FINANCE: finance(page, d); break;
            default: activity(page, d);
        }
    }

    // ---------------- building blocks ----------------
    private TextView valueView() {
        return new TextView(this);
    }

    /** Two filled cards side by side. */
    private void pair(LinearLayout page, int c1, String t1, String v1, String n1, int c2, String t2, String v2, String n2) {
        LinearLayout row = Ui.row(this);
        row.addView(card(c1, t1, v1, n1), half());
        row.addView(Ui.gap(this, 10));
        row.addView(card(c2, t2, v2, n2), half());
        page.addView(row, Ui.lp(this, 10));
    }

    private LinearLayout card(int color, String title, String value, String note) {
        TextView v = valueView(), n = valueView();
        v.setText(value);
        n.setText(note);
        LinearLayout c = Ui.statCard(this, color, title, v, n);
        v.setTextSize(20);
        return c;
    }

    private static LinearLayout.LayoutParams half() {
        return new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1);
    }

    private void heading(LinearLayout page, String text) {
        page.addView(Ui.text(this, text, 16, Ui.NAVY, true), Ui.lp(this, 18));
    }

    /** A white card with lines of "left .... right". */
    private LinearLayout table(LinearLayout page) {
        LinearLayout c = Ui.card(this);
        page.addView(c, Ui.lp(this, 6));
        return c;
    }

    private void line(LinearLayout card, String left, String sub, String right, int rightColor) {
        LinearLayout row = Ui.row(this);
        LinearLayout l = Ui.column(this);
        l.addView(Ui.text(this, left, 14, Ui.TEXT, true));
        if (sub != null && !sub.isEmpty()) l.addView(Ui.text(this, sub, 12, Ui.MUTED, false));
        row.addView(l, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        row.addView(Ui.text(this, right, 14, rightColor, true));
        row.setPadding(0, Ui.dp(this, 5), 0, Ui.dp(this, 5));
        card.addView(row);
    }

    private void empty(LinearLayout card, String text) {
        card.addView(Ui.text(this, text, 13, Ui.MUTED, false));
    }

    private static String qty(double q) {
        return q == Math.rint(q) ? String.valueOf((long) q) : String.valueOf(q);
    }

    private static String gb(JSONObject p, String key) {
        return p.isNull(key) || p.optInt(key, 0) <= 0 ? "-" : p.optInt(key) + " GB";
    }

    // ---------------- sections ----------------
    private void stock(LinearLayout page, JSONObject d) {
        pair(page, Ui.NAVY, "Stock Items", String.valueOf(d.optInt("items")), "products available",
                Ui.TEAL, "Stock Quantity", qty(d.optDouble("quantity")), "pieces on hand");
        pair(page, Ui.PURPLE, "Purchase Value", Ui.money(d.optDouble("purchase_value")), "at purchase rate",
                Ui.GREEN, "Selling Value", Ui.money(d.optDouble("sale_value")), "at selling price");
        pair(page, Ui.ORANGE, "Low Stock", String.valueOf(d.optInt("low_count")), "running low (no mobiles)",
                Ui.RED, "Out of Stock", String.valueOf(d.optInt("out_count")), "finished (no mobiles)");
        heading(page, "Category-wise stock");
        LinearLayout t = table(page);
        JSONArray cats = d.optJSONArray("categories");
        if (cats == null || cats.length() == 0) empty(t, "No stock.");
        for (int i = 0; cats != null && i < cats.length(); i++) {
            JSONObject c = cats.optJSONObject(i);
            line(t, c.optString("category"), c.optInt("items") + " item(s), " + qty(c.optDouble("qty")) + " pcs   |   sells for "
                    + Ui.money(c.optDouble("sale_value")), Ui.money(c.optDouble("purchase_value")), Ui.NAVY);
        }
        heading(page, "Low stock items");
        t = table(page);
        JSONArray low = d.optJSONArray("low_items");
        if (low == null || low.length() == 0) empty(t, "Nothing is running low.");
        for (int i = 0; low != null && i < low.length(); i++) {
            JSONObject r = low.optJSONObject(i);
            line(t, r.optString("name"), r.optString("category") + "   |   alert at " + qty(r.optDouble("level")),
                    qty(r.optDouble("qty")) + " left", Ui.ORANGE);
        }
    }

    private void mobiles(LinearLayout page, JSONObject d) {
        pair(page, Ui.CYAN, "Mobiles in Hand", String.valueOf(d.optInt("total")), "phones available now",
                Ui.GREEN, "Selling Value", Ui.money(d.optDouble("sale_value")),
                "purchase value " + Ui.money(d.optDouble("purchase_value")));
        heading(page, "Brand-wise");
        LinearLayout t = table(page);
        JSONArray brands = d.optJSONArray("brands");
        if (brands == null || brands.length() == 0) empty(t, "No phones in stock.");
        for (int i = 0; brands != null && i < brands.length(); i++) {
            JSONObject b = brands.optJSONObject(i);
            line(t, b.optString("brand"), null, b.optInt("qty") + " pcs", Ui.NAVY);
        }
        heading(page, "Model-wise");
        t = table(page);
        JSONArray models = d.optJSONArray("models");
        if (models == null || models.length() == 0) empty(t, "No phones in stock.");
        for (int i = 0; models != null && i < models.length(); i++) {
            JSONObject m = models.optJSONObject(i);
            line(t, m.optString("model"), m.optString("brand"), m.optInt("qty") + " pcs", Ui.NAVY);
        }
        heading(page, "Available phones");
        phoneSearch = new EditText(this);
        phoneSearch.setHint("Search brand, model or IMEI");
        phoneSearch.setSingleLine(true);
        page.addView(phoneSearch, Ui.lp(this, 4));
        phonesBox = Ui.column(this);
        page.addView(phonesBox);
        final JSONArray list = d.optJSONArray("phones");
        phoneSearch.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int a, int c, int e) {}
            public void onTextChanged(CharSequence s, int a, int c, int e) {}
            public void afterTextChanged(Editable s) { showPhones(list); }
        });
        showPhones(list);
    }

    private void showPhones(JSONArray list) {
        phonesBox.removeAllViews();
        String q = phoneSearch.getText().toString().trim().toLowerCase();
        int shown = 0, matched = 0;
        for (int i = 0; list != null && i < list.length(); i++) {
            JSONObject p = list.optJSONObject(i);
            String all = (p.optString("brand") + " " + p.optString("model") + " " + p.optString("imei1") + " "
                    + p.optString("imei2")).toLowerCase();
            if (!q.isEmpty() && !all.contains(q)) continue;
            matched++;
            if (shown >= MOBILE_ROWS) continue;
            shown++;
            LinearLayout c = Ui.card(this);
            LinearLayout top = Ui.row(this);
            top.addView(Ui.text(this, (p.optString("brand") + " " + p.optString("model")).trim(), 15, Ui.NAVY, true),
                    new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
            top.addView(Ui.chip(this, p.optString("condition").toUpperCase(),
                    "Used".equals(p.optString("condition")) ? Ui.PURPLE : Ui.TEAL));
            c.addView(top);
            boolean keypad = p.optString("type").startsWith("Keypad");
            String spec = keypad ? "Keypad phone" : "RAM " + gb(p, "ram_gb") + "   |   Storage " + gb(p, "storage_gb");
            c.addView(Ui.text(this, spec, 13, Ui.TEXT, false));
            String imei = "IMEI " + p.optString("imei1") + (p.optString("imei2").isEmpty() ? "" : " / " + p.optString("imei2"));
            c.addView(Ui.text(this, imei, 12, Ui.MUTED, false));
            LinearLayout nums = Ui.row(this);
            nums.addView(OutstandingActivity.figure(this, "Purchase Rate", p.optDouble("purchase_price"), Ui.TEXT),
                    new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
            nums.addView(OutstandingActivity.figure(this, "Selling Price", p.optDouble("sale_price"), Ui.GREEN),
                    new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
            c.addView(nums, Ui.lp(this, 4));
            phonesBox.addView(c, Ui.lp(this, 6));
        }
        if (matched == 0) {
            phonesBox.addView(Ui.text(this, "No phone found.", 13, Ui.MUTED, false), Ui.lp(this, 6));
        } else if (matched > shown) {
            phonesBox.addView(Ui.text(this, "Showing " + shown + " of " + matched + ". Search to narrow the list.", 13,
                    Ui.MUTED, false), Ui.lp(this, 6));
        }
    }

    private void sales(LinearLayout page, JSONObject d) {
        pair(page, Ui.GREEN, "Today's Sales", Ui.money(d.optDouble("today_total")), d.optInt("today_count") + " bill(s)",
                Ui.NAVY, "This Month", Ui.money(d.optDouble("month_total")), d.optInt("month_count") + " bill(s)");
        pair(page, Ui.TEAL, "Total Sales", String.valueOf(d.optInt("all_count")), "bills in all",
                Ui.PURPLE, "All-time Amount", Ui.money(d.optDouble("all_total")), "all bills");
        heading(page, "Today's sales transactions");
        LinearLayout t = table(page);
        JSONArray today = d.optJSONArray("today_list");
        if (today == null || today.length() == 0) empty(t, "No sale today yet.");
        for (int i = 0; today != null && i < today.length(); i++) {
            JSONObject r = today.optJSONObject(i);
            double due = r.optDouble("total") - r.optDouble("paid");
            line(t, r.optString("customer"), r.optString("time") + "   " + r.optString("no")
                    + (due > 0.5 ? "   |   credit " + Ui.money(due) : ""), Ui.money(r.optDouble("total")), Ui.GREEN);
        }
        heading(page, "Monthly sales summary");
        t = table(page);
        JSONArray months = d.optJSONArray("monthly");
        for (int i = months == null ? -1 : months.length() - 1; i >= 0; i--) {
            JSONObject m = months.optJSONObject(i);
            line(t, m.optString("month"), null, Ui.money(m.optDouble("total")), Ui.NAVY);
        }
    }

    private void purchases(LinearLayout page, JSONObject d) {
        pair(page, Ui.CYAN, "Today's Purchases", Ui.money(d.optDouble("today_total")), d.optInt("today_count") + " purchase(s)",
                Ui.NAVY, "This Month", Ui.money(d.optDouble("month_total")), "purchases this month");
        pair(page, Ui.PURPLE, "Total Purchase Amount", Ui.money(d.optDouble("all_total")), "all purchases",
                Ui.TEAL, "Purchases", String.valueOf(d.optInt("all_count")), "records in all");
        heading(page, "Recent purchases");
        LinearLayout t = table(page);
        JSONArray rec = d.optJSONArray("recent");
        if (rec == null || rec.length() == 0) empty(t, "No purchase yet.");
        for (int i = 0; rec != null && i < rec.length(); i++) {
            JSONObject r = rec.optJSONObject(i);
            line(t, r.optString("supplier"), r.optString("date") + "   " + r.optString("no"),
                    Ui.money(r.optDouble("total")), Ui.NAVY);
        }
    }

    private void finance(LinearLayout page, JSONObject d) {
        pair(page, Ui.GOLD, "Cash in Hand", Ui.money(d.optDouble("cash_in_hand")), "in the drawer",
                Ui.RED, "Receivables", Ui.money(d.optDouble("receivables")), "customers owe you");
        pair(page, Ui.ORANGE, "Payables", Ui.money(d.optDouble("payables")), "you owe suppliers",
                Ui.PURPLE, "Monthly Profit", Ui.money(d.optDouble("month_profit")), "this month (net)");
        double today = d.optDouble("today_profit");
        LinearLayout row = Ui.row(this);
        row.addView(card(today < 0 ? Ui.RED : Ui.GREEN, "Today's Profit", Ui.money(today), today < 0 ? "loss today" : "net, after expenses"), half());
        page.addView(row, Ui.lp(this, 10));
        page.addView(Ui.text(this, "Same figures as the Windows program (Profit & Loss, Cash Book, Outstanding).", 12,
                Ui.MUTED, false), Ui.lp(this, 10));
    }

    private void activity(LinearLayout page, JSONObject d) {
        listOf(page, "Recent sales", d.optJSONArray("sales"), "name", "no", "amount", Ui.GREEN);
        listOf(page, "Recent purchases", d.optJSONArray("purchases"), "name", "no", "amount", Ui.NAVY);
        heading(page, "Stock updates");
        LinearLayout t = table(page);
        JSONArray moves = d.optJSONArray("stock_updates");
        if (moves == null || moves.length() == 0) empty(t, "Nothing yet.");
        for (int i = 0; moves != null && i < moves.length(); i++) {
            JSONObject m = moves.optJSONObject(i);
            double q = m.optDouble("qty");
            line(t, m.optString("product"), m.optString("date") + "   " + m.optString("kind"),
                    (q > 0 ? "+" : "") + qty(q), q < 0 ? Ui.RED : Ui.GREEN);
        }
        heading(page, "New products added");
        t = table(page);
        JSONArray added = d.optJSONArray("new_products");
        if (added == null || added.length() == 0) empty(t, "Nothing yet.");
        for (int i = 0; added != null && i < added.length(); i++) {
            JSONObject a = added.optJSONObject(i);
            line(t, a.optString("text"), a.optString("date"), "", Ui.TEXT);
        }
        heading(page, "Other changes");
        t = table(page);
        JSONArray ch = d.optJSONArray("changes");
        if (ch == null || ch.length() == 0) empty(t, "Nothing yet.");
        for (int i = 0; ch != null && i < ch.length(); i++) {
            JSONObject a = ch.optJSONObject(i);
            line(t, a.optString("action"), a.optString("date") + "   " + a.optString("text"), "", Ui.TEXT);
        }
        JSONArray cust = Store.data(this).optJSONArray("transactions");
        heading(page, "Recent customer transactions");
        t = table(page);
        if (cust == null || cust.length() == 0) empty(t, "Nothing yet.");
        for (int i = 0; cust != null && i < cust.length(); i++) {
            JSONObject r = cust.optJSONObject(i);
            boolean in = "in".equals(r.optString("direction"));
            line(t, r.optString("name"), r.optString("date") + "   " + r.optString("kind"),
                    (in ? "+ " : "- ") + Ui.money(r.optDouble("amount")), in ? Ui.GREEN : Ui.RED);
        }
    }

    private void listOf(LinearLayout page, String title, JSONArray rows, String name, String sub, String amount, int color) {
        heading(page, title);
        LinearLayout t = table(page);
        if (rows == null || rows.length() == 0) empty(t, "Nothing yet.");
        for (int i = 0; rows != null && i < rows.length(); i++) {
            JSONObject r = rows.optJSONObject(i);
            line(t, r.optString(name), r.optString("date") + "   " + r.optString(sub), Ui.money(r.optDouble(amount)), color);
        }
    }
}
