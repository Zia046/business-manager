package com.burhannexus.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.text.InputFilter;
import android.text.InputType;
import android.view.Gravity;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

/** Pairing with the Windows Business Manager: the PC is found on the Wi-Fi, the user types the 6-digit code. */
public class ConnectActivity extends BaseActivity {
    @Override
    protected String screenKey() {
        return "connect";
    }

    private TextView status;
    private EditText code;
    private Button pair;
    private List<Api.Server> found = new ArrayList<>();
    private Api.Server chosen;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        setTitle("Connection with Computer");
        build();
    }

    private void build() {
        LinearLayout page = Ui.page(this);
        if (Store.paired(this)) {
            LinearLayout card = Ui.card(this);
            card.addView(Ui.text(this, "Paired with", 13, Ui.MUTED, false));
            card.addView(Ui.text(this, Store.shop(this).isEmpty() ? "Business Manager" : Store.shop(this), 20,
                    Ui.NAVY, true));
            card.addView(Ui.text(this, "Last address: " + Store.host(this) + "\nLast Sync: "
                    + Store.lastSyncText(this), 13, Ui.MUTED, false), Ui.lp(this, 4));
            page.addView(card);
            page.addView(Ui.text(this, "The computer is found automatically on the Wi-Fi each time, even when its "
                    + "address changes. Keep Business Manager open on the computer.", 13, Ui.MUTED, false),
                    Ui.lp(this, 10));
            Button sync = Ui.button(this, "SYNC NOW", Ui.RED);
            sync.setOnClickListener(v -> {
                Sync.now(this);
                finish();
            });
            page.addView(sync, Ui.lp(this, 14));
            Button forget = Ui.outlineButton(this, "Unpair this phone");
            forget.setOnClickListener(v -> new AlertDialog.Builder(this).setTitle("Unpair?")
                    .setMessage("The saved data stays on this phone, but it will not sync until you pair again.")
                    .setPositiveButton("Unpair", (d, w) -> {
                        Store.forgetPairing(this);
                        Sync.online = false;
                        build();
                    }).setNegativeButton("Cancel", null).show());
            page.addView(forget, Ui.lp(this, 8));
            return;
        }
        page.addView(Ui.text(this, "Pair with your computer", 19, Ui.NAVY, true));
        page.addView(Ui.text(this, "1. Connect this phone and the computer to the same Wi-Fi.\n"
                + "2. On the computer open Business Manager > Utilities > Mobile App (Android), turn the connection "
                + "on and press \"Pair a new phone\".\n3. Type the 6-digit code shown there.", 14, Ui.TEXT, false),
                Ui.lp(this, 8));
        status = Ui.text(this, "", 14, Ui.MUTED, true);
        page.addView(status, Ui.lp(this, 14));
        Button search = Ui.outlineButton(this, "Search again");
        search.setOnClickListener(v -> search());
        page.addView(search, Ui.lp(this, 6));

        code = new EditText(this);
        code.setHint("6-digit code");
        code.setInputType(InputType.TYPE_CLASS_NUMBER);
        code.setFilters(new InputFilter[] {new InputFilter.LengthFilter(6)});
        code.setGravity(Gravity.CENTER);
        code.setTextSize(26);
        page.addView(code, Ui.lp(this, 14));
        pair = Ui.button(this, "PAIR", Ui.RED);
        pair.setOnClickListener(v -> pair());
        page.addView(pair, Ui.lp(this, 8));
        search();
    }

    private void search() {
        chosen = null;
        status.setTextColor(Ui.MUTED);
        status.setText("Searching for the computer on this Wi-Fi…");
        Sync.background(() -> Api.discover(), (result, error) -> {
            if (Store.paired(this) || status == null) return;
            @SuppressWarnings("unchecked")
            List<Api.Server> list = result == null ? new ArrayList<Api.Server>() : (List<Api.Server>) result;
            found = list;
            if (found.isEmpty()) {
                status.setTextColor(Ui.ORANGE);
                status.setText("No computer found. Check that both are on the same Wi-Fi, that Business Manager is "
                        + "open and that the Mobile App connection is turned on, then press Search again.");
            } else if (found.size() == 1) {
                choose(found.get(0));
            } else {
                String[] names = new String[found.size()];
                for (int i = 0; i < names.length; i++) names[i] = found.get(i).shop + "  (" + found.get(i).host + ")";
                new AlertDialog.Builder(this).setTitle("Which computer?")
                        .setItems(names, (d, which) -> choose(found.get(which))).show();
            }
        });
    }

    private void choose(Api.Server s) {
        chosen = s;
        status.setTextColor(Ui.GREEN);
        status.setText("Found: " + (s.shop.isEmpty() ? "Business Manager" : s.shop) + "  (" + s.host + ")");
    }

    private void pair() {
        final String c = code.getText().toString().trim();
        if (chosen == null) {
            Ui.toast(this, "The computer has not been found yet. Press Search again.");
            return;
        }
        if (c.length() != 6) {
            Ui.toast(this, "Type the 6-digit code shown on the computer");
            return;
        }
        pair.setEnabled(false);
        final Api.Server target = chosen;
        Sync.background(() -> {
            Api.pair(this, target, c);
            return null;
        }, (result, error) -> {
            pair.setEnabled(true);
            if (error != null) {
                Ui.toast(this, error.getMessage());
                return;
            }
            Ui.toast(this, "Paired. Syncing…");
            Sync.now(this);
            finish();
        });
    }
}
