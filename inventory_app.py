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
DATE_FORMAT_STRING = '%Y-%m-%d' # ISO standard for internal/form use
DATE_DISPLAY_FORMAT = 'MM/DD/YYYY' 
EXPIRY_WARNING_DAYS = 7 
EXPIRY_CRITICAL_DAYS = 3 

MASTER_COLUMNS = [
    'serial', 'segment', 'source', 'blood_type', 'component', 'volume', 
    'collected', 'expiry', 'age', 'status', 'patient'
]

# Standard Blood Types and Components for Select boxes
BLOOD_TYPES = ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']
COMPONENTS = ['Whole Blood', 'PRBC', 'Platelets', 'FFP']
STATUS_OPTIONS = ['Available', 'Crossmatched', 'Expired', 'Transfused']

# --- Utility Functions (Python Reimplementation) ---

def calculate_expiry(collected_date, component):
    """Calculates the expiry date based on the component and collected date."""
    if collected_date is None or pd.isna(collected_date):
        return None
    
    # Ensure collected_date is a date object for timedelta arithmetic
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
    """Computes the age of the unit, formatted as 'Nd' or 'Ny Md' for FFP."""
    # CRITICAL FIX: Check for NaT or None aggressively before proceeding
    if collected_date is None or pd.isna(collected_date) or not component:
        return 'N/A' # Return a single, simple string for alignment
    
    # Ensure collected_date is a date object for comparison
    if isinstance(collected_date, datetime):
        collected_date = collected_date.date()
        
    today = datetime.today().date()
    
    if collected_date > today:
        return 'Future'
        
    diff_days = (today - collected_date).days
    
    if component == "FFP":
        y = diff_days // 365
        d = diff_days % 365
        return f"{y}y {d}d"
    
    return f"{diff_days}d"

def load_data():
    """Loads or initializes the inventory DataFrame."""
    if os.path.exists(INVENTORY_FILE):
        df = pd.read_csv(INVENTORY_FILE)
    else:
        df = pd.DataFrame(columns=MASTER_COLUMNS)
    
    # 1. CLEANUP: Replace any bad strings with NaN
    for col in ['collected', 'expiry']:
        if col in df.columns:
            df[col] = df[col].replace('None', np.nan) 

    # 2. TYPE COERCION: Ensure date columns are proper datetime objects
    for col in ['collected', 'expiry']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format=DATE_FORMAT_STRING, errors='coerce')
        else:
            df[col] = pd.NaT # Add column if missing

    # 3. FILL TEXT NaNs
    for col in ['segment', 'source', 'patient', 'component', 'blood_type']:
        if col in df.columns:
            df[col] = df[col].fillna('None').astype(str)
        
    # 4. RECALCULATE AGE and STATUS
    # This line now uses a robust compute_age_text function that returns a simple string 
    # ('N/A') even if inputs are missing/NaT, preventing the ValueError.
    df['age'] = df.apply(lambda row: compute_age_text(row['collected'], row['component']), axis=1)
    df = update_inventory_status(df)
        
    df = df.reindex(columns=MASTER_COLUMNS, fill_value=None)
    return df

# The rest of the functions (update_inventory_status, save_data, color_rows_by_expiry, 
# generate_docx_report) remain the same as the last working version.
# I will omit them here for brevity but ensure you use the complete version
# including the rest of the app code below this line.

def update_inventory_status(df):
    """Checks expiry dates and updates unit status."""
    today_date_only = datetime.today().date()
    expirable_statuses = ['Available', 'Crossmatched']
    
    if 'expiry' in df.columns:
        # Check if the date is less than or equal to today, and if it's one of the expirable statuses
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

# --- Streamlit UI (The rest of the code remains the same) ---

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

                new_unit_df = pd.DataFrame([new_unit_data], columns=MASTER_COLUMNS)
                
                final_concatenated_df = pd.concat([st.session_state['inventory_df'], new_unit_df], ignore_index=True)
                
                save_data(final_concatenated_df)
                
                st.session_state['inventory_df'] = load_data() 
                st.success(f"Unit {serial} successfully added! Status: {initial_status}")
                st
