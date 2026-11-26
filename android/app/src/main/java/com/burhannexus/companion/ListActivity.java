package com.burhannexus.companion;

import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.ViewGroup;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.burhannexus.companion.sync.Engine;
import com.burhannexus.companion.sync.Json;
import com.burhannexus.companion.sync.Op;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Every history / list screen: works from the phone's own copy, so it opens offline too. */
public class ListActivity extends BaseActivity {
    private String kind;
    private LinearLayout box;
    private EditText search;
    private static final int LIMIT = 300;

    static String title(String kind) {
        switch (kind) {
            case "invoice": return "Sales History";
            case "purchase": return "Purchase History";
            case "return": return "Returns";
            case "voucher": return "Payments (Received / Paid)";
            case "expense": return "Expenses";
            case "product": return "Stock";
            case "phone": return "Phones in Stock";
            case "low": return "Low Stock";
            case "customer": return "Customers";
            case "supplier": return "Suppliers";
            default: return "Sync Status";
        }
    }

    @Override
    protected String screenKey() {
        return "list:" + kind;
    }

    @Override
    protected void onCreate(Bundle b) {
        kind = String.valueOf(getIntent().getStringExtra("kind"));
        super.onCreate(b);
        setTitle(title(kind));
        LinearLayout page = Ui.page(this);
        if (!"sync".equals(kind)) {
            search = new EditText(this);
            search.setHint("Search");
            search.setSingleLine(true);
            search.addTextChangedListener(new TextWatcher() {
                public void beforeTextChanged(CharSequence s, int a, int c, int d) {}
                public void onTextChanged(CharSequence s, int a, int c, int d) {}
                public void afterTextChanged(Editable s) { show(); }
            });
            page.addView(search);
        }
        box = Ui.column(this);
        page.addView(box, Ui.lp(this, 6));
        show();
    }

    @Override
    protected void onDataChanged() {
        show();
    }

    @Override
    protected void onResume() {
        super.onResume();
        show();
    }

    private String q() {
        return search == null ? "" : search.getText().toString().trim().toLowerCase(Locale.ROOT);
    }

    private static boolean has(String q, Object... parts) {
        if (q.isEmpty()) return true;
        for (Object p : parts) if (p != null && String.valueOf(p).toLowerCase(Locale.ROOT).contains(q)) return true;
        return false;
    }

    private void show() {
        if (box == null) return;
        box.removeAllViews();
        Engine e = Local.engine(this);
        String q = q();
        int n = 0;
        switch (kind) {
            case "invoice": case "purchase": case "return": case "voucher": case "expense":
                for (Map<String, Object> d : e.documents(kind)) {
                    if (!has(q, d.get("no"), d.get("party"), d.get("category"), d.get("note"))) continue;
                    if (n++ >= LIMIT) break;
                    box.addView(docRow(d), Ui.lp(this, 6));
                }
                break;
            case "product": case "low":
                for (Map.Entry<String, Map<String, Object>> en : e.products().entrySet()) {
                    Map<String, Object> p = en.getValue();
                    if (Json.num(p.get("active")) == 0) continue;
                    boolean phone = Json.num(p.get("track_serial")) != 0;
                    if ("low".equals(kind) && (phone || Json.num(p.get("qty")) > Json.num(p.get("low_stock_level")))) continue;
                    if (!has(q, p.get("name"), p.get("brand"), p.get("category"), p.get("barcode"))) continue;
                    if (n++ >= LIMIT) break;
                    box.addView(productRow(p), Ui.lp(this, 6));
                }
                break;
            case "phone":
                for (Map<String, Object> p : e.products().values()) {
                    if (Json.num(p.get("track_serial")) == 0) continue;
                    for (Map<String, Object> s : e.phonesInStock(Json.lng(p.get("id")))) {
                        if (!has(q, p.get("name"), s.get("serial"), s.get("imei2"))) continue;
                        if (n++ >= LIMIT) break;
                        LinearLayout c = Ui.card(this);
                        c.addView(Ui.text(this, Json.txt(p.get("name")), 15, Ui.NAVY, true));
                        String i2 = Json.txt(s.get("imei2"));
                        c.addView(Ui.text(this, "IMEI " + s.get("serial") + (i2.isEmpty() || "null".equals(i2) ? "" : " / " + i2),
                                13, Ui.TEXT, false));
                        String spec = spec(p);
                        c.addView(Ui.text(this, spec + "Sale price " + Ui.money(Json.num(p.get("sale_price"))), 12, Ui.MUTED, false));
                        box.addView(c, Ui.lp(this, 6));
                    }
                }
                break;
            case "customer": case "supplier":
                for (Map.Entry<String, Map<String, Object>> en : e.parties(kind).entrySet()) {
                    Map<String, Object> p = en.getValue();
                    if (!has(q, p.get("name"), p.get("phone"))) continue;
                    if (n++ >= LIMIT) break;
                    box.addView(partyRow(en.getKey(), p), Ui.lp(this, 6));
                }
                break;
            default:
                syncList(e);
                return;
        }
        if (n == 0) box.addView(Ui.text(this, q.isEmpty() ? "Nothing here yet." : "Nothing matches.", 14, Ui.MUTED, false));
        if (n > LIMIT) box.addView(Ui.text(this, "Showing the first " + LIMIT + ". Search to find others.", 12, Ui.MUTED, false));
    }

