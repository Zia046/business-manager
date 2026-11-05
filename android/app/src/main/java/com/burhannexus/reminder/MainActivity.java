package com.burhannexus.reminder;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.telephony.SmsManager;
import android.telephony.SubscriptionInfo;
import android.telephony.SubscriptionManager;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Burhan Reminder: opens the reminders file made by the Business Manager program on the PC and sends each
 * customer's finished message as an SMS from the SIM chosen by the owner.
 */
public class MainActivity extends Activity {
    private static final String PREFS = "reminder";
    private static final String KEY_DATA = "data";
    private static final String KEY_SUB = "sub_id";
    private static final String KEY_SUB_NAME = "sub_name";
    private static final String ACTION_SENT = "com.burhannexus.reminder.SENT";
    private static final int REQ_PICK_FILE = 11;
    private static final int REQ_PERMS = 12;

    private static class Item {
        String id = "", name = "", phone = "", message = "", status = "";
        double amount;
    }

    private final List<Item> items = new ArrayList<>();
    private final Map<String, int[]> pending = new HashMap<>();   // item id -> {parts still to confirm, failed?}
    private final Handler handler = new Handler(Looper.getMainLooper());
    private SharedPreferences prefs;
    private BaseAdapter adapter;
    private TextView header, simLabel;
    private Runnable afterPermission;

