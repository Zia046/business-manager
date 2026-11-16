package com.burhannexus.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

/** Outstanding SMS Template Settings: the same message as on the PC. Saving needs the PC to be reachable. */
public class TemplateActivity extends Activity {
    private static final String[] KEYS = {"business_name", "contact", "account_name", "easypaisa", "jazzcash", "other"};
    private static final String[] LABELS = {"Business Name", "Business Contact Number", "Payment Account Name",
            "Easypaisa Number", "JazzCash Number", "Other Payment Instructions"};

    private EditText edit;
    private TextView info;
    private final EditText[] fields = new EditText[KEYS.length];
    private int baseVersion = 0;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        setTitle("SMS Template Settings");
        LinearLayout page = Ui.page(this);

        page.addView(Ui.text(this, "Outstanding SMS Template", 17, Ui.NAVY, true));
        String help = Store.data(this).optString("instructions", "");
        if (help.isEmpty()) {
            help = "اپنا پیغام اپنی مرضی کے مطابق تحریر کریں۔ جہاں آپ کسٹمر کی بقایا رقم ظاہر کرنا چاہتے ہیں، وہاں لازماً چار ستارے "
                    + "(****) لکھیں۔ سافٹ ویئر خود متعلقہ کسٹمر کی اصل بقایا رقم ظاہر کرے گا۔";
        }
        TextView helpView = Ui.text(this, help, 14, Ui.TEXT, false);
        helpView.setBackground(Ui.outline(this, 0xFFFFF7E0, Ui.GOLD));
        int p = Ui.dp(this, 10);
        helpView.setPadding(p, p, p, p);
        page.addView(helpView, Ui.lp(this, 8));

        edit = new EditText(this);
        edit.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        edit.setMinLines(8);
        edit.setGravity(Gravity.TOP);
        edit.setBackground(Ui.outline(this, 0xFFFFFFFF, Ui.LINE));
        edit.setPadding(p, p, p, p);
        page.addView(edit, Ui.lp(this, 8));
        info = Ui.text(this, "", 12, Ui.MUTED, false);
        page.addView(info, Ui.lp(this, 4));

        Button save = Ui.button(this, "SAVE TEMPLATE", Ui.RED);
        save.setOnClickListener(v -> saveTemplate(false));
        page.addView(save, Ui.lp(this, 10));
        Button preview = Ui.outlineButton(this, "Preview Message");
        preview.setOnClickListener(v -> preview());
        page.addView(preview, Ui.lp(this, 8));
        Button restore = Ui.outlineButton(this, "Restore Default Template");
        restore.setOnClickListener(v -> new AlertDialog.Builder(this).setTitle("Restore the default message?")
                .setMessage("Your own message will be replaced by the standard message, on the computer too.")
                .setPositiveButton("Restore", (d, w) -> saveTemplate(true)).setNegativeButton("Cancel", null).show());
        page.addView(restore, Ui.lp(this, 8));

        page.addView(Ui.text(this, "Business and payment details", 17, Ui.NAVY, true), Ui.lp(this, 22));
        page.addView(Ui.text(this, "Used by the default message. Each business keeps its own details.", 13,
                Ui.MUTED, false), Ui.lp(this, 2));
        for (int i = 0; i < KEYS.length; i++) {
            page.addView(Ui.text(this, LABELS[i], 13, Ui.MUTED, false), Ui.lp(this, 8));
            fields[i] = new EditText(this);
            fields[i].setSingleLine(true);
            page.addView(fields[i]);
        }
        Button saveBusiness = Ui.button(this, "SAVE BUSINESS DETAILS", Ui.NAVY);
        saveBusiness.setOnClickListener(v -> saveBusiness());
        page.addView(saveBusiness, Ui.lp(this, 12));
        fill(true);
    }

    /** Show what is saved. keepDraft=false replaces the text in the editor too. */
    private void fill(boolean replaceText) {
        JSONObject t = Store.template(this);
        baseVersion = t.optInt("version", 0);
        if (replaceText) edit.setText(t.optString("text", ""));
        String when = t.optString("updated_at", "");
        info.setText(baseVersion == 0 ? "Standard message (not edited yet)"
                : "Version " + baseVersion + "  |  saved " + when + "  |  by " + t.optString("updated_by", ""));
        JSONObject biz = Store.data(this).optJSONObject("business");
        if (biz != null && replaceText) {
            for (int i = 0; i < KEYS.length; i++) fields[i].setText(biz.optString(KEYS[i], ""));
        }
    }

    private void preview() {
        String text = edit.getText().toString();
        double amount = 12500;
        String who = "example amount";
        JSONArray all = Store.customers(this);
        if (all.length() > 0 && all.optJSONObject(0) != null) {
            amount = all.optJSONObject(0).optDouble("balance", amount);
            who = all.optJSONObject(0).optString("name");
        }
        String msg = Template.render(text, amount);
        if (msg == null) {
            warnNoStars();
            return;
        }
        new AlertDialog.Builder(this).setTitle("Preview (" + who + ")").setMessage(msg)
                .setPositiveButton("OK", null).show();
    }

    private void warnNoStars() {
        new AlertDialog.Builder(this).setTitle("**** is missing")
                .setMessage("Write exactly four stars **** where the customer's outstanding amount should appear.\n\n"
                        + "جہاں بقایا رقم آنی ہے وہاں چار ستارے (****) لکھیں۔")
                .setPositiveButton("OK", null).show();
    }

    private void saveTemplate(boolean restoreDefault) {
        final String text = edit.getText().toString().trim();
        if (!restoreDefault && !Template.hasSlot(text)) {
            warnNoStars();
            return;
        }
        if (!Store.paired(this)) {
            Ui.toast(this, "Pair with the computer first");
            return;
        }
        info.setText("Saving…");
        Sync.background(() -> {
            JSONObject args = new JSONObject();
            args.put("base_version", baseVersion);
            if (restoreDefault) args.put("restore_default", true); else args.put("text", text);
            return Api.call(this, "template_save", args);
        }, (result, error) -> {
            if (error == null) {
                Store.patch(this, "template", (JSONObject) result);
                fill(true);
                Ui.toast(this, "Saved on the computer. Both devices now use this message.");
            } else if ("conflict".equals(error.code)) {
                fill(true);                                     // the newer message is already in the store
                new AlertDialog.Builder(this).setTitle("A newer message exists")
                        .setMessage("The message was changed on the computer after your last sync. The newest "
                                + "message is loaded now; make your change again and save.")
                        .setPositiveButton("OK", null).show();
            } else {
                fill(false);
                Ui.toast(this, "offline".equals(error.code)
                        ? "Not saved: the computer is not reachable. Connect to the same Wi-Fi and try again."
                        : "Not saved: " + error.getMessage());
            }
        });
    }

    private void saveBusiness() {
        if (!Store.paired(this)) {
            Ui.toast(this, "Pair with the computer first");
            return;
        }
        Sync.background(() -> {
            JSONObject args = new JSONObject();
            for (int i = 0; i < KEYS.length; i++) args.put(KEYS[i], fields[i].getText().toString().trim());
            return Api.call(this, "business_save", args);
        }, (result, error) -> {
            if (error == null) {
                Store.patch(this, "business", (JSONObject) result);
                Ui.toast(this, "Business details saved on the computer");
                Sync.now(this);
            } else {
                Ui.toast(this, "offline".equals(error.code)
                        ? "Not saved: the computer is not reachable." : "Not saved: " + error.getMessage());
            }
        });
    }
}