    private static String spec(Map<String, Object> p) {
        StringBuilder sb = new StringBuilder();
        String t = Json.txt(p.get("mobile_type"));
        if (!t.isEmpty() && !"null".equals(t)) sb.append(t).append(" · ");
        if (Json.num(p.get("ram_gb")) > 0) sb.append(Pick.qty(Json.num(p.get("ram_gb")))).append("GB RAM · ");
        if (Json.num(p.get("storage_gb")) > 0) sb.append(Pick.qty(Json.num(p.get("storage_gb")))).append("GB · ");
        return sb.toString();
    }

    private TextView badge(Map<String, Object> d) {
        String s = Json.txt(d.get("sync"));
        if ("pending".equals(s)) return Ui.chip(this, "Not sent yet", Ui.ORANGE);
        if ("conflict".equals(s)) return Ui.chip(this, "Needs attention", Ui.RED);
        if ("cancelled".equals(d.get("status"))) return Ui.chip(this, "Cancelled", Ui.MUTED);
        return null;
    }

    private LinearLayout docRow(Map<String, Object> d) {
        LinearLayout c = Ui.card(this);
        LinearLayout top = Ui.row(this);
        String head = "expense".equals(kind) ? Json.txt(d.get("category")) : Json.txt(d.get("no"));
        top.addView(Ui.text(this, head, 15, Ui.NAVY, true), new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        double amount = "voucher".equals(kind) || "expense".equals(kind) ? Json.num(d.get("amount") != null ? d.get("amount") : d.get("total"))
                : Json.num(d.get("total"));
        top.addView(Ui.text(this, Ui.money(amount), 15, Ui.TEXT, true));
        c.addView(top);
        StringBuilder sub = new StringBuilder(Json.txt(d.get("date")).replace('T', ' '));
        if (sub.length() > 16) sub.setLength(16);
        String party = Json.txt(d.get("party"));
        if (!party.isEmpty() && !"null".equals(party)) sub.append(" · ").append(party);
        if ("return".equals(kind)) sub.append(" · ").append("sale".equals(d.get("kind")) ? "sale return" : "purchase return");
        if ("voucher".equals(kind)) sub.append(" · ").append("receipt".equals(d.get("kind")) ? "received" : "paid");
        if ("invoice".equals(kind)) {
            double left = Json.num(d.get("total")) - Json.num(d.get("paid"));
            if (left > 0.004) sub.append(" · credit ").append(Ui.money(left));
        }
        c.addView(Ui.text(this, sub.toString(), 12, Ui.MUTED, false));
        TextView bd = badge(d);
        if (bd != null) {
            LinearLayout r = Ui.row(this);
            r.addView(bd);
            c.addView(r, Ui.lp(this, 4));
        }
        if (!"voucher".equals(kind) && !"expense".equals(kind)) {
            c.setOnClickListener(v -> startActivity(new Intent(this, DetailActivity.class).putExtra("kind", kind)
                    .putExtra("id", String.valueOf(d.get("id") instanceof String ? d.get("id") : Json.lng(d.get("id"))))));
        }
        return c;
    }

    private LinearLayout productRow(Map<String, Object> p) {
        LinearLayout c = Ui.card(this);
        LinearLayout top = Ui.row(this);
        top.addView(Ui.text(this, Json.txt(p.get("name")), 15, Ui.NAVY, true),
                new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        double qty = Json.num(p.get("qty"));
        top.addView(Ui.text(this, Pick.qty(qty) + " " + Json.txt(p.get("unit")).replace("null", ""), 15,
                qty <= Json.num(p.get("low_stock_level")) ? Ui.RED : Ui.GREEN, true));
        c.addView(top);
        c.addView(Ui.text(this, spec(p) + "Sale " + Ui.money(Json.num(p.get("sale_price"))) + " · Cost "
                + Ui.money(Json.num(p.get("avg_cost"))), 12, Ui.MUTED, false));
        return c;
    }

    private LinearLayout partyRow(String key, Map<String, Object> p) {
        LinearLayout c = Ui.card(this);
        LinearLayout top = Ui.row(this);
        top.addView(Ui.text(this, Json.txt(p.get("name")), 15, Ui.NAVY, true),
                new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        double bal = Json.num(p.get("balance"));
        top.addView(Ui.text(this, Ui.money(bal), 15, bal > 0.004 ? Ui.RED : Ui.TEXT, true));
        c.addView(top);
        String ph = Json.txt(p.get("phone"));
        if (!ph.isEmpty() && !"null".equals(ph)) c.addView(Ui.text(this, ph, 12, Ui.MUTED, false));
        if (Boolean.TRUE.equals(p.get("pending"))) {
            LinearLayout r = Ui.row(this);
            r.addView(Ui.chip(this, "Not sent yet", Ui.ORANGE));
            c.addView(r, Ui.lp(this, 4));
        }
        boolean customer = "customer".equals(kind);
        c.setOnClickListener(v -> {
            List<String> acts = new ArrayList<>();
            acts.add(customer ? "Receive Payment" : "Pay Supplier");
            acts.add(customer ? "New Sale" : "New Purchase");
            if (!ph.isEmpty() && !"null".equals(ph)) acts.add("Send SMS");
            new AlertDialog.Builder(this).setTitle(Json.txt(p.get("name")) + "  (" + Ui.money(bal) + ")")
                    .setItems(acts.toArray(new String[0]), (dlg, w) -> {
                        String a = acts.get(w);
                        if (a.startsWith("Receive") || a.startsWith("Pay")) {
                            startActivity(new Intent(this, MoneyActivity.class)
                                    .putExtra("kind", customer ? "receipt" : "supplier_payment").putExtra("party", key));
                        } else if (a.startsWith("New")) {
                            open(this, customer ? "new:sale" : "new:purchase");
                        } else {
                            Ui.openSms(this, ph, "");
                        }
                    }).show();
        });
        return c;
    }

    private void syncList(Engine e) {
        LinearLayout head = Ui.card(this);
        head.addView(Ui.text(this, e.state(), 16, Ui.NAVY, true));
        String err = e.lastError();
        if (err != null && !err.isEmpty()) head.addView(Ui.text(this, err, 12, Ui.MUTED, false));
        String last = Json.txt(e.store.meta("last_sync"));
        head.addView(Ui.text(this, "Last complete sync: " + (last.isEmpty() || "null".equals(last) ? "never" : last.replace('T', ' ')),
                12, Ui.MUTED, false));
        android.widget.Button now = Ui.button(this, "Sync now", Ui.NAVY);
        now.setOnClickListener(v -> Sync.now(this));
        head.addView(now, Ui.lp(this, 8));
        box.addView(head);

        List<Op> waiting = e.unfinished(), bad = e.conflicts();
        box.addView(Ui.text(this, "Needs attention (" + bad.size() + ")", 15, Ui.RED, true), Ui.lp(this, 14));
        if (bad.isEmpty()) box.addView(Ui.text(this, "Nothing. Everything the computer received was accepted.", 13, Ui.MUTED, false));
        for (Op o : bad) {
            LinearLayout c = Ui.card(this);
            c.addView(Ui.text(this, label(o), 14, Ui.NAVY, true));
            c.addView(Ui.text(this, o.message, 13, Ui.RED, false));
            c.addView(Ui.text(this, "The computer kept it aside. Fix it on the computer (Mobile App window), or dismiss it here.",
                    12, Ui.MUTED, false));
            android.widget.Button dismiss = Ui.outlineButton(this, "Dismiss");
            dismiss.setOnClickListener(v -> new AlertDialog.Builder(this).setMessage("Remove this entry from the phone?")
                    .setNegativeButton("No", null).setPositiveButton("Yes", (d, w) -> {
                        o.status = Op.DISMISSED;
                        e.store.updateOp(o);
                        show();
                    }).show());
            c.addView(dismiss, Ui.lp(this, 6));
            box.addView(c, Ui.lp(this, 6));
        }
        box.addView(Ui.text(this, "Waiting to reach the computer (" + waiting.size() + ")", 15, Ui.NAVY, true), Ui.lp(this, 14));
        if (waiting.isEmpty()) box.addView(Ui.text(this, "Nothing waiting.", 13, Ui.MUTED, false));
        for (Op o : waiting) {
            LinearLayout c = Ui.card(this);
            c.addView(Ui.text(this, label(o), 14, Ui.NAVY, true));
            c.addView(Ui.text(this, Op.PENDING.equals(o.status) ? "Saved on the phone, not sent yet"
                    : "Received by the computer, refreshing the phone copy", 12, Ui.MUTED, false));
            box.addView(c, Ui.lp(this, 6));
        }
    }

    private static String label(Op o) {
        String k;
        switch (o.kind) {
            case "sale": k = "Sale"; break;
            case "sale_return": k = "Sale return"; break;
            case "purchase": k = "Purchase"; break;
            case "purchase_return": k = "Purchase return"; break;
            case "receipt": k = "Payment received"; break;
            case "supplier_payment": k = "Supplier payment"; break;
            case "expense": k = "Expense"; break;
            case "customer_add": k = "New customer"; break;
            case "supplier_add": k = "New supplier"; break;
            default: k = o.kind;
        }
        String when = o.madeAt == null ? "" : o.madeAt.replace('T', ' ');
        if (when.length() > 16) when = when.substring(0, 16);
        return k + (o.docNo == null || o.docNo.isEmpty() ? "" : " " + o.docNo) + " · " + when;
    }
}