    private final BroadcastReceiver sentReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String id = intent.getStringExtra("id");
            int[] st = pending.get(id);
            Item it = find(id);
            if (st == null || it == null) return;
            if (getResultCode() != Activity.RESULT_OK) st[1] = 1;
            st[0]--;
            if (st[0] <= 0) {
                it.status = st[1] == 1 ? "failed" : "sent";
                pending.remove(id);
                save();
                adapter.notifyDataSetChanged();
                updateHeader();
            }
        }
    };

    // ------------------------------------------------------------------ screen
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        setTitle("Burhan Reminder");

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.parseColor("#F3F6FB"));

        LinearLayout top = new LinearLayout(this);
        top.setOrientation(LinearLayout.VERTICAL);
        top.setPadding(dp(14), dp(10), dp(14), dp(8));
        Button open = button("Open reminders file", "#1B6EF3");
        open.setOnClickListener(v -> pickFile());
        top.addView(open, new LinearLayout.LayoutParams(-1, -2));

        LinearLayout simRow = new LinearLayout(this);
        simRow.setOrientation(LinearLayout.HORIZONTAL);
        simRow.setGravity(Gravity.CENTER_VERTICAL);
        simLabel = new TextView(this);
        simLabel.setTextSize(14);
        simLabel.setTextColor(Color.parseColor("#1F2937"));
        simRow.addView(simLabel, new LinearLayout.LayoutParams(0, -2, 1f));
        Button sim = button("Change SIM", "#6B7280");
        sim.setOnClickListener(v -> ensurePermissions(() -> chooseSim(true)));
        simRow.addView(sim);
        top.addView(simRow, new LinearLayout.LayoutParams(-1, -2));

        header = new TextView(this);
        header.setTextSize(15);
        header.setTypeface(Typeface.DEFAULT_BOLD);
        header.setTextColor(Color.parseColor("#0D3B99"));
        header.setPadding(0, dp(6), 0, dp(4));
        top.addView(header);

        Button all = button("Send to all not yet sent", "#16A34A");
        all.setOnClickListener(v -> confirmSendAll());
        top.addView(all, new LinearLayout.LayoutParams(-1, -2));
        root.addView(top);

        ListView list = new ListView(this);
        list.setDividerHeight(dp(1));
        adapter = new RowAdapter();
        list.setAdapter(adapter);
        root.addView(list, new LinearLayout.LayoutParams(-1, 0, 1f));
        setContentView(root);

        IntentFilter f = new IntentFilter(ACTION_SENT);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(sentReceiver, f, Context.RECEIVER_NOT_EXPORTED);
        else registerReceiver(sentReceiver, f);

        load();
        updateHeader();
        handleIntent(getIntent());
        ensurePermissions(() -> {
            if (!prefs.contains(KEY_SUB)) chooseSim(false);
            updateHeader();
        });
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        handleIntent(intent);
    }

    @Override
    protected void onDestroy() {
        unregisterReceiver(sentReceiver);
        super.onDestroy();
    }

    private Button button(String text, String color) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextColor(Color.WHITE);
        b.setBackgroundColor(Color.parseColor(color));
        b.setPadding(dp(14), dp(6), dp(14), dp(6));
        return b;
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    private void updateHeader() {
        int sent = 0;
        double total = 0;
        for (Item it : items) {
            total += it.amount;
            if ("sent".equals(it.status)) sent++;
        }
        header.setText(items.isEmpty() ? "No file opened yet."
                : String.format(Locale.US, "%d customers, Rs %,.0f   |   %d sent", items.size(), total, sent));
        String name = prefs.getString(KEY_SUB_NAME, "");
        simLabel.setText("SIM: " + (name.isEmpty() ? "not chosen yet" : name));
    }

    // ------------------------------------------------------------------ file
    private void pickFile() {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("*/*");
        startActivityForResult(i, REQ_PICK_FILE);
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (req == REQ_PICK_FILE && res == RESULT_OK && data != null && data.getData() != null) {
            importFile(data.getData());
        }
    }

    private void handleIntent(Intent intent) {
        if (intent != null && Intent.ACTION_VIEW.equals(intent.getAction()) && intent.getData() != null) {
            importFile(intent.getData());
        }
    }

    private void importFile(Uri uri) {
        try (InputStream in = getContentResolver().openInputStream(uri)) {
            if (in == null) throw new Exception("File could not be opened");
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            JSONObject root = new JSONObject(out.toString("UTF-8"));
            if (!"BusinessManagerReminders".equals(root.optString("app"))) {
                throw new Exception("This is not a reminders file made by Business Manager");
            }
            JSONArray arr = root.getJSONArray("items");
            List<Item> fresh = new ArrayList<>();
            for (int k = 0; k < arr.length(); k++) {
                JSONObject o = arr.getJSONObject(k);
                Item it = new Item();
                it.id = String.valueOf(o.get("id"));
                it.name = o.optString("name");
                it.phone = o.optString("phone");
                it.amount = o.optDouble("amount", 0);
                it.message = o.optString("message");
                fresh.add(it);
            }
            items.clear();
            items.addAll(fresh);
            pending.clear();
            save();
            adapter.notifyDataSetChanged();
            updateHeader();
            Toast.makeText(this, items.size() + " customers loaded", Toast.LENGTH_SHORT).show();
        } catch (Exception e) {
            new AlertDialog.Builder(this).setTitle("File not opened").setMessage(String.valueOf(e.getMessage()))
                    .setPositiveButton("OK", null).show();
        }
    }

    private void save() {
        try {
            JSONArray arr = new JSONArray();
            for (Item it : items) {
                JSONObject o = new JSONObject();
                o.put("id", it.id).put("name", it.name).put("phone", it.phone).put("amount", it.amount)
                        .put("message", it.message).put("status", it.status);
                arr.put(o);
            }
            prefs.edit().putString(KEY_DATA, arr.toString()).apply();
        } catch (Exception ignored) {
        }
    }

    private void load() {
        try {
            JSONArray arr = new JSONArray(prefs.getString(KEY_DATA, "[]"));
            for (int k = 0; k < arr.length(); k++) {
                JSONObject o = arr.getJSONObject(k);
                Item it = new Item();
                it.id = o.optString("id");
                it.name = o.optString("name");
                it.phone = o.optString("phone");
                it.amount = o.optDouble("amount", 0);
                it.message = o.optString("message");
                it.status = o.optString("status");
                if ("sending".equals(it.status)) it.status = "";     // an interrupted send is not "sent"
                items.add(it);
            }
        } catch (Exception ignored) {
        }
    }

    private Item find(String id) {
        for (Item it : items) if (it.id.equals(id)) return it;
        return null;
    }

    // ------------------------------------------------------------------ permission + SIM
    private boolean hasPermissions() {
        return checkSelfPermission(Manifest.permission.SEND_SMS) == PackageManager.PERMISSION_GRANTED
                && checkSelfPermission(Manifest.permission.READ_PHONE_STATE) == PackageManager.PERMISSION_GRANTED;
    }

    private void ensurePermissions(Runnable then) {
        if (hasPermissions()) {
            then.run();
            return;
        }
        afterPermission = then;
        requestPermissions(new String[]{Manifest.permission.SEND_SMS, Manifest.permission.READ_PHONE_STATE}, REQ_PERMS);
    }

    @Override
    public void onRequestPermissionsResult(int req, String[] perms, int[] results) {
        super.onRequestPermissionsResult(req, perms, results);
        if (req != REQ_PERMS) return;
        Runnable r = afterPermission;
        afterPermission = null;
        if (hasPermissions()) {
            if (r != null) r.run();
        } else {
            new AlertDialog.Builder(this).setTitle("Permission needed")
                    .setMessage("To send SMS the app needs the permission to send messages and to see the SIM cards. "
                            + "Please allow them (Settings > Apps > Burhan Reminder > Permissions).")
                    .setPositiveButton("OK", null).show();
        }
    }

    private void chooseSim(boolean force) {
        final List<SubscriptionInfo> subs;
        try {
            SubscriptionManager sm = (SubscriptionManager) getSystemService(Context.TELEPHONY_SUBSCRIPTION_SERVICE);
            List<SubscriptionInfo> l = sm.getActiveSubscriptionInfoList();
            subs = l == null ? new ArrayList<>() : l;
        } catch (SecurityException e) {
            return;
        }
        if (subs.size() <= 1) {                                    // one SIM (or unknown): nothing to choose
            int id = subs.isEmpty() ? -1 : subs.get(0).getSubscriptionId();
            String name = subs.isEmpty() ? "default SIM" : label(subs.get(0));
            prefs.edit().putInt(KEY_SUB, id).putString(KEY_SUB_NAME, name).apply();
            updateHeader();
            if (force) Toast.makeText(this, "Only one SIM found: " + name, Toast.LENGTH_SHORT).show();
            return;
        }
        String[] names = new String[subs.size()];
        for (int k = 0; k < names.length; k++) names[k] = label(subs.get(k));
        new AlertDialog.Builder(this).setTitle("Send messages from which SIM?").setCancelable(false)
                .setItems(names, (d, which) -> {
                    prefs.edit().putInt(KEY_SUB, subs.get(which).getSubscriptionId())
                            .putString(KEY_SUB_NAME, names[which]).apply();
                    updateHeader();
                }).show();
    }

    private String label(SubscriptionInfo s) {
        return "SIM " + (s.getSimSlotIndex() + 1) + " - " + s.getDisplayName();
    }

    // ------------------------------------------------------------------ sending
    @SuppressWarnings("deprecation")
    private SmsManager smsManager() {
        int sub = prefs.getInt(KEY_SUB, -1);
        if (Build.VERSION.SDK_INT >= 31) {
            SmsManager base = getSystemService(SmsManager.class);
            return sub >= 0 ? base.createForSubscriptionId(sub) : base;
        }
        return sub >= 0 ? SmsManager.getSmsManagerForSubscriptionId(sub) : SmsManager.getDefault();
    }

    private void confirmSend(Item it) {
        new AlertDialog.Builder(this).setTitle("Send to " + it.name + "?")
                .setMessage(it.phone + "\n\n" + it.message)
                .setPositiveButton("Send", (d, w) -> ensurePermissions(() -> {
                    if (!prefs.contains(KEY_SUB)) chooseSim(false);
                    send(it);
                }))
                .setNegativeButton("Cancel", null).show();
    }

    private void confirmSendAll() {
        final List<Item> todo = new ArrayList<>();
        for (Item it : items) if (!"sent".equals(it.status) && !it.phone.isEmpty()) todo.add(it);
        if (todo.isEmpty()) {
            Toast.makeText(this, "Nothing left to send", Toast.LENGTH_SHORT).show();
            return;
        }
        new AlertDialog.Builder(this).setTitle("Send " + todo.size() + " messages?")
                .setMessage("A message goes to each of these customers from the chosen SIM ("
                        + prefs.getString(KEY_SUB_NAME, "default") + "). Operator SMS charges apply.")
                .setPositiveButton("Send all", (d, w) -> ensurePermissions(() -> {
                    if (!prefs.contains(KEY_SUB)) chooseSim(false);
                    long delay = 0;
                    for (Item it : todo) {
                        handler.postDelayed(() -> send(it), delay);
                        delay += 2500;                                   // gently, one after another
                    }
                }))
                .setNegativeButton("Cancel", null).show();
    }

    private void send(Item it) {
        if (pending.containsKey(it.id)) return;
        try {
            SmsManager sms = smsManager();
            ArrayList<String> parts = sms.divideMessage(it.message);
            ArrayList<PendingIntent> sentIntents = new ArrayList<>();
            for (int k = 0; k < parts.size(); k++) {
                Intent i = new Intent(ACTION_SENT).setPackage(getPackageName()).putExtra("id", it.id);
                int code = (it.id + "#" + k).hashCode();
                sentIntents.add(PendingIntent.getBroadcast(this, code, i,
                        PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
            }
            pending.put(it.id, new int[]{parts.size(), 0});
            it.status = "sending";
            adapter.notifyDataSetChanged();
            sms.sendMultipartTextMessage(it.phone, null, parts, sentIntents, null);
        } catch (Exception e) {
            pending.remove(it.id);
            it.status = "failed";
            adapter.notifyDataSetChanged();
            Toast.makeText(this, "Could not send to " + it.name + ": " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
        updateHeader();
    }

    // ------------------------------------------------------------------ list
    private class RowAdapter extends BaseAdapter {
        @Override public int getCount() { return items.size(); }
        @Override public Object getItem(int p) { return items.get(p); }
        @Override public long getItemId(int p) { return p; }

        @Override
        public View getView(int pos, View convert, ViewGroup parent) {
            final Item it = items.get(pos);
            LinearLayout row = new LinearLayout(MainActivity.this);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setPadding(dp(14), dp(10), dp(14), dp(10));
            row.setBackgroundColor(Color.WHITE);

            LinearLayout text = new LinearLayout(MainActivity.this);
            text.setOrientation(LinearLayout.VERTICAL);
            TextView name = new TextView(MainActivity.this);
            name.setText(it.name);
            name.setTextSize(16);
            name.setTypeface(Typeface.DEFAULT_BOLD);
            name.setTextColor(Color.parseColor("#111827"));
            TextView sub = new TextView(MainActivity.this);
            sub.setText(String.format(Locale.US, "%s   |   Rs %,.0f", it.phone, it.amount));
            sub.setTextSize(13);
            sub.setTextColor(Color.parseColor("#4B5563"));
            text.addView(name);
            text.addView(sub);
            row.addView(text, new LinearLayout.LayoutParams(0, -2, 1f));

            TextView status = new TextView(MainActivity.this);
            status.setTextSize(13);
            status.setPadding(0, 0, dp(10), 0);
            switch (it.status) {
                case "sent": status.setText("Sent ✔"); status.setTextColor(Color.parseColor("#16A34A")); break;
                case "failed": status.setText("Failed"); status.setTextColor(Color.parseColor("#DC2626")); break;
                case "sending": status.setText("Sending..."); status.setTextColor(Color.parseColor("#B45309")); break;
                default: status.setText("");
            }
            row.addView(status);

            Button send = button("sent".equals(it.status) ? "Send again" : "Send", "#1B6EF3");
            send.setFocusable(false);
            send.setOnClickListener(v -> confirmSend(it));
            row.addView(send);
            return row;
        }
    }
}
