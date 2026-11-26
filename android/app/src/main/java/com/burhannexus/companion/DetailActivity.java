package com.burhannexus.companion;

import android.content.Intent;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;

import com.burhannexus.companion.sync.Json;

import java.util.Map;

/** One bill (sale, purchase or return) laid out like the printed invoice; can be shared on WhatsApp/SMS. */
public class DetailActivity extends BaseActivity {
    private String kind, id;
    private LinearLayout box;

    static String docKind(String opKind) {
        switch (opKind) {
            case "sale": return "invoice";
            case "purchase": return "purchase";
            default: return "return";
        }
    }

    @Override
    protected String screenKey() {
        return "list:" + kind;
    }

    @Override
    protected void onCreate(Bundle b) {
        kind = String.valueOf(getIntent().getStringExtra("kind"));
        id = String.valueOf(getIntent().getStringExtra("id"));
        super.onCreate(b);
        setTitle("invoice".equals(kind) ? "Invoice" : "purchase".equals(kind) ? "Purchase" : "Return");
        box = Ui.page(this);
        show();
    }

    @Override
    protected void onDataChanged() {
        show();
    }

    private Map<String, Object> find() {
        for (Map<String, Object> d : Local.engine(this).documents(kind)) {
            Object k = d.get("id");
            String key = k instanceof String ? (String) k : String.valueOf(Json.lng(k));
            if (key.equals(id)) return d;
        }
        // a phone bill that has just reached the computer: find it there by its number
        return null;
    }

