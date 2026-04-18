import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

# Optional PIL (Pillow) library for handling and displaying images (e.g., photo/signature previews)
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Optional reportlab library used for generating PDF account statements and passbooks
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
# Determines the absolute path to the application icon (logo.ico) relative to this script
_ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.ico")

def _set_icon(win):
    """
    Sets the logo.ico as the window icon for any given Tk or Toplevel window.
    Fails silently if the icon file is unavailable or unsupported.
    """
    try:
        win.iconbitmap(_ICON_PATH)
    except Exception:
        pass

# -------------- BUTTON IMAGE LOADER ----------------
_BTN_IMAGES = {}  # Global dictionary cache to store loaded images so they aren't garbage-collected by Python

def _load_btn_image(name, size=(20, 20)):
    """
    Loads a PNG image file to be used as a button icon.
    
    Args:
        name: The filename of the image without the .png extension.
        size: A tuple (width, height) to resize the image to.
        
    Returns:
        A PhotoImage object if successful, or None if PIL is missing or the file is not found.
    """
    if not PIL_AVAILABLE:
        return None
    key = (name, size)
    if key in _BTN_IMAGES:
        return _BTN_IMAGES[key] # Return from cache if already loaded
        
    # Look for the image in the current directory or a designated uploads folder
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.png"),
        os.path.join("/mnt/user-data/uploads", f"{name}.png"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                # Open, resize using high-quality LANCZOS resampling, and convert to Tkinter format
                img = Image.open(path).resize(size, Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                _BTN_IMAGES[key] = photo
                return photo
            except Exception:
                pass
    return None

def _set_btn_image(btn, name, size=(20, 20)):
    """
    Helper function to attach a loaded PNG icon to a ttk.Button widget.
    Places the image on the left side of the button text.
    """
    photo = _load_btn_image(name, size)
    if photo:
        btn.configure(image=photo, compound="left")
        btn.image = photo  # Keep a local reference to prevent garbage collection

# -------------- MySQL CONFIG ----------------
# Database connection credentials and application constants
DB_HOST = "localhost"
DB_USER = "root"          # <-- MySQL username
DB_PASSWORD = "Admin@123" # <-- MySQL password
DB_NAME = "bankdb"

BANK_NAME = "Modern Bank of India"

# -------------- DATABASE LAYER --------------
def get_connection(db=None):
    """
    Establishes and returns a connection to the MySQL server.
    If 'db' is specified, it connects directly to that database.
    """
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=db
    )

def init_database():
    """
    Initializes the database schema.
    Creates the database and necessary tables (customers, transactions, pending_accounts) 
    if they do not exist. Also attempts to dynamically alter existing tables to add 
    new columns if running on an older version of the schema.
    """
    # Create database if not exists
    conn = get_connection(None)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
    conn.commit()
    cur.close()
    conn.close()

    # Connect to the specific database to create tables
    conn = get_connection(DB_NAME)
    cur = conn.cursor()

    # Create the main Customers table for approved accounts
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

    # Create the Transactions table, linked to customers via account_no
    # Uses ON DELETE CASCADE so if a customer is removed, their transactions are too.
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

    # Create the Pending Accounts table for new registrations awaiting admin approval
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

    # Ensure newer columns exist in case the script is running against an older DB version
    try:
        # Columns for customers table
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS address VARCHAR(255)")
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS mobile VARCHAR(20)")
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS ifsc VARCHAR(20)")
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS branch VARCHAR(100)")
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS signature_path VARCHAR(255)")
        # Columns for pending_accounts table
        cur.execute("ALTER TABLE pending_accounts ADD COLUMN IF NOT EXISTS address VARCHAR(255)")
        cur.execute("ALTER TABLE pending_accounts ADD COLUMN IF NOT EXISTS mobile VARCHAR(20)")
        cur.execute("ALTER TABLE pending_accounts ADD COLUMN IF NOT EXISTS ifsc VARCHAR(20)")
        cur.execute("ALTER TABLE pending_accounts ADD COLUMN IF NOT EXISTS branch VARCHAR(100)")
        cur.execute("ALTER TABLE pending_accounts ADD COLUMN IF NOT EXISTS signature_path VARCHAR(255)")
    except Exception:
        # Catch and ignore errors where older MySQL versions do not support 'IF NOT EXISTS' in ALTER queries
        pass

    conn.commit()
    cur.close()
    conn.close()

# ---------- AUTO ACCOUNT NUMBER (START FROM 10000001) ---------
def generate_next_account_no():
    """
    Generates a unique, sequential account number.
    Scans both 'customers' and 'pending_accounts' tables for the highest existing
    numeric account number and increments it by 1. 
    If no accounts exist, it defaults to starting at 10000001.
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
    Directly inserts a new record into the 'customers' table.
    Typically used internally when migrating a pending account to an approved status.
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
                data["account_no"], data["password"], data["name"],
                data["father_name"], data["mother_name"], data["aadhaar"],
                data["address"], data["mobile"], data["ifsc"],
                data["branch"], data["signature_path"], data["balance"],
                data["photo_path"],
            )
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

def get_all_customers():
    """Fetches all approved customers from the database, returned as a list of dictionaries."""
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
    """
    Searches the approved customers table.
    Filters records where the given keyword partially matches the Name, Account No, or Aadhaar.
    """
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
    """Deletes a customer based on their database primary key (id). Cascades to their transactions."""
    conn = get_connection(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM customers WHERE id = %s", (cust_id,))
    conn.commit()
    cur.close()
    conn.close()

def get_customer_by_login(account_no, password):
    """Authenticates a customer by matching their Account Number and Password. Returns the customer row or None."""
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
    """Authenticates a customer by matching their Aadhaar number and Password. Returns the customer row or None."""
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
    """Retrieves a single customer's detailed record by their account number."""
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
    """Updates the password string for the specified account number in the database."""
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
    Inserts a newly requested account into the 'pending_accounts' table.
    Admin intervention is required to move this into the 'customers' table.
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
                data["account_no"], data["password"], data["name"],
                data["father_name"], data["mother_name"], data["aadhaar"],
                data["address"], data["mobile"], data["ifsc"], data["branch"],
                data["signature_path"], data["opening_balance"], data["photo_path"],
            )
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

def get_all_pending_accounts():
    """Retrieves a list of all account requests currently waiting for admin approval."""
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
    """Retrieves a specific pending account request by its account number."""
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
    """Deletes a pending account request entirely (used when an admin rejects an application)."""
    conn = get_connection(DB_NAME)
    cur = conn.cursor()
    cur.execute("DELETE FROM pending_accounts WHERE id = %s", (pending_id,))
    conn.commit()
    cur.close()
    conn.close()

def approve_pending_account(pending_id):
    """
    Approves a pending account by migrating its record from 'pending_accounts' to 'customers'.
    It also creates an initial DEPOSIT transaction log if an opening balance was provided,
    and finally cleans up the pending_accounts table.
    """
    conn = get_connection(DB_NAME)
    cur = conn.cursor(dictionary=True)
    try:
        # Step 1: Fetch pending record
        cur.execute("SELECT * FROM pending_accounts WHERE id = %s", (pending_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Pending account not found")

        account_no = row["account_no"]

        # Step 2: Insert into approved customers table
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
                    row["account_no"], row["password"], row["name"], row["father_name"],
                    row["mother_name"], row["aadhaar"], row["address"], row["mobile"],
                    row["ifsc"], row["branch"], row["signature_path"],
                    row["opening_balance"], row["photo_path"],
                )
            )
        except mysql.connector.IntegrityError:
            raise ValueError("Account number already exists in customers")
        finally:
            cur2.close()

        # Step 3: Record initial deposit transaction if opening balance > 0
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

        # Step 4: Remove from pending accounts
        cur4 = conn.cursor()
        cur4.execute("DELETE FROM pending_accounts WHERE id = %s", (pending_id,))
        cur4.close()

        conn.commit() # Commit all changes atomically

    except Exception:
        conn.rollback() # Revert any partial changes on failure
        raise
    finally:
        cur.close()
        conn.close()

