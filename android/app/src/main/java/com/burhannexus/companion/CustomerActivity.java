package com.burhannexus.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;

import org.json.JSONArray;
import org.json.JSONObject;

/** One customer: figures, SEND PAYMENT REMINDER, and the complete ledger with the payment history. */
public class CustomerActivity extends BaseActivity {
    @Override
    protected String screenKey() {
        return "outstanding";
    }

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        setTitle("Customer Details");
    }

    @Override
    protected void onResume() {
        super.onResume();
        final JSONObject o = Store.customer(this, String.valueOf(getIntent().getStringExtra("id")));
        LinearLayout page = Ui.page(this);
        if (o == null) {
            page.addView(Ui.text(this, "This customer has no outstanding balance any more.", 15, Ui.TEXT, false));
            return;
        }
        LinearLayout card = Ui.card(this);
        LinearLayout top = Ui.row(this);
        top.addView(Ui.text(this, o.optString("name"), 20, Ui.NAVY, true),
                new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        if ("loan".equals(o.optString("type"))) top.addView(Ui.chip(this, "CASH LOAN", Ui.PURPLE));
        card.addView(top);
        final String phone = o.optString("phone");
        card.addView(Ui.text(this, phone.isEmpty() ? "No mobile number saved" : phone, 14, Ui.MUTED, false));
        LinearLayout nums = Ui.row(this);
        LinearLayout.LayoutParams cell = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        nums.addView(OutstandingActivity.figure(this, "Total Purchase", o.optDouble("total_purchase"), Ui.TEXT), cell);
        nums.addView(OutstandingActivity.figure(this, "Total Paid", o.optDouble("total_paid"), Ui.GREEN), cell);
        nums.addView(OutstandingActivity.figure(this, "Outstanding", o.optDouble("balance"), Ui.RED), cell);
        card.addView(nums, Ui.lp(this, 8));
        String last = o.optString("last_payment");
        card.addView(Ui.text(this, "Last payment: " + (last.isEmpty() ? "none yet" : last), 13, Ui.MUTED, false),
                Ui.lp(this, 6));
        if (o.optBoolean("overdue")) {
            card.addView(Ui.text(this, "Overdue: " + o.optString("overdue_reason"), 13, Ui.ORANGE, true),
                    Ui.lp(this, 2));
        }
        page.addView(card);

        Button send = Ui.button(this, "SEND PAYMENT REMINDER", Ui.RED);
        send.setEnabled(!phone.isEmpty());
        if (phone.isEmpty()) send.setAlpha(0.5f);
        send.setOnClickListener(v -> {
            final String msg = Ui.messageFor(this, o);
            if (msg == null) return;
            new AlertDialog.Builder(this).setTitle("Message for " + o.optString("name"))
                    .setMessage("To: " + phone + "\n\n" + msg)
                    .setPositiveButton("Open SMS App", (d, w) -> Ui.openSms(this, phone, msg))
                    .setNegativeButton("Cancel", null).show();
        });
        page.addView(send, Ui.lp(this, 12));

        page.addView(Ui.text(this, "Ledger and payment history", 16, Ui.NAVY, true), Ui.lp(this, 16));
        JSONArray led = o.optJSONArray("ledger");
        if (led == null || led.length() == 0) {
            page.addView(Ui.text(this, "No entries.", 14, Ui.MUTED, false), Ui.lp(this, 6));
            return;
        }
        for (int i = led.length() - 1; i >= 0; i--) {                       // newest first
            JSONObject l = led.optJSONObject(i);
            if (l == null) continue;
            LinearLayout row = Ui.card(this);
            LinearLayout head = Ui.row(this);
            head.addView(Ui.text(this, l.optString("desc"), 14, Ui.TEXT, true),
                    new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
            double credit = l.optDouble("credit", 0), debit = l.optDouble("debit", 0);
            head.addView(Ui.text(this, credit > 0 ? "- " + Ui.money(credit) : "+ " + Ui.money(debit), 14,
                    credit > 0 ? Ui.GREEN : Ui.RED, true));
            row.addView(head);
            row.addView(Ui.text(this, l.optString("date") + "    Balance: " + Ui.money(l.optDouble("balance", 0)),
                    12, Ui.MUTED, false));
            page.addView(row, Ui.lp(this, 6));
        }
    }
}