    private void show() {
        box.removeAllViews();
        Map<String, Object> d = find();
        if (d == null && id.startsWith("op:")) {
            for (com.burhannexus.companion.sync.Op o : Local.engine(this).store.ops()) {
                if (("op:" + o.opId).equals(id) && o.docNo != null && !o.docNo.isEmpty()) {
                    for (Map<String, Object> x : Local.engine(this).documents(kind)) {
                        if (o.docNo.equals(x.get("no"))) { d = x; id = String.valueOf(Json.lng(x.get("id"))); break; }
                    }
                }
            }
        }
        if (d == null) {
            box.addView(Ui.text(this, "This bill is not on the phone any more.", 14, Ui.MUTED, false));
            return;
        }
        final Map<String, Object> doc = d;
        String shop = Json.txt(Local.engine(this).meta().get("shop"));
        LinearLayout card = Ui.card(this);
        if (!shop.isEmpty() && !"null".equals(shop)) card.addView(Ui.text(this, shop, 18, Ui.NAVY, true));
        card.addView(Ui.text(this, Json.txt(d.get("no")) + "   " + Json.txt(d.get("date")).replace('T', ' '), 14, Ui.TEXT, true));
        card.addView(Ui.text(this, ("invoice".equals(kind) || "sale".equals(d.get("kind")) ? "Customer: " : "Supplier: ")
                + Json.txt(d.get("party")), 14, Ui.TEXT, false));
        if ("pending".equals(d.get("sync"))) card.addView(Ui.text(this, "Not sent to the computer yet", 12, Ui.ORANGE, true));
        if ("conflict".equals(d.get("sync"))) card.addView(Ui.text(this, "Not accepted: " + d.get("message"), 12, Ui.RED, true));
        if ("cancelled".equals(d.get("status"))) card.addView(Ui.text(this, "CANCELLED", 13, Ui.RED, true));
        box.addView(card);

        LinearLayout lines = Ui.card(this);
        for (Object o : Json.list(d.get("lines"))) {
            Map<String, Object> l = Json.map(o);
            LinearLayout r = Ui.row(this);
            double qty = Json.num(l.get("qty")), price = Json.num(l.get("price")), disc = Json.num(l.get("discount"));
            r.addView(Ui.text(this, Json.txt(l.get("name")) + "\n" + Pick.qty(qty) + " × " + Ui.money(price)
                    + (disc > 0 ? "  − " + Ui.money(disc) : ""), 14, Ui.TEXT, false),
                    new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
            r.addView(Ui.text(this, Ui.money(qty * price - disc), 14, Ui.TEXT, true));
            lines.addView(r, Ui.lp(this, 4));
            String imei = imeis(l);
            if (!imei.isEmpty()) lines.addView(Ui.text(this, "IMEI " + imei, 12, Ui.MUTED, false));
        }
        box.addView(lines, Ui.lp(this, 8));

        LinearLayout tot = Ui.card(this);
        if (Json.num(d.get("discount")) > 0) tot.addView(Ui.text(this, "Discount: " + Ui.money(Json.num(d.get("discount"))), 14, Ui.TEXT, false));
        tot.addView(Ui.text(this, "Total: " + Ui.money(Json.num(d.get("total"))), 18, Ui.NAVY, true));
        String cashKey = d.containsKey("paid") ? "paid" : d.containsKey("refunded") ? "refunded" : "received";
        double cash = Json.num(d.get(cashKey));
        tot.addView(Ui.text(this, ("paid".equals(cashKey) ? "Paid: " : "refunded".equals(cashKey) ? "Refunded: " : "Received: ")
                + Ui.money(cash), 14, Ui.TEXT, false));
        double left = Json.num(d.get("total")) - cash;
        if (left > 0.004 && "invoice".equals(kind)) tot.addView(Ui.text(this, "Balance (credit): " + Ui.money(left), 14, Ui.RED, true));
        String note = Json.txt(d.get("note"));
        if (!note.isEmpty() && !"null".equals(note)) tot.addView(Ui.text(this, "Note: " + note, 13, Ui.MUTED, false));
        box.addView(tot, Ui.lp(this, 8));

        Button share = Ui.button(this, "Share (WhatsApp / SMS)", Ui.NAVY);
        share.setOnClickListener(v -> startActivity(Intent.createChooser(new Intent(Intent.ACTION_SEND).setType("text/plain")
                .putExtra(Intent.EXTRA_TEXT, text(doc, shop)), "Share bill")));
        box.addView(share, Ui.lp(this, 12));
    }

    private static String imeis(Map<String, Object> l) {
        StringBuilder sb = new StringBuilder();
        for (String k : new String[] {"serial", "serial2"}) {
            String s = Json.txt(l.get(k));
            if (!s.isEmpty() && !"null".equals(s)) sb.append(sb.length() > 0 ? " / " : "").append(s);
        }
        if (l.get("serials") != null) {
            for (Object s : Json.list(l.get("serials"))) {
                sb.append(sb.length() > 0 ? ", " : "").append(Json.list(s).get(0));
            }
        }
        return sb.toString();
    }

    private static String text(Map<String, Object> d, String shop) {
        StringBuilder sb = new StringBuilder();
        if (!shop.isEmpty() && !"null".equals(shop)) sb.append(shop).append('\n');
        sb.append(Json.txt(d.get("no"))).append("  ").append(Json.txt(d.get("date")).replace('T', ' ')).append('\n');
        sb.append(Json.txt(d.get("party"))).append("\n\n");
        for (Object o : Json.list(d.get("lines"))) {
            Map<String, Object> l = Json.map(o);
            double qty = Json.num(l.get("qty")), price = Json.num(l.get("price")), disc = Json.num(l.get("discount"));
            sb.append(Json.txt(l.get("name"))).append("  ").append(Pick.qty(qty)).append(" x ").append(Ui.money(price))
                    .append(" = ").append(Ui.money(qty * price - disc)).append('\n');
            String imei = imeis(l);
            if (!imei.isEmpty()) sb.append("IMEI ").append(imei).append('\n');
        }
        sb.append("\nTotal: ").append(Ui.money(Json.num(d.get("total"))));
        if (d.containsKey("paid")) sb.append("\nPaid: ").append(Ui.money(Json.num(d.get("paid"))));
        return sb.toString();
    }
}