# -------------- Transactions ----------------
def update_balance_and_add_txn(account_no, amount, txn_type):
    """
    Processes a financial transaction (DEPOSIT or WITHDRAW).
    Locks the customer's row using 'FOR UPDATE' to prevent race conditions during concurrent access.
    Updates the customer's balance and records the event in the transactions table.
    
    Args:
        account_no: Customer's account number.
        amount: Positive transaction value.
        txn_type: Either 'DEPOSIT' or 'WITHDRAW'.
        
    Returns:
        The customer's new updated balance.
    """
    conn = get_connection(DB_NAME)
    cur = conn.cursor()
    try:
        # Lock the specific customer row for atomic reading/updating
        cur.execute(
            "SELECT balance FROM customers WHERE account_no=%s FOR UPDATE",
            (account_no,)
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Account not found")
        current_balance = float(row[0])

        # Validate withdrawal rules
        if txn_type == "DEPOSIT":
            new_balance = current_balance + amount
        else:
            if current_balance < amount:
                raise ValueError("Insufficient balance")
            new_balance = current_balance - amount

        # Execute balance update
        cur.execute(
            "UPDATE customers SET balance=%s WHERE account_no=%s",
            (new_balance, account_no)
        )

        # Log the transaction
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
    """Retrieves the most recent transactions for a given account. Usually displayed on Dashboards."""
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
    """Retrieves the entire transaction history for an account, ordered chronologically. Used for PDF Statement generation."""
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

# Light-mode colors used exclusively for popups to enforce a clean white look regardless of the main window's theme
_POPUP_BG  = "#ffffff"
_POPUP_FG  = "#111827"
_POPUP_ENT = "#f9fafb"   # entry background

def _register_popup_light_styles(style: ttk.Style):
    """
    Registers custom 'PopupLight.*' ttk style variants.
    Ensures popups like Forgot Password or PDF  Download remain white/light-themed even if the main app is in Dark Mode.
    """
    style.configure("PopupLight.TFrame",  background=_POPUP_BG)
    style.configure("PopupLight.TLabel",  background=_POPUP_BG, foreground=_POPUP_FG, font=("Segoe UI", 10))
    style.configure("PopupLight.TEntry",  fieldbackground=_POPUP_ENT, foreground=_POPUP_FG)
    style.configure("PopupLight.TButton", padding=6, relief="flat", font=("Segoe UI", 10))
    style.configure("PopupLight.Treeview", background="#ffffff", fieldbackground="#ffffff", foreground=_POPUP_FG, font=("Segoe UI", 9), rowheight=26)
    style.configure("PopupLight.Treeview.Heading", background="#e5e7eb", foreground=_POPUP_FG, font=("Segoe UI", 9, "bold"))
    style.configure("PopupLight.TScrollbar")
    style.configure("PopupLight.TSeparator", background="#d1d5db")
    style.configure("PopupLight.TNotebook", background=_POPUP_BG)
    style.configure("PopupLight.TNotebook.Tab", background="#e5e7eb", foreground=_POPUP_FG)

def _force_light_popup(win: tk.Toplevel):
    """Forces a given Toplevel window to ignore the app theme and enforce a light background."""
    win.configure(bg=_POPUP_BG)

def _make_light_frame(parent, **kw) -> ttk.Frame:
    """Helper method creating a ttk.Frame pre-configured with the 'PopupLight' styles."""
    kw.setdefault("style", "PopupLight.TFrame")
    return ttk.Frame(parent, **kw)

def _make_light_label(parent, **kw) -> ttk.Label:
    """Helper method creating a ttk.Label pre-configured with the 'PopupLight' styles."""
    kw.setdefault("style", "PopupLight.TLabel")
    return ttk.Label(parent, **kw)

def center_window(win, parent=None):
    """
    Geometrically centers a tkinter Toplevel or root window on the screen.
    If 'parent' is provided, it centers the window relative to the parent's current position instead.
    Must be called after all widgets have populated and .geometry() has resolved.
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
    """
    Main Application class bridging Tkinter's Root Window logic.
    Handles dynamic frame switching, session management (login states), and Theme toggling (Light/Dark).
    """
    def __init__(self):
        super().__init__()
        _set_icon(self) 
        self.title("Bank Management System")
        self.geometry("1100x650")
        self.minsize(980, 580)
        center_window(self)

        # Initialize core UI styling
        self.current_theme = "dark"
        self.style = ttk.Style(self)
        self._apply_dark_theme()
        _register_popup_light_styles(self.style) 

        self.current_user = None  # Holds the currently authenticated customer's dictionary record

        # ── Global Top Navigation Bar (Theme toggle and Logout) ──
        topbar = ttk.Frame(self)
        topbar.pack(fill="x", padx=10, pady=(6, 0))

        btn_col = ttk.Frame(topbar)
        btn_col.pack(side="right")

        self.theme_btn = ttk.Button(
            btn_col, text="☀  Light Mode", command=self.toggle_theme,
        )
        self.theme_btn.pack(side="top", anchor="e", fill="x")

        # Logout button (Dynamically hidden until a dashboard is loaded)
        self.topbar_logout_btn = ttk.Button(
            btn_col, text="Logout", command=self._topbar_logout,
        )
        _set_btn_image(self.topbar_logout_btn, "Logout") 

        # ── Main Container for View Navigation ──
        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.container.rowconfigure(0, weight=1)
        self.container.columnconfigure(0, weight=1)

        # Pre-initialize and store all core frames (views)
        self.frames = {}
        for F in (LandingFrame, AdminLoginFrame, CustomerLoginFrame,
                  AdminDashboardFrame, CustomerDashboardFrame):
            frame = F(parent=self.container, controller=self)
            self.frames[F.__name__] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        # Initial view on launch
        self.show_frame("LandingFrame")

    def _apply_dark_theme(self):
        """Applies the custom Dark Theme palettes to ttk styles."""
        self.configure(bg="#111827")  
        self.style.theme_use("clam")

        self.style.configure("TButton", padding=6, relief="flat", font=("Segoe UI", 10))
        self.style.map("TButton", background=[("active", "#2563eb")])
        self.style.configure("TLabel", font=("Segoe UI", 10), background="#111827", foreground="#e5e7eb")
        self.style.configure("TFrame", background="#111827")
        self.style.configure("Treeview", font=("Segoe UI", 9), rowheight=26)
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        self.style.configure("Green.TButton", padding=6, relief="flat", font=("Segoe UI", 10), background="#16a34a", foreground="#ffffff")
        self.style.map("Green.TButton", background=[("active", "#15803d"), ("disabled", "#374151")], foreground=[("disabled", "#6b7280")])
        self.style.configure("Red.TButton", padding=6, relief="flat", font=("Segoe UI", 10), background="#dc2626", foreground="#ffffff")
        self.style.map("Red.TButton", background=[("active", "#b91c1c"), ("disabled", "#374151")], foreground=[("disabled", "#6b7280")])

    def _apply_light_theme(self):
        """Applies the custom Light Theme palettes to ttk styles."""
        self.configure(bg="#f3f4f6")  
        self.style.theme_use("clam")

        self.style.configure("TButton", padding=6, relief="flat", font=("Segoe UI", 10))
        self.style.map("TButton", background=[("active", "#2563eb")])
        self.style.configure("TLabel", font=("Segoe UI", 10), background="#f3f4f6", foreground="#111827")
        self.style.configure("TFrame", background="#f3f4f6")
        self.style.configure("Treeview", font=("Segoe UI", 9), rowheight=26)
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        self.style.configure("Green.TButton", padding=6, relief="flat", font=("Segoe UI", 10), background="#16a34a", foreground="#ffffff")
        self.style.map("Green.TButton", background=[("active", "#15803d"), ("disabled", "#d1fae5")], foreground=[("disabled", "#6b7280")])
        self.style.configure("Red.TButton", padding=6, relief="flat", font=("Segoe UI", 10), background="#dc2626", foreground="#ffffff")
        self.style.map("Red.TButton", background=[("active", "#b91c1c"), ("disabled", "#fee2e2")], foreground=[("disabled", "#6b7280")])

    def toggle_theme(self):
        """Toggles the application between light and dark modes, manually forcing updates on specific widgets."""
        if self.current_theme == "dark":
            self.current_theme = "light"
            self._apply_light_theme()
            self.theme_btn.configure(text="🌙  Dark Mode")
        else:
            self.current_theme = "dark"
            self._apply_dark_theme()
            self.theme_btn.configure(text="☀  Light Mode")
            
        # Re-apply light styles for popup menus as calling theme_use wipes them out
        _register_popup_light_styles(self.style)
        
        # Propagate theme changes to non-ttk widgets (plain tk.Labels and tk.Text)
        admin_frame = self.frames.get("AdminDashboardFrame")
        if admin_frame:
            admin_frame.update_preview_theme(self.current_theme)
        cust_frame = self.frames.get("CustomerDashboardFrame")
        if cust_frame:
            cust_frame.update_theme(self.current_theme)

    def show_frame(self, name):
        """Raises the targeted frame (by class name) to the top of the GUI stack to make it visible."""
        frame = self.frames[name]
        frame.tkraise()
        
        # Toggle visibility of the Top-bar Logout button based on the active screen
        if name in ("AdminDashboardFrame", "CustomerDashboardFrame"):
            self.topbar_logout_btn.pack(side="top", anchor="e", pady=(2, 0), fill="x")
        else:
            self.topbar_logout_btn.pack_forget()

    def _topbar_logout(self):
        """Handles logout routing depending on who is logged in (Customer vs Admin)."""
        cust = self.frames.get("CustomerDashboardFrame")
        if cust and cust.winfo_ismapped():
            cust.logout()
        else:
            self.show_frame("LandingFrame")

    def admin_auth(self, username, password):
        """Simple hardcoded authentication check for the Admin layer."""
        return username == "admin" and password == "admin123"

    def set_current_user(self, user_dict):
        """Sets the global session dictionary for the authenticated customer."""
        self.current_user = user_dict


class LandingFrame(ttk.Frame):
    """
    Initial Home Screen View.
    Presents routing options for Admin Login, Customer Login, or Opening a New Account.
    """
    def __init__(self, parent, controller: BankApp):
        super().__init__(parent)
        self.controller = controller

        # Inner frame to keep items strictly centered
        inner = ttk.Frame(self)
        inner.place(relx=0.5, rely=0.5, anchor="center")

        self._logo_img = None
        if PIL_AVAILABLE and os.path.exists(_ICON_PATH):
            try:
                raw = Image.open(_ICON_PATH).convert("RGBA").resize((64, 64), Image.LANCZOS)
                self._logo_img = ImageTk.PhotoImage(raw)
                ttk.Label(inner, image=self._logo_img).pack(pady=(0, 5))
            except Exception:
                pass

        ttk.Label(inner, text=BANK_NAME, font=("Segoe UI", 22, "bold")).pack(pady=(0 if self._logo_img else 0, 2))
        ttk.Label(inner, text="Secure  •  Reliable  •  Modern", font=("Segoe UI", 10)).pack(pady=(0, 4))
        ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=60, pady=10)
        ttk.Label(inner, text="Please choose an option to continue", font=("Segoe UI", 11)).pack(pady=(0, 8))

        btn_frame = ttk.Frame(inner)
        btn_frame.pack(pady=20)

        admin_btn = ttk.Button(btn_frame, text="Admin Login", command=lambda: controller.show_frame("AdminLoginFrame"))
        admin_btn.grid(row=0, column=0, padx=20, ipadx=30, ipady=10)
        _set_btn_image(admin_btn, "admin_login")

        cust_btn = ttk.Button(btn_frame, text="Customer Login", command=lambda: controller.show_frame("CustomerLoginFrame"))
        cust_btn.grid(row=0, column=1, padx=20, ipadx=30, ipady=10)
        _set_btn_image(cust_btn, "customer_login")

        # Routing to the external application form modal
        open_account_btn = ttk.Button(
            btn_frame, text="Open New Account", 
            command=lambda: NewAccountWindow(controller.frames["AdminDashboardFrame"])
        )
        open_account_btn.grid(row=1, column=0, columnspan=2, pady=20, ipadx=40, ipady=10)
        _set_btn_image(open_account_btn, "Open_New_Account")


class AdminLoginFrame(ttk.Frame):
    """
    Admin Authentication View.
    Collects standard username/password combinations to validate against `controller.admin_auth`.
    """
    def __init__(self, parent, controller: BankApp):
        super().__init__(parent)
        self.controller = controller

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

        ttk.Label(inner, text="Admin Login", font=("Segoe UI", 18, "bold")).pack(pady=(0, 20))

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

        login_btn = ttk.Button(btn_frame, text="Login", command=self.handle_login)
        login_btn.grid(row=0, column=0, padx=10, ipadx=20)
        _set_btn_image(login_btn, "Login")

        back_btn = ttk.Button(btn_frame, text="Back", command=lambda: controller.show_frame("LandingFrame"))
        back_btn.grid(row=0, column=1, padx=10, ipadx=20)
        _set_btn_image(back_btn, "Back")

    def handle_login(self):
        """Processes the submit action for Admin Authentication."""
        u = self.username_var.get().strip()
        p = self.password_var.get().strip()

        if self.controller.admin_auth(u, p):
            admin_frame: AdminDashboardFrame = self.controller.frames["AdminDashboardFrame"]
            admin_frame.refresh_all() # Ensure the dashboard tables are populated immediately
            self.controller.show_frame("AdminDashboardFrame")
        else:
            messagebox.showerror("Login Failed", "Invalid admin credentials")


class CustomerLoginFrame(ttk.Frame):
    """
    Customer Authentication View.
    Allows standard users to authenticate using either their 8-digit Account Number OR their 12-digit Aadhaar.
    """
    def __init__(self, parent, controller: BankApp):
        super().__init__(parent)
        self.controller = controller

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

        ttk.Label(inner, text="Customer Login", font=("Segoe UI", 18, "bold")).pack(pady=(0, 20))

        form = ttk.Frame(inner)
        form.pack(pady=10)

        ttk.Label(form, text="Login Type:").grid(row=0, column=0, sticky="e", pady=5, padx=5)
        ttk.Label(form, text="Login ID:").grid(row=1, column=0, sticky="e", pady=5, padx=5)
        ttk.Label(form, text="Password:").grid(row=2, column=0, sticky="e", pady=5, padx=5)

        self.login_type_var = tk.StringVar(value="Account Number")
        self.id_var = tk.StringVar()
        self.pass_var = tk.StringVar()

        # Combobox allowing user to toggle auth strategy
        login_type_combo = ttk.Combobox(
            form, textvariable=self.login_type_var, state="readonly",
            values=["Account Number", "Aadhaar Number"], width=20
        )
        login_type_combo.grid(row=0, column=1, pady=5, padx=5)

        id_entry = ttk.Entry(form, textvariable=self.id_var, width=22)
        pass_entry = ttk.Entry(form, textvariable=self.pass_var, show="*", width=22)
        id_entry.grid(row=1, column=1, pady=5, padx=5)
        pass_entry.grid(row=2, column=1, pady=5, padx=5)

        btn_frame = ttk.Frame(inner)
        btn_frame.pack(pady=20)

        login_btn = ttk.Button(btn_frame, text="Login", command=self.handle_login)
        login_btn.grid(row=0, column=0, padx=10, ipadx=20)
        _set_btn_image(login_btn, "Login")

        back_btn = ttk.Button(btn_frame, text="Back", command=lambda: controller.show_frame("LandingFrame"))
        back_btn.grid(row=0, column=1, padx=10, ipadx=20)
        _set_btn_image(back_btn, "Back")

        # Forgot Password button logic routing to the external modal window
        forgot_btn = ttk.Button(inner, text="Forgot Password?", command=self.open_forgot_password)
        forgot_btn.pack(pady=(0, 10))
        _set_btn_image(forgot_btn, "forgot_password")

    def open_forgot_password(self):
        """Spawns the Forgot Password Toplevel window."""
        ForgotPasswordWindow(self)

    def handle_login(self):
        """Validates inputs and attempts to fetch user data based on the chosen authentication strategy."""
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
                # Enforce Aadhaar criteria prior to querying the database
                if len(login_id) != 12 or not login_id.isdigit():
                    messagebox.showwarning("Validation", "Enter a valid 12-digit Aadhaar number")
                    return
                user = get_customer_by_aadhaar(login_id, password)

            if user:
                # Save user to global app session state
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
    Two-step forgotten password recovery window popup:
      Step 1: Verifies identity using a strict combination of Account No + Aadhaar + Registered Mobile.
      Step 2: Allows input of a new password to overwrite the old one.
    """
    _IMG_VERIFY = "forgot_password"    
    _IMG_CHANGE = "change_password"    
    _IMG_SIZE   = (72, 72)

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Forgot Password")
        self.resizable(False, False)
        _set_icon(self)
        self.grab_set() # Block interaction with background windows

        self._verified_account = None

        self._img_verify = _load_btn_image(self._IMG_VERIFY, self._IMG_SIZE)
        self._img_change = _load_btn_image(self._IMG_CHANGE, self._IMG_SIZE)

        outer = ttk.Frame(self)
        outer.pack(padx=32, pady=24, fill="both", expand=True)

        self._img_label = ttk.Label(outer)
        self._img_label.pack(pady=(0, 4))
        self._title_label = ttk.Label(outer, font=("Segoe UI", 15, "bold"))
        self._title_label.pack(pady=(0, 2))
        self._sub_label = ttk.Label(outer, font=("Segoe UI", 9))
        self._sub_label.pack(pady=(0, 14))

        # ══════════════════════════════════════════════
        # Step 1 – Identity Verification Frame
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
            ttk.Label(form1, text=lbl_text, anchor="e").grid(row=i, column=0, sticky="e", pady=6, padx=8)
            var = tk.StringVar()
            self._vars[key] = var
            ttk.Entry(form1, textvariable=var, width=26).grid(row=i, column=1, pady=6, padx=8)

        self._verify_btn = ttk.Button(self._step1_frame, text="Verify Details", command=self._verify)
        self._verify_btn.pack(pady=(14, 0), ipadx=16)
        _set_btn_image(self._verify_btn, "verify_details")

        # ══════════════════════════════════════════════
        # Step 2 – Change Password Frame (Initially un-packed)
        # ══════════════════════════════════════════════
        self._step2_frame = ttk.Frame(outer)

        self._verified_label = ttk.Label(
            self._step2_frame, text="✔  Identity verified. Set your new password.",
            font=("Segoe UI", 9, "bold"), foreground="#16a34a"
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

        self._change_btn = ttk.Button(self._step2_frame, text="Change Password", command=self._change_password)
        self._change_btn.pack(pady=(14, 0), ipadx=16)
        _set_btn_image(self._change_btn, "change_password")

        self._show_step1()
        self.update_idletasks()
        center_window(self, parent)

    def _show_step1(self):
        """Swaps UI logic to configure labels and images for the Identity Verification stage."""
        if self._img_verify:
            self._img_label.configure(image=self._img_verify, text="")
        else:
            self._img_label.configure(image="", text="🔒", font=("Segoe UI", 32))
        self._title_label.configure(text="Forgot Password")
        self._sub_label.configure(text="Enter your account details to verify identity")

    def _show_step2(self):
        """Swaps UI logic to configure labels and images for the New Password setup stage."""
        if self._img_change:
            self._img_label.configure(image=self._img_change, text="")
        else:
            self._img_label.configure(image="", text="🔑", font=("Segoe UI", 32))
        self._title_label.configure(text="Reset Password")
        self._sub_label.configure(text="Choose a strong new password")

    def _verify(self):
        """Validates input fields to confirm user identity for password resetting."""
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

        # Ensure that ALL inputs match database strictly for security purposes
        if (customer and str(customer.get("aadhaar", "")).strip() == aadhaar 
            and str(customer.get("mobile",  "")).strip() == mobile):
            self._verified_account = acc
            # Unpack step 1, pack step 2
            self._step1_frame.pack_forget()
            self._show_step2()
            self._step2_frame.pack(fill="x")
            self.update_idletasks()
            center_window(self, self.master)
        else:
            messagebox.showerror("Verification Failed", "Details do not match our records.\nPlease check and try again.", parent=self)

    def _change_password(self):
        """Validates new password conditions and queries DB to finalize password update."""
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
            messagebox.showinfo("Success", "Password changed successfully!\nYou can now log in with your new password.", parent=self)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update password: {e}", parent=self)


class AdminDashboardFrame(ttk.Frame):
    """
    Main Administrator Interface View.
    Allows managing active users, checking pending approvals, performing direct
    deposits/withdrawals, Downloading statements, and searching accounts.
    Uses ttk.Notebook (tabs) to separate approved Customers from Pending Accounts.
    """
    def __init__(self, parent, controller: BankApp):
        super().__init__(parent)
        self.controller = controller
        self.photo_cache = None  # Cache to prevent Tk from garbage collecting image bytes
        self.sig_cache = None
        self.search_var = tk.StringVar()

        # -------- Header (centered title + logout) --------
        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", pady=(0, 5))
        header_frame.columnconfigure(0, weight=1)

        title = ttk.Label(header_frame, text="Admin Dashboard", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, pady=10, sticky="n")

        # -------- Search box --------
        search_frame = ttk.Frame(self)
        search_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(search_frame, text="Search (Name / Acc / Aadhaar):", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=5, pady=(2, 0))
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=32)
        search_entry.grid(row=1, column=0, padx=5, pady=2, sticky="w")

        btn_search = ttk.Button(search_frame, text="Search", command=self.search_customers)
        btn_search.grid(row=1, column=1, padx=3, pady=2, sticky="w")
        _set_btn_image(btn_search, "Search")

        btn_clear = ttk.Button(search_frame, text="Clear", command=self.clear_search)
        btn_clear.grid(row=1, column=2, padx=3, pady=2, sticky="w")
        _set_btn_image(btn_clear, "Clear")

        # -------- Main body layout: left tables (notebook), right preview pane --------
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=5)

        table_frame = ttk.Frame(body)
        table_frame.pack(side="left", fill="both", expand=True)

        self.notebook = ttk.Notebook(table_frame)
        self.notebook.pack(fill="both", expand=True)
        # Bind an event so actions like approve/reject only light up when the Pending tab is active
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # Tab 1: Active Customers list
        cust_tab = ttk.Frame(self.notebook)
        self.notebook.add(cust_tab, text="Customers")

        cols_cust = ("id", "photo", "name", "father", "mother", "aadhaar", "account_no", "branch", "balance", "photo_path", "sig_path")
        self.tree = ttk.Treeview(cust_tab, columns=cols_cust, show="headings", selectmode="browse")

        # Configure visible table headings
        self.tree.heading("id", text="ID")
        self.tree.heading("photo", text="Photo")
        self.tree.heading("name", text="Name")
        self.tree.heading("father", text="Father")
        self.tree.heading("mother", text="Mother")
        self.tree.heading("aadhaar", text="Aadhaar")
        self.tree.heading("account_no", text="Account No")
        self.tree.heading("branch", text="Branch")
        self.tree.heading("balance", text="Balance")

        # Configure visible column widths
        self.tree.column("id", width=40, anchor="center")
        self.tree.column("photo", width=60, anchor="center")
        self.tree.column("name", width=140)
        self.tree.column("father", width=120)
        self.tree.column("mother", width=120)
        self.tree.column("aadhaar", width=110, anchor="center")
        self.tree.column("account_no", width=110, anchor="center")
        self.tree.column("branch", width=130)
        self.tree.column("balance", width=90, anchor="e")

        # Hide sensitive file-path columns (used internally for loading preview images)
        self.tree.heading("photo_path", text="Photo Path")
        self.tree.heading("sig_path", text="Signature Path")
        self.tree.column("photo_path", width=0, stretch=False)
        self.tree.column("sig_path", width=0, stretch=False)

        self.tree.pack(fill="both", expand=True, side="left")
        self.tree.tag_configure('low', foreground='red')
        self.tree.tag_configure('high', foreground='green')

        scrollbar_cust = ttk.Scrollbar(cust_tab, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar_cust.set)
        scrollbar_cust.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_row_select) # Hook row selection to image preview update

        # Tab 2: Pending Approvals list
        pending_tab = ttk.Frame(self.notebook)
        self.notebook.add(pending_tab, text="Pending Approvals")

        cols_pending = ("id", "photo", "name", "father", "mother", "aadhaar", "account_no", "branch", "opening_balance", "requested_at")
        self.pending_tree = ttk.Treeview(pending_tab, columns=cols_pending, show="headings", selectmode="browse")

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
        scrollbar_p = ttk.Scrollbar(pending_tab, orient="vertical", command=self.pending_tree.yview)
        self.pending_tree.configure(yscroll=scrollbar_p.set)
        scrollbar_p.pack(side="right", fill="y")
        self.pending_tree.bind("<<TreeviewSelect>>", self.on_pending_select)

        # Right sidebar pane - Image Previews
        right = ttk.Frame(body, width=340)
        right.pack(side="left", fill="y", padx=10)
        right.pack_propagate(False) 

        ttk.Label(right, text="Photo & Signature Preview:", font=("Segoe UI", 10, "bold")).pack(pady=(10, 5))

        preview_frame = ttk.Frame(right)
        preview_frame.pack(pady=5)

        # tk.Label is necessary over ttk.Label here to properly handle embedded image data natively
        self.photo_label = tk.Label(preview_frame, text="No photo", anchor="center", width=150, height=150, relief="flat", bg="#111827", fg="#9ca3af", font=("Segoe UI", 9))
        self.photo_label.grid(row=0, column=0, padx=5, pady=2)

        self.sig_label = tk.Label(preview_frame, text="No signature", anchor="center", width=150, height=80, relief="flat", bg="#111827", fg="#9ca3af", font=("Segoe UI", 9))
        self.sig_label.grid(row=1, column=0, padx=5, pady=2)

        self.btn_full_detail = ttk.Button(right, text="🔍  See Full Detail", command=self.show_full_detail)
        self.btn_full_detail.pack(pady=(8, 4), ipadx=6, ipady=4, fill="x", padx=10)

        # -------- Bottom Buttons Action Bar --------
        btn_bar = ttk.Frame(self)
        btn_bar.pack(fill="x", pady=5)

        self.btn_add = ttk.Button(btn_bar, text="Open New Account", command=self.open_new_account_window)
        self.btn_add.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_add, "Open_New_Account")

        self.btn_refresh = ttk.Button(btn_bar, text="Refresh All", command=self.refresh_all)
        self.btn_refresh.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_refresh, "Refresh_All")

        self.btn_delete = ttk.Button(btn_bar, text="Close Account", command=self.delete_selected)
        self.btn_delete.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_delete, "Delete")

        self.btn_statement = ttk.Button(btn_bar, text="Account Statement", command=self.open_account_statement)
        self.btn_statement.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_statement, "Account_Statement")

        self.btn_dep = ttk.Button(btn_bar, text="Deposit", command=self.admin_deposit)
        self.btn_dep.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_dep, "Deposit")

        self.btn_wd = ttk.Button(btn_bar, text="Withdraw", command=self.admin_withdraw)
        self.btn_wd.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_wd, "Withdrawl")

        # Approval/Rejection tools - Note: Only enabled natively via `on_tab_changed`
        self.btn_approve = ttk.Button(btn_bar, text="Approve Selected Pending", command=self.approve_selected_pending, style="Green.TButton")
        self.btn_approve.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_approve, "Approve_Request")

        self.btn_reject = ttk.Button(btn_bar, text="Reject Selected Pending", command=self.reject_selected_pending, style="Red.TButton")
        self.btn_reject.pack(side="left", padx=3, ipadx=5, ipady=2)
        _set_btn_image(self.btn_reject, "Reject_Request")

        self.btn_approve.state(["disabled"])
        self.btn_reject.state(["disabled"])

    def update_preview_theme(self, theme):
        """Manually forces theme colors onto standard tk.Labels used for images."""
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
        """Clears and re-fetches the 'Customers' table data from the database."""
        for row in self.tree.get_children():
            self.tree.delete(row)
        try:
            if rows is None:
                rows = get_all_customers()
            for r in rows:
                photo_flag = "Yes" if r["photo_path"] else "No"
                bal = float(r["balance"])
                tag = "low" if bal < 1000 else "high" # Highlight balances under ₹1000
                self.tree.insert(
                    "", "end",
                    values=(
                        r["id"], photo_flag, r["name"], r["father_name"] or "",
                        r["mother_name"] or "", r["aadhaar"] or "", r["account_no"],
                        r["branch"] or "", f"{bal:.2f}", r.get("photo_path") or "",
                        r.get("signature_path") or "",
                    ),
                    tags=(tag,),
                )
        except Exception as e:
            messagebox.showerror("Error", f"Unable to load customers: {e}")

    def refresh_pending(self):
        """Clears and re-fetches the 'Pending Approvals' table data from the database."""
        for row in self.pending_tree.get_children():
            self.pending_tree.delete(row)
        try:
            rows = get_all_pending_accounts()
            for r in rows:
                photo_flag = "Yes" if r["photo_path"] else "No"
                req_time = r["requested_at"].strftime("%Y-%m-%d %H:%M:%S") if r["requested_at"] else ""
                self.pending_tree.insert(
                    "", "end",
                    values=(
                        r["id"], photo_flag, r["name"], r["father_name"] or "",
                        r["mother_name"] or "", r["aadhaar"] or "", r["account_no"],
                        r["branch"] or "", f"{float(r['opening_balance']):.2f}", req_time
                    )
                )
        except Exception as e:
            messagebox.showerror("Error", f"Unable to load pending accounts: {e}")

    def refresh_all(self):
        """Wrapper method to reset/refresh all tables and clear the image preview sidebar."""
        self.refresh_customers()
        self.refresh_pending()
        self._update_previews(None, None)

    # ---------- Actions ----------
    def open_new_account_window(self):
        """Spawns the New Account modal directly from the Admin Dash."""
        NewAccountWindow(self)

    def get_selected_customer_id(self):
        """Helper to safely fetch the database `id` column of the currently clicked tree item."""
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.item(sel[0])["values"][0]

    def get_selected_customer_account(self):
        """Helper to safely fetch the database `account_no` column of the currently clicked tree item."""
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.item(sel[0])["values"][6]

    def delete_selected(self):
        """Handles the process of permanently deleting a customer from the system. Requires re-authenticating as admin to execute."""
        cust_id = self.get_selected_customer_id()
        if not cust_id:
            messagebox.showinfo("Close Account", "Please select a customer")
            return

        if not messagebox.askyesno("Confirm Close Account", "Are you sure you want to close this customer's Account ?"):
            return

        # Verification popup layer for high-risk actions
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
        ttk.Entry(win, textvariable=user_var, style="PopupLight.TEntry").pack(pady=5)

        _make_light_label(win, text="Enter Admin Password:").pack(pady=5)
        pass_var = tk.StringVar()
        ttk.Entry(win, textvariable=pass_var, show="*", style="PopupLight.TEntry").pack(pady=5)

        def verify_and_delete():
            username = user_var.get().strip()
            password = pass_var.get().strip()

            if not self.controller.admin_auth(username, password):
                messagebox.showerror("Access Denied", "Incorrect admin login")
                return

            try:
                delete_customer(cust_id)
                self.refresh_customers()
                self._update_previews(None, None)
                messagebox.showinfo("Success", "Customer's account close successfully")
                win.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Unable to Close Account: {e}")

        btn_frame = _make_light_frame(win)
        btn_frame.pack(pady=10)
        verify_del_btn = ttk.Button(btn_frame, text="Verify & Close", command=verify_and_delete, style="PopupLight.TButton")
        verify_del_btn.grid(row=0, column=0, padx=5)
        _set_btn_image(verify_del_btn, "Delete")
        
        cancel_del_btn = ttk.Button(btn_frame, text="Cancel", command=win.destroy, style="PopupLight.TButton")
        cancel_del_btn.grid(row=0, column=1, padx=5)
        _set_btn_image(cancel_del_btn, "Cancel")

    def _update_previews(self, photo_path, sig_path):
        """Internal helper to load, resize, and display images in the right-sidebar based on file paths."""
        # Process Photo
        if not photo_path or not os.path.exists(str(photo_path)):
            self.photo_label.configure(text="No photo", image="", width=150, height=150)
            self.photo_cache = None
        elif not PIL_AVAILABLE:
            self.photo_label.configure(text="Pillow not installed\nCannot show photo", image="", width=150, height=150)
            self.photo_cache = None
        else:
            try:
                img = Image.open(photo_path).convert("RGBA").resize((150, 150), Image.LANCZOS)
                img_tk = ImageTk.PhotoImage(img)
                self.photo_cache = img_tk
                self.photo_label.configure(image=img_tk, text="", width=150, height=150)
            except Exception as e:
                self.photo_label.configure(text=f"Error loading photo\n{e}", image="", width=150, height=150)
                self.photo_cache = None

        # Process Signature
        if not sig_path or not os.path.exists(str(sig_path)):
            self.sig_label.configure(text="No signature", image="", width=150, height=80)
            self.sig_cache = None
        elif not PIL_AVAILABLE:
            self.sig_label.configure(text="Pillow not installed\nCannot show signature", image="", width=150, height=80)
            self.sig_cache = None
        else:
            try:
                img = Image.open(sig_path).convert("RGBA").resize((150, 80), Image.LANCZOS)
                img_tk2 = ImageTk.PhotoImage(img)
                self.sig_cache = img_tk2
                self.sig_label.configure(image=img_tk2, text="", width=150, height=80)
            except Exception as e:
                self.sig_label.configure(text=f"Error loading signature\n{e}", image="", width=150, height=80)
                self.sig_cache = None

    def on_row_select(self, event):
        """Treeview event handler: Triggered when a row in the 'Customers' table is selected to display images."""
        sel = self.tree.selection()
        if not sel:
            self._update_previews(None, None)
            return

        item = self.tree.item(sel[0])
        values = item.get("values", [])
        # Extract hidden paths located at indices 9 and 10 of tree.insert call
        photo_path = values[9] if len(values) > 9 else None
        sig_path = values[10] if len(values) > 10 else None
        self._update_previews(photo_path, sig_path)

    def on_pending_select(self, event):
        """Treeview event handler: Triggered when a row in the 'Pending Approvals' table is selected to display images."""
        sel = self.pending_tree.selection()
        if not sel:
            return
        item = self.pending_tree.item(sel[0])
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
        Dynamically generates a popup containing the fully detailed profile card of the selected user.
        Determines which database to fetch from based on the currently active Notebook tab.
        """
        try:
            current = self.notebook.select()
            tab_index = self.notebook.index(current)
        except Exception:
            tab_index = 0

        row_data = None

        if tab_index == 0:
            # Sourcing from Customers Tab
            sel = self.tree.selection()
            if not sel:
                messagebox.showinfo("No Selection", "Please select a customer first.")
                return
            item = self.tree.item(sel[0])
            account_no = item.get("values", [])[6] if len(item.get("values", [])) > 6 else None
            if not account_no:
                return
            try:
                row_data = get_customer_by_account(str(account_no))
            except Exception as e:
                messagebox.showerror("Error", f"Could not load customer details:\n{e}")
                return
            source = "customer"
        else:
            # Sourcing from Pending Approvals Tab
            sel = self.pending_tree.selection()
            if not sel:
                messagebox.showinfo("No Selection", "Please select a pending account first.")
                return
            item = self.pending_tree.item(sel[0])
            account_no = item.get("values", [])[6] if len(item.get("values", [])) > 6 else None
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

        # Instantiate Detailed UI Popup (Scrollable UI handling)
        popup = tk.Toplevel(self)
        popup.title("Full Customer Details")
        popup.geometry("520x640")
        popup.resizable(False, False)
        _set_icon(popup)
        _force_light_popup(popup)
        popup.grab_set()
        center_window(popup, self.winfo_toplevel())

        hdr = tk.Frame(popup, bg="#1e3a5f", height=50)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Customer Full Details", bg="#1e3a5f", fg="white", font=("Segoe UI", 13, "bold")).pack(pady=12)

        # Allow scrolling since details might overflow height
        canvas_w = tk.Canvas(popup, bg=_POPUP_BG, highlightthickness=0)
        scrollbar_w = ttk.Scrollbar(popup, orient="vertical", command=canvas_w.yview)
        canvas_w.configure(yscrollcommand=scrollbar_w.set)
        scrollbar_w.pack(side="right", fill="y")
        canvas_w.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas_w, bg=_POPUP_BG)
        inner_win = canvas_w.create_window((0, 0), window=inner, anchor="nw")

        def on_frame_configure(e): canvas_w.configure(scrollregion=canvas_w.bbox("all"))
        def on_canvas_configure(e): canvas_w.itemconfig(inner_win, width=e.width)

        inner.bind("<Configure>", on_frame_configure)
        canvas_w.bind("<Configure>", on_canvas_configure)

        def _on_mousewheel(e):
            canvas_w.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas_w.bind_all("<MouseWheel>", _on_mousewheel)
        popup.bind("<Destroy>", lambda e: canvas_w.unbind_all("<MouseWheel>"))

        # Render User Images directly in the Detail Panel
        photo_path = row_data.get("photo_path")
        if PIL_AVAILABLE and photo_path and os.path.exists(str(photo_path)):
            try:
                img = Image.open(photo_path).convert("RGBA").resize((120, 120), Image.LANCZOS)
                img_tk = ImageTk.PhotoImage(img)
                photo_lbl = tk.Label(inner, image=img_tk, bg=_POPUP_BG)
                photo_lbl.image = img_tk
                photo_lbl.pack(pady=(15, 4))
            except Exception:
                tk.Label(inner, text="[Photo unavailable]", bg=_POPUP_BG, fg="#6b7280", font=("Segoe UI", 9)).pack(pady=(15, 4))
        else:
            tk.Label(inner, text="No Photo", bg="#e5e7eb", fg="#6b7280", font=("Segoe UI", 9), width=18, height=6).pack(pady=(15, 4))

        sig_path = row_data.get("signature_path")
        sig_lbl_txt = tk.Label(inner, text="Signature:", bg=_POPUP_BG, fg="#374151", font=("Segoe UI", 9, "bold"))
        sig_lbl_txt.pack(anchor="w", padx=20)
        if PIL_AVAILABLE and sig_path and os.path.exists(str(sig_path)):
            try:
                sig_img = Image.open(sig_path).convert("RGBA").resize((200, 70), Image.LANCZOS)
                sig_tk = ImageTk.PhotoImage(sig_img)
                sig_lbl = tk.Label(inner, image=sig_tk, bg=_POPUP_BG)
                sig_lbl.image = sig_tk
                sig_lbl.pack(pady=(2, 10))
            except Exception:
                tk.Label(inner, text="[Signature unavailable]", bg=_POPUP_BG, fg="#6b7280", font=("Segoe UI", 9)).pack(pady=(2, 10))
        else:
            tk.Label(inner, text="No Signature", bg="#e5e7eb", fg="#6b7280", font=("Segoe UI", 9), width=28, height=3).pack(pady=(2, 10))

        ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=20, pady=4)

        # Helper rendering dynamic list rows 
        def add_field(label, value):
            row_f = tk.Frame(inner, bg=_POPUP_BG)
            row_f.pack(fill="x", padx=20, pady=3)
            tk.Label(row_f, text=f"{label}:", bg=_POPUP_BG, fg="#374151", font=("Segoe UI", 9, "bold"), width=18, anchor="w").pack(side="left")
            tk.Label(row_f, text=str(value) if value else "—", bg=_POPUP_BG, fg=_POPUP_FG, font=("Segoe UI", 9), anchor="w", wraplength=280, justify="left").pack(side="left", fill="x", expand=True)

        add_field("Account No", row_data.get("account_no"))
        add_field("Full Name", row_data.get("name"))
        add_field("Father's Name", row_data.get("father_name"))
        add_field("Mother's Name", row_data.get("mother_name"))
        add_field("Aadhaar No", row_data.get("aadhaar"))
        add_field("Mobile", row_data.get("mobile"))
        add_field("Address", row_data.get("address"))
        add_field("IFSC Code", row_data.get("ifsc"))
        add_field("Branch", row_data.get("branch"))

        # Conditionally format fields related to Approval Status
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
        tk.Label(status_row, text="Status:", bg=_POPUP_BG, fg="#374151", font=("Segoe UI", 9, "bold"), width=18, anchor="w").pack(side="left")
        tk.Label(status_row, text=status_text, bg=_POPUP_BG, fg=status_color, font=("Segoe UI", 9, "bold"), anchor="w").pack(side="left")

        ttk.Separator(inner, orient="horizontal").pack(fill="x", padx=20, pady=8)
        ttk.Button(inner, text="Close", command=popup.destroy, style="PopupLight.TButton").pack(pady=(0, 15), ipadx=20, ipady=4)

    # ---------- Search ----------
    def search_customers(self):
        """Fires the DB keyword search logic to filter the customers table dynamically."""
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
        """Clears the search input field and reloads the full customer set."""
        self.search_var.set("")
        self.refresh_customers()

    def on_tab_changed(self, event):
        """
        Notebook event handler. Ensures buttons related to 'Pending' accounts 
        (e.g., Approve / Reject) are disabled when looking at standard Customers to prevent logical errors.
        """
        try:
            current = self.notebook.select()
            index = self.notebook.index(current)
        except Exception:
            return

        needed = ("btn_add", "btn_refresh", "btn_delete", "btn_statement", "btn_dep", "btn_wd", "btn_approve", "btn_reject")
        if not all(hasattr(self, name) for name in needed):
            return

        main_buttons = (self.btn_add, self.btn_refresh, self.btn_delete, self.btn_statement, self.btn_dep, self.btn_wd)

        if index == 1:  # Navigated to Pending Approvals tab
            for b in main_buttons:
                b.state(["disabled"])
            self.btn_approve.state(["!disabled"])
            self.btn_reject.state(["!disabled"])
            self._update_previews(None, None) 
        else:  # Navigated to Customers tab
            for b in main_buttons:
                b.state(["!disabled"])
            self.btn_approve.state(["disabled"])
            self.btn_reject.state(["disabled"])

    # ---------- Pending approvals ----------
    def get_selected_pending_id(self):
        """Safely extract the selected ID from the 'Pending Approvals' view."""
        sel = self.pending_tree.selection()
        if not sel:
            return None
        return self.pending_tree.item(sel[0])["values"][0]

    def approve_selected_pending(self):
        """Fires the database migration to convert a Pending user to an Approved user."""
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
        """Fires the database deletion script to reject a user application permanently."""
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
        """Proxy to spawn a deposit dialog for a user account."""
        self._admin_txn_dialog("DEPOSIT")

    def admin_withdraw(self):
        """Proxy to spawn a withdrawal dialog for a user account."""
        self._admin_txn_dialog("WITHDRAW")

    def _admin_txn_dialog(self, txn_type):
        """
        Generates an input modal allowing Admins to execute money movement (Deposit/Withdrawal).
        Executes against the currently selected user in the tree.
        """
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
            """Input validation and database callback for processing."""
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
                messagebox.showinfo("Success", f"{txn_type.title()} successful.\nNew Balance: {new_balance:.2f}")
                self.refresh_customers()
                win.destroy()
            except ValueError as ve:
                messagebox.showerror("Error", str(ve))
            except Exception as e:
                messagebox.showerror("Error", f"Transaction failed: {e}")

        btn_frame = _make_light_frame(win)
        btn_frame.pack(pady=15)

        submit_txn_btn = ttk.Button(btn_frame, text="Submit", command=do_txn, style="PopupLight.TButton")
        submit_txn_btn.grid(row=0, column=0, padx=10)
        _set_btn_image(submit_txn_btn, "Submit_Request")
        
        cancel_txn_btn = ttk.Button(btn_frame, text="Cancel", command=win.destroy, style="PopupLight.TButton")
        cancel_txn_btn.grid(row=0, column=1, padx=10)
        _set_btn_image(cancel_txn_btn, "Cancel")

    # ---------- Account Statement (Admin) ----------
    def open_account_statement(self):
        """
        Creates a dedicated popup showing a tabulated history of all user transactions.
        Also provides the function to Download that statement to a PDF locally.
        """
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

        _make_light_label(win, text=f"All Transactions - {account_no}", font=("Segoe UI", 11, "bold")).pack(pady=5)

        cols = ("type", "amount", "time")
        tree = ttk.Treeview(win, columns=cols, show="headings", style="PopupLight.Treeview")
        tree.heading("type", text="Type")
        tree.heading("amount", text="Amount")
        tree.heading("time", text="Time")

        tree.column("type", width=80, anchor="center")
        tree.column("amount", width=100, anchor="e")
        tree.column("time", width=220, anchor="center")

        tree.pack(fill="both", expand=True, padx=10, pady=10)

        tree.tag_configure("low", foreground="red")
        tree.tag_configure("high", foreground="green")

        for t in txns:
            amt = float(t["amount"])
            time_str = t["txn_time"].strftime("%Y-%m-%d %H:%M:%S")
            tag = "low" if amt < 1000 else "high"
            tree.insert("", "end", values=(t["txn_type"], f"{amt:.2f}", time_str), tags=(tag,))

        btn_frame = _make_light_frame(win)
        btn_frame.pack(pady=5)

        def download_pdf():
            """Relies on ReportLab logic delegated from the Customer Dashboard format to Download PDFs."""
            if not REPORTLAB_AVAILABLE:
                messagebox.showerror("PDF Error", "reportlab is not installed.\n\nInstall it using:\n\npip install reportlab")
                return

            if not txns:
                messagebox.showinfo("Download", "No transactions to Download")
                return

            default_name = f"statement_{account_no}.pdf"
            path = filedialog.asksaveasfilename(
                title="Save Statement PDF", defaultextension=".pdf",
                initialfile=default_name, filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")]
            )
            if not path:
                return

            try:
                # Reuse identical layout system from Customer implementation for uniformity
                cust_frame: CustomerDashboardFrame = self.controller.frames["CustomerDashboardFrame"]
                cust_frame._create_passbook_pdf(path, customer, txns)
                messagebox.showinfo("Download", f"Statement PDF Downloaded to:\n{path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to Download PDF: {e}")

        dl_pdf_btn = ttk.Button(btn_frame, text="Download Statement PDF", command=download_pdf, style="PopupLight.TButton")
        dl_pdf_btn.pack(side="left", padx=5)
        _set_btn_image(dl_pdf_btn, "Account_Statement")

        close_stmt_btn = ttk.Button(btn_frame, text="Close", command=win.destroy, style="PopupLight.TButton")
        close_stmt_btn.pack(side="left", padx=5)
        _set_btn_image(close_stmt_btn, "Cancel")


class NewAccountWindow(tk.Toplevel):
    """
    Dedicated Window handling the Open New Account form flow.
    Gathers complex KYC info (Aadhaar, Photos, Signatures, Initial Balance).
    Saves payload directly to `pending_accounts` where it waits for Admin approval.
    """
    def __init__(self, admin_frame: AdminDashboardFrame):
        super().__init__(admin_frame)
        self.admin_frame = admin_frame
        self.title("Open New Account — Pending Approval")
        self.geometry("580x660")
        self.minsize(540, 560)
        self.resizable(True, True)
        self.transient(admin_frame.controller)
        center_window(self, admin_frame.controller)
        self.grab_set()
        self.focus_set()
        _set_icon(self)
        _force_light_popup(self)

        self.photo_path = tk.StringVar()
        self.signature_path = tk.StringVar()

        # ── Header Construction ──────────────────────────────────────
        header = ttk.Frame(self, style="PopupLight.TFrame")
        header.pack(fill="x", padx=15, pady=(12, 0))

        self._logo_img = None 
        if PIL_AVAILABLE and os.path.exists(_ICON_PATH):
            try:
                raw = Image.open(_ICON_PATH).convert("RGBA").resize((48, 48), Image.LANCZOS)
                self._logo_img = ImageTk.PhotoImage(raw)
                logo_lbl = ttk.Label(header, image=self._logo_img, style="PopupLight.TLabel")
                logo_lbl.pack(side="left", padx=(0, 10))
            except Exception:
                pass

        title_frame = ttk.Frame(header, style="PopupLight.TFrame")
        title_frame.pack(side="left")
        ttk.Label(title_frame, text=BANK_NAME, font=("Segoe UI", 13, "bold"), style="PopupLight.TLabel").pack(anchor="w")
        ttk.Label(title_frame, text="New Account Registration", font=("Segoe UI", 9), style="PopupLight.TLabel").pack(anchor="w")

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=8)

        # ── Setup static bottom action buttons before constructing scrollable canvas ──
        ttk.Separator(self, orient="horizontal").pack(side="bottom", fill="x", padx=10, pady=(4, 0))
        btn_bar = ttk.Frame(self, style="PopupLight.TFrame")
        btn_bar.pack(side="bottom", fill="x", pady=10)

        save_btn = tk.Button(
            btn_bar, text="✔  Submit Request", command=self.save_account,
            bg="#16a34a", fg="white", activebackground="#15803d", activeforeground="white",
            relief="flat", bd=0, highlightthickness=0, font=("Segoe UI", 10, "bold"), cursor="hand2", padx=18, pady=7,
        )
        save_btn.pack(side="left", expand=True, fill="x", padx=(20, 8), pady=4)

        cancel_btn = tk.Button(
            btn_bar, text="✖  Cancel", command=self.destroy,
            bg="#dc2626", fg="white", activebackground="#b91c1c", activeforeground="white",
            relief="flat", bd=0, highlightthickness=0, font=("Segoe UI", 10, "bold"), cursor="hand2", padx=18, pady=7,
        )
        cancel_btn.pack(side="left", expand=True, fill="x", padx=(8, 20), pady=4)

        # ── Dynamic Scrollable Form View setup ─────────────────────────────────────────
        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0, bg=_POPUP_BG)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        form_container = ttk.Frame(canvas, style="PopupLight.TFrame")
        form_window = canvas.create_window((0, 0), window=form_container, anchor="nw")

        def _on_frame_configure(event): canvas.configure(scrollregion=canvas.bbox("all"))
        def _on_canvas_configure(event): canvas.itemconfig(form_window, width=event.width)

        form_container.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # ── Form Construction using ttk grids ────────────────────────────────────────────
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

        # Draw red asterisks adjacent to required fields
        _readonly_labels = {"Account No:", "IFSC Code:", "Branch:"}
        for i, (text, _) in enumerate(field_specs):
            lf = ttk.Frame(form, style="PopupLight.TFrame")
            lf.grid(row=i, column=0, sticky="e", pady=5, padx=(5, 8))
            ttk.Label(lf, text=text, font=("Segoe UI", 9), style="PopupLight.TLabel").pack(side="left")
            if text not in _readonly_labels:
                tk.Label(lf, text=" *", font=("Segoe UI", 9, "bold"), fg="#dc2626", bg=_POPUP_BG).pack(side="left")

        # Associate tracking Variables (some fields get generated or hardcoded default values)
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
            (self.pass_var,    "normal",   True),   # Hidden password input
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
            kw = {"textvariable": var, "state": state, "width": 30, "style": "PopupLight.TEntry"}
            if is_pass:
                kw["show"] = "*"
            e = ttk.Entry(form, **kw)
            e.grid(row=i, column=1, sticky="ew", pady=5, padx=(0, 10))
            self._entries.append(e)

        # ── Photo attachment inputs ──
        row_photo = len(field_specs)
        photo_lbl_frame = ttk.Frame(form, style="PopupLight.TFrame")
        photo_lbl_frame.grid(row=row_photo, column=0, sticky="e", pady=5, padx=(5, 8))
        ttk.Label(photo_lbl_frame, text="Photo:", font=("Segoe UI", 9), style="PopupLight.TLabel").pack(side="left")
        tk.Label(photo_lbl_frame, text=" *", font=("Segoe UI", 9, "bold"), fg="#dc2626", bg=_POPUP_BG).pack(side="left")
        photo_frame = ttk.Frame(form, style="PopupLight.TFrame")
        photo_frame.grid(row=row_photo, column=1, sticky="ew", pady=5, padx=(0, 10))
        photo_frame.columnconfigure(0, weight=1)

        self.photo_entry = ttk.Entry(photo_frame, textvariable=self.photo_path, state="readonly", style="PopupLight.TEntry")
        self.photo_entry.grid(row=0, column=0, sticky="ew")

        browse_photo_btn = ttk.Button(photo_frame, text="Browse…", command=self.browse_photo, style="PopupLight.TButton")
        browse_photo_btn.grid(row=0, column=1, padx=(5, 0))
        _set_btn_image(browse_photo_btn, "Browser")

        # ── Signature attachment inputs ──
        row_sig = row_photo + 1
        sig_lbl_frame = ttk.Frame(form, style="PopupLight.TFrame")
        sig_lbl_frame.grid(row=row_sig, column=0, sticky="e", pady=5, padx=(5, 8))
        ttk.Label(sig_lbl_frame, text="Signature:", font=("Segoe UI", 9), style="PopupLight.TLabel").pack(side="left")
        tk.Label(sig_lbl_frame, text=" *", font=("Segoe UI", 9, "bold"), fg="#dc2626", bg=_POPUP_BG).pack(side="left")
        sig_frame = ttk.Frame(form, style="PopupLight.TFrame")
        sig_frame.grid(row=row_sig, column=1, sticky="ew", pady=5, padx=(0, 10))
        sig_frame.columnconfigure(0, weight=1)

        self.sig_entry = ttk.Entry(sig_frame, textvariable=self.signature_path, state="readonly", style="PopupLight.TEntry")
        self.sig_entry.grid(row=0, column=0, sticky="ew")

        browse_sig_btn = ttk.Button(sig_frame, text="Browse…", command=self.browse_signature, style="PopupLight.TButton")
        browse_sig_btn.grid(row=0, column=1, padx=(5, 0))
        _set_btn_image(browse_sig_btn, "Browser")

        # Sub-note
        ttk.Label(
            form_container, text="* All fields are required. Account No, IFSC and Branch are auto-filled.",
            font=("Segoe UI", 8), foreground="#6b7280", style="PopupLight.TLabel"
        ).pack(anchor="w", padx=15, pady=(4, 8))

        self._entries[1].focus_set() # Focus Password Entry on load

    def browse_photo(self):
        """Spawns an OS file dialog for linking an image file to represent the applicant's photo."""
        path = filedialog.askopenfilename(
            title="Select Photo",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp *.gif"), ("All Files", "*.*")]
        )
        if path:
            self.photo_path.set(path)

    def browse_signature(self):
        """Spawns an OS file dialog for linking an image file to represent the applicant's signature."""
        path = filedialog.askopenfilename(
            title="Select Signature Image",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.bmp *.gif"), ("All Files", "*.*")]
        )
        if path:
            self.signature_path.set(path)

    def save_account(self):
        """
        Gathers fields from the GUI and runs extensive validation checks before constructing a payload dict.
        Ultimately proxies saving the user details to the Pending Accounts database layout.
        """
        account_no      = self.acc_var.get().strip()
        password        = self.pass_var.get().strip()
        name            = self.name_var.get().strip()
        father_name     = self.father_var.get().strip()
        mother_name     = self.mother_var.get().strip()
        aadhaar         = self.aadhaar_var.get().strip()
        address         = self.address_var.get().strip()
        mobile          = self.mobile_var.get().strip()
        opening_balance = self.balance_var.get().strip()

        # Input Integrity - Ensure every field has a value
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
            messagebox.showwarning("Validation", "The following required fields are missing:\n\n• " + "\n• ".join(missing))
            return

        # Pattern validations
        if len(password) < 6:
            messagebox.showwarning("Validation", "Password must be at least 6 characters.")
            return

        if not aadhaar.isdigit() or len(aadhaar) != 12:
            messagebox.showwarning("Validation", "Aadhaar must be exactly 12 digits.")
            return

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

        # Prepare formatted dictionary data payload
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
            self.destroy() # Self close modal on success
        except mysql.connector.IntegrityError:
            messagebox.showerror("Error", "Account number already exists in pending/customers")
        except Exception as e:
            messagebox.showerror("Error", f"Unable to create account request: {e}")

