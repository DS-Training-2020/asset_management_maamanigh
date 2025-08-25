# asset_manager.py
import os
import sqlite3
import base64
import hashlib
import secrets
from datetime import date, datetime
from io import BytesIO

import pandas as pd
import qrcode
import streamlit as st
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# Optional: nice charts
import plotly.express as px

# =============================
# CONFIG
# =============================
DB_FILE = "maamani_assets.db"

ASSET_COLUMNS = [
    "Asset Tag",
    "Asset Name",
    "Category",
    "Description",
    "Serial Number",
    "Assigned To",
    "Department",
    "Purchase Date",
    "Purchase Price (GHS)",
    "Condition",
    "Location",
    "Status",
    "Warranty End Date",
    "Maintenance Schedule",
    "Date Added",
    "Last Updated",
    "Disposal Date",
    "Notes",
    "Update Count",
    "Update History",
]

CATEGORY_OPTIONS = ["Laptop", "Desktop", "Printer", "Vehicle", "Furniture", "Tool", "Phone", "Other"]
DEPARTMENT_OPTIONS = ["IT", "HR", "Finance", "Operations", "Admin", "Marketing", "Logistics", "Other"]
CONDITION_OPTIONS = ["New", "Good", "Fair", "Poor", "Broken"]
STATUS_OPTIONS = ["In Use", "In Storage", "Under Maintenance", "Disposed", "Lost"]

# =============================
# DB / AUTH UTILITIES
# =============================
def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # Assets table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS assets (
            asset_tag TEXT PRIMARY KEY,
            asset_name TEXT,
            category TEXT,
            description TEXT,
            serial_number TEXT,
            assigned_to TEXT,
            department TEXT,
            purchase_date TEXT,
            purchase_price_ghs REAL,
            condition TEXT,
            location TEXT,
            status TEXT,
            warranty_end_date TEXT,
            maintenance_schedule TEXT,
            date_added TEXT,
            last_updated TEXT,
            disposal_date TEXT,
            notes TEXT,
            update_count INTEGER DEFAULT 0,
            update_history TEXT
        );
        """
    )

    # Users table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','user'))
        );
        """
    )

    # Ensure an admin exists, using st.secrets if present
    admin_pw = None
    try:
        admin_pw = st.secrets.get("ADMIN_PASSWORD", None)
    except Exception:
        admin_pw = None

    c.execute("SELECT COUNT(*) AS n FROM users WHERE username='admin';")
    exists = c.fetchone()["n"]


    conn.commit()
    conn.close()


def _pbkdf2_hash(password: str, salt: bytes) -> str:
    # Strong hash via PBKDF2-HMAC-SHA256
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return base64.b64encode(dk).decode("utf-8")

def add_user(username: str, password: str, role: str = "user", _conn=None):
    if role not in ("admin", "user"):
        raise ValueError("Invalid role")

    salt = secrets.token_bytes(16)
    pwd_hash = _pbkdf2_hash(password, salt)
    salt_b64 = base64.b64encode(salt).decode("utf-8")

    conn = _conn or get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
        (username, pwd_hash, salt_b64, role),
    )
    conn.commit()
    if _conn is None:
        conn.close()

def verify_user(username: str, password: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT username, password_hash, salt, role FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if not row:
        return False, None
    salt = base64.b64decode(row["salt"])
    derived = _pbkdf2_hash(password, salt)
    if secrets.compare_digest(derived, row["password_hash"]):
        return True, row["role"]
    return False, None

# =============================
# ASSET CRUD
# =============================
def df_from_sql(query: str, params: tuple = ()):
    conn = get_conn()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def get_all_assets_df():
    return df_from_sql("SELECT * FROM assets ORDER BY date_added DESC;")

def get_asset(asset_tag: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM assets WHERE asset_tag=?", (asset_tag,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def insert_asset(record: dict):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO assets (
            asset_tag, asset_name, category, description, serial_number,
            assigned_to, department, purchase_date, purchase_price_ghs,
            condition, location, status, warranty_end_date, maintenance_schedule,
            date_added, last_updated, disposal_date, notes, update_count, update_history
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            record.get("Asset Tag"),
            record.get("Asset Name"),
            record.get("Category"),
            record.get("Description"),
            record.get("Serial Number"),
            record.get("Assigned To"),
            record.get("Department"),
            record.get("Purchase Date"),
            float(record.get("Purchase Price (GHS)", 0) or 0),
            record.get("Condition"),
            record.get("Location"),
            record.get("Status"),
            record.get("Warranty End Date"),
            record.get("Maintenance Schedule"),
            record.get("Date Added"),
            record.get("Last Updated"),
            record.get("Disposal Date"),
            record.get("Notes"),
            int(record.get("Update Count", 0) or 0),
            record.get("Update History"),
        ),
    )
    conn.commit()
    conn.close()

