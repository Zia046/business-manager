"""Activation Key generator - FOR THE OWNER ONLY (Burhan Nexus).

Keep `license_private.key` secret and backed up in two places. Whoever has that file can issue keys.
Put it in the same folder as this program (or choose it when asked). Needs no installation:
    KeyGenerator.exe   (built by GitHub Actions)    or    python tools/keygen_gui.py
"""
import csv
import sys
import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from app.services import licensing  # noqa: E402

KEY_FILE = "license_private.key"


def base_dir() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def load_private(path: Path) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(path.read_text().strip()))


def make_key(private: Ed25519PrivateKey, machine_code: str, expiry: date | None) -> str:
    return licensing.encode_key(machine_code, expiry, private.sign)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Business Manager - Activation Key Generator (owner only)")
        self.geometry("640x520")
        self.private = None
        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Machine Code sent by the customer:").pack(anchor="w")
        self.machine = ttk.Entry(f, font=("Consolas", 14))
        self.machine.pack(fill="x", pady=(2, 10))
        ttk.Label(f, text="Customer / shop name (for your record):").pack(anchor="w")
        self.customer = ttk.Entry(f)
        self.customer.pack(fill="x", pady=(2, 10))
        ttk.Label(f, text="Licence period:").pack(anchor="w")
        self.period = tk.StringVar(value="life")
        for text, val in (("For life (never expires)", "life"), ("1 year", "365"), ("6 months", "182"),
                          ("1 month", "30"), ("Custom number of days:", "custom")):
            ttk.Radiobutton(f, text=text, value=val, variable=self.period).pack(anchor="w")
        self.days = ttk.Entry(f, width=8)
        self.days.pack(anchor="w", padx=22, pady=(0, 10))
        ttk.Button(f, text="Generate Activation Key", command=self.generate).pack(fill="x", pady=4)
        self.out = tk.Text(f, height=6, wrap="char", font=("Consolas", 11))
        self.out.pack(fill="both", expand=True)
        ttk.Button(f, text="Copy Key", command=self.copy).pack(fill="x", pady=4)
        self.info = ttk.Label(f, text="")
        self.info.pack(anchor="w")
        self.after(100, self.ensure_private)

    def ensure_private(self):
        p = base_dir() / KEY_FILE
        if not p.exists():
            messagebox.showinfo("Private key", f"Select your {KEY_FILE} file.")
            chosen = filedialog.askopenfilename(title=f"Select {KEY_FILE}")
            if not chosen:
                self.destroy()
                return
            p = Path(chosen)
        try:
            self.private = load_private(p)
        except Exception:
            messagebox.showerror("Private key", "This file is not a valid private key.")
            self.destroy()
            return
        self.key_path = p

    def generate(self):
        if not self.private:
            return
        code = self.machine.get().strip()
        try:
            if self.period.get() == "life":
                expiry = None
            else:
                n = int(self.days.get()) if self.period.get() == "custom" else int(self.period.get())
                expiry = date.today() + timedelta(days=n)
            key = make_key(self.private, code, expiry)
        except Exception as exc:
            messagebox.showerror("Cannot generate", f"Check the Machine Code and period.\n\n{exc}")
            return
        self.out.delete("1.0", "end")
        self.out.insert("1.0", key)
        until = "for life" if expiry is None else f"until {expiry:%d-%m-%Y}"
        self.info.config(text=f"Key created ({until}). Send it only to this customer.")
        log = self.key_path.parent / "keys_issued.csv"        # your own record of who got a key
        new = not log.exists()
        with open(log, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["date", "customer", "machine_code", "valid_until"])
            w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), self.customer.get().strip(), code,
                        "life" if expiry is None else expiry.isoformat()])

    def copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.out.get("1.0", "end").strip())


if __name__ == "__main__":
    App().mainloop()
