import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date 
import os
import numpy as np 
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from io import BytesIO

# --- Configuration & Data Store ---
INVENTORY_FILE = 'df.csv'
DATE_FORMAT_STRING = '%Y-%m-%d' 
DATE_DISPLAY_FORMAT = 'MM/DD/YYYY' 
EXPIRY_WARNING_DAYS = 7 
EXPIRY_CRITICAL_DAYS = 3 

# Define MASTER_COLUMNS with correct expected dtypes
MASTER_COLUMNS = {
    'serial': str, 
    'segment': str, 
    'source': str, 
    'blood_type': str, 
    'component': str, 
    'volume': float, 
    'collected': 'datetime64[ns]', 
    'expiry': 'datetime64[ns]', 
    'age': str, 
    'status': str, 
    'patient': str
}
COLUMN_NAMES = list(MASTER_COLUMNS.keys())

BLOOD_TYPES = ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']
COMPONENTS = ['Whole Blood', 'PRBC', 'Platelets', 'FFP']
STATUS_OPTIONS = ['Available', 'Crossmatched', 'Expired', 'Transfused']

# --- Utility Functions ---

def calculate_expiry(collected_date, component):
    if collected_date is None or pd.isna(collected_date):
        return None
    
    if isinstance(collected_date, datetime):
        collected_date = collected_date.date()
    
    if component in ['PRBC', 'Whole Blood']:
        return collected_date + timedelta(days=42) 
    elif component == 'Platelets':
        return collected_date + timedelta(days=5)
    elif component == 'FFP':
        return collected_date + timedelta(days=7 * 365 + 1)
    else:
        return collected_date + timedelta(days=42)

def compute_age_text(collected_date, component):
    """Computes the age of the unit, now with simplified time delta logic."""
    if collected_date is None or pd.isna(collected_date) or not component:
        return 'N/A'
    
    today = datetime.now().date()
    # Safely convert to date object if it's a Pandas timestamp
    collected_date = collected_date.date() if isinstance(collected_date, (datetime, pd.Timestamp)) else collected_date
    
    if collected_date > today:
        return 'Future'
        
    diff_days = (today - collected_date).days
    
    if component == "FFP":
        # Simplified: just show years/days for FFP
        y = diff_days // 365
        d = diff_days % 365
        return f"{y}y {d}d"
    
    return f"{diff_days}d"

def load_data():
    """Loads, cleans, and validates the inventory DataFrame."""
    try:
        if os.path.exists(INVENTORY_FILE):
            df = pd.read_csv(INVENTORY_FILE)
            st.warning(f"Loaded {len(df)} rows from {INVENTORY_FILE}. Performing validation...")
        else:
            df = pd.DataFrame(columns=COLUMN_NAMES)
            st.info("Creating new inventory file.")
    except Exception as e:
        st.error(f"Error reading {INVENTORY_FILE}. Creating empty DataFrame. Error: {e}")
        df = pd.DataFrame(columns=COLUMN_NAMES)
        
    # 1. ENFORCE COLUMN STRUCTURE
    # Add missing columns with default values and remove unknown columns
    df = df.reindex(columns=COLUMN_NAMES)
    
    # 2. DATA CLEANUP & TYPE COERCION
    
    # Text Columns Cleanup (Fill NaNs with 'None', convert to string)
    for col in ['serial', 'segment', 'source', 'blood_type', 'component', 'status', 'patient', 'age']:
        if col in df.columns:
            # Replace common bad values with NaN, then fill NaN with 'None'
            df[col] = df[col].replace(['', 'None', 'nan'], np.nan).fillna('None').astype(str)
        
    # Numeric Columns Cleanup
    if 'volume' in df.columns:
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0).astype(float)
        
    # Date Columns Cleanup (CRITICAL STEP)
    for col in ['collected', 'expiry']:
        if col in df.columns:
            # Replace 'None' string with NaN, then coerce to datetime.
            df[col] = df[col].replace('None', np.nan) 
            df[col] = pd.to_datetime(df[col], format=DATE_FORMAT_STRING, errors='coerce')
        else:
            df[col] = pd.NaT # Ensure column exists if it didn't
    
    # 3. RE-CALCULATE AGE and STATUS (This step is now safer)
    df['age'] = df.apply(lambda row: compute_age_text(row['collected'], row['component']), axis=1)
    df = update_inventory_status(df)
        
    return df