class CustomerDashboardFrame(ttk.Frame):
    """
    Main portal presented when a bank customer logs into the system.
    Displays user metadata, recent transaction logs, supports real-time Deposits
    and handles Downloading account PDF summaries.
    """
    def __init__(self, parent, controller: BankApp):
        super().__init__(parent)
        self.controller = controller
        self.photo_cache = None

        header = ttk.Frame(self)
        header.pack(fill="x")
        self.title_label = ttk.Label(header, text="Customer Dashboard", font=("Segoe UI", 16, "bold"))
        self.title_label.pack(side="left", pady=10)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=10)

        # Split UI Strategy -> Left (Stats/Buttons) | Right (Images/Transactions)
        left = ttk.Frame(body)
        left.pack(side="left", fill="y", padx=10)

        ttk.Label(left, text="Account Details", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 5))

        # Dynamic theming handler initial configuration
        _init_bg = "#020617" if controller.current_theme == "dark" else "#ffffff"
        _init_fg = "#e5e7eb" if controller.current_theme == "dark" else "#111827"
        self.details_text = tk.Text(
            left, width=50, height=12, state="disabled",
            bg=_init_bg, fg=_init_fg, relief="flat", bd=1
        )
        self.details_text.pack(pady=5)

        ttk.Label(left, text="Quick Actions", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(10, 5))

        btn_dep = ttk.Button(left, text="Deposit", command=self.deposit_dialog)
        btn_dep.pack(fill="x", pady=3)
        _set_btn_image(btn_dep, "Deposit")

        btn_refresh = ttk.Button(left, text="Refresh Balance", command=self.refresh_details)
        btn_refresh.pack(fill="x", pady=3)
        _set_btn_image(btn_refresh, "Refresh_All")

        btn_Download_pdf = ttk.Button(left, text="Download Passbook (PDF)", command=self.Download_passbook_pdf)
        btn_Download_pdf.pack(fill="x", pady=3)
        _set_btn_image(btn_Download_pdf, "Account_Statement")

        # Right View Block Construction
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=10)

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

        self.txn_tree.tag_configure("low", foreground="red")
        self.txn_tree.tag_configure("high", foreground="green")
        self.txn_tree.pack(fill="both", expand=True)

    def load_user(self):
        """Called natively by login. Formats heading text and executes data load routines."""
        user = self.controller.current_user
        if not user:
            return
        self.title_label.configure(text=f"Customer Dashboard - {user['name']}")
        self.refresh_details()

    def refresh_details(self):
        """
        Re-polls the MySQL Database for the logged in user's profile details & limits
        recent transactions to top 25 results. Binds fetched content back to the UI interface.
        """
        user = self.controller.current_user
        if not user:
            return

        # Fetch fresh copy of account data
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

        # Colorizes the raw text inside of the 'details_text' widget dynamically based on balance limits
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

        # Repopulate the history tree using maximum of 25 nodes
        for row in self.txn_tree.get_children():
            self.txn_tree.delete(row)

        txns = get_last_transactions(user["account_no"], limit=25)
        for t in txns:
            time_str = t["txn_time"].strftime("%Y-%m-%d %H:%M:%S")
            amt = float(t["amount"])
            tag = "low" if amt < 1000 else "high"
            self.txn_tree.insert("", "end", values=(t["txn_type"], f"{amt:.2f}", time_str), tags=(tag,))

        # Sync profile avatar locally to UI
        path = user.get("photo_path")
        if not path or not os.path.exists(path):
            self.photo_label.configure(text="No photo", image="")
            self.photo_cache = None
        elif not PIL_AVAILABLE:
            self.photo_label.configure(text="Pillow not installed\nCannot show photo", image="")
            self.photo_cache = None
        else:
            try:
                img = Image.open(path).resize((140, 140), Image.LANCZOS)
                img_tk = ImageTk.PhotoImage(img)
                self.photo_cache = img_tk
                self.photo_label.configure(image=img_tk, text="")
            except Exception as e:
                self.photo_label.configure(text=f"Error loading photo\n{e}", image="")
                self.photo_cache = None

    def update_theme(self, theme: str):
        """Forces plain tk.Text styling updates based on active system theming."""
        if theme == "dark":
            bg, fg, ins = "#020617", "#e5e7eb", "#e5e7eb"
        else:
            bg, fg, ins = "#ffffff", "#111827", "#111827"
        self.details_text.configure(bg=bg, fg=fg, insertbackground=ins)

    def logout(self):
        """Cleans internal memory context holding user data and routes app back to the Landing Frame."""
        self.controller.set_current_user(None)
        self.controller.show_frame("LandingFrame")

    def deposit_dialog(self):
        """Exposes user deposit feature proxy logic."""
        self._txn_dialog("DEPOSIT")

    def _txn_dialog(self, txn_type):
        """
        Creates popup windows allowing customers to execute direct transactions on their own accounts.
        Automatically updates UI metrics following completion.
        """
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
                if amt <= 0: raise ValueError
            except ValueError:
                messagebox.showwarning("Validation", "Enter a valid positive amount")
                return

            try:
                new_balance = update_balance_and_add_txn(user["account_no"], amt, txn_type)
                messagebox.showinfo("Success", f"{txn_type.title()} successful.\nNew Balance: {new_balance:.2f}")
                self.refresh_details()
                win.destroy()
            except ValueError as ve:
                messagebox.showerror("Error", str(ve))
            except Exception as e:
                messagebox.showerror("Error", f"Transaction failed: {e}")

        btn_frame = _make_light_frame(win)
        btn_frame.pack(pady=15)

        cust_submit_btn = ttk.Button(btn_frame, text="Submit", command=do_txn, style="PopupLight.TButton")
        cust_submit_btn.grid(row=0, column=0, padx=10)
        _set_btn_image(cust_submit_btn, "Submit_Request")
        
        cust_cancel_btn = ttk.Button(btn_frame, text="Cancel", command=win.destroy, style="PopupLight.TButton")
        cust_cancel_btn.grid(row=0, column=1, padx=10)
        _set_btn_image(cust_cancel_btn, "Cancel")

    # --------- PDF Download ---------
    def Download_passbook_pdf(self):
        """
        Gathers system constraints, executes all historic transaction pulling logic, handles UI File saving dialogs
        and ultimately fires off formatting parameters to generating PDF binaries directly to the file system.
        """
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("PDF Error", "reportlab is not installed.\n\nInstall it using:\n\npip install reportlab")
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
            messagebox.showinfo("Download", "No transactions to Download")
            return

        default_name = f"passbook_{user['account_no']}.pdf"
        path = filedialog.asksaveasfilename(
            title="Save Passbook PDF", defaultextension=".pdf",
            initialfile=default_name, filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")]
        )
        if not path:
            return

        try:
            self._create_passbook_pdf(path, user, txns)
            messagebox.showinfo("Download", f"Passbook PDF Download to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to Download PDF: {e}")

    def _create_passbook_pdf(self, filepath, user, txns):
        """
        Uses the third-party `reportlab` library to natively trace and map a custom PDF visual format.
        Iterates dynamic tables breaking into new pages when visual padding constraints break maximum y_height constraints.
        Draws QR codes and handles dynamically formatting and placing user imagery inline into standard A4 documents.
        """
        c = canvas.Canvas(filepath, pagesize=A4)
        width, height = A4
        margin = 25 * mm

        photo_path = user.get("photo_path")
        photo_available = bool(photo_path and os.path.exists(photo_path))

        def draw_header():
            """Sub-routine: Renders Bank Information, Requesting Timestamp, and QR code to current page header context."""
            c.setFont("Helvetica-Bold", 18)
            c.setFillColor(colors.HexColor("#111827"))
            c.drawCentredString(width / 2, height - margin, BANK_NAME)

            c.setFont("Helvetica", 11)
            c.setFillColor(colors.HexColor("#4b5563"))
            c.drawCentredString(width / 2, height - margin - 15, "Account Statement (Passbook)")

            c.setFont("Helvetica", 9)
            c.setFillColor(colors.black)
            c.drawRightString(width - margin, height - margin - 32, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            try:
                qr_code = qr.QrCodeWidget(user["account_no"])
                bounds = qr_code.getBounds()
                size = 50 
                w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
                d = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
                d.add(qr_code)
                renderPDF.draw(d, c, width - margin - size, height - margin - 60)
            except Exception:
                pass

        def draw_customer_info(start_y):
            """Sub-routine: Iterates data payload dict mapping textual lines vertically along side an embedded photo representation."""
            c.setFont("Helvetica-Bold", 11)
            c.setFillColor(colors.black)
            c.drawString(margin, start_y, "Customer Details")
            y = start_y - 4

            text_x = margin
            img_height = 40
            if photo_available:
                try:
                    img = ImageReader(photo_path)
                    c.drawImage(img, margin, y - img_height, width=40, height=40, preserveAspectRatio=True, mask='auto')
                    text_x = margin + 50
                except Exception:
                    text_x = margin

            c.setFont("Helvetica", 9)
            line_gap = 12
            y -= 6

            info_lines = [
                f"Name: {user['name']}", f"Account No: {user['account_no']}",
                f"IFSC: {user.get('ifsc') or ''}", f"Branch: {user.get('branch') or ''}",
                f"Mobile: {user.get('mobile') or ''}", f"Address: {user.get('address') or ''}",
                f"Aadhaar: {user.get('aadhaar') or ''}", f"Opened On: {user.get('created_at')}",
            ]
            for line in info_lines:
                c.drawString(text_x, y, line)
                y -= line_gap

            c.setStrokeColor(colors.HexColor("#e5e7eb"))
            c.line(margin, y + 5, width - margin, y + 5)
            return y - 10 

        def draw_table_header(y):
            """Sub-routine: Initializes Transaction Table columns tracking X values for proper spacing."""
            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(colors.black)

            col_x = [margin, margin + 130, margin + 210]
            headers = ["Date & Time", "Type", "Amount (₹)"]
            for x, h_name in zip(col_x, headers):
                c.drawString(x, y, h_name)

            c.setStrokeColor(colors.HexColor("#9ca3af"))
            c.line(margin, y - 2, width - margin, y - 2)
            return y - 14

        def draw_transactions(start_y):
            """
            Sub-routine: Core loop iterating transaction objects and writing textual rows onto a PDF canvas line by line.
            Determines when available rendering estate (height) is fully exhausted triggering canvas pagination `c.showPage()`
            """
            c.setFont("Helvetica", 9)
            line_height = 12
            y = start_y
            col_x = [margin, margin + 130, margin + 210]

            total_deposit, total_withdraw = 0.0, 0.0

            for t in txns:
                if y < margin + 80:
                    c.showPage()
                    draw_header()
                    y = draw_customer_info(height - margin - 110)
                    y = draw_table_header(y)

                dt_str = t["txn_time"].strftime("%Y-%m-%d %H:%M:%S")
                amt = float(t["amount"])
                row_color = colors.HexColor("#15803d") if t["txn_type"] == "DEPOSIT" else colors.HexColor("#b91c1c")

                c.setFillColor(colors.black)
                c.drawString(col_x[0], y, dt_str)
                c.setFillColor(row_color)
                c.drawString(col_x[1], y, t["txn_type"])
                c.drawRightString(width - margin, y, f"{amt:,.2f}")

                if t["txn_type"] == "DEPOSIT":
                    total_deposit += amt
                else:
                    total_withdraw += amt

                c.setFillColor(colors.black) 
                y -= line_height

            return y, total_deposit, total_withdraw

        def draw_summary(y, total_deposit, total_withdraw):
            """Sub-routine: Summarizes totals and establishes footer branding details."""
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

            c.setFillColor(colors.HexColor("#16a34a")) 
            c.drawString(margin, y, f"Total Deposited: ₹ {total_deposit:,.2f}")
            y -= 14
            c.setFillColor(colors.HexColor("#dc2626")) 
            c.drawString(margin, y, f"Total Withdrawn: ₹ {total_withdraw:,.2f}")
            y -= 14
            c.setFillColor(colors.black)
            c.drawString(margin, y, f"Final Balance: ₹ {current_balance:,.2f}")
            y -= 20

            c.setFillColor(colors.HexColor("#6b7280"))
            c.setFont("Helvetica-Oblique", 8)
            c.drawString(margin, y, "This is a system-generated statement and does not require a physical signature.")

        # ---- Run all sub-routines mapping PDF layout schema sequentially ----
        draw_header()
        y = draw_customer_info(height - margin - 100)
        y = draw_table_header(y)
        y, total_deposit, total_withdraw = draw_transactions(y)
        draw_summary(y, total_deposit, total_withdraw)

        c.showPage()
        c.save()

# -------------- MAIN ENTRY ------------------
def main():
    """
    Primary Entry Point for the execution of the entire Bank Python Script.
    Fires DB validation/setup checks prior to attempting UI Construction, handling errors natively.
    """
    try:
        init_database()
    except Exception as e:
        root = tk.Tk()
        root.withdraw()
        _set_icon(root)
        messagebox.showerror("DB Error", f"Could not initialize database:\n{e}")
        root.destroy()
        return

    app = BankApp()
    app.mainloop() # Trigger UI render event loop 

if __name__ == "__main__":
    main()
