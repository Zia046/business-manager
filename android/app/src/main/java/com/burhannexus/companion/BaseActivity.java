package com.burhannexus.companion;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.burhannexus.companion.sync.Engine;

/**
 * Every screen: a navy top bar with the three-line menu, the screen's title and the sync status line,
 * and a side drawer (slides in from the left) with all modules in sections. The open screen is highlighted.
 */
public class BaseActivity extends Activity {
    private FrameLayout root;
    private FrameLayout content;
    private View scrim;
    private ScrollView drawer;
    private TextView titleView, statusView;
    private boolean drawerOpen;

    // section, then {label, icon, screen key}
    static final Object[][] MENU = {
            {"Main", new String[][] {{"Dashboard", "🏠", "home"}}},
            {"Sale", new String[][] {{"New Sale", "🧾", "new:sale"}, {"Sales History", "📜", "list:invoice"},
                    {"Sale Return", "↩️", "new:sale_return"}, {"Receive Payment", "💵", "money:receipt"}}},
            {"Purchase", new String[][] {{"New Purchase", "🛒", "new:purchase"}, {"Purchase History", "📦", "list:purchase"},
                    {"Purchase Return", "↪️", "new:purchase_return"}, {"Pay Supplier", "💸", "money:supplier_payment"}}},
            {"Stock", new String[][] {{"Products & Stock", "📋", "list:product"}, {"Mobile Phones (IMEI)", "📱", "list:phone"},
                    {"Low Stock", "⚠️", "list:low"}}},
            {"Accounts", new String[][] {{"Customers", "👥", "list:customer"}, {"Suppliers", "🏭", "list:supplier"},
                    {"Outstanding", "📒", "outstanding"}, {"Payments History", "🧮", "list:voucher"},
                    {"Returns History", "🔁", "list:return"}, {"Expenses", "🧾", "list:expense"},
                    {"New Expense", "➕", "money:expense"}}},
            {"Reports", new String[][] {{"Stock Position", "📊", "biz:stock"}, {"Mobile in Hand", "📱", "biz:mobiles"},
                    {"Sales Overview", "📈", "biz:sales"}, {"Purchase Overview", "📉", "biz:purchases"},
                    {"Financial Overview", "💰", "biz:finance"}, {"Recent Activity", "🕘", "biz:activity"}}},
            {"Messages", new String[][] {{"SMS Reminders", "✉️", "reminders"}, {"SMS Template", "📝", "template"}}},
            {"Settings", new String[][] {{"Sync & Conflicts", "🔄", "list:sync"},
                    {"Connection with Computer", "🔗", "connect"}}},
    };

    /** Which menu entry this screen is (highlighted in the drawer). */
    protected String screenKey() {
        return "";
    }

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        root = new FrameLayout(this);
        LinearLayout frame = Ui.column(this);
        frame.setBackgroundColor(Ui.BG);

        LinearLayout bar = Ui.row(this);
        bar.setBackgroundColor(Ui.NAVY);
        bar.setPadding(Ui.dp(this, 4), Ui.dp(this, 6), Ui.dp(this, 12), Ui.dp(this, 6));
        TextView burger = Ui.text(this, "☰", 24, Color.WHITE, true);
        burger.setPadding(Ui.dp(this, 12), Ui.dp(this, 4), Ui.dp(this, 14), Ui.dp(this, 4));
        burger.setContentDescription("Menu");
        burger.setOnClickListener(v -> toggleDrawer());
        bar.addView(burger);
        titleView = Ui.text(this, String.valueOf(getTitle()), 18, Color.WHITE, true);
        titleView.setSingleLine(true);
        bar.addView(titleView, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        frame.addView(bar);

        statusView = Ui.text(this, "", 12, Color.WHITE, false);
        statusView.setGravity(Gravity.CENTER);
        statusView.setPadding(0, Ui.dp(this, 3), 0, Ui.dp(this, 3));
        statusView.setOnClickListener(v -> Sync.now(this));
        frame.addView(statusView);

        content = new FrameLayout(this);
        frame.addView(content, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        root.addView(frame);

        scrim = new View(this);
        scrim.setBackgroundColor(Color.parseColor("#66000000"));
        scrim.setVisibility(View.GONE);
        scrim.setOnClickListener(v -> closeDrawer());
        root.addView(scrim);

        drawer = buildDrawer();
        int w = Math.min(Ui.dp(this, 300), (int) (getResources().getDisplayMetrics().widthPixels * 0.82));
        root.addView(drawer, new FrameLayout.LayoutParams(w, ViewGroup.LayoutParams.MATCH_PARENT, Gravity.START));
        drawer.setTranslationX(-w);
        drawer.setVisibility(View.INVISIBLE);
        super.setContentView(root);
    }

    @Override
    public void setTitle(CharSequence title) {
        super.setTitle(title);
        if (titleView != null) titleView.setText(title);
    }

    /** Screens keep calling setContentView as before: their view goes under the bar. */
    @Override
    public void setContentView(View v) {
        if (content == null) {
            super.setContentView(v);
            return;
        }
        content.removeAllViews();
        content.addView(v, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));
    }