def update_asset(asset_tag: str, updates: dict):
    # Build dynamic SQL
    fields = []
    values = []
    for k, v in updates.items():
        col = _py_to_sql_col(k)
        fields.append(f"{col}=?")
        values.append(v if v is not None else None)
    values.append(asset_tag)

    sql = f"UPDATE assets SET {', '.join(fields)} WHERE asset_tag=?"
    conn = get_conn()
    c = conn.cursor()
    c.execute(sql, tuple(values))
    conn.commit()
    conn.close()

def _py_to_sql_col(py_col: str):
    mapping = {
        "Asset Tag": "asset_tag",
        "Asset Name": "asset_name",
        "Category": "category",
        "Description": "description",
        "Serial Number": "serial_number",
        "Assigned To": "assigned_to",
        "Department": "department",
        "Purchase Date": "purchase_date",
        "Purchase Price (GHS)": "purchase_price_ghs",
        "Condition": "condition",
        "Location": "location",
        "Status": "status",
        "Warranty End Date": "warranty_end_date",
        "Maintenance Schedule": "maintenance_schedule",
        "Date Added": "date_added",
        "Last Updated": "last_updated",
        "Disposal Date": "disposal_date",
        "Notes": "notes",
        "Update Count": "update_count",
        "Update History": "update_history",
    }
    return mapping.get(py_col, py_col)

# =============================
# UTIL: DATES / TAGS
# =============================
def to_iso(d):
    if d is None or d == "":
        return None
    if isinstance(d, (datetime, date)):
        return d.strftime("%Y-%m-%d")
    try:
        return pd.to_datetime(d).strftime("%Y-%m-%d")
    except Exception:
        return None

def now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def generate_asset_tag(form_data: dict):
    serial = str(form_data.get("Serial Number", "")).zfill(4) if form_data.get("Serial Number") else "0000"
    dept = (form_data.get("Department") or "GEN")[:3].upper()
    loc = (form_data.get("Location") or "LOC")[:3].upper()
    asset = (form_data.get("Asset Name") or "AST")[:3].upper()
    return f"{asset}-{loc}-{dept}-{serial}"

# =============================
# QR PDF
# =============================
def generate_qr_pdf(asset_tags):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    x, y = 50, height - 150
    for tag in asset_tags:
        qr = qrcode.QRCode(box_size=4, border=2)
        qr.add_data(tag)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        img_buffer = BytesIO()
        qr_img.save(img_buffer, format="PNG")
        img_buffer.seek(0)

        c.drawImage(ImageReader(img_buffer), x, y, width=100, height=100)
        c.drawString(x, y - 15, tag)

        x += 150
        if x > width - 120:
            x = 50
            y -= 150
            if y < 100:
                c.showPage()
                y = height - 150

    c.save()
    buffer.seek(0)
    return buffer

# =============================
# APP
# =============================
st.set_page_config(page_title="Maamani Asset Management", layout="wide")
st.title("📦 Maamani Asset Management System")

# Initialize DB
init_db()

# --- Simple login system ---
if "auth" not in st.session_state:
    st.session_state.auth = {"logged_in": False, "username": None, "role": None}