def update_inventory_status(df):
    """Checks expiry dates and updates unit status."""
    today_date_only = datetime.today().date()
    expirable_statuses = ['Available', 'Crossmatched']
    
    # Check for expired units
    if 'expiry' in df.columns and not df['expiry'].isnull().all():
        # Check if the date is less than or equal to today, and if it's one of the expirable statuses
        # The .dt.date access is now safe because load_data enforces datetime type.
        df.loc[(df['status'].isin(expirable_statuses)) & (df['expiry'].dt.date <= today_date_only), 'status'] = 'Expired'
    
    return df

def save_data(df):
    """Saves the current DataFrame back to the CSV file using ISO format."""
    
    def date_to_string(d):
        if pd.isna(d): 
            return 'None'
        try:
            return d.strftime(DATE_FORMAT_STRING)
        except:
            return 'None'
    
    df_save = df.copy()
    df_save['collected'] = df_save['collected'].apply(date_to_string)
    df_save['expiry'] = df_save['expiry'].apply(date_to_string)
    
    # Save only the MASTER_COLUMNS to prevent proliferation of unwanted columns
    df_save = df_save.reindex(columns=COLUMN_NAMES)
    df_save.to_csv(INVENTORY_FILE, index=False)

def color_rows_by_expiry(row):
    """Apply CSS styling based on proximity to expiry date."""
    if row['status'] == 'Expired':
        return ['background-color: #f8d7da'] * len(row) 
        
    if pd.isna(row['expiry']):
        return [''] * len(row)

    days_left = (row['expiry'].date() - datetime.today().date()).days
    
    if days_left <= EXPIRY_CRITICAL_DAYS and days_left > 0:
        return ['background-color: #fff3cd'] * len(row)
    
    return [''] * len(row)

def generate_docx_report(df_active):
    """Generates a DOCX file based on active inventory, grouped by component and blood type."""
    doc = Document()
    doc.add_heading('Daily Blood Inventory Report', 0)
    doc.add_paragraph(f"Date: {datetime.now().strftime('%B %d, %Y')}")
    
    df_active = df_active[df_active['status'].isin(['Available', 'Crossmatched'])].copy()
    
    inventory_data = {comp: {bt: [] for bt in BLOOD_TYPES} for comp in COMPONENTS}
    
    for index, row in df_active.iterrows():
        comp = row['component']
        bt = row['blood_type']
        
        if comp in inventory_data and bt in inventory_data[comp]:
            age_or_expiry = ''
            if comp == 'FFP':
                if pd.notna(row['expiry']):
                    age_or_expiry = row['expiry'].strftime('%b %d, %Y')
            else:
                age_or_expiry = compute_age_text(row['collected'], comp)

            inventory_data[comp][bt].append({
                'serial': row['serial'],
                'ageOrExpiry': age_or_expiry,
                'patient': row['patient'] if row['patient'] != 'None' else ''
            })

    for component_name in COMPONENTS:
        component_map = inventory_data[component_name]
        
        doc.add_heading(component_name, level=2)
        
        max_rows = max([len(units) for units in component_map.values()], default=0)
        max_rows = max(max_rows, 1)
        
        table = doc.add_table(rows=max_rows + 1, cols=len(BLOOD_TYPES))
        table.style = 'Table Grid'
        
        header_cells = table.rows[0].cells
        for i, bt in enumerate(BLOOD_TYPES):
            header_cells[i].text = bt
            header_cells[i].paragraphs[0].runs[0].font.bold = True
            header_cells[i].width = Inches(0.8)

        for r_index in range(max_rows):
            row_cells = table.rows[r_index + 1].cells
            for c_index, bt in enumerate(BLOOD_TYPES):
                units = component_map[bt]
                if r_index < len(units):
                    item = units[r_index]
                    p = row_cells[c_index].paragraphs[0]
                    p.add_run(f"{item['serial']} — {item['ageOrExpiry']}").font.size = Pt(9)
                    if item['patient']:
                        p.add_run(f"\nPatient: {item['patient']}").italic = True
                        p.runs[-1].font.size = Pt(8)
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    
    bio = BytesIO()
    doc.save(bio)
    return bio.getvalue()

