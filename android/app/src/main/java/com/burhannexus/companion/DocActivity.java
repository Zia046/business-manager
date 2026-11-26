package com.burhannexus.companion;

import android.app.AlertDialog;
import android.os.Bundle;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.burhannexus.companion.sync.Engine;
import com.burhannexus.companion.sync.Json;
import com.burhannexus.companion.sync.Op;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** New Sale / Sale Return / New Purchase / Purchase Return - saved on the phone, sent to the computer by itself. */
public class DocActivity extends BaseActivity {
    private String kind;
    private boolean customerSide;
    private String partyKey;
    private Map<String, Object> party;
    private final List<Map<String, Object>> lines = new ArrayList<>();
    private Button partyButton;
    private LinearLayout linesBox;
    private EditText discount, cash, note;
    private TextView totalView, balanceView;
    private boolean cashTouched, filling;

    static String title(String kind) {
        switch (kind) {
            case "sale": return "New Sale";
            case "sale_return": return "Sale Return";
            case "purchase": return "New Purchase";
            default: return "Purchase Return";
        }
    }

    @Override
    protected String screenKey() {
        return "new:" + kind;
    }

    @Override
    protected void onCreate(Bundle b) {
        kind = String.valueOf(getIntent().getStringExtra("kind"));
        super.onCreate(b);
        customerSide = kind.startsWith("sale");
        setTitle(title(kind));
        LinearLayout page = Ui.page(this);

        if ("sale".equals(kind) && (Local.engine(this).series() == null)) {
            page.addView(Ui.text(this, "Connect to the computer once (same Wi-Fi) before the first sale: the phone gets its own "
                    + "invoice numbers then. After that, sales work offline too.", 14, Ui.ORANGE, true));
        }
        partyButton = Ui.outlineButton(this, "");
        partyButton.setOnClickListener(v -> Pick.party(this, customerSide ? "customer" : "supplier", (k, row) -> setParty(k, row)));
        page.addView(partyButton, Ui.lp(this, 4));
        if ("sale".equals(kind)) {                       // default: walk-in customer, like the computer
            for (Map.Entry<String, Map<String, Object>> e : Local.engine(this).parties("customer").entrySet()) {
                if (Json.num(e.getValue().get("is_walkin")) != 0) { setParty(e.getKey(), e.getValue()); break; }
            }
        }
        if (party == null) setParty(null, null);

        linesBox = Ui.column(this);
        page.addView(linesBox, Ui.lp(this, 10));
        Button add = Ui.button(this, "+ Add Product", Ui.NAVY);
        add.setOnClickListener(v -> Pick.product(this, (k, p) -> addProduct(k, p)));
        page.addView(add, Ui.lp(this, 8));

        LinearLayout totals = Ui.card(this);
        if ("sale".equals(kind)) {
            discount = Pick.money(this, totals, "Bill discount");
            discount.addTextChangedListener(watch());
        }
        totalView = Pick.value(this, totals, "Total");
        totalView.setTextSize(22);
        totalView.setTextColor(Ui.NAVY);
        String cashLabel = "sale".equals(kind) ? "Paid now" : "purchase".equals(kind) ? "Paid to supplier"
                : "sale_return".equals(kind) ? "Cash refunded" : "Cash received back";
        cash = Pick.money(this, totals, cashLabel);
        cash.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int a, int c, int d) {}
            public void onTextChanged(CharSequence s, int a, int c, int d) {}
            public void afterTextChanged(Editable s) {
                if (!filling) cashTouched = true;
                showTotals();
            }
        });
        balanceView = Ui.text(this, "", 13, Ui.MUTED, false);
        totals.addView(balanceView, Ui.lp(this, 4));
        note = Pick.field(this, totals, "Note", InputType.TYPE_CLASS_TEXT);
        page.addView(totals, Ui.lp(this, 12));

        Button save = Ui.button(this, "SAVE", Ui.RED);
        save.setOnClickListener(v -> save());
        page.addView(save, Ui.lp(this, 14));
        showLines();
    }

    private TextWatcher watch() {
        return new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int a, int c, int d) {}
            public void onTextChanged(CharSequence s, int a, int c, int d) {}
            public void afterTextChanged(Editable s) { showTotals(); }
        };
    }

    private void setParty(String key, Map<String, Object> row) {
        partyKey = key;
        party = row;
        String who = customerSide ? "Customer" : "Supplier";
        partyButton.setText(row == null ? "Select " + who.toLowerCase() + " ▸"
                : who + ": " + Json.txt(row.get("name")) + "   (balance " + Ui.money(Json.num(row.get("balance"))) + ")  ▸");
        if (totalView != null) showTotals();
    }

    private boolean phone(Map<String, Object> p) {
        return Json.num(p.get("track_serial")) != 0;
    }

    private void addProduct(String key, Map<String, Object> p) {
        double price = customerSide ? Json.num(p.get("sale_price")) : Json.num(p.get("avg_cost"));
        if (!phone(p)) {
            for (Map<String, Object> l : lines) {
                if (key.equals(l.get("key"))) { l.put("qty", Json.num(l.get("qty")) + 1); showLines(); return; }
            }
            lines.add(Json.of("key", key, "name", p.get("name"), "qty", 1.0, "price", price, "discount", 0.0));
            showLines();
            return;
        }
        long pid = Json.lng(p.get("id"));
        if ("sale".equals(kind) || "purchase_return".equals(kind)) {
            Pick.imei(this, pid, (imei, s) -> {
                for (Map<String, Object> l : lines) {
                    if (imei.equals(l.get("serial"))) { Ui.toast(this, "This IMEI is already on the bill"); return; }
                }
                lines.add(Json.of("key", key, "name", p.get("name"), "qty", 1.0, "price", price, "discount", 0.0,
                        "serial", imei));
                showLines();
            });
            return;
        }
        boolean dbl = "double".equals(p.get("imei_mode"));
        LinearLayout box = Ui.column(this);
        int pad = Ui.dp(this, 16);
        box.setPadding(pad, pad, pad, 0);
        String hint = "sale_return".equals(kind) ? "IMEI of the returned phone"
                : dbl ? "One phone per line: IMEI 1, IMEI 2" : "One IMEI per line (one line for each phone)";
        EditText input = Pick.field(this, box, hint, InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        input.setMinLines("sale_return".equals(kind) ? 1 : 3);
        new AlertDialog.Builder(this).setTitle(Json.txt(p.get("name"))).setView(box).setNegativeButton("Cancel", null)
                .setPositiveButton("Add", (d, w) -> {
                    List<Object> serials = new ArrayList<>();
                    for (String row : input.getText().toString().split("\\n")) {
                        String[] parts = row.trim().split("[\\s,;]+");
                        if (parts.length == 0 || parts[0].isEmpty()) continue;
                        List<Object> pair = new ArrayList<>();
                        for (String x : parts) pair.add(x);
                        serials.add(pair);
                    }
                    if (serials.isEmpty()) { Ui.toast(this, "Type the IMEI"); return; }
                    if ("sale_return".equals(kind)) {
                        List<Object> first = Json.list(serials.get(0));
                        lines.add(Json.of("key", key, "name", p.get("name"), "qty", 1.0, "price", price, "discount", 0.0,
                                "serial", Json.txt(first.get(0))));
                    } else {
                        lines.add(Json.of("key", key, "name", p.get("name"), "qty", (double) serials.size(), "price", price,
                                "discount", 0.0, "serials", serials));
                    }
                    showLines();
                }).show();
    }

    private void showLines() {
        linesBox.removeAllViews();
        if (lines.isEmpty()) {
            linesBox.addView(Ui.text(this, "No products yet. Press + Add Product.", 14, Ui.MUTED, false));
        }
        for (int i = 0; i < lines.size(); i++) {
            final Map<String, Object> l = lines.get(i);
            LinearLayout card = Ui.card(this);
            LinearLayout top = Ui.row(this);
            top.addView(Ui.text(this, Json.txt(l.get("name")), 15, Ui.NAVY, true),
                    new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
            Button rm = Ui.button(this, "Remove", Ui.RED);
            rm.setTextSize(13);
            rm.setMinHeight(Ui.dp(this, 36));
            rm.setOnClickListener(v -> { lines.remove(l); showLines(); });
            top.addView(rm);
            card.addView(top);
            if (l.get("serial") != null) card.addView(Ui.text(this, "IMEI " + l.get("serial"), 12, Ui.MUTED, false));
            if (l.get("serials") != null) {
                StringBuilder sb = new StringBuilder();
                for (Object s : Json.list(l.get("serials"))) sb.append(sb.length() > 0 ? ", " : "").append(Json.list(s).get(0));
                card.addView(Ui.text(this, "IMEI " + sb, 12, Ui.MUTED, false));
            }
            LinearLayout nums = Ui.row(this);
            boolean fixedQty = l.get("serial") != null || l.get("serials") != null;
            nums.addView(numBox(l, "qty", "Qty", !fixedQty), cell());
            nums.addView(Ui.gap(this, 8));
            nums.addView(numBox(l, "price", "Price", true), cell());
            if ("sale".equals(kind)) {
                nums.addView(Ui.gap(this, 8));
                nums.addView(numBox(l, "discount", "Discount", true), cell());
            }
            card.addView(nums);
            linesBox.addView(card, Ui.lp(this, 6));
        }
        showTotals();
    }

    private LinearLayout.LayoutParams cell() {
        return new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
    }

    private LinearLayout numBox(Map<String, Object> l, String field, String label, boolean editable) {
        LinearLayout c = Ui.column(this);
        c.addView(Ui.text(this, label, 11, Ui.MUTED, false));
        EditText e = new EditText(this);
        e.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        e.setText(Pick.qty(Json.num(l.get(field))));
        e.setEnabled(editable);
        e.setSelectAllOnFocus(true);
        e.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int a, int b, int d) {}
            public void onTextChanged(CharSequence s, int a, int b, int d) {}
            public void afterTextChanged(Editable s) {
                l.put(field, Pick.num(e));
                showTotals();
            }
        });
        c.addView(e);
        return c;
    }

    private Map<String, Object> data() {
        List<Object> items = new ArrayList<>();
        for (Map<String, Object> l : lines) {
            Map<String, Object> it = Json.of("product_id", Engine.ref(Json.txt(l.get("key"))), "qty", Json.num(l.get("qty")),
                    "price", Json.num(l.get("price")));
            if (Json.num(l.get("discount")) > 0) it.put("discount", Json.num(l.get("discount")));
            if (l.get("serial") != null) it.put("serial", l.get("serial"));
            if (l.get("serials") != null) it.put("serials", l.get("serials"));
            items.add(it);
        }
        Map<String, Object> d = Json.of("items", items, "note", note == null ? "" : note.getText().toString().trim());
        if (partyKey != null) d.put("party_id", Engine.ref(partyKey));
        if (discount != null) d.put("discount", Pick.num(discount));
        String cashKey = "sale".equals(kind) || "purchase".equals(kind) ? "paid" : "sale_return".equals(kind) ? "refunded" : "received";
        d.put(cashKey, cash == null ? 0 : Pick.num(cash));
        return d;
    }

    private void showTotals() {
        if (totalView == null || cash == null) return;
        double total = Engine.total(kind, data());
        totalView.setText(Ui.money(total));
        if (!cashTouched && "sale".equals(kind)) {       // like the computer: a cash sale is paid in full
            filling = true;
            cash.setText(Pick.qty(Engine.round2(total)));
            filling = false;
        }
        double left = total - Pick.num(cash);
        balanceView.setText(customerSide ? ("sale".equals(kind) ? "On credit: " + Ui.money(left) : "Taken off the customer's account: " + Ui.money(left))
                : ("purchase".equals(kind) ? "On credit (we owe): " + Ui.money(left) : "Taken off the supplier's account: " + Ui.money(left)));
    }

    private void save() {
        try {
            Op op = Local.engine(this).record(kind, data());
            Sync.now(this);
            Ui.toast(this, "Saved" + (op.docNo.isEmpty() ? "" : " - " + op.docNo) + ". It goes to the computer by itself.");
            startActivity(new android.content.Intent(this, DetailActivity.class)
                    .putExtra("kind", DetailActivity.docKind(kind)).putExtra("id", "op:" + op.opId));
            finish();
        } catch (Engine.Invalid e) {
            new AlertDialog.Builder(this).setTitle("Cannot save").setMessage(e.getMessage()).setPositiveButton("OK", null).show();
        }
    }
}
