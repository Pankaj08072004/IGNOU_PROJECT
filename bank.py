import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

# Optional PIL for image preview
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Optional reportlab for PDF generation
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.graphics.barcode import qr
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics import renderPDF
    from reportlab.lib.utils import ImageReader
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

import mysql.connector

# -------------- ICON PATH ----------------
_ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")

def _set_icon(win):
    """Set logo.ico on any Tk or Toplevel window, silently skip if unavailable."""
    try:
        win.iconbitmap(_ICON_PATH)
    except Exception:
        pass

# -------------- BUTTON IMAGE LOADER ----------------
_BTN_IMAGES = {}  # global cache so images aren't garbage-collected

def _load_btn_image(name, size=(20, 20)):
    """
    Load a PNG button image by name.
    name: filename without extension, e.g. 'Login'
    Returns a PhotoImage or None if PIL unavailable / file missing.
    """
    if not PIL_AVAILABLE:
        return None
    key = (name, size)
    if key in _BTN_IMAGES:
        return _BTN_IMAGES[key]
    # Look for the image next to this script OR in a fixed uploads folder
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.png"),
        os.path.join("/mnt/user-data/uploads", f"{name}.png"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                img = Image.open(path).resize(size, Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                _BTN_IMAGES[key] = photo
                return photo
            except Exception:
                pass
    return None

def _set_btn_image(btn, name, size=(20, 20)):
    """Attach a PNG image to a ttk.Button (image on left, text on right)."""
    photo = _load_btn_image(name, size)
    if photo:
        btn.configure(image=photo, compound="left")
        btn.image = photo  # prevent GC

# -------------- MySQL CONFIG ----------------
DB_HOST = "localhost"
DB_USER = "root"          # <-- change to your MySQL username
DB_PASSWORD = "Admin@123"     # <-- change to your MySQL password
DB_NAME = "bankdb"

BANK_NAME = "Modern Bank of India"

# -------------- DATABASE LAYER --------------
def get_connection(db=None):
    """Return a MySQL connection."""
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=db
    )

def init_database():
    """Create database, tables if not exist, and ensure new columns exist."""
    # Create database if not exists
    conn = get_connection(None)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
    conn.commit()
    cur.close()
    conn.close()

    # Create tables
    conn = get_connection(DB_NAME)
    cur = conn.cursor()

    # Customers table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            account_no VARCHAR(20) UNIQUE NOT NULL,
            password VARCHAR(100) NOT NULL,
            name VARCHAR(100) NOT NULL,
            father_name VARCHAR(100),
            mother_name VARCHAR(100),
            aadhaar VARCHAR(12),
            address VARCHAR(255),
            mobile VARCHAR(20),
            ifsc VARCHAR(20),
            branch VARCHAR(100),
            signature_path VARCHAR(255),
            balance DECIMAL(15,2) DEFAULT 0,
            photo_path VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Transactions table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            account_no VARCHAR(20) NOT NULL,
            txn_type ENUM('DEPOSIT','WITHDRAW') NOT NULL,
            amount DECIMAL(15,2) NOT NULL,
            txn_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_no) REFERENCES customers(account_no)
                ON DELETE CASCADE
        )
        """
    )

    # Pending accounts table (for approval system)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_accounts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            account_no VARCHAR(20) UNIQUE NOT NULL,
            password VARCHAR(100) NOT NULL,
            name VARCHAR(100) NOT NULL,
            father_name VARCHAR(100),
            mother_name VARCHAR(100),
            aadhaar VARCHAR(12),
            address VARCHAR(255),
            mobile VARCHAR(20),
            ifsc VARCHAR(20),
            branch VARCHAR(100),
            signature_path VARCHAR(255),
            opening_balance DECIMAL(15,2) DEFAULT 0,
            photo_path VARCHAR(255),
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Ensure new columns exist even if tables were created by older version
    try:
        # Customers
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS address VARCHAR(255)")
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS mobile VARCHAR(20)")
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS ifsc VARCHAR(20)")
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS branch VARCHAR(100)")
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS signature_path VARCHAR(255)")
        # Pending
        cur.execute("ALTER TABLE pending_accounts ADD COLUMN IF NOT EXISTS address VARCHAR(255)")
        cur.execute("ALTER TABLE pending_accounts ADD COLUMN IF NOT EXISTS mobile VARCHAR(20)")
        cur.execute("ALTER TABLE pending_accounts ADD COLUMN IF NOT EXISTS ifsc VARCHAR(20)")
        cur.execute("ALTER TABLE pending_accounts ADD COLUMN IF NOT EXISTS branch VARCHAR(100)")
        cur.execute("ALTER TABLE pending_accounts ADD COLUMN IF NOT EXISTS signature_path VARCHAR(255)")
    except Exception:
        # Older MySQL may not support IF NOT EXISTS; ignore if columns already exist.
        pass

    conn.commit()
    cur.close()
    conn.close()

# ---------- AUTO ACCOUNT NUMBER (START FROM 10000001) ---------
def generate_next_account_no():
    """
    Generate next numeric account number:
    - Looks at both customers and pending_accounts.
    - Uses highest numeric account_no and adds 1.
    - If none numeric, starts from 10000001.
    """
    conn = get_connection(DB_NAME)
    cur = conn.cursor()
    max_num = 0

    for table in ("customers", "pending_accounts"):
        try:
            cur.execute(f"SELECT account_no FROM {table}")
            for (acc,) in cur.fetchall():
                if acc and acc.isdigit():
                    n = int(acc)
                    if n > max_num:
                        max_num = n
        except mysql.connector.Error:
            pass

    cur.close()
    conn.close()

    if max_num == 0:
        return "10000001"
    else:
        return str(max_num + 1)

# ---------- Customers (approved) ------------
def create_customer(data):
    """
    Directly create a customer (used by approval logic).
    data: dict with keys:
        account_no, password, name, father_name, mother_name,
        aadhaar, address, mobile, ifsc, branch, signature_path,
        balance, photo_path
    """
    conn = get_connection(DB_NAME)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO customers
                (account_no, password, name, father_name, mother_name,
                 aadhaar, address, mobile, ifsc, branch, signature_path,
                 balance, photo_path)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                data["account_no"],
                data["password"],
                data["name"],
                data["father_name"],
                data["mother_name"],
                data["aadhaar"],
                data["address"],
                data["mobile"],
                data["ifsc"],
                data["branch"],
                data["signature_path"],
                data["balance"],
                data["photo_path"],
            )
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

def get_all_customers():
    """Return all approved customers ordered by ID."""
    conn = get_connection(DB_NAME)
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT id, account_no, name, father_name, mother_name,
               aadhaar, address, mobile, ifsc, branch,
               signature_path, balance, photo_path
        FROM customers
        ORDER BY id ASC
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def search_customers(keyword):
    """Search customers by name, account_no, or aadhaar."""
    like = f"%{keyword}%"
    conn = get_connection(DB_NAME)
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT id, account_no, name, father_name, mother_name,
               aadhaar, address, mobile, ifsc, branch,
               signature_path, balance, photo_path
        FROM customers
        WHERE name LIKE %s
           OR account_no LIKE %s
           OR aadhaar LIKE %s
        ORDER BY id ASC
        """,
        (like, like, like)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def delete_customer(cust_id):
    """Delete a customer and all their transactions by internal ID."""
    conn = get_connection(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM customers WHERE id = %s", (cust_id,))
    conn.commit()
    cur.close()
    conn.close()

def get_customer_by_login(account_no, password):
    """Return customer row matching account_no and password, or None."""
    conn = get_connection(DB_NAME)
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT *
        FROM customers
        WHERE account_no = %s AND password = %s
        """,
        (account_no, password)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def get_customer_by_aadhaar(aadhaar, password):
    """Return customer row matching Aadhaar number and password, or None."""
    conn = get_connection(DB_NAME)
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT *
        FROM customers
        WHERE aadhaar = %s AND password = %s
        """,
        (aadhaar, password)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def get_customer_by_account(account_no):
    """Return customer row for the given account number, or None."""
    conn = get_connection(DB_NAME)
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT *
        FROM customers
        WHERE account_no = %s
        """,
        (account_no,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

# ---------- Customer Password Update ----------
def update_customer_password(account_no, new_password):
    """Update password for a customer by account number."""
    conn = get_connection(DB_NAME)
    cur = conn.cursor()
    cur.execute(
        "UPDATE customers SET password = %s WHERE account_no = %s",
        (new_password, account_no)
    )
    conn.commit()
    cur.close()
    conn.close()

# ---------- Pending Accounts (for approval) ----------
def create_pending_account(data):
    """
    Insert account into pending_accounts instead of customers.
    data keys:
        account_no, password, name, father_name, mother_name,
        aadhaar, address, mobile, ifsc, branch,
        signature_path, opening_balance, photo_path
    """
    conn = get_connection(DB_NAME)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO pending_accounts
                (account_no, password, name, father_name, mother_name,
                 aadhaar, address, mobile, ifsc, branch,
                 signature_path, opening_balance, photo_path)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                data["account_no"],
                data["password"],
                data["name"],
                data["father_name"],
                data["mother_name"],
                data["aadhaar"],
                data["address"],
                data["mobile"],
                data["ifsc"],
                data["branch"],
                data["signature_path"],
                data["opening_balance"],
                data["photo_path"],
            )
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

def get_all_pending_accounts():
    """Return all pending account requests ordered by ID."""
    conn = get_connection(DB_NAME)
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT id, account_no, name, father_name, mother_name,
               aadhaar, address, mobile, ifsc, branch,
               signature_path, opening_balance, photo_path, requested_at
        FROM pending_accounts
        ORDER BY id ASC
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def get_pending_account_by_account(account_no):
    """Get one pending account by account number."""
    conn = get_connection(DB_NAME)
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT *
        FROM pending_accounts
        WHERE account_no = %s
        """,
        (account_no,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def delete_pending_account(pending_id):
    """Delete a pending account request by its internal ID (used for rejection)."""
    conn = get_connection(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM pending_accounts WHERE id = %s", (pending_id,))
    conn.commit()
    cur.close()
    conn.close()

def approve_pending_account(pending_id):
    """
    Move record from pending_accounts -> customers,
    set opening balance, create initial DEPOSIT transaction (if > 0),
    then delete from pending_accounts.
    """
    conn = get_connection(DB_NAME)
    cur = conn.cursor(dictionary=True)
    try:
        # Get pending record
        cur.execute(
            """
            SELECT *
            FROM pending_accounts
            WHERE id = %s
            """,
            (pending_id,)
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Pending account not found")

        account_no = row["account_no"]

        # Insert into customers
        cur2 = conn.cursor()
        try:
            cur2.execute(
                """
                INSERT INTO customers
                    (account_no, password, name, father_name, mother_name,
                     aadhaar, address, mobile, ifsc, branch, signature_path,
                     balance, photo_path)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    row["account_no"],
                    row["password"],
                    row["name"],
                    row["father_name"],
                    row["mother_name"],
                    row["aadhaar"],
                    row["address"],
                    row["mobile"],
                    row["ifsc"],
                    row["branch"],
                    row["signature_path"],
                    row["opening_balance"],
                    row["photo_path"],
                )
            )
        except mysql.connector.IntegrityError:
            raise ValueError("Account number already exists in customers")
        finally:
            cur2.close()

        # Initial deposit transaction if opening_balance > 0
        if float(row["opening_balance"]) > 0:
            cur3 = conn.cursor()
            cur3.execute(
                """
                INSERT INTO transactions (account_no, txn_type, amount)
                VALUES (%s, 'DEPOSIT', %s)
                """,
                (account_no, float(row["opening_balance"]))
            )
            cur3.close()

        # Delete from pending
        cur4 = conn.cursor()
        cur4.execute("DELETE FROM pending_accounts WHERE id = %s", (pending_id,))
        cur4.close()

        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

# -------------- Transactions ----------------
def update_balance_and_add_txn(account_no, amount, txn_type):
    """
    txn_type: 'DEPOSIT' or 'WITHDRAW'
    amount: positive value
    """
    conn = get_connection(DB_NAME)
    cur = conn.cursor()
    try:
        # Lock the row for update
        cur.execute(
            "SELECT balance FROM customers WHERE account_no=%s FOR UPDATE",
            (account_no,)
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Account not found")
        current_balance = float(row[0])

        if txn_type == "DEPOSIT":
            new_balance = current_balance + amount
        else:
            if current_balance < amount:
                raise ValueError("Insufficient balance")
            new_balance = current_balance - amount

        cur.execute(
            "UPDATE customers SET balance=%s WHERE account_no=%s",
            (new_balance, account_no)
        )

        cur.execute(
            """
            INSERT INTO transactions (account_no, txn_type, amount)
            VALUES (%s,%s,%s)
            """,
            (account_no, txn_type, amount)
        )

        conn.commit()
        return new_balance
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def get_last_transactions(account_no, limit=5):
    """Return the most recent `limit` transactions for an account, newest first."""
    conn = get_connection(DB_NAME)
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT txn_type, amount, txn_time
        FROM transactions
        WHERE account_no=%s
        ORDER BY txn_time DESC
        LIMIT %s
        """,
        (account_no, limit)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def get_all_transactions(account_no):
    """Get all transactions for passbook export or full statement."""
    conn = get_connection(DB_NAME)
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT txn_type, amount, txn_time
        FROM transactions
        WHERE account_no=%s
        ORDER BY txn_time ASC
        """,
        (account_no,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

# -------------- GUI HELPERS -----------------

# Light-mode colours used exclusively for popups that must stay white
_POPUP_BG  = "#ffffff"
_POPUP_FG  = "#111827"
_POPUP_ENT = "#f9fafb"   # entry background

def _register_popup_light_styles(style: ttk.Style):
    """
    Register 'PopupLight.*' ttk style variants that always use a white/light
    palette regardless of the app-wide dark/light theme.
    Call this once after the main ttk.Style is created.
    """
    style.configure("PopupLight.TFrame",  background=_POPUP_BG)
    style.configure("PopupLight.TLabel",  background=_POPUP_BG, foreground=_POPUP_FG,
                    font=("Segoe UI", 10))
    style.configure("PopupLight.TEntry",  fieldbackground=_POPUP_ENT,
                    foreground=_POPUP_FG)
    style.configure("PopupLight.TButton", padding=6, relief="flat",
                    font=("Segoe UI", 10))
    style.configure("PopupLight.Treeview", background="#ffffff",
                    fieldbackground="#ffffff", foreground=_POPUP_FG,
                    font=("Segoe UI", 9), rowheight=26)
    style.configure("PopupLight.Treeview.Heading",
                    background="#e5e7eb", foreground=_POPUP_FG,
                    font=("Segoe UI", 9, "bold"))
    style.configure("PopupLight.TScrollbar")
    style.configure("PopupLight.TSeparator", background="#d1d5db")
    style.configure("PopupLight.TNotebook", background=_POPUP_BG)
    style.configure("PopupLight.TNotebook.Tab", background="#e5e7eb",
                    foreground=_POPUP_FG)


def _force_light_popup(win: tk.Toplevel):
    """
    Force a Toplevel window to always display with a white / light background,
    ignoring the current app theme.  Call immediately after creating the window.
    """
    win.configure(bg=_POPUP_BG)


def _make_light_frame(parent, **kw) -> ttk.Frame:
    """Return a ttk.Frame pre-styled for the light-popup palette."""
    kw.setdefault("style", "PopupLight.TFrame")
    return ttk.Frame(parent, **kw)


def _make_light_label(parent, **kw) -> ttk.Label:
    """Return a ttk.Label pre-styled for the light-popup palette."""
    kw.setdefault("style", "PopupLight.TLabel")
    return ttk.Label(parent, **kw)


def center_window(win, parent=None):
    """
    Center a Toplevel (or root) window over its parent.
    If parent is None, center on screen.
    Must be called AFTER setting geometry so the size is known.
    """
    win.update_idletasks()
    w = win.winfo_width()
    h = win.winfo_height()

    if parent is not None:
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
    else:
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2

    win.geometry(f"{w}x{h}+{x}+{y}")

# -------------- GUI LAYER -------------------
class BankApp(tk.Tk):
    def __init__(self):
        super().__init__()
        _set_icon(self)  # Set window icon
        self.title("Bank Management System")
        self.geometry("1100x650")
        self.minsize(980, 580)
        center_window(self)

        # Theme and style
        self.current_theme = "dark"
        self.style = ttk.Style(self)
        self._apply_dark_theme()
        _register_popup_light_styles(self.style)  # always-light styles for specific popups

        self.current_user = None  # for customer

        # ── Top bar with theme toggle + logout (always visible) ──
        topbar = ttk.Frame(self)
        topbar.pack(fill="x", padx=10, pady=(6, 0))

        # Column on the right: theme on top, logout directly below
        btn_col = ttk.Frame(topbar)
        btn_col.pack(side="right")

        self.theme_btn = ttk.Button(
            btn_col,
            text="☀  Light Mode",
            command=self.toggle_theme,
        )
        self.theme_btn.pack(side="top", anchor="e", fill="x")

        self.topbar_logout_btn = ttk.Button(
            btn_col,
            text="Logout",
            command=self._topbar_logout,
        )
        _set_btn_image(self.topbar_logout_btn, "Logout")  # adds icon if Logout.png exists
        # Hidden until a dashboard is shown

        # container frame to hold different screens
        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        # Allow the single cell to expand so child frames fill the container,
        # which is required for place(relx=0.5, rely=0.5) to find true centre.
        self.container.rowconfigure(0, weight=1)
        self.container.columnconfigure(0, weight=1)

        self.frames = {}
        for F in (LandingFrame, AdminLoginFrame, CustomerLoginFrame,
                  AdminDashboardFrame, CustomerDashboardFrame):
            frame = F(parent=self.container, controller=self)
            self.frames[F.__name__] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("LandingFrame")

    def _apply_dark_theme(self):
        """Apply dark theme styles."""
        self.configure(bg="#111827")  # dark background
        self.style.theme_use("clam")

        self.style.configure(
            "TButton",
            padding=6,
            relief="flat",
            font=("Segoe UI", 10),
        )
        self.style.map("TButton",
                       background=[("active", "#2563eb")])

        self.style.configure(
            "TLabel",
            font=("Segoe UI", 10),
            background="#111827",
            foreground="#e5e7eb"
        )
        self.style.configure(
            "TFrame",
            background="#111827"
        )
        self.style.configure(
            "Treeview",
            font=("Segoe UI", 9),
            rowheight=26
        )
        self.style.configure(
            "Treeview.Heading",
            font=("Segoe UI", 9, "bold")
        )
        self.style.configure(
            "Green.TButton",
            padding=6, relief="flat", font=("Segoe UI", 10),
            background="#16a34a", foreground="#ffffff"
        )
        self.style.map("Green.TButton",
                       background=[("active", "#15803d"), ("disabled", "#374151")],
                       foreground=[("disabled", "#6b7280")])
        self.style.configure(
            "Red.TButton",
            padding=6, relief="flat", font=("Segoe UI", 10),
            background="#dc2626", foreground="#ffffff"
        )
        self.style.map("Red.TButton",
                       background=[("active", "#b91c1c"), ("disabled", "#374151")],
                       foreground=[("disabled", "#6b7280")])

    def _apply_light_theme(self):
        """Apply light theme styles."""
        self.configure(bg="#f3f4f6")  # light gray background
        self.style.theme_use("clam")

        self.style.configure(
            "TButton",
            padding=6,
            relief="flat",
            font=("Segoe UI", 10),
        )
        self.style.map("TButton",
                       background=[("active", "#2563eb")])

        self.style.configure(
            "TLabel",
            font=("Segoe UI", 10),
            background="#f3f4f6",
            foreground="#111827"
        )
        self.style.configure(
            "TFrame",
            background="#f3f4f6"
        )
        self.style.configure(
            "Treeview",
            font=("Segoe UI", 9),
            rowheight=26
        )
        self.style.configure(
            "Treeview.Heading",
            font=("Segoe UI", 9, "bold")
        )
        self.style.configure(
            "Green.TButton",
            padding=6, relief="flat", font=("Segoe UI", 10),
            background="#16a34a", foreground="#ffffff"
        )
        self.style.map("Green.TButton",
                       background=[("active", "#15803d"), ("disabled", "#d1fae5")],
                       foreground=[("disabled", "#6b7280")])
        self.style.configure(
            "Red.TButton",
            padding=6, relief="flat", font=("Segoe UI", 10),
            background="#dc2626", foreground="#ffffff"
        )
        self.style.map("Red.TButton",
                       background=[("active", "#b91c1c"), ("disabled", "#fee2e2")],
                       foreground=[("disabled", "#6b7280")])

    def toggle_theme(self):
        """Toggle between dark and light themes."""
        if self.current_theme == "dark":
            self.current_theme = "light"
            self._apply_light_theme()
            self.theme_btn.configure(text="🌙  Dark Mode")
        else:
            self.current_theme = "dark"
            self._apply_dark_theme()
            self.theme_btn.configure(text="☀  Light Mode")
        # Re-apply popup-specific always-light styles (theme_use resets them)
        _register_popup_light_styles(self.style)
        # Update plain tk.Label widgets in AdminDashboard that don't follow ttk styles
        admin_frame = self.frames.get("AdminDashboardFrame")
        if admin_frame:
            admin_frame.update_preview_theme(self.current_theme)
        # Update plain tk.Text widget in CustomerDashboard that doesn't follow ttk styles
        cust_frame = self.frames.get("CustomerDashboardFrame")
        if cust_frame:
            cust_frame.update_theme(self.current_theme)

    def show_frame(self, name):
        frame = self.frames[name]
        frame.tkraise()
        # Show topbar logout only when a dashboard is active
        if name in ("AdminDashboardFrame", "CustomerDashboardFrame"):
            self.topbar_logout_btn.pack(side="top", anchor="e", pady=(2, 0), fill="x")
        else:
            self.topbar_logout_btn.pack_forget()

    def _topbar_logout(self):
        """Shared logout: delegate to customer dashboard if active, else go to landing."""
        cust = self.frames.get("CustomerDashboardFrame")
        if cust and cust.winfo_ismapped():
            cust.logout()
        else:
            self.show_frame("LandingFrame")

    # Simple admin auth
    def admin_auth(self, username, password):
        return username == "admin" and password == "admin123"

    def set_current_user(self, user_dict):
        self.current_user = user_dict

class LandingFrame(ttk.Frame):
    def __init__(self, parent, controller: BankApp):
        super().__init__(parent)
        self.controller = controller

        # ── All content in a centred inner frame ──────────────────────
        inner = ttk.Frame(self)
        inner.place(relx=0.5, rely=0.5, anchor="center")

        # Logo image in header
        self._logo_img = None
        if PIL_AVAILABLE and os.path.exists(_ICON_PATH):
            try:
                raw = Image.open(_ICON_PATH).convert("RGBA").resize((64, 64), Image.LANCZOS)
                self._logo_img = ImageTk.PhotoImage(raw)
                ttk.Label(inner, image=self._logo_img).pack(pady=(0, 5))
            except Exception:
                pass

        ttk.Label(
            inner,
            text=BANK_NAME,
            font=("Segoe UI", 22, "bold")
        ).pack(pady=(0 if self._logo_img else 0, 2))

        ttk.Label(
            inner,
            text="Secure  •  Reliable  •  Modern",
            font=("Segoe UI", 10)
        ).pack(pady=(0, 4))

        ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=60, pady=10)

        ttk.Label(
            inner,
            text="Please choose an option to continue",
            font=("Segoe UI", 11)
        ).pack(pady=(0, 8))

        btn_frame = ttk.Frame(inner)
        btn_frame.pack(pady=20)

        # Admin Login
        admin_btn = ttk.Button(
            btn_frame,
            text="Admin Login",
            command=lambda: controller.show_frame("AdminLoginFrame")
        )
        admin_btn.grid(row=0, column=0, padx=20, ipadx=30, ipady=10)
        _set_btn_image(admin_btn, "admin_login")

        # Customer Login
        cust_btn = ttk.Button(
            btn_frame,
            text="Customer Login",
            command=lambda: controller.show_frame("CustomerLoginFrame")
        )
        cust_btn.grid(row=0, column=1, padx=20, ipadx=30, ipady=10)
        _set_btn_image(cust_btn, "customer_login")

        # Public Open New Account form (goes to pending)
        open_account_btn = ttk.Button(
            btn_frame,
            text="Open New Account",
            command=lambda: NewAccountWindow(controller.frames["AdminDashboardFrame"])
        )
        open_account_btn.grid(row=1, column=0, columnspan=2, pady=20, ipadx=40, ipady=10)
        _set_btn_image(open_account_btn, "Open_New_Account")

class AdminLoginFrame(ttk.Frame):
    def __init__(self, parent, controller: BankApp):
        super().__init__(parent)
        self.controller = controller

        # ── All content in a centred inner frame ──────────────────────
        inner = ttk.Frame(self)
        inner.place(relx=0.5, rely=0.5, anchor="center")

        self._logo_img = None
        if PIL_AVAILABLE and os.path.exists(_ICON_PATH):
            try:
                raw = Image.open(_ICON_PATH).convert("RGBA").resize((52, 52), Image.LANCZOS)
                self._logo_img = ImageTk.PhotoImage(raw)
                ttk.Label(inner, image=self._logo_img).pack(pady=(0, 4))
            except Exception:
                pass

        ttk.Label(
            inner,
            text="Admin Login",
            font=("Segoe UI", 18, "bold")
        ).pack(pady=(0, 20))

        form = ttk.Frame(inner)
        form.pack(pady=10)

        ttk.Label(form, text="Username:").grid(row=0, column=0, sticky="e", pady=5, padx=5)
        ttk.Label(form, text="Password:").grid(row=1, column=0, sticky="e", pady=5, padx=5)

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()

        username_entry = ttk.Entry(form, textvariable=self.username_var, width=22)
        password_entry = ttk.Entry(form, textvariable=self.password_var, show="*", width=22)
        username_entry.grid(row=0, column=1, pady=5, padx=5)
        password_entry.grid(row=1, column=1, pady=5, padx=5)

        btn_frame = ttk.Frame(inner)
        btn_frame.pack(pady=20)

        login_btn = ttk.Button(
            btn_frame,
            text="Login",
            command=self.handle_login
        )
        login_btn.grid(row=0, column=0, padx=10, ipadx=20)
        _set_btn_image(login_btn, "Login")

        back_btn = ttk.Button(
            btn_frame,
            text="Back",
            command=lambda: controller.show_frame("LandingFrame")
        )
        back_btn.grid(row=0, column=1, padx=10, ipadx=20)
        _set_btn_image(back_btn, "Back")

    def handle_login(self):
        u = self.username_var.get().strip()
        p = self.password_var.get().strip()

        if self.controller.admin_auth(u, p):
            admin_frame: AdminDashboardFrame = self.controller.frames["AdminDashboardFrame"]
            admin_frame.refresh_all()
            self.controller.show_frame("AdminDashboardFrame")
        else:
            messagebox.showerror("Login Failed", "Invalid admin credentials")

class CustomerLoginFrame(ttk.Frame):
    def __init__(self, parent, controller: BankApp):
        super().__init__(parent)
        self.controller = controller

        # ── All content in a centred inner frame ──────────────────────
        inner = ttk.Frame(self)
        inner.place(relx=0.5, rely=0.5, anchor="center")

        self._logo_img = None
        if PIL_AVAILABLE and os.path.exists(_ICON_PATH):
            try:
                raw = Image.open(_ICON_PATH).convert("RGBA").resize((52, 52), Image.LANCZOS)
                self._logo_img = ImageTk.PhotoImage(raw)
                ttk.Label(inner, image=self._logo_img).pack(pady=(0, 4))
            except Exception:
                pass

        ttk.Label(
            inner,
            text="Customer Login",
            font=("Segoe UI", 18, "bold")
        ).pack(pady=(0, 20))

        form = ttk.Frame(inner)
        form.pack(pady=10)

        ttk.Label(form, text="Login Type:").grid(row=0, column=0, sticky="e", pady=5, padx=5)
        ttk.Label(form, text="Login ID:").grid(row=1, column=0, sticky="e", pady=5, padx=5)
        ttk.Label(form, text="Password:").grid(row=2, column=0, sticky="e", pady=5, padx=5)

        self.login_type_var = tk.StringVar(value="Account Number")
        self.id_var = tk.StringVar()
        self.pass_var = tk.StringVar()

        login_type_combo = ttk.Combobox(
            form,
            textvariable=self.login_type_var,
            state="readonly",
            values=["Account Number", "Aadhaar Number"],
            width=20
        )
        login_type_combo.grid(row=0, column=1, pady=5, padx=5)

        id_entry = ttk.Entry(form, textvariable=self.id_var, width=22)
        pass_entry = ttk.Entry(form, textvariable=self.pass_var, show="*", width=22)
        id_entry.grid(row=1, column=1, pady=5, padx=5)
        pass_entry.grid(row=2, column=1, pady=5, padx=5)

        btn_frame = ttk.Frame(inner)
        btn_frame.pack(pady=20)

        login_btn = ttk.Button(
            btn_frame,
            text="Login",
            command=self.handle_login
        )
        login_btn.grid(row=0, column=0, padx=10, ipadx=20)
        _set_btn_image(login_btn, "Login")

        back_btn = ttk.Button(
            btn_frame,
            text="Back",
            command=lambda: controller.show_frame("LandingFrame")
        )
        back_btn.grid(row=0, column=1, padx=10, ipadx=20)
        _set_btn_image(back_btn, "Back")

        # Forgot Password button
        forgot_btn = ttk.Button(
            inner,
            text="Forgot Password?",
            command=self.open_forgot_password
        )
        forgot_btn.pack(pady=(0, 10))
        _set_btn_image(forgot_btn, "forgot_password")

    def open_forgot_password(self):
        ForgotPasswordWindow(self)

    def handle_login(self):
        login_type = self.login_type_var.get()
        login_id = self.id_var.get().strip()
        password = self.pass_var.get().strip()

        if not login_id or not password:
            messagebox.showwarning("Validation", "Please enter Login ID and password")
            return

        try:
            if login_type == "Account Number":
                user = get_customer_by_login(login_id, password)
            else:
                # Basic Aadhaar format check
                if len(login_id) != 12 or not login_id.isdigit():
                    messagebox.showwarning("Validation", "Enter a valid 12-digit Aadhaar number")
                    return
                user = get_customer_by_aadhaar(login_id, password)

            if user:
                self.controller.set_current_user(user)
                cust_frame: CustomerDashboardFrame = self.controller.frames["CustomerDashboardFrame"]
                cust_frame.load_user()
                self.controller.show_frame("CustomerDashboardFrame")
            else:
                messagebox.showerror("Login Failed", "Invalid credentials for selected login type")
        except Exception as e:
            messagebox.showerror("Error", f"Database error: {e}")



class ForgotPasswordWindow(tk.Toplevel):
    """
    Two-step forgot password window:
      Step 1 – Verify identity  : Account No + Aadhaar + Mobile
              image name hint   : forgot_password.png  (64×64)
      Step 2 – Set new password (shown only after verification passes)
              image name hint   : change_password.png  (64×64)

    Each step shows its own illustration above the form title.
    If the PNG files are not present the window still works fine.
    """

    # PNG file-names (without extension) to look for next to bank.py
    _IMG_VERIFY = "forgot_password"    # shown on the verify-identity screen
    _IMG_CHANGE = "change_password"    # shown on the set-new-password screen
    _IMG_SIZE   = (72, 72)

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Forgot Password")
        self.resizable(False, False)
        _set_icon(self)
        self.grab_set()

        self._verified_account = None

        # Pre-load images (stored on self so they aren't GC'd)
        self._img_verify = _load_btn_image(self._IMG_VERIFY, self._IMG_SIZE)
        self._img_change = _load_btn_image(self._IMG_CHANGE, self._IMG_SIZE)

        outer = ttk.Frame(self)
        outer.pack(padx=32, pady=24, fill="both", expand=True)

        # ── shared image label (swapped between steps) ──
        self._img_label = ttk.Label(outer)
        self._img_label.pack(pady=(0, 4))

        # ── shared title label (text swapped between steps) ──
        self._title_label = ttk.Label(
            outer,
            font=("Segoe UI", 15, "bold")
        )
        self._title_label.pack(pady=(0, 2))

        # ── shared subtitle label ──
        self._sub_label = ttk.Label(
            outer,
            font=("Segoe UI", 9),
        )
        self._sub_label.pack(pady=(0, 14))

        # ══════════════════════════════════════════════
        # Step 1 – Verify identity
        # ══════════════════════════════════════════════
        self._step1_frame = ttk.Frame(outer)
        self._step1_frame.pack(fill="x")

        form1 = ttk.Frame(self._step1_frame)
        form1.pack()

        fields = [
            ("Account Number:",              "acc"),
            ("Aadhaar Number (12 digits):",  "aadhaar"),
            ("Registered Mobile Number:",    "mobile"),
        ]
        self._vars = {}
        for i, (lbl_text, key) in enumerate(fields):
            ttk.Label(form1, text=lbl_text, anchor="e").grid(
                row=i, column=0, sticky="e", pady=6, padx=8
            )
            var = tk.StringVar()
            self._vars[key] = var
            ttk.Entry(form1, textvariable=var, width=26).grid(
                row=i, column=1, pady=6, padx=8
            )

        self._verify_btn = ttk.Button(
            self._step1_frame,
            text="Verify Details",
            command=self._verify
        )
        self._verify_btn.pack(pady=(14, 0), ipadx=16)
        _set_btn_image(self._verify_btn, "verify_details")

        # ══════════════════════════════════════════════
        # Step 2 – Change password  (hidden until verified)
        # ══════════════════════════════════════════════
        self._step2_frame = ttk.Frame(outer)
        # not packed yet

        self._verified_label = ttk.Label(
            self._step2_frame,
            text="✔  Identity verified. Set your new password.",
            font=("Segoe UI", 9, "bold"),
            foreground="#16a34a"
        )
        self._verified_label.pack(pady=(0, 10))

        form2 = ttk.Frame(self._step2_frame)
        form2.pack()

        self._new_pass_var     = tk.StringVar()
        self._confirm_pass_var = tk.StringVar()

        ttk.Label(form2, text="New Password:",     anchor="e").grid(row=0, column=0, sticky="e", pady=6, padx=8)
        ttk.Label(form2, text="Confirm Password:", anchor="e").grid(row=1, column=0, sticky="e", pady=6, padx=8)

        ttk.Entry(form2, textvariable=self._new_pass_var,     show="*", width=26).grid(row=0, column=1, pady=6, padx=8)
        ttk.Entry(form2, textvariable=self._confirm_pass_var, show="*", width=26).grid(row=1, column=1, pady=6, padx=8)

        self._change_btn = ttk.Button(
            self._step2_frame,
            text="Change Password",
            command=self._change_password
        )
        self._change_btn.pack(pady=(14, 0), ipadx=16)
        _set_btn_image(self._change_btn, "change_password")

        # Show step-1 UI
        self._show_step1()

        self.update_idletasks()
        center_window(self, parent)

    # ── internal helpers ──────────────────────────────────────────────────

    def _show_step1(self):
        """Set image / text for the verify-identity screen."""
        if self._img_verify:
            self._img_label.configure(image=self._img_verify, text="")
        else:
            self._img_label.configure(image="", text="🔒", font=("Segoe UI", 32))
        self._title_label.configure(text="Forgot Password")
        self._sub_label.configure(text="Enter your account details to verify identity")

    def _show_step2(self):
        """Set image / text for the change-password screen."""
        if self._img_change:
            self._img_label.configure(image=self._img_change, text="")
        else:
            self._img_label.configure(image="", text="🔑", font=("Segoe UI", 32))
        self._title_label.configure(text="Reset Password")
        self._sub_label.configure(text="Choose a strong new password")

    # ── Step 1: verify ───────────────────────────────────────────────────

    def _verify(self):
        acc     = self._vars["acc"].get().strip()
        aadhaar = self._vars["aadhaar"].get().strip()
        mobile  = self._vars["mobile"].get().strip()

        if not acc or not aadhaar or not mobile:
            messagebox.showwarning("Validation", "Please fill in all fields.", parent=self)
            return

        if len(aadhaar) != 12 or not aadhaar.isdigit():
            messagebox.showwarning("Validation", "Aadhaar must be exactly 12 digits.", parent=self)
            return

        try:
            customer = get_customer_by_account(acc)
        except Exception as e:
            messagebox.showerror("Error", f"Database error: {e}", parent=self)
            return

        if (
            customer
            and str(customer.get("aadhaar", "")).strip() == aadhaar
            and str(customer.get("mobile",  "")).strip() == mobile
        ):
            self._verified_account = acc
            # swap frames and update header
            self._step1_frame.pack_forget()
            self._show_step2()
            self._step2_frame.pack(fill="x")
            self.update_idletasks()
            center_window(self, self.master)
        else:
            messagebox.showerror(
                "Verification Failed",
                "Details do not match our records.\nPlease check and try again.",
                parent=self
            )

    # ── Step 2: change password ───────────────────────────────────────────

    def _change_password(self):
        new_pass     = self._new_pass_var.get()
        confirm_pass = self._confirm_pass_var.get()

        if not new_pass or not confirm_pass:
            messagebox.showwarning("Validation", "Please fill in both password fields.", parent=self)
            return
        if len(new_pass) < 6:
            messagebox.showwarning("Validation", "Password must be at least 6 characters.", parent=self)
            return
        if new_pass != confirm_pass:
            messagebox.showerror("Mismatch", "Passwords do not match.", parent=self)
            return

        try:
            update_customer_password(self._verified_account, new_pass)
            messagebox.showinfo(
                "Success",
                "Password changed successfully!\nYou can now log in with your new password.",
                parent=self
            )
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update password: {e}", parent=self)


class AdminDashboardFrame(ttk.Frame):
    def __init__(self, parent, controller: BankApp):
        super().__init__(parent)
        self.controller = controller
        self.photo_cache = None  # keep reference for Tk image
        self.sig_cache = None
        self.search_var = tk.StringVar()

        # -------- Header (centered title + logout) --------
        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", pady=(0, 5))

        header_frame.columnconfigure(0, weight=1)
        header_frame.columnconfigure(1, weight=0)
        header_frame.columnconfigure(2, weight=0)

        title = ttk.Label(
            header_frame,
            text="Admin Dashboard",
            font=("Segoe UI", 16, "bold")
        )
        title.grid(row=0, column=0, pady=10, sticky="n")

        # -------- Search box (below heading) --------
        search_frame = ttk.Frame(self)
        search_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(
            search_frame,
            text="Search (Name / Acc / Aadhaar):",
            font=("Segoe UI", 9, "bold")
        ).grid(row=0, column=0, sticky="w", padx=5, pady=(2, 0))

        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=32)
        search_entry.grid(row=1, column=0, padx=5, pady=2, sticky="w")

        btn_search = ttk.Button(
            search_frame,
            text="Search",
            command=self.search_customers
        )
        btn_search.grid(row=1, column=1, padx=3, pady=2, sticky="w")
        _set_btn_image(btn_search, "Search")

        btn_clear = ttk.Button(
            search_frame,
            text="Clear",
            command=self.clear_search
        )
        btn_clear.grid(row=1, column=2, padx=3, pady=2, sticky="w")
        _set_btn_image(btn_clear, "Clear")

        # -------- Main body: left tables, right preview --------
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=5)

        # Left side - notebook: customers + pending
        table_frame = ttk.Frame(body)
        table_frame.pack(side="left", fill="both", expand=True)

        self.notebook = ttk.Notebook(table_frame)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # Customers tab
        cust_tab = ttk.Frame(self.notebook)
        self.notebook.add(cust_tab, text="Customers")

        cols_cust = (
            "id",
            "photo",
            "name",
            "father",
            "mother",
            "aadhaar",
            "account_no",
            "branch",
            "balance",
            "photo_path",
            "sig_path",
        )

        self.tree = ttk.Treeview(
            cust_tab,
            columns=cols_cust,
            show="headings",
            selectmode="browse"
        )

        # Visible headings
        self.tree.heading("id", text="ID")
        self.tree.heading("photo", text="Photo")
        self.tree.heading("name", text="Name")
        self.tree.heading("father", text="Father")
        self.tree.heading("mother", text="Mother")
        self.tree.heading("aadhaar", text="Aadhaar")
        self.tree.heading("account_no", text="Account No")
        self.tree.heading("branch", text="Branch")
        self.tree.heading("balance", text="Balance")

        # Visible columns
        self.tree.column("id", width=40, anchor="center")
        self.tree.column("photo", width=60, anchor="center")
        self.tree.column("name", width=140)
        self.tree.column("father", width=120)
        self.tree.column("mother", width=120)
        self.tree.column("aadhaar", width=110, anchor="center")
        self.tree.column("account_no", width=110, anchor="center")
        self.tree.column("branch", width=130)
        self.tree.column("balance", width=90, anchor="e")

        # Hidden internal columns to store file paths
        self.tree.heading("photo_path", text="Photo Path")
        self.tree.heading("sig_path", text="Signature Path")
        self.tree.column("photo_path", width=0, stretch=False)
        self.tree.column("sig_path", width=0, stretch=False)

        self.tree.pack(fill="both", expand=True, side="left")

        self.tree.tag_configure('low', foreground='red')
        self.tree.tag_configure('high', foreground='green')

        scrollbar_cust = ttk.Scrollbar(
            cust_tab,
            orient="vertical",
            command=self.tree.yview
        )
        self.tree.configure(yscroll=scrollbar_cust.set)
        scrollbar_cust.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self.on_row_select)

        # Pending tab
        pending_tab = ttk.Frame(self.notebook)
        self.notebook.add(pending_tab, text="Pending Approvals")

        cols_pending = ("id", "photo", "name", "father", "mother",
                        "aadhaar", "account_no", "branch",
                        "opening_balance", "requested_at")

        self.pending_tree = ttk.Treeview(
            pending_tab,
            columns=cols_pending,
            show="headings",
            selectmode="browse"
        )

        for c, text, w, anchor in [
            ("id", "ID", 40, "center"),
            ("photo", "Photo", 60, "center"),
            ("name", "Name", 140, "w"),
            ("father", "Father", 120, "w"),
            ("mother", "Mother", 120, "w"),
            ("aadhaar", "Aadhaar", 110, "center"),
            ("account_no", "Account No", 110, "center"),
            ("branch", "Branch", 130, "w"),
            ("opening_balance", "Opening Bal", 100, "e"),
            ("requested_at", "Requested At", 150, "center"),
        ]:
            self.pending_tree.heading(c, text=text)
            self.pending_tree.column(c, width=w, anchor=anchor)

        self.pending_tree.pack(fill="both", expand=True, side="left")

        scrollbar_p = ttk.Scrollbar(
            pending_tab,
            orient="vertical",
            command=self.pending_tree.yview
        )
        self.pending_tree.configure(yscroll=scrollbar_p.set)
        scrollbar_p.pack(side="right", fill="y")

        # NEW: preview on selecting pending account
        self.pending_tree.bind("<<TreeviewSelect>>", self.on_pending_select)

        # Right side - ONLY Photo + Signature preview
        right = ttk.Frame(body, width=340)
        right.pack(side="left", fill="y", padx=10)
        right.pack_propagate(False)  # keep fixed width

        ttk.Label(right, text="Photo & Signature Preview:",
                  font=("Segoe UI", 10, "bold")).pack(pady=(10, 5))

        preview_frame = ttk.Frame(right)
        preview_frame.pack(pady=5)

        # Use tk.Label (not ttk.Label) so images display correctly
        self.photo_label = tk.Label(preview_frame, text="No photo", anchor="center",
                                    width=150, height=150,
                                    relief="flat", bg="#111827", fg="#9ca3af",
                                    font=("Segoe UI", 9))
        self.photo_label.grid(row=0, column=0, padx=5, pady=2)

        self.sig_label = tk.Label(preview_frame, text="No signature", anchor="center",
                                  width=150, height=80,
                                  relief="flat", bg="#111827", fg="#9ca3af",
                                  font=("Segoe UI", 9))
        self.sig_label.grid(row=1, column=0, padx=5, pady=2)

        # "See Full Detail" button below photo & signature preview
        self.btn_full_detail = ttk.Button(
            right,
            text="🔍  See Full Detail",
            command=self.show_full_detail
        )
        self.btn_full_detail.pack(pady=(8, 4), ipadx=6, ipady=4, fill="x", padx=10)

        # -------- Buttons below customer table (horizontal) --------
        btn_bar = ttk.Frame(self)
        btn_bar.pack(fill="x", pady=5)

        self.btn_add = ttk.Button(
            btn_bar,
            text="Open New Account",
            command=self.open_new_account_window
        )
        self.btn_add.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_add, "Open_New_Account")

        self.btn_refresh = ttk.Button(
            btn_bar,
            text="Refresh All",
            command=self.refresh_all
        )
        self.btn_refresh.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_refresh, "Refresh_All")

        self.btn_delete = ttk.Button(
            btn_bar,
            text="Delete",
            command=self.delete_selected
        )
        self.btn_delete.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_delete, "Delete")

        self.btn_statement = ttk.Button(
            btn_bar,
            text="Account Statement",
            command=self.open_account_statement
        )
        self.btn_statement.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_statement, "Account_Statement")

        # NEW: Admin Deposit & Withdraw
        self.btn_dep = ttk.Button(
            btn_bar,
            text="Deposit",
            command=self.admin_deposit
        )
        self.btn_dep.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_dep, "Deposit")

        self.btn_wd = ttk.Button(
            btn_bar,
            text="Withdraw",
            command=self.admin_withdraw
        )
        self.btn_wd.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_wd, "Withdrawl")

        self.btn_approve = ttk.Button(
            btn_bar,
            text="Approve Selected Pending",
            command=self.approve_selected_pending,
            style="Green.TButton"
        )
        self.btn_approve.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_approve, "Approve_Request")

        self.btn_reject = ttk.Button(
            btn_bar,
            text="Reject Selected Pending",
            command=self.reject_selected_pending,
            style="Red.TButton"
        )
        self.btn_reject.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_reject, "Reject_Request")

        # Initially disable pending action buttons (enabled only on Pending tab)
        self.btn_approve.state(["disabled"])
        self.btn_reject.state(["disabled"])

    def update_preview_theme(self, theme):
        """Update plain tk.Label preview widgets to match the current theme."""
        if theme == "dark":
            bg = "#111827"
            fg = "#9ca3af"
        else:
            bg = "#f3f4f6"
            fg = "#6b7280"
        self.photo_label.configure(bg=bg, fg=fg)
        self.sig_label.configure(bg=bg, fg=fg)

    # ---------- Refresh helpers ----------
    def refresh_customers(self, rows=None):
        for row in self.tree.get_children():
            self.tree.delete(row)
        try:
            if rows is None:
                rows = get_all_customers()
            for r in rows:
                photo_flag = "Yes" if r["photo_path"] else "No"
                bal = float(r["balance"])
                tag = "low" if bal < 1000 else "high"
                self.tree.insert(
                    "",
                    "end",
                    values=(
                        r["id"],
                        photo_flag,
                        r["name"],
                        r["father_name"] or "",
                        r["mother_name"] or "",
                        r["aadhaar"] or "",
                        r["account_no"],
                        r["branch"] or "",
                        f"{bal:.2f}",
                        r.get("photo_path") or "",
                        r.get("signature_path") or "",
                    ),
                    tags=(tag,),
                )
        except Exception as e:
            messagebox.showerror("Error", f"Unable to load customers: {e}")

    def refresh_pending(self):
        for row in self.pending_tree.get_children():
            self.pending_tree.delete(row)
        try:
            rows = get_all_pending_accounts()
            for r in rows:
                photo_flag = "Yes" if r["photo_path"] else "No"
                req_time = r["requested_at"].strftime("%Y-%m-%d %H:%M:%S") if r["requested_at"] else ""
                self.pending_tree.insert(
                    "",
                    "end",
                    values=(
                        r["id"],
                        photo_flag,
                        r["name"],
                        r["father_name"] or "",
                        r["mother_name"] or "",
                        r["aadhaar"] or "",
                        r["account_no"],
                        r["branch"] or "",
                        f"{float(r['opening_balance']):.2f}",
                        req_time
                    )
                )
        except Exception as e:
            messagebox.showerror("Error", f"Unable to load pending accounts: {e}")

    def refresh_all(self):
        self.refresh_customers()
        self.refresh_pending()
        self._update_previews(None, None)

    # ---------- Actions ----------
    def open_new_account_window(self):
        NewAccountWindow(self)

    def get_selected_customer_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        item = self.tree.item(sel[0])
        cust_id = item["values"][0]
        return cust_id

    def get_selected_customer_account(self):
        sel = self.tree.selection()
        if not sel:
            return None
        item = self.tree.item(sel[0])
        account_no = item["values"][6]
        return account_no

    def delete_selected(self):
        """Delete the selected customer after admin verification."""
        cust_id = self.get_selected_customer_id()
        if not cust_id:
            messagebox.showinfo("Delete", "Please select a customer")
            return

        # First confirmation dialog
        if not messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this customer?"):
            return

        # Admin verification popup
        win = tk.Toplevel(self)
        win.title("Admin Verification Required")
        win.geometry("320x200")
        win.resizable(False, False)
        win.transient(self.controller)
        center_window(win, self.controller)
        win.grab_set()
        win.focus_set()
        _set_icon(win)
        _force_light_popup(win)

        _make_light_label(win, text="Enter Admin Username:").pack(pady=5)
        user_var = tk.StringVar()
        user_entry = ttk.Entry(win, textvariable=user_var, style="PopupLight.TEntry")
        user_entry.pack(pady=5)

        _make_light_label(win, text="Enter Admin Password:").pack(pady=5)
        pass_var = tk.StringVar()
        pass_entry = ttk.Entry(win, textvariable=pass_var, show="*", style="PopupLight.TEntry")
        pass_entry.pack(pady=5)

        def verify_and_delete():
            username = user_var.get().strip()
            password = pass_var.get().strip()

            # Use existing admin_auth() on controller
            if not self.controller.admin_auth(username, password):
                messagebox.showerror("Access Denied", "Incorrect admin login")
                return

            try:
                delete_customer(cust_id)
                self.refresh_customers()
                self._update_previews(None, None)
                messagebox.showinfo("Success", "Customer deleted successfully")
                win.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Unable to delete customer: {e}")

        btn_frame = _make_light_frame(win)
        btn_frame.pack(pady=10)
        verify_del_btn = ttk.Button(btn_frame, text="Verify & Delete", command=verify_and_delete,
                                    style="PopupLight.TButton")
        verify_del_btn.grid(row=0, column=0, padx=5)
        _set_btn_image(verify_del_btn, "Delete")
        cancel_del_btn = ttk.Button(btn_frame, text="Cancel", command=win.destroy,
                                    style="PopupLight.TButton")
        cancel_del_btn.grid(row=0, column=1, padx=5)
        _set_btn_image(cancel_del_btn, "Cancel")

    def _update_previews(self, photo_path, sig_path):
        """Common helper to show photo + signature stacked in preview area."""
        # Photo preview
        if not photo_path or not os.path.exists(str(photo_path)):
            self.photo_label.configure(text="No photo", image="", width=150, height=150)
            self.photo_cache = None
        elif not PIL_AVAILABLE:
            self.photo_label.configure(
                text="Pillow not installed\nCannot show photo",
                image="", width=150, height=150
            )
            self.photo_cache = None
        else:
            try:
                img = Image.open(photo_path).convert("RGBA")
                img = img.resize((150, 150), Image.LANCZOS)
                img_tk = ImageTk.PhotoImage(img)
                self.photo_cache = img_tk
                self.photo_label.configure(image=img_tk, text="", width=150, height=150)
            except Exception as e:
                self.photo_label.configure(text=f"Error loading photo\n{e}", image="", width=150, height=150)
                self.photo_cache = None

        # Signature preview
        if not sig_path or not os.path.exists(str(sig_path)):
            self.sig_label.configure(text="No signature", image="", width=150, height=80)
            self.sig_cache = None
        elif not PIL_AVAILABLE:
            self.sig_label.configure(
                text="Pillow not installed\nCannot show signature",
                image="", width=150, height=80
            )
            self.sig_cache = None
        else:
            try:
                img = Image.open(sig_path).convert("RGBA")
                img = img.resize((150, 80), Image.LANCZOS)
                img_tk2 = ImageTk.PhotoImage(img)
                self.sig_cache = img_tk2
                self.sig_label.configure(image=img_tk2, text="", width=150, height=80)
            except Exception as e:
                self.sig_label.configure(text=f"Error loading signature\n{e}", image="", width=150, height=80)
                self.sig_cache = None

    def on_row_select(self, event):
        """When selecting an APPROVED customer from the Customers table."""

        sel = self.tree.selection()
        if not sel:
            self._update_previews(None, None)
            return

        item = self.tree.item(sel[0])
        values = item.get("values", [])

        # According to cols_cust:
        # 0:id, 1:photo flag, 2:name, 3:father, 4:mother,
        # 5:aadhaar, 6:account_no, 7:branch, 8:balance,
        # 9:photo_path, 10:sig_path
        photo_path = values[9] if len(values) > 9 else None
        sig_path = values[10] if len(values) > 10 else None
        self._update_previews(photo_path, sig_path)

    def on_pending_select(self, event):
        """When selecting a PENDING account."""
        sel = self.pending_tree.selection()
        if not sel:
            return
        item = self.pending_tree.item(sel[0])
        # account_no is column index 6 in pending tree
        account_no = item["values"][6]

        try:
            pending = get_pending_account_by_account(account_no)
        except Exception as e:
            messagebox.showerror("Error", f"Unable to load pending account details: {e}")
            return

        if not pending:
            self._update_previews(None, None)
            return

        self._update_previews(pending.get("photo_path"), pending.get("signature_path"))

    # ---------- See Full Detail ----------
    def show_full_detail(self):
        """
        Open a popup showing ALL details of the currently selected customer
        (from Customers tab) or pending account (from Pending Approvals tab).
        """
        try:
            current = self.notebook.select()
            tab_index = self.notebook.index(current)
        except Exception:
            tab_index = 0

        row_data = None

        if tab_index == 0:
            # Customers tab
            sel = self.tree.selection()
            if not sel:
                messagebox.showinfo("No Selection", "Please select a customer first.")
                return
            item = self.tree.item(sel[0])
            values = item.get("values", [])
            account_no = values[6] if len(values) > 6 else None
            if not account_no:
                return
            try:
                row_data = get_customer_by_account(str(account_no))
            except Exception as e:
                messagebox.showerror("Error", f"Could not load customer details:\n{e}")
                return
            source = "customer"
        else:
            # Pending Approvals tab
            sel = self.pending_tree.selection()
            if not sel:
                messagebox.showinfo("No Selection", "Please select a pending account first.")
                return
            item = self.pending_tree.item(sel[0])
            values = item.get("values", [])
            account_no = values[6] if len(values) > 6 else None
            if not account_no:
                return
            try:
                row_data = get_pending_account_by_account(str(account_no))
            except Exception as e:
                messagebox.showerror("Error", f"Could not load pending account details:\n{e}")
                return
            source = "pending"

        if not row_data:
            messagebox.showinfo("Not Found", "Could not retrieve details for this record.")
            return

        # ---- Build the detail popup ----
        popup = tk.Toplevel(self)
        popup.title("Full Customer Details")
        popup.geometry("520x640")
        popup.resizable(False, False)
        _set_icon(popup)
        _force_light_popup(popup)
        popup.grab_set()
        center_window(popup, self.winfo_toplevel())

        # Header
        hdr = tk.Frame(popup, bg="#1e3a5f", height=50)
        hdr.pack(fill="x")
        tk.Label(
            hdr,
            text="Customer Full Details",
            bg="#1e3a5f", fg="white",
            font=("Segoe UI", 13, "bold")
        ).pack(pady=12)

        # Scrollable content area
        canvas_w = tk.Canvas(popup, bg=_POPUP_BG, highlightthickness=0)
        scrollbar_w = ttk.Scrollbar(popup, orient="vertical", command=canvas_w.yview)
        canvas_w.configure(yscrollcommand=scrollbar_w.set)
        scrollbar_w.pack(side="right", fill="y")
        canvas_w.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas_w, bg=_POPUP_BG)
        inner_win = canvas_w.create_window((0, 0), window=inner, anchor="nw")

        def on_frame_configure(e):
            canvas_w.configure(scrollregion=canvas_w.bbox("all"))

        def on_canvas_configure(e):
            canvas_w.itemconfig(inner_win, width=e.width)

        inner.bind("<Configure>", on_frame_configure)
        canvas_w.bind("<Configure>", on_canvas_configure)

        # Mouse-wheel scrolling
        def _on_mousewheel(e):
            canvas_w.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas_w.bind_all("<MouseWheel>", _on_mousewheel)
        popup.bind("<Destroy>", lambda e: canvas_w.unbind_all("<MouseWheel>"))

        # ---- Photo ----
        photo_path = row_data.get("photo_path")
        if PIL_AVAILABLE and photo_path and os.path.exists(str(photo_path)):
            try:
                img = Image.open(photo_path).convert("RGBA")
                img = img.resize((120, 120), Image.LANCZOS)
                img_tk = ImageTk.PhotoImage(img)
                photo_lbl = tk.Label(inner, image=img_tk, bg=_POPUP_BG)
                photo_lbl.image = img_tk
                photo_lbl.pack(pady=(15, 4))
            except Exception:
                tk.Label(inner, text="[Photo unavailable]", bg=_POPUP_BG,
                         fg="#6b7280", font=("Segoe UI", 9)).pack(pady=(15, 4))
        else:
            tk.Label(inner, text="No Photo", bg="#e5e7eb", fg="#6b7280",
                     font=("Segoe UI", 9), width=18, height=6).pack(pady=(15, 4))

        # ---- Signature ----
        sig_path = row_data.get("signature_path")
        sig_lbl_txt = tk.Label(inner, text="Signature:", bg=_POPUP_BG,
                               fg="#374151", font=("Segoe UI", 9, "bold"))
        sig_lbl_txt.pack(anchor="w", padx=20)
        if PIL_AVAILABLE and sig_path and os.path.exists(str(sig_path)):
            try:
                sig_img = Image.open(sig_path).convert("RGBA")
                sig_img = sig_img.resize((200, 70), Image.LANCZOS)
                sig_tk = ImageTk.PhotoImage(sig_img)
                sig_lbl = tk.Label(inner, image=sig_tk, bg=_POPUP_BG)
                sig_lbl.image = sig_tk
                sig_lbl.pack(pady=(2, 10))
            except Exception:
                tk.Label(inner, text="[Signature unavailable]", bg=_POPUP_BG,
                         fg="#6b7280", font=("Segoe UI", 9)).pack(pady=(2, 10))
        else:
            tk.Label(inner, text="No Signature", bg="#e5e7eb", fg="#6b7280",
                     font=("Segoe UI", 9), width=28, height=3).pack(pady=(2, 10))

        # ---- Separator ----
        ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=20, pady=4)

        # ---- Detail fields ----
        def add_field(label, value):
            row_f = tk.Frame(inner, bg=_POPUP_BG)
            row_f.pack(fill="x", padx=20, pady=3)
            tk.Label(
                row_f,
                text=f"{label}:",
                bg=_POPUP_BG, fg="#374151",
                font=("Segoe UI", 9, "bold"),
                width=18, anchor="w"
            ).pack(side="left")
            tk.Label(
                row_f,
                text=str(value) if value else "—",
                bg=_POPUP_BG, fg=_POPUP_FG,
                font=("Segoe UI", 9),
                anchor="w", wraplength=280, justify="left"
            ).pack(side="left", fill="x", expand=True)

        add_field("Account No", row_data.get("account_no"))
        add_field("Full Name", row_data.get("name"))
        add_field("Father's Name", row_data.get("father_name"))
        add_field("Mother's Name", row_data.get("mother_name"))
        add_field("Aadhaar No", row_data.get("aadhaar"))
        add_field("Mobile", row_data.get("mobile"))
        add_field("Address", row_data.get("address"))
        add_field("IFSC Code", row_data.get("ifsc"))
        add_field("Branch", row_data.get("branch"))

        if source == "customer":
            bal = row_data.get("balance")
            bal_str = f"₹ {float(bal):,.2f}" if bal is not None else "—"
            add_field("Balance", bal_str)
            add_field("Account Opened", row_data.get("created_at"))
        else:
            ob = row_data.get("opening_balance")
            ob_str = f"₹ {float(ob):,.2f}" if ob is not None else "—"
            add_field("Opening Balance", ob_str)
            add_field("Requested At", row_data.get("requested_at"))

        status_text = "Approved ✔" if source == "customer" else "Pending ⏳"
        status_color = "#16a34a" if source == "customer" else "#d97706"
        status_row = tk.Frame(inner, bg=_POPUP_BG)
        status_row.pack(fill="x", padx=20, pady=3)
        tk.Label(status_row, text="Status:", bg=_POPUP_BG, fg="#374151",
                 font=("Segoe UI", 9, "bold"), width=18, anchor="w").pack(side="left")
        tk.Label(status_row, text=status_text, bg=_POPUP_BG, fg=status_color,
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(side="left")

        # ---- Close button ----
        ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=20, pady=8)
        ttk.Button(
            inner,
            text="Close",
            command=popup.destroy,
            style="PopupLight.TButton"
        ).pack(pady=(0, 15), ipadx=20, ipady=4)

    # ---------- Search ----------
    def search_customers(self):
        keyword = self.search_var.get().strip()
        if not keyword:
            self.refresh_customers()
            return
        try:
            rows = search_customers(keyword)
            self.refresh_customers(rows)
        except Exception as e:
            messagebox.showerror("Error", f"Search failed: {e}")

    def clear_search(self):
        self.search_var.set("")
        self.refresh_customers()

    def on_tab_changed(self, event):
        """Enable/disable buttons depending on active tab.

        - Customers tab (index 0):
            * Main action buttons ENABLED
            * Approve/Reject DISABLED
        - Pending Approvals tab (index 1):
            * Main action buttons DISABLED
            * Approve/Reject ENABLED
        """
        try:
            current = self.notebook.select()
            index = self.notebook.index(current)
        except Exception:
            return

        # Make sure all buttons exist before changing state
        needed = (
            "btn_add", "btn_refresh", "btn_delete",
            "btn_statement", "btn_dep", "btn_wd",
            "btn_approve", "btn_reject",
        )
        if not all(hasattr(self, name) for name in needed):
            return

        main_buttons = (
            self.btn_add,
            self.btn_refresh,
            self.btn_delete,
            self.btn_statement,
            self.btn_dep,
            self.btn_wd,
        )

        if index == 1:  # Pending Approvals tab
            for b in main_buttons:
                b.state(["disabled"])
            self.btn_approve.state(["!disabled"])
            self.btn_reject.state(["!disabled"])
            self._update_previews(None, None)  # clear preview on pending tab
        else:  # Customers tab (or any other)
            for b in main_buttons:
                b.state(["!disabled"])
            self.btn_approve.state(["disabled"])
            self.btn_reject.state(["disabled"])

    # ---------- Pending approvals ----------
    def get_selected_pending_id(self):
        sel = self.pending_tree.selection()
        if not sel:
            return None
        item = self.pending_tree.item(sel[0])
        pid = item["values"][0]
        return pid

    def approve_selected_pending(self):
        pid = self.get_selected_pending_id()
        if not pid:
            messagebox.showinfo("Approve", "Please select a pending account")
            return
        if not messagebox.askyesno("Confirm", "Approve selected account?"):
            return
        try:
            approve_pending_account(pid)
            messagebox.showinfo("Success", "Account approved")
            self.refresh_all()
        except ValueError as ve:
            messagebox.showerror("Error", str(ve))
        except Exception as e:
            messagebox.showerror("Error", f"Approval failed: {e}")

    def reject_selected_pending(self):
        pid = self.get_selected_pending_id()
        if not pid:
            messagebox.showinfo("Reject", "Please select a pending account")
            return
        if not messagebox.askyesno("Confirm", "Reject selected account?"):
            return
        try:
            delete_pending_account(pid)
            messagebox.showinfo("Success", "Pending account rejected")
            self.refresh_pending()
            self._update_previews(None, None)
        except Exception as e:
            messagebox.showerror("Error", f"Rejection failed: {e}")

    # ---------- Admin Deposit / Withdraw ----------
    def admin_deposit(self):
        self._admin_txn_dialog("DEPOSIT")

    def admin_withdraw(self):
        self._admin_txn_dialog("WITHDRAW")

    def _admin_txn_dialog(self, txn_type):
        account_no = self.get_selected_customer_account()
        if not account_no:
            messagebox.showinfo(txn_type.title(), "Please select a customer first")
            return

        win = tk.Toplevel(self)
        win.title(f"{txn_type.title()} - {account_no}")
        win.geometry("280x160")
        win.resizable(False, False)
        win.transient(self.controller)
        center_window(win, self.controller)
        win.grab_set()
        win.focus_set()
        _set_icon(win)
        _force_light_popup(win)

        _make_light_label(win, text=f"{txn_type.title()} Amount:").pack(pady=15)

        amount_var = tk.StringVar()
        entry = ttk.Entry(win, textvariable=amount_var, style="PopupLight.TEntry")
        entry.pack(pady=5)
        entry.focus()

        def do_txn():
            amt_str = amount_var.get().strip()
            try:
                amt = float(amt_str)
                if amt <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Validation", "Enter a valid positive amount")
                return

            try:
                new_balance = update_balance_and_add_txn(account_no, amt, txn_type)
                messagebox.showinfo(
                    "Success",
                    f"{txn_type.title()} successful.\nNew Balance: {new_balance:.2f}"
                )
                self.refresh_customers()
                win.destroy()
            except ValueError as ve:
                messagebox.showerror("Error", str(ve))
            except Exception as e:
                messagebox.showerror("Error", f"Transaction failed: {e}")

        btn_frame = _make_light_frame(win)
        btn_frame.pack(pady=15)

        submit_txn_btn = ttk.Button(btn_frame, text="Submit", command=do_txn,
                                    style="PopupLight.TButton")
        submit_txn_btn.grid(row=0, column=0, padx=10)
        _set_btn_image(submit_txn_btn, "Submit_Request")
        cancel_txn_btn = ttk.Button(btn_frame, text="Cancel", command=win.destroy,
                                    style="PopupLight.TButton")
        cancel_txn_btn.grid(row=0, column=1, padx=10)
        _set_btn_image(cancel_txn_btn, "Cancel")

    # ---------- Account Statement (Admin) ----------
    def open_account_statement(self):
        account_no = self.get_selected_customer_account()
        if not account_no:
            messagebox.showinfo("Account Statement", "Please select a customer first")
            return

        try:
            customer = get_customer_by_account(account_no)
            if not customer:
                messagebox.showerror("Account Statement", "Customer not found in database")
                return
            txns = get_all_transactions(account_no)
        except Exception as e:
            messagebox.showerror("Error", f"Could not load transactions: {e}")
            return

        win = tk.Toplevel(self)
        win.title(f"Account Statement - {account_no}")
        win.geometry("650x520")
        win.transient(self.controller)
        center_window(win, self.controller)
        win.grab_set()
        win.focus_set()
        _set_icon(win)
        _force_light_popup(win)

        _make_light_label(
            win,
            text=f"All Transactions - {account_no}",
            font=("Segoe UI", 11, "bold")
        ).pack(pady=5)

        cols = ("type", "amount", "time")
        tree = ttk.Treeview(win, columns=cols, show="headings",
                            style="PopupLight.Treeview")
        tree.heading("type", text="Type")
        tree.heading("amount", text="Amount")
        tree.heading("time", text="Time")

        tree.column("type", width=80, anchor="center")
        tree.column("amount", width=100, anchor="e")
        tree.column("time", width=220, anchor="center")

        tree.pack(fill="both", expand=True, padx=10, pady=10)

        # Color tags for amounts
        tree.tag_configure("low", foreground="red")
        tree.tag_configure("high", foreground="green")

        for t in txns:
            amt = float(t["amount"])
            time_str = t["txn_time"].strftime("%Y-%m-%d %H:%M:%S")
            tag = "low" if amt < 1000 else "high"
            tree.insert(
                "",
                "end",
                values=(t["txn_type"], f"{amt:.2f}", time_str),
                tags=(tag,)
            )

        # Buttons for PDF & close
        btn_frame = _make_light_frame(win)
        btn_frame.pack(pady=5)

        def download_pdf():
            if not REPORTLAB_AVAILABLE:
                messagebox.showerror(
                    "PDF Error",
                    "reportlab is not installed.\n\nInstall it using:\n\npip install reportlab"
                )
                return

            if not txns:
                messagebox.showinfo("Export", "No transactions to export")
                return

            default_name = f"statement_{account_no}.pdf"
            path = filedialog.asksaveasfilename(
                title="Save Statement PDF",
                defaultextension=".pdf",
                initialfile=default_name,
                filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")]
            )
            if not path:
                return

            try:
                # Reuse same PDF generator as customer, which:
                # - Adds photo at top
                # - No signature stamp
                cust_frame: CustomerDashboardFrame = self.controller.frames["CustomerDashboardFrame"]
                cust_frame._create_passbook_pdf(path, customer, txns)
                messagebox.showinfo("Export", f"Statement PDF exported to:\n{path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export PDF: {e}")

        dl_pdf_btn = ttk.Button(
            btn_frame,
            text="Download Statement PDF",
            command=download_pdf,
            style="PopupLight.TButton"
        )
        dl_pdf_btn.pack(side="left", padx=5)
        _set_btn_image(dl_pdf_btn, "Account_Statement")

        close_stmt_btn = ttk.Button(
            btn_frame,
            text="Close",
            command=win.destroy,
            style="PopupLight.TButton"
        )
        close_stmt_btn.pack(side="left", padx=5)
        _set_btn_image(close_stmt_btn, "Cancel")

class NewAccountWindow(tk.Toplevel):
    def __init__(self, admin_frame: AdminDashboardFrame):
        super().__init__(admin_frame)
        self.admin_frame = admin_frame
        self.title("Open New Account — Pending Approval")
        self.geometry("580x660")
        self.minsize(540, 560)
        self.resizable(True, True)
        # Stay above the main app window only (not all windows system-wide)
        self.transient(admin_frame.controller)
        center_window(self, admin_frame.controller)
        self.grab_set()
        self.focus_set()
        # Set window icon
        _set_icon(self)
        # Always use light / white background regardless of app theme
        _force_light_popup(self)

        self.photo_path = tk.StringVar()
        self.signature_path = tk.StringVar()

        # ── Logo + Bank name header ──────────────────────────────────────
        header = ttk.Frame(self, style="PopupLight.TFrame")
        header.pack(fill="x", padx=15, pady=(12, 0))

        self._logo_img = None  # keep reference
        if PIL_AVAILABLE and os.path.exists(_ICON_PATH):
            try:
                # Render the .ico at 48×48 for the header
                raw = Image.open(_ICON_PATH)
                raw = raw.convert("RGBA").resize((48, 48), Image.LANCZOS)
                self._logo_img = ImageTk.PhotoImage(raw)
                logo_lbl = ttk.Label(header, image=self._logo_img,
                                     style="PopupLight.TLabel")
                logo_lbl.pack(side="left", padx=(0, 10))
            except Exception:
                pass

        title_frame = ttk.Frame(header, style="PopupLight.TFrame")
        title_frame.pack(side="left")
        ttk.Label(
            title_frame,
            text=BANK_NAME,
            font=("Segoe UI", 13, "bold"),
            style="PopupLight.TLabel"
        ).pack(anchor="w")
        ttk.Label(
            title_frame,
            text="New Account Registration",
            font=("Segoe UI", 9),
            style="PopupLight.TLabel"
        ).pack(anchor="w")

        # Separator
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=8)

        # ── Bottom button bar — packed BEFORE canvas so it anchors correctly ──
        ttk.Separator(self, orient="horizontal").pack(side="bottom", fill="x", padx=10, pady=(4, 0))
        btn_bar = ttk.Frame(self, style="PopupLight.TFrame")
        btn_bar.pack(side="bottom", fill="x", pady=10)

        # Submit Request — green button
        save_btn = tk.Button(
            btn_bar,
            text="✔  Submit Request",
            command=self.save_account,
            bg="#16a34a", fg="white",
            activebackground="#15803d", activeforeground="white",
            relief="flat", bd=0, highlightthickness=0,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2", padx=18, pady=7,
        )
        save_btn.pack(side="left", expand=True, fill="x", padx=(20, 8), pady=4)

        # Cancel — red button
        cancel_btn = tk.Button(
            btn_bar,
            text="✖  Cancel",
            command=self.destroy,
            bg="#dc2626", fg="white",
            activebackground="#b91c1c", activeforeground="white",
            relief="flat", bd=0, highlightthickness=0,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2", padx=18, pady=7,
        )
        cancel_btn.pack(side="left", expand=True, fill="x", padx=(8, 20), pady=4)

        # ── Scrollable form area ─────────────────────────────────────────
        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0,
                           bg=_POPUP_BG)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        form_container = ttk.Frame(canvas, style="PopupLight.TFrame")
        form_window = canvas.create_window((0, 0), window=form_container, anchor="nw")

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(form_window, width=event.width)

        form_container.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Mousewheel scroll
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # ── Form grid ────────────────────────────────────────────────────
        form = ttk.Frame(form_container, style="PopupLight.TFrame")
        form.pack(padx=15, pady=8, fill="both", expand=True)
        form.columnconfigure(1, weight=1)

        field_specs = [
            ("Account No:",      "readonly"),
            ("Password:",        "password"),
            ("Full Name:",       "normal"),
            ("Father's Name:",   "normal"),
            ("Mother's Name:",   "normal"),
            ("Aadhaar No:",      "normal"),
            ("Address:",         "normal"),
            ("Mobile:",          "normal"),
            ("IFSC Code:",       "readonly"),
            ("Branch:",          "readonly"),
            ("Opening Balance:", "normal"),
        ]

        # Fields that are auto-filled (readonly) don't need an asterisk
        _readonly_labels = {"Account No:", "IFSC Code:", "Branch:"}
        for i, (text, _) in enumerate(field_specs):
            lf = ttk.Frame(form, style="PopupLight.TFrame")
            lf.grid(row=i, column=0, sticky="e", pady=5, padx=(5, 8))
            ttk.Label(lf, text=text, font=("Segoe UI", 9),
                      style="PopupLight.TLabel").pack(side="left")
            if text not in _readonly_labels:
                tk.Label(lf, text=" *", font=("Segoe UI", 9, "bold"),
                         fg="#dc2626", bg=_POPUP_BG).pack(side="left")

        # Variables
        self.acc_var     = tk.StringVar(value=generate_next_account_no())
        self.pass_var    = tk.StringVar()
        self.name_var    = tk.StringVar()
        self.father_var  = tk.StringVar()
        self.mother_var  = tk.StringVar()
        self.aadhaar_var = tk.StringVar()
        self.address_var = tk.StringVar()
        self.mobile_var  = tk.StringVar()
        self.ifsc_var    = tk.StringVar(value="bank123456")
        self.branch_var  = tk.StringVar(value="G.T ROAD")
        self.balance_var = tk.StringVar(value="0")

        entry_configs = [
            (self.acc_var,     "readonly", False),
            (self.pass_var,    "normal",   True),   # show="*"
            (self.name_var,    "normal",   False),
            (self.father_var,  "normal",   False),
            (self.mother_var,  "normal",   False),
            (self.aadhaar_var, "normal",   False),
            (self.address_var, "normal",   False),
            (self.mobile_var,  "normal",   False),
            (self.ifsc_var,    "readonly", False),
            (self.branch_var,  "readonly", False),
            (self.balance_var, "normal",   False),
        ]

        self._entries = []
        for i, (var, state, is_pass) in enumerate(entry_configs):
            kw = {"textvariable": var, "state": state, "width": 30,
                  "style": "PopupLight.TEntry"}
            if is_pass:
                kw["show"] = "*"
            e = ttk.Entry(form, **kw)
            e.grid(row=i, column=1, sticky="ew", pady=5, padx=(0, 10))
            self._entries.append(e)

        # ── Photo row ──
        row_photo = len(field_specs)
        photo_lbl_frame = ttk.Frame(form, style="PopupLight.TFrame")
        photo_lbl_frame.grid(row=row_photo, column=0, sticky="e", pady=5, padx=(5, 8))
        ttk.Label(photo_lbl_frame, text="Photo:", font=("Segoe UI", 9),
                  style="PopupLight.TLabel").pack(side="left")
        tk.Label(photo_lbl_frame, text=" *", font=("Segoe UI", 9, "bold"),
                 fg="#dc2626", bg=_POPUP_BG).pack(side="left")
        photo_frame = ttk.Frame(form, style="PopupLight.TFrame")
        photo_frame.grid(row=row_photo, column=1, sticky="ew", pady=5, padx=(0, 10))
        photo_frame.columnconfigure(0, weight=1)

        self.photo_entry = ttk.Entry(photo_frame, textvariable=self.photo_path,
                                     state="readonly", style="PopupLight.TEntry")
        self.photo_entry.grid(row=0, column=0, sticky="ew")

        browse_photo_btn = ttk.Button(photo_frame, text="Browse…",
                                      command=self.browse_photo,
                                      style="PopupLight.TButton")
        browse_photo_btn.grid(row=0, column=1, padx=(5, 0))
        _set_btn_image(browse_photo_btn, "Browser")

        # ── Signature row ──
        row_sig = row_photo + 1
        sig_lbl_frame = ttk.Frame(form, style="PopupLight.TFrame")
        sig_lbl_frame.grid(row=row_sig, column=0, sticky="e", pady=5, padx=(5, 8))
        ttk.Label(sig_lbl_frame, text="Signature:", font=("Segoe UI", 9),
                  style="PopupLight.TLabel").pack(side="left")
        tk.Label(sig_lbl_frame, text=" *", font=("Segoe UI", 9, "bold"),
                 fg="#dc2626", bg=_POPUP_BG).pack(side="left")
        sig_frame = ttk.Frame(form, style="PopupLight.TFrame")
        sig_frame.grid(row=row_sig, column=1, sticky="ew", pady=5, padx=(0, 10))
        sig_frame.columnconfigure(0, weight=1)

        self.sig_entry = ttk.Entry(sig_frame, textvariable=self.signature_path,
                                   state="readonly", style="PopupLight.TEntry")
        self.sig_entry.grid(row=0, column=0, sticky="ew")

        browse_sig_btn = ttk.Button(sig_frame, text="Browse…",
                                    command=self.browse_signature,
                                    style="PopupLight.TButton")
        browse_sig_btn.grid(row=0, column=1, padx=(5, 0))
        _set_btn_image(browse_sig_btn, "Browser")

        # ── Required fields note ──
        ttk.Label(
            form_container,
            text="* All fields are required. Account No, IFSC and Branch are auto-filled.",
            font=("Segoe UI", 8),
            foreground="#6b7280",
            style="PopupLight.TLabel"
        ).pack(anchor="w", padx=15, pady=(4, 8))

        # Focus first editable entry (Password)
        self._entries[1].focus_set()

    def browse_photo(self):
        path = filedialog.askopenfilename(
            title="Select Photo",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp *.gif"), ("All Files", "*.*")]
        )
        if path:
            self.photo_path.set(path)

    def browse_signature(self):
        path = filedialog.askopenfilename(
            title="Select Signature Image",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp *.gif"), ("All Files", "*.*")]
        )
        if path:
            self.signature_path.set(path)

    def save_account(self):
        account_no      = self.acc_var.get().strip()
        password        = self.pass_var.get().strip()
        name            = self.name_var.get().strip()
        father_name     = self.father_var.get().strip()
        mother_name     = self.mother_var.get().strip()
        aadhaar         = self.aadhaar_var.get().strip()
        address         = self.address_var.get().strip()
        mobile          = self.mobile_var.get().strip()
        opening_balance = self.balance_var.get().strip()

        # ── All text fields required ──
        missing = []
        if not password:        missing.append("Password")
        if not name:            missing.append("Full Name")
        if not father_name:     missing.append("Father's Name")
        if not mother_name:     missing.append("Mother's Name")
        if not aadhaar:         missing.append("Aadhaar No")
        if not address:         missing.append("Address")
        if not mobile:          missing.append("Mobile")
        if not opening_balance: missing.append("Opening Balance")
        if not self.photo_path.get().strip():      missing.append("Photo")
        if not self.signature_path.get().strip():  missing.append("Signature")

        if missing:
            messagebox.showwarning(
                "Validation",
                "The following required fields are missing:\n\n• " + "\n• ".join(missing)
            )
            return

        # ── Password strength: min 6 chars ──
        if len(password) < 6:
            messagebox.showwarning("Validation", "Password must be at least 6 characters.")
            return

        # ── Aadhaar format ──
        if not aadhaar.isdigit() or len(aadhaar) != 12:
            messagebox.showwarning("Validation", "Aadhaar must be exactly 12 digits.")
            return

        # ── Mobile format ──
        if not mobile.isdigit() or len(mobile) != 10:
            messagebox.showwarning("Validation", "Mobile number must be exactly 10 digits.")
            return

        try:
            bal = float(opening_balance or 0)
            if bal < 0:
                raise ValueError("negative")
        except ValueError:
            messagebox.showwarning("Validation", "Opening Balance must be a non-negative number.")
            return

        data = {
            "account_no": account_no,
            "password": password,
            "name": name,
            "father_name": self.father_var.get().strip(),
            "mother_name": self.mother_var.get().strip(),
            "aadhaar": self.aadhaar_var.get().strip(),
            "address": self.address_var.get().strip(),
            "mobile": self.mobile_var.get().strip(),
            "ifsc": self.ifsc_var.get().strip(),
            "branch": self.branch_var.get().strip(),
            "signature_path": self.signature_path.get().strip() or None,
            "opening_balance": bal,
            "photo_path": self.photo_path.get().strip() or None
        }

        try:
            create_pending_account(data)
            messagebox.showinfo("Success", "Account request submitted for approval")
            self.admin_frame.refresh_pending()
            self.destroy()
        except mysql.connector.IntegrityError:
            messagebox.showerror("Error", "Account number already exists in pending/customers")
        except Exception as e:
            messagebox.showerror("Error", f"Unable to create account request: {e}")

class CustomerDashboardFrame(ttk.Frame):
    def __init__(self, parent, controller: BankApp):
        super().__init__(parent)
        self.controller = controller
        self.photo_cache = None

        header = ttk.Frame(self)
        header.pack(fill="x")

        self.title_label = ttk.Label(
            header,
            text="Customer Dashboard",
            font=("Segoe UI", 16, "bold")
        )
        self.title_label.pack(side="left", pady=10)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=10)

        # Left: details & actions
        left = ttk.Frame(body)
        left.pack(side="left", fill="y", padx=10)

        ttk.Label(left, text="Account Details", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 5))

        # Use theme-aware initial colors; will be updated by update_theme()
        _init_bg = "#020617" if controller.current_theme == "dark" else "#ffffff"
        _init_fg = "#e5e7eb" if controller.current_theme == "dark" else "#111827"
        self.details_text = tk.Text(
            left, width=50, height=12, state="disabled",
            bg=_init_bg, fg=_init_fg,
            relief="flat", bd=1
        )
        self.details_text.pack(pady=5)

        # Actions
        ttk.Label(left, text="Quick Actions", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(10, 5))

        btn_dep = ttk.Button(left, text="Deposit", command=self.deposit_dialog)
        btn_dep.pack(fill="x", pady=3)
        _set_btn_image(btn_dep, "Deposit")

        btn_wd = ttk.Button(left, text="Withdraw", command=self.withdraw_dialog)
        btn_wd.pack(fill="x", pady=3)
        _set_btn_image(btn_wd, "Withdrawl")

        btn_refresh = ttk.Button(left, text="Refresh Balance", command=self.refresh_details)
        btn_refresh.pack(fill="x", pady=3)
        _set_btn_image(btn_refresh, "Refresh_All")

        btn_export_pdf = ttk.Button(left, text="Export Passbook (PDF)", command=self.export_passbook_pdf)
        btn_export_pdf.pack(fill="x", pady=3)
        _set_btn_image(btn_export_pdf, "Account_Statement")

        # Right: photo at TOP + last 25 transactions
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=10)

        # Photo preview at TOP
        ttk.Label(right, text="Photo Preview", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 5))
        self.photo_label = ttk.Label(right, text="No photo", anchor="center")
        self.photo_label.pack(pady=5)

        ttk.Label(right, text="Last 25 Transactions", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(10, 5))

        cols = ("type", "amount", "time")
        self.txn_tree = ttk.Treeview(right, columns=cols, show="headings")
        self.txn_tree.heading("type", text="Type")
        self.txn_tree.heading("amount", text="Amount")
        self.txn_tree.heading("time", text="Time")

        self.txn_tree.column("type", width=80, anchor="center")
        self.txn_tree.column("amount", width=80, anchor="e")
        self.txn_tree.column("time", width=190, anchor="center")

        # Tags for red/green amounts
        self.txn_tree.tag_configure("low", foreground="red")
        self.txn_tree.tag_configure("high", foreground="green")

        self.txn_tree.pack(fill="both", expand=True)

    def load_user(self):
        user = self.controller.current_user
        if not user:
            return
        self.title_label.configure(text=f"Customer Dashboard - {user['name']}")
        self.refresh_details()

    def refresh_details(self):
        user = self.controller.current_user
        if not user:
            return

        # Reload from DB to get latest balance
        fresh = get_customer_by_account(user["account_no"])
        if fresh:
            self.controller.set_current_user(fresh)
            user = fresh

        bal = float(user["balance"])
        details = [
            f"Name: {user['name']}",
            f"Account No: {user['account_no']}",
            f"Father Name: {user.get('father_name') or ''}",
            f"Mother Name: {user.get('mother_name') or ''}",
            f"Aadhaar: {user.get('aadhaar') or ''}",
            f"Address: {user.get('address') or ''}",
            f"Mobile: {user.get('mobile') or ''}",
            f"IFSC: {user.get('ifsc') or ''}",
            f"Branch: {user.get('branch') or ''}",
            f"Balance: {bal:.2f}",
            f"Created At: {user.get('created_at')}"
        ]

        self.details_text.configure(state="normal")
        self.details_text.delete("1.0", "end")
        self.details_text.insert("1.0", "\n".join(details))

        # Color only the balance line
        try:
            balance_line_index = next(
                i for i, line in enumerate(details) if line.startswith("Balance:")
            )
            start_index = f"{balance_line_index + 1}.0"
            end_index = f"{balance_line_index + 1}.end"
            color = "red" if bal < 1000 else "green"
            self.details_text.tag_add("bal", start_index, end_index)
            self.details_text.tag_config("bal", foreground=color)
        except StopIteration:
            pass

        self.details_text.configure(state="disabled")

        # Refresh transactions (last 25)
        for row in self.txn_tree.get_children():
            self.txn_tree.delete(row)

        txns = get_last_transactions(user["account_no"], limit=25)
        for t in txns:
            time_str = t["txn_time"].strftime("%Y-%m-%d %H:%M:%S")
            amt = float(t["amount"])
            tag = "low" if amt < 1000 else "high"
            self.txn_tree.insert(
                "",
                "end",
                values=(t["txn_type"], f"{amt:.2f}", time_str),
                tags=(tag,)
            )

        # Photo preview
        path = user.get("photo_path")
        if not path or not os.path.exists(path):
            self.photo_label.configure(text="No photo", image="")
            self.photo_cache = None
        elif not PIL_AVAILABLE:
            self.photo_label.configure(text="Pillow not installed\nCannot show photo", image="")
            self.photo_cache = None
        else:
            try:
                img = Image.open(path)
                img = img.resize((140, 140), Image.LANCZOS)
                img_tk = ImageTk.PhotoImage(img)
                self.photo_cache = img_tk
                self.photo_label.configure(image=img_tk, text="")
            except Exception as e:
                self.photo_label.configure(text=f"Error loading photo\n{e}", image="")
                self.photo_cache = None

    def update_theme(self, theme: str):
        """Update the plain tk.Text widget colours when the app theme changes."""
        if theme == "dark":
            bg = "#020617"
            fg = "#e5e7eb"
            ins = "#e5e7eb"
        else:
            bg = "#ffffff"
            fg = "#111827"
            ins = "#111827"
        self.details_text.configure(bg=bg, fg=fg, insertbackground=ins)

    def logout(self):
        self.controller.set_current_user(None)
        self.controller.show_frame("LandingFrame")

    def deposit_dialog(self):
        self._txn_dialog("DEPOSIT")

    def withdraw_dialog(self):
        self._txn_dialog("WITHDRAW")

    def _txn_dialog(self, txn_type):
        user = self.controller.current_user
        if not user:
            return

        win = tk.Toplevel(self)
        win.title(txn_type.title())
        win.geometry("280x160")
        win.resizable(False, False)
        win.transient(self.controller)
        center_window(win, self.controller)
        win.grab_set()
        win.focus_set()
        _force_light_popup(win)

        _make_light_label(win, text=f"{txn_type.title()} Amount:").pack(pady=15)

        amount_var = tk.StringVar()
        entry = ttk.Entry(win, textvariable=amount_var, style="PopupLight.TEntry")
        entry.pack(pady=5)
        entry.focus()

        def do_txn():
            amt_str = amount_var.get().strip()
            try:
                amt = float(amt_str)
                if amt <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Validation", "Enter a valid positive amount")
                return

            try:
                new_balance = update_balance_and_add_txn(
                    user["account_no"],
                    amt,
                    txn_type
                )
                messagebox.showinfo(
                    "Success",
                    f"{txn_type.title()} successful.\nNew Balance: {new_balance:.2f}"
                )
                self.refresh_details()
                win.destroy()
            except ValueError as ve:
                messagebox.showerror("Error", str(ve))
            except Exception as e:
                messagebox.showerror("Error", f"Transaction failed: {e}")

        btn_frame = _make_light_frame(win)
        btn_frame.pack(pady=15)

        cust_submit_btn = ttk.Button(btn_frame, text="Submit", command=do_txn,
                                     style="PopupLight.TButton")
        cust_submit_btn.grid(row=0, column=0, padx=10)
        _set_btn_image(cust_submit_btn, "Submit_Request")
        cust_cancel_btn = ttk.Button(btn_frame, text="Cancel", command=win.destroy,
                                     style="PopupLight.TButton")
        cust_cancel_btn.grid(row=0, column=1, padx=10)
        _set_btn_image(cust_cancel_btn, "Cancel")

    # --------- PDF Export ---------
    def export_passbook_pdf(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(
                "PDF Error",
                "reportlab is not installed.\n\nInstall it using:\n\npip install reportlab"
            )
            return

        user = self.controller.current_user
        if not user:
            return

        try:
            txns = get_all_transactions(user["account_no"])
        except Exception as e:
            messagebox.showerror("Error", f"Could not load transactions: {e}")
            return

        if not txns:
            messagebox.showinfo("Export", "No transactions to export")
            return

        default_name = f"passbook_{user['account_no']}.pdf"
        path = filedialog.asksaveasfilename(
            title="Save Passbook PDF",
            defaultextension=".pdf",
            initialfile=default_name,
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")]
        )
        if not path:
            return

        try:
            self._create_passbook_pdf(path, user, txns)
            messagebox.showinfo("Export", f"Passbook PDF exported to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export PDF: {e}")

    def _create_passbook_pdf(self, filepath, user, txns):
        """
        Modern minimal PDF passbook / statement with:
        - Header with bank name and title
        - Customer photo at top (if available)
        - Customer details section
        - Transactions table
        - Summary
        - QR code of account number
        - NO signatures or stamp (as requested)
        """
        c = canvas.Canvas(filepath, pagesize=A4)
        width, height = A4
        margin = 25 * mm

        photo_path = user.get("photo_path")
        photo_available = bool(photo_path and os.path.exists(photo_path))

        def draw_header():
            # Bank name
            c.setFont("Helvetica-Bold", 18)
            c.setFillColor(colors.HexColor("#111827"))
            c.drawCentredString(width / 2, height - margin, BANK_NAME)

            # Subtitle
            c.setFont("Helvetica", 11)
            c.setFillColor(colors.HexColor("#4b5563"))
            c.drawCentredString(width / 2, height - margin - 15, "Account Statement (Passbook)")

            # Date
            c.setFont("Helvetica", 9)
            c.setFillColor(colors.black)
            c.drawRightString(
                width - margin,
                height - margin - 32,
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

            # QR code of account number (optional)
            try:
                qr_code = qr.QrCodeWidget(user["account_no"])
                bounds = qr_code.getBounds()
                size = 50  # px
                w = bounds[2] - bounds[0]
                h = bounds[3] - bounds[1]
                d = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
                d.add(qr_code)
                renderPDF.draw(d, c, width - margin - size, height - margin - 60)
            except Exception:
                # Ignore QR errors
                pass

        def draw_customer_info(start_y):
            c.setFont("Helvetica-Bold", 11)
            c.setFillColor(colors.black)
            c.drawString(margin, start_y, "Customer Details")

            y = start_y - 4

            # Draw photo at top-left (if available)
            text_x = margin
            img_height = 40
            if photo_available:
                try:
                    img = ImageReader(photo_path)
                    c.drawImage(
                        img,
                        margin,
                        y - img_height,
                        width=40,
                        height=40,
                        preserveAspectRatio=True,
                        mask='auto'
                    )
                    text_x = margin + 50
                except Exception:
                    text_x = margin

            c.setFont("Helvetica", 9)
            line_gap = 12
            y -= 6

            info_lines = [
                f"Name: {user['name']}",
                f"Account No: {user['account_no']}",
                f"IFSC: {user.get('ifsc') or ''}",
                f"Branch: {user.get('branch') or ''}",
                f"Mobile: {user.get('mobile') or ''}",
                f"Address: {user.get('address') or ''}",
                f"Aadhaar: {user.get('aadhaar') or ''}",
                f"Opened On: {user.get('created_at')}",
            ]

            for line in info_lines:
                c.drawString(text_x, y, line)
                y -= line_gap

            # Line separator
            c.setStrokeColor(colors.HexColor("#e5e7eb"))
            c.line(margin, y + 5, width - margin, y + 5)

            return y - 10  # return new y position

        def draw_table_header(y):
            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(colors.black)

            # Columns: Date, Type, Amount
            col_x = [margin, margin + 130, margin + 210]
            headers = ["Date & Time", "Type", "Amount (₹)"]
            for x, h_name in zip(col_x, headers):
                c.drawString(x, y, h_name)

            # underline
            c.setStrokeColor(colors.HexColor("#9ca3af"))
            c.line(margin, y - 2, width - margin, y - 2)
            return y - 14

        def draw_transactions(start_y):
            c.setFont("Helvetica", 9)
            line_height = 12

            y = start_y
            col_x = [margin, margin + 130, margin + 210]

            total_deposit = 0.0
            total_withdraw = 0.0

            for t in txns:
                if y < margin + 80:
                    # New page
                    c.showPage()
                    draw_header()
                    y = draw_customer_info(height - margin - 110)
                    y = draw_table_header(y)

                dt_str = t["txn_time"].strftime("%Y-%m-%d %H:%M:%S")
                amt = float(t["amount"])
                # Color: green for DEPOSIT, red for WITHDRAW
                if t["txn_type"] == "DEPOSIT":
                    row_color = colors.HexColor("#15803d")  # green
                else:
                    row_color = colors.HexColor("#b91c1c")  # red
                c.setFillColor(colors.black)
                c.drawString(col_x[0], y, dt_str)
                c.setFillColor(row_color)
                c.drawString(col_x[1], y, t["txn_type"])
                c.drawRightString(width - margin, y, f"{amt:,.2f}")

                if t["txn_type"] == "DEPOSIT":
                    total_deposit += amt
                else:
                    total_withdraw += amt

                c.setFillColor(colors.black)  # reset for next row
                y -= line_height

            return y, total_deposit, total_withdraw

        def draw_summary(y, total_deposit, total_withdraw):
            # Move to next page if not enough space
            if y < margin + 120:
                c.showPage()
                draw_header()
                y = height - margin - 150

            c.setStrokeColor(colors.HexColor("#e5e7eb"))
            c.line(margin, y, width - margin, y)
            y -= 10

            c.setFont("Helvetica-Bold", 11)
            c.setFillColor(colors.black)
            c.drawString(margin, y, "Summary")
            y -= 16

            c.setFont("Helvetica", 9)
            current_balance = float(user["balance"])

            c.setFillColor(colors.HexColor("#16a34a"))  # green for deposits
            c.drawString(margin, y, f"Total Deposited: ₹ {total_deposit:,.2f}")
            y -= 14
            c.setFillColor(colors.HexColor("#dc2626"))  # red for withdrawals
            c.drawString(margin, y, f"Total Withdrawn: ₹ {total_withdraw:,.2f}")
            y -= 14
            c.setFillColor(colors.black)
            c.drawString(margin, y, f"Final Balance: ₹ {current_balance:,.2f}")
            y -= 20

            c.setFillColor(colors.HexColor("#6b7280"))
            c.setFont("Helvetica-Oblique", 8)
            c.drawString(
                margin,
                y,
                "This is a system-generated statement and does not require a physical signature."
            )

        # ---- Draw content ----
        draw_header()
        y = draw_customer_info(height - margin - 100)
        y = draw_table_header(y)
        y, total_deposit, total_withdraw = draw_transactions(y)
        draw_summary(y, total_deposit, total_withdraw)

        c.showPage()
        c.save()

# -------------- MAIN ENTRY ------------------
def main():
    try:
        init_database()
    except Exception as e:
        # Use basic Tk root for messagebox if main window not created
        root = tk.Tk()
        root.withdraw()
        _set_icon(root)
        messagebox.showerror("DB Error", f"Could not initialize database:\n{e}")
        root.destroy()
        return

    app = BankApp()
    app.mainloop()

if __name__ == "__main__":
    main()