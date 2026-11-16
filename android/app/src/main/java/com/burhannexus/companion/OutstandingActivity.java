package com.burhannexus.companion;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.View;
import android.view.ViewGroup;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.BaseAdapter;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.Spinner;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Everyone with a pending balance: search, sort, filter; tap a row for the ledger. */
public class OutstandingActivity extends Activity implements Sync.Listener {
    private final List<JSONObject> shown = new ArrayList<>();
    private EditText search, minAmount;
    private Spinner sort;
    private CheckBox overdueOnly;
    private TextView count;
    private final BaseAdapter adapter = new RowAdapter();

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        setTitle("Outstanding Customers");
        LinearLayout root = Ui.column(this);
        root.setBackgroundColor(Ui.BG);
        int p = Ui.dp(this, 12);
        root.setPadding(p, p, p, 0);

        search = new EditText(this);
        search.setHint("Search name or mobile number");
        search.setSingleLine(true);
        root.addView(search);

        LinearLayout filters = Ui.row(this);
        sort = new Spinner(this);
        sort.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item,
                new String[] {"Highest outstanding", "Lowest outstanding", "Name A-Z", "Oldest payment first"}));
        filters.addView(sort, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1.4f));
        minAmount = new EditText(this);
        minAmount.setHint("Min Rs");
        minAmount.setInputType(InputType.TYPE_CLASS_NUMBER);
        minAmount.setSingleLine(true);
        filters.addView(minAmount, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        root.addView(filters);
        overdueOnly = new CheckBox(this);
        overdueOnly.setText("Overdue customers only");
        root.addView(overdueOnly);
        count = Ui.text(this, "", 13, Ui.MUTED, false);
        root.addView(count);

        ListView list = new ListView(this);
        list.setDividerHeight(Ui.dp(this, 8));
        list.setDivider(new android.graphics.drawable.ColorDrawable(Color.TRANSPARENT));
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) -> startActivity(
                new Intent(this, CustomerActivity.class).putExtra("id", shown.get(position).optString("id"))));
        root.addView(list, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(root);

        TextWatcher w = new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int a, int c, int d) {}
            public void onTextChanged(CharSequence s, int a, int c, int d) {}
            public void afterTextChanged(Editable s) { reload(); }
        };
        search.addTextChangedListener(w);
        minAmount.addTextChangedListener(w);
        overdueOnly.setOnCheckedChangeListener((v, on) -> reload());
        sort.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            public void onItemSelected(AdapterView<?> a, View v, int pos, long id) { reload(); }
            public void onNothingSelected(AdapterView<?> a) {}
        });
    }

    @Override
    protected void onResume() {
        super.onResume();
        Sync.addListener(this);
        reload();
    }

    @Override
    protected void onPause() {
        super.onPause();
        Sync.removeListener(this);
    }

    @Override
    public void onSyncState() {
        reload();
    }

    private static String digits(String s) {
        return s.replaceAll("[^0-9]", "");
    }

    private void reload() {
        String q = search.getText().toString().trim().toLowerCase();
        String qDigits = digits(q);
        double min = 0;
        try {
            min = Double.parseDouble(minAmount.getText().toString().trim());
        } catch (Exception ignored) {
        }
        shown.clear();
        JSONArray all = Store.customers(this);
        double sum = 0;
        for (int i = 0; i < all.length(); i++) {
            JSONObject o = all.optJSONObject(i);
            if (o == null || o.optDouble("balance", 0) <= 0) continue;        // only a real positive balance
            if (o.optDouble("balance", 0) < min) continue;
            if (overdueOnly.isChecked() && !o.optBoolean("overdue")) continue;
            if (!q.isEmpty()) {
                boolean byName = o.optString("name").toLowerCase().contains(q);
                boolean byPhone = !qDigits.isEmpty() && digits(o.optString("phone")).contains(qDigits);
                if (!byName && !byPhone) continue;
            }
            shown.add(o);
            sum += o.optDouble("balance", 0);
        }
        final int mode = sort.getSelectedItemPosition();
        Collections.sort(shown, (a, b2) -> {
            switch (mode) {
                case 1: return Double.compare(a.optDouble("balance"), b2.optDouble("balance"));
                case 2: return a.optString("name").compareToIgnoreCase(b2.optString("name"));
                case 3: return a.optString("last_payment").compareTo(b2.optString("last_payment"));
                default: return Double.compare(b2.optDouble("balance"), a.optDouble("balance"));
            }
        });
        count.setText(shown.size() + " customer(s)   |   " + Ui.money(sum)
                + "   |   Last Sync: " + Store.lastSyncText(this));
        adapter.notifyDataSetChanged();
    }

    private class RowAdapter extends BaseAdapter {
        public int getCount() { return shown.size(); }
        public Object getItem(int i) { return shown.get(i); }
        public long getItemId(int i) { return i; }

        public View getView(int i, View reuse, ViewGroup parent) {
            Activity a = OutstandingActivity.this;
            JSONObject o = shown.get(i);
            LinearLayout card = Ui.card(a);
            LinearLayout top = Ui.row(a);
            top.addView(Ui.text(a, o.optString("name"), 16, Ui.NAVY, true),
                    new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
            if ("loan".equals(o.optString("type"))) {
                top.addView(Ui.chip(a, "CASH LOAN", Ui.PURPLE));
                top.addView(Ui.gap(a, 6));
            }
            if (o.optBoolean("overdue")) top.addView(Ui.chip(a, "OVERDUE", Ui.ORANGE));
            card.addView(top);
            String phone = o.optString("phone");
            card.addView(Ui.text(a, phone.isEmpty() ? "No mobile number saved" : phone, 13, Ui.MUTED, false));
            LinearLayout nums = Ui.row(a);
            nums.addView(figure(a, "Total Purchase", o.optDouble("total_purchase"), Ui.TEXT), cell());
            nums.addView(figure(a, "Total Paid", o.optDouble("total_paid"), Ui.GREEN), cell());
            nums.addView(figure(a, "Outstanding", o.optDouble("balance"), Ui.RED), cell());
            card.addView(nums, Ui.lp(a, 6));
            String last = o.optString("last_payment");
            card.addView(Ui.text(a, "Last payment: " + (last.isEmpty() ? "none yet" : last), 12, Ui.MUTED, false),
                    Ui.lp(a, 4));
            return card;
        }
    }

    private static LinearLayout.LayoutParams cell() {
        return new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
    }

    static LinearLayout figure(Activity a, String label, double value, int color) {
        LinearLayout l = Ui.column(a);
        l.addView(Ui.text(a, label, 11, Ui.MUTED, false));
        l.addView(Ui.text(a, Ui.money(value), 14, color, true));
        return l;
    }
}