if not st.session_state.auth["logged_in"]:
    st.subheader("🔑 Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    # Security hint if using fallback admin password
    try:
        has_secret = bool(st.secrets.get("ADMIN_PASSWORD", None))
    except Exception:
        has_secret = False
    if not has_secret:
        pass

    if st.button("Login"):
        ok, role = verify_user(username, password)
        if ok:
            st.session_state.auth = {"logged_in": True, "username": username, "role": role}
            st.success(f"✅ Welcome, {username}!")
            st.rerun()
        else:
            st.error("❌ Invalid username or password")
else:
    # --- After Login ---
    role = st.session_state.auth["role"]
    is_admin = role == "admin"

    menu_items = ["View Assets", "Add/Update Asset", "Generate QR Codes", "Dashboard"]
    if is_admin:
        menu_items.insert(0, "User Management")
    menu_items.append("Logout")

    menu = st.sidebar.selectbox("Menu", menu_items)

    # ---------------- USER MGMT (Admins) ----------------
    if menu == "User Management":
        st.subheader("👤 User Management (Admins)")
        st.caption("Add users with secure, salted password hashing (PBKDF2).")
        with st.form("add_user_form", clear_on_submit=True):
            new_user = st.text_input("New Username")
            new_pw = st.text_input("New Password", type="password")
            new_role = st.selectbox("Role", ["user", "admin"])
            add_user_sub = st.form_submit_button("Add / Update User")

        if add_user_sub:
            if not new_user or not new_pw:
                st.warning("Username and password required.")
            else:
                add_user(new_user, new_pw, role=new_role)
                st.success(f"User '{new_user}' added/updated with role '{new_role}'.")

        # Show users (no hashes)
        users_df = df_from_sql("SELECT username, role FROM users ORDER BY username;")
        st.dataframe(users_df, use_container_width=True)

    # ---------------- VIEW ASSETS ----------------
    elif menu == "View Assets":
        st.subheader("📑 Asset Records")
        df = get_all_assets_df()
        st.dataframe(df, use_container_width=True)

    # ---------------- ADD / UPDATE ----------------
    elif menu == "Add/Update Asset":
        st.subheader("➕ Add or Update Asset")
        df = get_all_assets_df()

        action = st.radio("Action", ["Add New Asset", "Update Existing Asset"], horizontal=True)

        if action == "Update Existing Asset" and not df.empty:
            selected_tag = st.selectbox("Select Asset Tag to Update", df["asset_tag"].tolist())
            existing = get_asset(selected_tag) or {}
        else:
            selected_tag = None
            existing = {}

        with st.form("asset_form", clear_on_submit=False):
            form = {}

            # Inputs (skip auto fields)
            # Category / Department / Condition / Status
            form["Category"] = st.selectbox(
                "Category", CATEGORY_OPTIONS,
                index=(CATEGORY_OPTIONS.index(existing.get("category")) if existing.get("category") in CATEGORY_OPTIONS else 0)
            )
            form["Department"] = st.selectbox(
                "Department", DEPARTMENT_OPTIONS,
                index=(DEPARTMENT_OPTIONS.index(existing.get("department")) if existing.get("department") in DEPARTMENT_OPTIONS else 0)
            )
            form["Condition"] = st.selectbox(
                "Condition", CONDITION_OPTIONS,
                index=(CONDITION_OPTIONS.index(existing.get("condition")) if existing.get("condition") in CONDITION_OPTIONS else 0)
            )
            form["Status"] = st.selectbox(
                "Status", STATUS_OPTIONS,
                index=(STATUS_OPTIONS.index(existing.get("status")) if existing.get("status") in STATUS_OPTIONS else 0)
            )

            # Text fields
            form["Asset Name"] = st.text_input("Asset Name", existing.get("asset_name", "") or "")
            form["Description"] = st.text_area("Description", existing.get("description", "") or "")
            form["Serial Number"] = st.text_input("Serial Number", existing.get("serial_number", "") or "")
            form["Assigned To"] = st.text_input("Assigned To", existing.get("assigned_to", "") or "")
            form["Location"] = st.text_input("Location", existing.get("location", "") or "")
            form["Notes"] = st.text_area("Notes", existing.get("notes", "") or "")

            # Dates (Purchase/Warranty default to today if missing; Disposal is optional with checkbox)
            form["Purchase Date"] = st.date_input(
                "Purchase Date",
                value=(pd.to_datetime(existing.get("purchase_date")).date() if existing.get("purchase_date") else date.today())
            )
            form["Warranty End Date"] = st.date_input(
                "Warranty End Date",
                value=(pd.to_datetime(existing.get("warranty_end_date")).date() if existing.get("warranty_end_date") else date.today())
            )
            form["Maintenance Schedule"] = st.text_input("Maintenance Schedule", existing.get("maintenance_schedule", "") or "")

            # Disposal date optional
            if existing.get("disposal_date"):
                form["Disposal Date"] = st.date_input("Disposal Date", value=pd.to_datetime(existing["disposal_date"]).date())
            else:
                add_disposal = st.checkbox("Add Disposal Date?", value=False, key=f"chk_disposal_{selected_tag or 'NEW'}")
                if add_disposal:
                    form["Disposal Date"] = st.date_input("Disposal Date", value=date.today(), key=f"date_disposal_{selected_tag or 'NEW'}")
                else:
                    form["Disposal Date"] = None

            # Price
            existing_price = existing.get("purchase_price_ghs")
            form["Purchase Price (GHS)"] = st.number_input(
                "Purchase Price (GHS)",
                min_value=0.0, step=0.01,
                value=float(existing_price) if existing_price not in [None, "nan"] else 0.0
            )

            submitted = st.form_submit_button("Save Asset")

        if submitted:
            now = now_iso()
            # Normalize dates to ISO
            form_norm = {
                "Asset Name": form["Asset Name"],
                "Category": form["Category"],
                "Description": form["Description"],
                "Serial Number": form["Serial Number"],
                "Assigned To": form["Assigned To"],
                "Department": form["Department"],
                "Purchase Date": to_iso(form["Purchase Date"]),
                "Purchase Price (GHS)": form["Purchase Price (GHS)"],
                "Condition": form["Condition"],
                "Location": form["Location"],
                "Status": form["Status"],
                "Warranty End Date": to_iso(form["Warranty End Date"]),
                "Maintenance Schedule": form["Maintenance Schedule"],
                "Disposal Date": to_iso(form["Disposal Date"]) if form["Disposal Date"] else None,
                "Notes": form["Notes"],
            }

            if action == "Add New Asset":
                # Generate stable tag on creation only
                new_tag = generate_asset_tag(form_norm)
                # Ensure uniqueness
                if get_asset(new_tag):
                    st.error(f"Asset Tag '{new_tag}' already exists. Please change Serial/Dept/Location/Name to generate a different tag.")
                else:
                    record = dict(form_norm)
                    record["Asset Tag"] = new_tag
                    record["Date Added"] = now
                    record["Last Updated"] = now
                    record["Update Count"] = 0
                    record["Update History"] = ""
                    insert_asset(record)
                    st.success(f"✅ Asset '{record['Asset Name']}' added with Tag: {new_tag}")
            else:
                # Update existing by selected_tag (do not regenerate tag)
                if not selected_tag:
                    st.error("Please select an Asset Tag to update.")
                else:
                    updates = dict(form_norm)
                    updates["Last Updated"] = now

                    # Update history / count
                    existing_uc = existing.get("update_count", 0) or 0
                    existing_hist = existing.get("update_history") or ""
                    updates["Update Count"] = int(existing_uc) + 1
                    updates["Update History"] = (existing_hist + " | " + now) if existing_hist else now

                    # Map keys to DB columns handled inside update_asset
                    update_asset(selected_tag, updates)
                    st.success(f"🔄 Asset '{selected_tag}' updated successfully!")

    # ---------------- QR CODES ----------------
    elif menu == "Generate QR Codes":
        st.subheader("📑 Generate QR Code Labels")
        df = get_all_assets_df()

        if df.empty:
            st.warning("⚠️ No assets found. Please add assets first.")
        else:
            asset_tags = st.multiselect("Select Asset IDs", df["asset_tag"].tolist())
            if asset_tags and st.button("Generate PDF"):
                pdf_bytes = generate_qr_pdf(asset_tags)
                st.download_button("⬇️ Download QR Codes PDF", data=pdf_bytes, file_name="asset_qr_codes.pdf")

    # ---------------- DASHBOARD ----------------
    elif menu == "Dashboard":
        st.subheader("📊 Asset Dashboard")
        df = get_all_assets_df()
        if df.empty:
            st.warning("No data available.")
        else:
            # Rename to friendly cols for charts
            friendly = df.rename(
                columns={
                    "asset_tag": "Asset Tag",
                    "asset_name": "Asset Name",
                    "category": "Category",
                    "department": "Department",
                    "condition": "Condition",
                    "status": "Status",
                    "purchase_price_ghs": "Purchase Price (GHS)",
                    "purchase_date": "Purchase Date",
                }
            )

            # ---- FILTERS (Power BI–style) ----
            with st.expander("🔎 Filters", expanded=True):
                search_text = st.text_input("Search (Asset Name / Tag / Description)")
                f1, f2, f3, f4 = st.columns(4)
                with f1:
                    f_category = st.multiselect("Category", options=sorted(friendly["Category"].dropna().unique().tolist()))
                with f2:
                    f_dept = st.multiselect("Department", options=sorted(friendly["Department"].dropna().unique().tolist()))
                with f3:
                    f_cond = st.multiselect("Condition", options=sorted(friendly["Condition"].dropna().unique().tolist()))
                with f4:
                    f_status = st.multiselect("Status", options=sorted(friendly["Status"].dropna().unique().tolist()))
                date_range = st.date_input("Purchase Date Range", [])

            fdf = friendly.copy()
            if search_text:
                mask = (
                    fdf["Asset Name"].astype(str).str.contains(search_text, case=False, na=False)
                    | fdf["Asset Tag"].astype(str).str.contains(search_text, case=False, na=False)
                    | fdf.get("Description", pd.Series("", index=fdf.index)).astype(str).str.contains(search_text, case=False, na=False)
                )
                fdf = fdf[mask]
            if f_category:
                fdf = fdf[fdf["Category"].isin(f_category)]
            if f_dept:
                fdf = fdf[fdf["Department"].isin(f_dept)]
            if f_cond:
                fdf = fdf[fdf["Condition"].isin(f_cond)]
            if f_status:
                fdf = fdf[fdf["Status"].isin(f_status)]
            if date_range and len(date_range) == 2:
                start, end = date_range
                fdf["Purchase Date"] = pd.to_datetime(fdf["Purchase Date"], errors="coerce")
                fdf = fdf[(fdf["Purchase Date"] >= pd.to_datetime(start)) & (fdf["Purchase Date"] <= pd.to_datetime(end))]

            # ---- KPIs ----
            total_assets = len(fdf)
            total_value = fdf["Purchase Price (GHS)"].fillna(0).sum()
            disposed_assets = (fdf["Status"] == "Disposed").sum()
            in_use_assets = (fdf["Status"] == "In Use").sum()

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total Assets", total_assets)
            k2.metric("Total Value (GHS)", f"{total_value:,.2f}")
            k3.metric("In Use", int(in_use_assets))
            k4.metric("Disposed", int(disposed_assets))

            st.markdown("---")

            # ---- CHARTS ----
            c1, c2 = st.columns(2)
            with c1:
                if not fdf.empty:
                    cat_counts = fdf["Category"].value_counts().reset_index()
                    cat_counts.columns = ["Category", "Count"]
                    st.plotly_chart(
                        px.bar(cat_counts, x="Category", y="Count", color="Category", title="Assets by Category", text_auto=True),
                        use_container_width=True,
                    )
            with c2:
                if not fdf.empty:
                    dept_counts = fdf["Department"].value_counts().reset_index()
                    dept_counts.columns = ["Department", "Count"]
                    st.plotly_chart(
                        px.bar(dept_counts, x="Department", y="Count", color="Department", title="Assets by Department", text_auto=True),
                        use_container_width=True,
                    )

            c3, c4 = st.columns(2)
            with c3:
                if not fdf.empty:
                    st.plotly_chart(px.pie(fdf, names="Condition", title="Condition Distribution", hole=0.4), use_container_width=True)
            with c4:
                if not fdf.empty:
                    st.plotly_chart(px.pie(fdf, names="Status", title="Status Distribution", hole=0.4), use_container_width=True)

            st.markdown("---")
            st.subheader("📜 Filtered Data")
            st.dataframe(fdf, use_container_width=True)

    elif menu == "Logout":
        st.session_state.auth = {"logged_in": False, "username": None, "role": None}
        st.rerun()
