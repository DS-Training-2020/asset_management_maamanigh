# asset_manager.py
import streamlit as st
import pandas as pd
import os
from io import BytesIO
import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from openpyxl import Workbook
from datetime import date, datetime
import matplotlib.pyplot as plt

# =============================
# CONFIG
# =============================
FILE_PATH = "Maamani_Asset_Register.xlsx"
EXCEL_FILE = "Maamani_Asset_Register.xlsx"

COLUMNS = [
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
    "Update History"
]

# ---------------------------
# Ensure Excel file exists
# ---------------------------
def initialize_excel():
    if not os.path.exists(FILE_PATH):
        wb = Workbook()
        ws = wb.active
        ws.append(COLUMNS)
        wb.save(FILE_PATH)

initialize_excel()

# Load data
def load_data():
    return pd.read_excel(EXCEL_FILE)

# Save data
def save_data(df):
    df.to_excel(EXCEL_FILE, index=False)

# Generate QR PDF
def generate_qr_pdf(asset_tags):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    x, y = 50, height - 150  # starting position
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

# ------------------- STREAMLIT APP -------------------
st.title("📦 Maamani Asset Management System")

# --- Simple login system ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

USER_CREDENTIALS = {
    "admin": "admin123",
    "user": "user123"
}

if not st.session_state.logged_in:
    st.subheader("🔑 Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
            st.session_state.logged_in = True
            st.success(f"✅ Welcome, {username}!")
            st.rerun()
        else:
            st.error("❌ Invalid username or password")
else:
    # --- After Login ---
    menu = st.sidebar.selectbox("Menu", ["View Assets", "Add/Update Asset", "Generate QR Codes","Dashboard" ,"Logout"])

    if menu == "View Assets":
        st.subheader("Asset Records")
        df = load_data()
        st.dataframe(df, use_container_width=True)

    elif menu == "Add/Update Asset":
        st.subheader("➕ Add or Update Asset")
        df = load_data()

        # Choose whether adding new or updating
        action = st.radio("Action", ["Add New Asset", "Update Existing Asset"])

        if action == "Update Existing Asset" and not df.empty:
            asset_tag = st.selectbox("Select Asset Tag to Update", df["Asset Tag"].tolist())
            asset_record = df[df["Asset Tag"] == asset_tag].iloc[0].to_dict()
        else:
            asset_tag = None
            asset_record = {}

        with st.form("asset_form", clear_on_submit=False):
            form_data = {}
            for col in COLUMNS:
                if col in ["Asset Tag", "Update Count", "Update History", "Date Added", "Last Updated"]:
                    continue  # handled internally

                elif col == "Category":
                    form_data[col] = st.selectbox(
                        "Category",
                        ["Laptop", "Desktop", "Printer", "Vehicle", "Furniture", "Tool", "Phone", "Other"],
                        index=(["Laptop", "Desktop", "Printer", "Vehicle", "Furniture", "Tool", "Phone", "Other"].index(asset_record[col]) if asset_record.get(col) in ["Laptop", "Desktop", "Printer", "Vehicle", "Furniture", "Tool", "Phone", "Other"] else 0)
                    )

                elif col == "Department":
                    form_data[col] = st.selectbox(
                        "Department",
                        ["IT", "HR", "Finance", "Operations", "Admin", "Marketing", "Logistics", "Other"],
                        index=(["IT", "HR", "Finance", "Operations", "Admin", "Marketing", "Logistics", "Other"].index(asset_record[col]) if asset_record.get(col) in ["IT", "HR", "Finance", "Operations", "Admin", "Marketing", "Logistics", "Other"] else 0)
                    )

                elif col == "Condition":
                    form_data[col] = st.selectbox(
                        "Condition",
                        ["New", "Good", "Fair", "Poor", "Broken"],
                        index=(["New", "Good", "Fair", "Poor", "Broken"].index(asset_record[col]) if asset_record.get(col) in ["New", "Good", "Fair", "Poor", "Broken"] else 0)
                    )

                elif col == "Status":
                    form_data[col] = st.selectbox(
                        "Status",
                        ["In Use", "In Storage", "Under Maintenance", "Disposed", "Lost"],
                        index=(["In Use", "In Storage", "Under Maintenance", "Disposed", "Lost"].index(asset_record[col]) if asset_record.get(col) in ["In Use", "In Storage", "Under Maintenance", "Disposed", "Lost"] else 0)
                    )

                elif col in ["Purchase Date", "Warranty End Date",]:
                    form_data[col] = st.date_input(col, value=pd.to_datetime(asset_record[col]).date() if asset_record.get(col) not in [None, "nan", "NaT"] and pd.notna(asset_record[col]) else date.today())
                    
                elif col == "Disposal Date":
                    if asset_record.get(col) not in [None, "nan", "NaT"] and pd.notna(asset_record.get(col)):
                    # Show the existing date if available
                        form_data[col] = st.date_input(col, value=pd.to_datetime(asset_record[col]).date())
                    else:
                    # Let the user decide whether to add a disposal date
                        safe_tag = asset_record.get("Asset Tag", "NEW")
                        add_disposal = st.checkbox("Add Disposal Date?", value=False, key=f"chk_{col}_{safe_tag}")
                        if add_disposal:
                            form_data[col] = st.date_input(col, value=date.today(), key=f"date_{col}_{safe_tag}")
                        else:
                            form_data[col] = None


                elif col == "Purchase Price (GHS)":
                    form_data[col] = st.number_input(col, min_value=0.0, step=0.01, value=float(asset_record[col]) if asset_record.get(col) not in [None, "nan"] and pd.notna(asset_record[col]) else 0.0)

                else:
                    form_data[col] = st.text_input(col, value=str(asset_record[col]) if asset_record.get(col) not in [None, "nan"] else "")

            submitted = st.form_submit_button("Save Asset")

        if submitted:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if action == "Add New Asset":
                # Generate new Asset Tag
                serial = str(form_data["Serial Number"]).zfill(4) if form_data["Serial Number"] else "0000"
                dept = form_data["Department"][:3].upper() if form_data["Department"] else "GEN"
                loc = form_data["Location"][:3].upper() if form_data["Location"] else "LOC"
                asset = form_data["Asset Name"][:3].upper() if form_data["Asset Name"] else "AST"
                new_tag = f"{asset}-{loc}-{dept}-{serial}"

                form_data["Asset Tag"] = new_tag
                form_data["Date Added"] = now
                form_data["Last Updated"] = now
                form_data["Update Count"] = 0
                form_data["Update History"] = ""

                df = pd.concat([df, pd.DataFrame([form_data])], ignore_index=True)
                st.success(f"✅ Asset '{form_data['Asset Name']}' added successfully with Tag: {new_tag}")

            else:
                # Update existing asset without regenerating Asset Tag
                idx = df[df["Asset Tag"] == asset_tag].index[0]
                for key, value in form_data.items():
                    df.at[idx, key] = value
                df.at[idx, "Last Updated"] = now

                # Track updates
                df.at[idx, "Update Count"] = (df.at[idx, "Update Count"] if not pd.isna(df.at[idx, "Update Count"]) else 0) + 1
                prev_history = str(df.at[idx, "Update History"])
                df.at[idx, "Update History"] = prev_history + " | " + now if prev_history not in ["", "nan", "None"] else now

                st.success(f"🔄 Asset '{asset_tag}' updated successfully!")

            save_data(df)

    elif menu == "Generate QR Codes":
        st.subheader("📑 Generate QR Code Labels")
        df = load_data()

        if df.empty:
            st.warning("⚠️ No assets found. Please add assets first.")
        else:
            asset_tags = st.multiselect("Select Asset IDs", df["Asset Tag"].tolist())
            if asset_tags and st.button("Generate PDF"):
                pdf_bytes = generate_qr_pdf(asset_tags)
                st.download_button("⬇️ Download QR Codes PDF", pdf_bytes, file_name="asset_qr_codes.pdf")
                
    elif menu == "Dashboard":
        st.subheader("📊 Asset Dashboard")
        df = load_data()

        if df.empty:
            st.warning("No data available.")
        else:
            import plotly.express as px

            # KPIs
            total_assets = len(df)
            total_value = df["Purchase Price (GHS)"].sum()
            disposed_assets = (df["Status"] == "Disposed").sum()
            in_use_assets = (df["Status"] == "In Use").sum()

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Total Assets", total_assets)
            kpi2.metric("Total Value (GHS)", f"{total_value:,.2f}")
            kpi3.metric("In Use", in_use_assets)
            kpi4.metric("Disposed", disposed_assets)

            st.markdown("---")

            # Layout for visuals (2x2 grid like Power BI)
            col1, col2 = st.columns(2)

            with col1:
                cat_counts = df["Category"].value_counts().reset_index()
                cat_counts.columns = ["Category", "Count"]
                fig_cat = px.bar(
                    cat_counts,
                    x="Category",
                    y="Count",
                    color="Category",
                    title="Assets by Category",
                    text_auto=True
                )
                fig_cat.update_layout(margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig_cat, use_container_width=True)

            with col2:
                dept_counts = df["Department"].value_counts().reset_index()
                dept_counts.columns = ["Department", "Count"]
                fig_dept = px.bar(
                    dept_counts,
                    x="Department",
                    y="Count",
                    color="Department",
                    title="Assets by Department",
                    text_auto=True
                )
                fig_dept.update_layout(margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig_dept, use_container_width=True)

            col3, col4 = st.columns(2)

            with col3:
                fig_cond = px.pie(
                    df,
                    names="Condition",
                    title="Condition Distribution",
                    hole=0.4
                )
                st.plotly_chart(fig_cond, use_container_width=True)

            with col4:
                fig_status = px.pie(
                    df,
                    names="Status",
                    title="Status Distribution",
                    hole=0.4
                )
                st.plotly_chart(fig_status, use_container_width=True)

            st.markdown("---")
            st.subheader("📜 Update History")
            st.dataframe(
                df[["Asset Tag", "Asset Name", "Update Count", "Update History"]],
                use_container_width=True
            )
    elif menu == "Logout":
        st.session_state.logged_in = False
        st.rerun()
