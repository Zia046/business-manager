package com.burhannexus.companion;

import android.app.AlertDialog;
import android.os.Bundle;
import android.text.InputType;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.burhannexus.companion.sync.Engine;
import com.burhannexus.companion.sync.Json;

import java.util.Map;

/** Receive Payment (customer) / Pay Supplier / New Expense. */
public class MoneyActivity extends BaseActivity {
    private String kind, partyKey;
    private Button partyButton;
    private TextView balance;

    @Override
    protected String screenKey() {
        return "money:" + kind;
    }

    @Override
    protected void onCreate(Bundle b) {
        kind = String.valueOf(getIntent().getStringExtra("kind"));
        super.onCreate(b);
        setTitle("receipt".equals(kind) ? "Receive Payment" : "supplier_payment".equals(kind) ? "Pay Supplier" : "New Expense");
        LinearLayout page = Ui.page(this);
        LinearLayout card = Ui.card(this);
        EditText category = null;
        if (!"expense".equals(kind)) {
            String pk = "receipt".equals(kind) ? "customer" : "supplier";
            partyButton = Ui.outlineButton(this, "Select " + pk + " ▸");
            partyButton.setOnClickListener(v -> Pick.party(this, pk, this::setParty));
            card.addView(partyButton);
            balance = Ui.text(this, "", 14, Ui.MUTED, false);
            card.addView(balance, Ui.lp(this, 6));
            String pre = getIntent().getStringExtra("party");
            if (pre != null) setParty(pre, Local.engine(this).parties(pk).get(pre));
        } else {
            category = Pick.field(this, card, "Category *", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
            final EditText cat = category;
            StringBuilder known = new StringBuilder();
            for (Object c : Json.list(Local.engine(this).meta().get("expense_categories"))) {
                known.append(known.length() > 0 ? " · " : "").append(c);
            }
            if (known.length() > 0) {
                TextView hint = Ui.text(this, "Used before: " + known, 12, Ui.MUTED, false);
                hint.setOnClickListener(v -> {
                    String[] all = known.toString().split(" · ");
                    new AlertDialog.Builder(this).setItems(all, (d, w) -> cat.setText(all[w])).show();
                });
                card.addView(hint);
            }
        }
        EditText amount = Pick.money(this, card, "Amount *");
        EditText note = Pick.field(this, card, "Note", InputType.TYPE_CLASS_TEXT);
        page.addView(card);
        Button save = Ui.button(this, "SAVE", Ui.RED);
        final EditText cat = category;
        save.setOnClickListener(v -> {
            if (!save.isEnabled()) return;
            Map<String, Object> d = Json.of("amount", Pick.num(amount), "note", note.getText().toString().trim());
            if (cat != null) d.put("category", cat.getText().toString().trim());
            if (partyKey != null) d.put("party_id", Engine.ref(partyKey));
            save.setEnabled(false);                    // one tap = one entry
            try {
                Local.engine(this).record(kind, d);
                Sync.now(this);
                Ui.toast(this, "Saved. It goes to the computer by itself.");
                finish();
            } catch (Engine.Invalid e) {
                save.setEnabled(true);
                new AlertDialog.Builder(this).setTitle("Cannot save").setMessage(e.getMessage()).setPositiveButton("OK", null).show();
            }
        });
        page.addView(save, Ui.lp(this, 14));
    }

    private void setParty(String key, Map<String, Object> row) {
        partyKey = key;
        if (row == null) return;
        partyButton.setText(Json.txt(row.get("name")) + "  ▸");
        double bal = Json.num(row.get("balance"));
        balance.setText(("receipt".equals(kind) ? "Customer owes: " : "We owe: ") + Ui.money(bal));
    }
}
