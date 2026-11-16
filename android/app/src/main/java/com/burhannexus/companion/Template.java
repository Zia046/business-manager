package com.burhannexus.companion;

import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** The outstanding SMS: four stars (****, or (****)) become the customer's own balance. Same rules as the PC. */
public final class Template {
    private Template() {}

    private static final String FOUR = "(?<!\\*)\\*{4}(?!\\*)";
    private static final Pattern SLOT = Pattern.compile("\\(\\s*" + FOUR + "\\s*\\)|" + FOUR);

    public static boolean hasSlot(String text) {
        return text != null && SLOT.matcher(text).find();
    }

    public static String amount(double value) {
        return new DecimalFormat("#,##0", new DecimalFormatSymbols(Locale.US)).format(Math.round(value));
    }

    /** null when the text has no **** (such a message must never be sent). */
    public static String render(String text, double balance) {
        if (!hasSlot(text)) return null;
        String out = SLOT.matcher(text).replaceAll(Matcher.quoteReplacement(amount(balance)));
        return hasSlot(out) ? null : out;
    }
}
