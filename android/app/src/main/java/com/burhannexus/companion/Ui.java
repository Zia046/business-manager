package com.burhannexus.companion;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

/** Small helpers so every screen has the same Burhan Nexus look (navy, red, white cards). */
public final class Ui {
    private Ui() {}

    public static final int NAVY = Color.parseColor("#14213D"), RED = Color.parseColor("#D32F3A"),
            GREEN = Color.parseColor("#1E8E4E"), GOLD = Color.parseColor("#D99A06"),
            CYAN = Color.parseColor("#0E9FC0"), PURPLE = Color.parseColor("#5A3EC8"),
            ORANGE = Color.parseColor("#E2620E"), TEAL = Color.parseColor("#149A80"),
            BG = Color.parseColor("#F3F5F9"), TEXT = Color.parseColor("#1F2937"), MUTED = Color.parseColor("#64748B"),
            LINE = Color.parseColor("#DDE3EC");

    public static int dp(Context c, float v) {
        return Math.round(v * c.getResources().getDisplayMetrics().density);
    }

    public static String money(double v) {
        return "Rs " + Template.amount(v);
    }

    public static GradientDrawable box(int color, float radiusPx) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(color);
        g.setCornerRadius(radiusPx);
        return g;
    }

    public static GradientDrawable outline(Context c, int fill, int stroke) {
        GradientDrawable g = box(fill, dp(c, 12));
        g.setStroke(dp(c, 1), stroke);
        return g;
    }

    public static TextView text(Context c, String s, float sp, int color, boolean bold) {
        TextView t = new TextView(c);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT_BOLD);
        return t;
    }

    public static Button button(Context c, String label, int color) {
        Button b = new Button(c);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextColor(Color.WHITE);
        b.setTextSize(15);
        b.setTypeface(Typeface.DEFAULT_BOLD);
        b.setBackground(box(color, dp(c, 10)));
        b.setStateListAnimator(null);
        b.setMinHeight(dp(c, 48));
        return b;
    }

    public static Button outlineButton(Context c, String label) {
        Button b = new Button(c);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextColor(NAVY);
        b.setTextSize(15);
        b.setBackground(outline(c, Color.WHITE, NAVY));
        b.setStateListAnimator(null);
        b.setMinHeight(dp(c, 48));
        return b;
    }

    public static LinearLayout.LayoutParams lp(Context c, int topDp) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        p.topMargin = dp(c, topDp);
        return p;
    }

    public static LinearLayout column(Context c) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.VERTICAL);
        return l;
    }

    public static LinearLayout row(Context c) {
        LinearLayout l = new LinearLayout(c);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        return l;
    }

    /** A white card with a thin border. */
    public static LinearLayout card(Context c) {
        LinearLayout l = column(c);
        l.setBackground(outline(c, Color.WHITE, LINE));
        int p = dp(c, 14);
        l.setPadding(p, p, p, p);
        return l;
    }

    /** A filled card for one figure of the dashboard: small title, big value, small note. */
    public static LinearLayout statCard(Context c, int color, String title, TextView value, TextView note) {
        LinearLayout l = column(c);
        l.setBackground(box(color, dp(c, 14)));
        int p = dp(c, 14);
        l.setPadding(p, p, p, p);
        l.addView(text(c, title.toUpperCase(), 12, Color.parseColor("#EBFFFFFF"), true));
        value.setTextColor(Color.WHITE);
        value.setTextSize(24);
        value.setTypeface(Typeface.DEFAULT_BOLD);
        l.addView(value);
        note.setTextColor(Color.parseColor("#EBFFFFFF"));
        note.setTextSize(12);
        l.addView(note);
        return l;
    }

    /** The page body: a scrolling column with the standard padding. Sets it as the activity's content. */
    public static LinearLayout page(Activity a) {
        ScrollView scroll = new ScrollView(a);
        scroll.setBackgroundColor(BG);
        scroll.setFillViewport(true);
        LinearLayout col = column(a);
        int p = dp(a, 16);
        col.setPadding(p, p, p, p);
        scroll.addView(col, new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        a.setContentView(scroll);
        return col;
    }

    public static TextView chip(Context c, String s, int color) {
        TextView t = text(c, s, 11, Color.WHITE, true);
        t.setBackground(box(color, dp(c, 9)));
        t.setPadding(dp(c, 8), dp(c, 2), dp(c, 8), dp(c, 2));
        return t;
    }

    public static View gap(Context c, int dp) {
        View v = new View(c);
        v.setLayoutParams(new LinearLayout.LayoutParams(dp(c, dp), dp(c, dp)));
        return v;
    }

    public static void toast(Context c, String s) {
        Toast.makeText(c, s, Toast.LENGTH_LONG).show();
    }

    /** Opens the phone's own SMS app with the number and the text filled in. The user presses Send there. */
    public static boolean openSms(Activity a, String phone, String body) {
        try {
            Intent i = new Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:" + Uri.encode(phone)));
            i.putExtra("sms_body", body);
            a.startActivity(i);
            return true;
        } catch (ActivityNotFoundException e) {
            toast(a, "No SMS app found on this phone");
            return false;
        }
    }

    /** The message for one customer from the saved template, or null (with a toast) if it cannot be sent. */
    public static String messageFor(Context c, org.json.JSONObject customer) {
        String template = Store.template(c).optString("text", "");
        String msg = Template.render(template, customer.optDouble("balance", 0));
        if (msg == null) {
            toast(c, "The SMS template has no **** for the amount. Fix it in SMS Template Settings.");
        }
        return msg;
    }
}
