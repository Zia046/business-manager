package com.burhannexus.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;

import com.burhannexus.companion.sync.Engine;
import com.burhannexus.companion.sync.Json;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** Searchable pick-lists (product, customer/supplier, IMEI) and small form helpers. */
public final class Pick {
    private Pick() {}

    public interface Chosen {
        void chosen(String key, Map<String, Object> row);
    }

    /** A dialog with a search box over a list. */
    static void list(Activity a, String title, List<String> keys, List<String> labels, List<Map<String, Object>> rows,
                     String extraButton, Runnable onExtra, Chosen done) {
        LinearLayout box = Ui.column(a);
        int p = Ui.dp(a, 12);
        box.setPadding(p, p, p, 0);
        EditText search = new EditText(a);
        search.setHint("Search");
        search.setSingleLine(true);
        box.addView(search);
        ListView lv = new ListView(a);
        List<Integer> shown = new ArrayList<>();
        ArrayAdapter<String> ad = new ArrayAdapter<>(a, android.R.layout.simple_list_item_1, new ArrayList<>());
        lv.setAdapter(ad);
        box.addView(lv, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(a, 380)));
        Runnable filter = () -> {
            String q = search.getText().toString().trim().toLowerCase();
            ad.clear();
            shown.clear();
            for (int i = 0; i < labels.size(); i++) {
                if (q.isEmpty() || labels.get(i).toLowerCase().contains(q)) {
                    shown.add(i);
                    ad.add(labels.get(i));
                }
            }
            ad.notifyDataSetChanged();
        };
        filter.run();
        search.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int x, int y, int z) {}
            public void onTextChanged(CharSequence s, int x, int y, int z) {}
            public void afterTextChanged(Editable s) { filter.run(); }
        });
        AlertDialog.Builder b = new AlertDialog.Builder(a).setTitle(title).setView(box).setNegativeButton("Cancel", null);
        if (extraButton != null) b.setNeutralButton(extraButton, (d, w) -> onExtra.run());
        AlertDialog dlg = b.show();
        lv.setOnItemClickListener((parent, view, pos, id) -> {
            int i = shown.get(pos);
            dlg.dismiss();
            done.chosen(keys.get(i), rows.get(i));
        });
    }

    static void product(Activity a, Chosen done) {
        Engine e = Local.engine(a);
        List<String> keys = new ArrayList<>(), labels = new ArrayList<>();
        List<Map<String, Object>> rows = new ArrayList<>();
        for (Map.Entry<String, Map<String, Object>> en : e.products().entrySet()) {
            Map<String, Object> p = en.getValue();
            if (Json.num(p.get("active")) == 0) continue;
            keys.add(en.getKey());
            rows.add(p);
            String bc = Json.txt(p.get("barcode"));
            labels.add(Json.txt(p.get("name")) + "   [" + qty(Json.num(p.get("qty"))) + "]   " + Ui.money(Json.num(p.get("sale_price")))
                    + (bc.isEmpty() ? "" : "   #" + bc));
        }
        list(a, "Select product", keys, labels, rows, null, null, done);
    }

    static void party(Activity a, String kind, Chosen done) {
        Engine e = Local.engine(a);
        List<String> keys = new ArrayList<>(), labels = new ArrayList<>();
        List<Map<String, Object>> rows = new ArrayList<>();
        for (Map.Entry<String, Map<String, Object>> en : e.parties(kind).entrySet()) {
            Map<String, Object> p = en.getValue();
            keys.add(en.getKey());
            rows.add(p);
            double bal = Json.num(p.get("balance"));
            labels.add(Json.txt(p.get("name")) + (Json.txt(p.get("phone")).isEmpty() ? "" : "  " + p.get("phone"))
                    + (Math.abs(bal) > 0.004 ? "   (" + Ui.money(bal) + ")" : ""));
        }
        list(a, "customer".equals(kind) ? "Select customer" : "Select supplier", keys, labels, rows,
                "+ New", () -> newParty(a, kind, done), done);
    }

    /** Add a customer/supplier on the phone (saved on the computer at the next sync). */
    static void newParty(Activity a, String kind, Chosen done) {
        LinearLayout box = Ui.column(a);
        int p = Ui.dp(a, 16);
        box.setPadding(p, p, p, 0);
        EditText name = field(a, box, "Name *", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_WORDS);
        EditText phone = field(a, box, "Mobile number", InputType.TYPE_CLASS_PHONE);
        EditText address = field(a, box, "Address", InputType.TYPE_CLASS_TEXT);
        new AlertDialog.Builder(a).setTitle("customer".equals(kind) ? "New customer" : "New supplier").setView(box)
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Save", (d, w) -> {
                    try {
                        com.burhannexus.companion.sync.Op op = Local.engine(a).record(
                                "customer".equals(kind) ? "customer_add" : "supplier_add",
                                Json.of("name", name.getText().toString().trim(), "phone", phone.getText().toString().trim(),
                                        "address", address.getText().toString().trim()));
                        Sync.now(a);
                        String key = "op:" + op.opId;
                        done.chosen(key, Local.engine(a).parties(kind).get(key));
                    } catch (Engine.Invalid ex) {
                        Ui.toast(a, ex.getMessage());
                    }
                }).show();
    }

    static void imei(Activity a, long productId, Chosen done) {
        List<String> keys = new ArrayList<>(), labels = new ArrayList<>();
        List<Map<String, Object>> rows = new ArrayList<>();
        for (Map<String, Object> s : Local.engine(a).phonesInStock(productId)) {
            keys.add(Json.txt(s.get("serial")));
            rows.add(s);
            String i2 = Json.txt(s.get("imei2"));
            labels.add(Json.txt(s.get("serial")) + (i2.isEmpty() || "null".equals(i2) ? "" : " / " + i2));
        }
        if (keys.isEmpty()) {
            Ui.toast(a, "No phone of this model is in stock");
            return;
        }
        list(a, "Select IMEI", keys, labels, rows, null, null, done);
    }

    // ---------------- small form helpers ----------------
    static EditText field(Activity a, LinearLayout box, String label, int type) {
        box.addView(Ui.text(a, label, 13, Ui.MUTED, false), Ui.lp(a, 8));
        EditText e = new EditText(a);
        e.setInputType(type);
        e.setSingleLine(type != (InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE));
        box.addView(e);
        return e;
    }

    static EditText money(Activity a, LinearLayout box, String label) {
        return field(a, box, label, InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
    }

    static double num(EditText e) {
        try {
            return Double.parseDouble(e.getText().toString().trim().replace(",", ""));
        } catch (Exception ex) {
            return 0;
        }
    }

    static String qty(double q) {
        return q == Math.rint(q) ? String.valueOf((long) q) : String.valueOf(q);
    }

    static TextView value(Activity a, LinearLayout box, String label) {
        box.addView(Ui.text(a, label, 13, Ui.MUTED, false), Ui.lp(a, 8));
        TextView t = Ui.text(a, "", 16, Ui.TEXT, true);
        box.addView(t);
        return t;
    }
}