    private ScrollView buildDrawer() {
        ScrollView s = new ScrollView(this);
        s.setBackgroundColor(Color.WHITE);
        s.setElevation(Ui.dp(this, 12));
        LinearLayout col = Ui.column(this);
        col.setPadding(0, 0, 0, Ui.dp(this, 20));
        LinearLayout head = Ui.column(this);
        head.setBackgroundColor(Ui.NAVY);
        head.setPadding(Ui.dp(this, 18), Ui.dp(this, 22), Ui.dp(this, 18), Ui.dp(this, 16));
        String shop = Store.shop(this);
        head.addView(Ui.text(this, shop.isEmpty() ? "Burhan Nexus" : shop, 19, Color.WHITE, true));
        head.addView(Ui.text(this, "Business Manager", 13, Color.parseColor("#CCFFFFFF"), false));
        col.addView(head);
        String me = screenKey();
        for (Object[] section : MENU) {
            TextView h = Ui.text(this, ((String) section[0]).toUpperCase(), 11, Ui.MUTED, true);
            h.setPadding(Ui.dp(this, 18), Ui.dp(this, 14), 0, Ui.dp(this, 4));
            col.addView(h);
            for (String[] item : (String[][]) section[1]) {
                LinearLayout row = Ui.row(this);
                row.setPadding(Ui.dp(this, 16), Ui.dp(this, 11), Ui.dp(this, 16), Ui.dp(this, 11));
                boolean active = item[2].equals(me);
                if (active) row.setBackground(Ui.box(Color.parseColor("#FBE3E5"), 0));
                TextView ic = Ui.text(this, item[1], 17, Ui.TEXT, false);
                ic.setWidth(Ui.dp(this, 34));
                row.addView(ic);
                TextView label = Ui.text(this, item[0], 15, active ? Ui.RED : Ui.TEXT, active);
                if (active) label.setTypeface(Typeface.DEFAULT_BOLD);
                row.addView(label);
                final String target = item[2];
                row.setOnClickListener(v -> {
                    closeDrawer();
                    if (!target.equals(me)) open(this, target);
                });
                col.addView(row);
            }
        }
        s.addView(col);
        return s;
    }

    /** Opens a module by its menu key. */
    public static void open(Activity a, String key) {
        Intent i;
        if (key.equals("home")) {
            i = new Intent(a, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        } else if (key.startsWith("new:")) {
            i = new Intent(a, DocActivity.class).putExtra("kind", key.substring(4));
        } else if (key.startsWith("money:")) {
            i = new Intent(a, MoneyActivity.class).putExtra("kind", key.substring(6));
        } else if (key.startsWith("list:")) {
            i = new Intent(a, ListActivity.class).putExtra("kind", key.substring(5));
        } else if (key.startsWith("biz:")) {
            i = new Intent(a, BusinessActivity.class).putExtra("section", key.substring(4));
        } else if (key.equals("outstanding")) {
            i = new Intent(a, OutstandingActivity.class);
        } else if (key.equals("reminders")) {
            i = new Intent(a, ReminderActivity.class);
        } else if (key.equals("template")) {
            i = new Intent(a, TemplateActivity.class);
        } else {
            i = new Intent(a, ConnectActivity.class);
        }
        a.startActivity(i);
    }

    private void toggleDrawer() {
        if (drawerOpen) closeDrawer(); else openDrawer();
    }

    private void openDrawer() {
        drawerOpen = true;
        drawer.setVisibility(View.VISIBLE);
        scrim.setVisibility(View.VISIBLE);
        scrim.setAlpha(0f);
        scrim.animate().alpha(1f).setDuration(180).start();
        drawer.animate().translationX(0).setDuration(200).start();
    }

    private void closeDrawer() {
        if (!drawerOpen) return;
        drawerOpen = false;
        drawer.animate().translationX(-drawer.getWidth()).setDuration(180)
                .withEndAction(() -> drawer.setVisibility(View.INVISIBLE)).start();
        scrim.animate().alpha(0f).setDuration(180).withEndAction(() -> scrim.setVisibility(View.GONE)).start();
    }

    @Override
    public void onBackPressed() {
        if (drawerOpen) closeDrawer(); else super.onBackPressed();
    }

    static final long AUTO_SYNC_MS = 30_000;
    private final android.os.Handler ticker = new android.os.Handler(android.os.Looper.getMainLooper());
    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            Sync.now(BaseActivity.this);
            ticker.postDelayed(this, AUTO_SYNC_MS);
        }
    };

    @Override
    protected void onResume() {
        super.onResume();
        Sync.addListener(shellListener);
        showStatus();
        ticker.removeCallbacks(tick);
        ticker.postDelayed(tick, 800);           // sync on opening a screen, then every 30 seconds
    }

    @Override
    protected void onPause() {
        super.onPause();
        Sync.removeListener(shellListener);
        ticker.removeCallbacks(tick);
    }

    private final Sync.Listener shellListener = () -> {
        showStatus();
        onDataChanged();
    };

    /** Called after a sync: screens redraw their figures. */
    protected void onDataChanged() {
    }

    private void showStatus() {
        if (statusView == null) return;
        if (!Store.paired(this)) {
            statusView.setText("Not paired – open menu ☰ > Connection");
            statusView.setBackgroundColor(Ui.MUTED);
            return;
        }
        Engine e = Local.engine(this);
        String s = Sync.state == Sync.RUNNING ? Engine.SYNCING : e.state();
        int unsent = 0;
        for (com.burhannexus.companion.sync.Op o : e.store.ops()) {
            if (com.burhannexus.companion.sync.Op.PENDING.equals(o.status)) unsent++;
        }
        int color = Engine.CONNECTED.equals(s) || Engine.COMPLETED.equals(s) ? Ui.GREEN
                : Engine.SYNCING.equals(s) ? Ui.CYAN : Engine.RETRY.equals(s) ? Ui.ORANGE : Ui.MUTED;
        statusView.setText(s + (unsent > 0 ? "  ·  " + unsent + " waiting" : ""));
        statusView.setBackgroundColor(color);
    }
}