# --- Application Initialization ---

if 'inventory_df' not in st.session_state:
    st.session_state['inventory_df'] = load_data()

st.session_state['inventory_df'] = update_inventory_status(st.session_state['inventory_df'].copy())

# --- Streamlit UI (The remaining Streamlit code remains the same) ---

st.set_page_config(layout="wide", page_title="Blood Bag Inventory")

st.markdown("""
<style>
    #liveClock {
        font-weight: 600;
        text-align: right;
    }
    .top-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

col_title, col_clock = st.columns([3, 1])

with col_title:
    st.markdown("<h1 class='h3 mb-0'>Blood Bag Inventory</h1>", unsafe_allow_html=True)
    st.markdown("<small class='text-muted'>Manage units • Live updates</small>", unsafe_allow_html=True)

with col_clock:
    clock_placeholder = st.empty()
    clock_placeholder.markdown(f"**⏱️ {datetime.now().strftime('%b %d, %Y — %H:%M:%S')}**")
    
st.markdown("---")


# --- Sidebar Global Filters (Replaces HTML floatingFilters) ---
st.sidebar.header("🔍 Search & Filters")

q_search = st.sidebar.text_input("Search (Serial / Blood / Patient)")
f_blood = st.sidebar.selectbox("Blood Type", ['All'] + BLOOD_TYPES)
f_component = st.sidebar.selectbox("Component", ['All'] + COMPONENTS)
f_status = st.sidebar.selectbox("Status", ['All'] + STATUS_OPTIONS)

# --- Data Filtering Logic ---

filtered_df = st.session_state['inventory_df'].copy()

if q_search:
    q_search = q_search.lower()
    filtered_df = filtered_df[
        filtered_df['serial'].str.lower().str.contains(q_search, na=False) |
        filtered_df['blood_type'].str.lower().str.contains(q_search, na=False) |
        filtered_df['patient'].str.lower().str.contains(q_search, na=False)
    ]

if f_blood != 'All':
    filtered_df = filtered_df[filtered_df['blood_type'] == f_blood]
if f_component != 'All':
    filtered_df = filtered_df[filtered_df['component'] == f_component]

# Status filter applied to the active inventory view later

# --- Main Tabs ---
tab_add, tab_inv, tab_exp, tab_trans = st.tabs(["➕ Add Blood Bag", "🔬 Inventory", "🔴 Expired", "💉 Transfused"])


# ==================================
# TAB 1: ADD BLOOD BAG
# ==================================
with tab_add:
    st.header("Add New Blood Bag")
    
    with st.form("new_unit_form", clear_on_submit=True):
        st.subheader("Unit Details")
        col_id, col_seg, col_src = st.columns(3)
        serial = col_id.text_input("Serial Number", key='add_serial', required=True)
        segment = col_seg.text_input("Segment Number", key='add_segment', required=True)
        source = col_src.text_input("Source", key='add_source', value='Donor')

        col_group, col_comp, col_vol, col_coll = st.columns(4)
        blood_type = col_group.selectbox("Blood Type", BLOOD_TYPES, key='add_blood_type', required=True)
        
        component = col_comp.selectbox("Component", COMPONENTS, key='add_component', required=True)
        volume = col_vol.number_input("Volume (mL)", min_value=1, value=450, step=10, key='add_volume', required=True)
        collected_date_input = col_coll.date_input("Collection Date", value='today', key='add_collected', required=True)
        
        calculated_expiry = calculate_expiry(collected_date_input, component)
        
        col_exp, col_status, col_pat = st.columns(3)
        expiry_date_input = col_exp.date_input(
            "Expiry Date (Auto-calculated, Edit if FFP)", 
            value=calculated_expiry, 
            key='add_expiry'
        )
        
        initial_status = col_status.selectbox("Status", STATUS_OPTIONS, key='add_status')
        patient = col_pat.text_input("Patient Name (Required if Crossmatched/Transfused)", key='add_patient', value='')

        st.markdown("---")
        submit_button = st.form_submit_button("➕ Add Blood Bag", type="primary")
        
        if submit_button:
            if serial in st.session_state['inventory_df']['serial'].values:
                st.error(f"Unit Serial Number {serial} already exists.")
            else:
                new_unit_data = {
                    'serial': serial,
                    'segment': segment,
                    'source': source,
                    'blood_type': blood_type,
                    'component': component,
                    'volume': volume,
                    'collected': pd.to_datetime(collected_date_input),
                    'expiry': pd.to_datetime(expiry_date_input),
                    'age': compute_age_text(collected_date_input, component),
                    'status': initial_status,
                    'patient': patient if patient else 'None'
                }

                new_unit_df = pd.DataFrame([new_unit_data], columns=COLUMN_NAMES)
                
                final_concatenated_df = pd.concat([st.session_state['inventory_df'], new_unit_df], ignore_index=True)
                
                save_data(final_concatenated_df)
                
                st.session_state['inventory_df'] = load_data() 
                st.success(f"Unit {serial} successfully added! Status: {initial_status}")
                st.rerun() 
            
# ==================================
# TAB 2: ACTIVE INVENTORY
# ==================================
with tab_inv:
    st.header("Active Inventory")
    
    inventory_df_filtered = filtered_df[filtered_df['status'].isin(['Available', 'Crossmatched'])].copy()
    
    if f_status != 'All':
        inventory_df_filtered = inventory_df_filtered[inventory_df_filtered['status'] == f_status]
        
    inventory_df_filtered = inventory_df_filtered.sort_values(
        by=['status', 'expiry'], 
        ascending=[True, True]
    )

    if inventory_df_filtered.empty:
        st.info("No active units found matching the current filters.")
    else:
        display_df = inventory_df_filtered.rename(columns={
            'serial': 'Serial', 'segment': 'Segment', 'source': 'Source', 
            'blood_type': 'Blood Type', 'component': 'Component', 
            'volume': 'Volume', 'collected': 'Collection', 'expiry': 'Expiry', 
            'age': 'Days Old', 'status': 'Status', 'patient': 'Patient'
        })[['Serial', 'Segment', 'Source', 'Blood Type', 'Component', 'Volume', 'Collection', 'Expiry', 'Days Old', 'Status', 'Patient']]
        
        st.caption("Editing the table below automatically updates the inventory data.")

        edited_df = st.data_editor(
            display_df.style.apply(color_rows_by_expiry, axis=1),
            key="active_inventory_editor",
            use_container_width=True,
            column_config={
                "Collection": st.column_config.DateColumn("Collection", format=DATE_DISPLAY_FORMAT, disabled=True),
                "Expiry": st.column_config.DateColumn("Expiry", format=DATE_DISPLAY_FORMAT),
                "Status": st.column_config.SelectboxColumn("Status", options=STATUS_OPTIONS),
            },
            num_rows="fixed" 
        )
        
        if st.button("💾 Save Changes", type="primary"):
            for col in ['Collection', 'Expiry']:
                edited_df[col] = pd.to_datetime(edited_df[col], errors='coerce')
                
            edited_df.columns = [c.lower().replace(' ', '_') for c in edited_df.columns]
            
            st.session_state['inventory_df'].loc[edited_df.index] = edited_df
