import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import time 
import numpy as np 

# --- Configuration ---
INVENTORY_FILE = 'df.csv'
# Define the master column order for consistency
MASTER_COLUMNS = [
    'unit_id', 'segment_number', 'blood_group', 'component', 'collected', 'expiry', 
    'volume', 'source', 
    'status', 'patient_id', 'crossmatched_date' 
]

# --- Utility Functions ---

def load_data():
    """Loads or initializes the inventory DataFrame."""
    if os.path.exists(INVENTORY_FILE):
        df = pd.read_csv(INVENTORY_FILE)
    else:
        # Initialize with ALL required columns
        df = pd.DataFrame(columns=MASTER_COLUMNS)
    
    # Ensure date columns are proper datetime objects for comparison
    df['collected'] = pd.to_datetime(df['collected'], errors='coerce')
    df['expiry'] = pd.to_datetime(df['expiry'], errors='coerce')
    df['crossmatched_date'] = pd.to_datetime(df['crossmatched_date'], errors='coerce')
    
    # Fill missing values to maintain data types
    if 'segment_number' in df.columns:
        df['segment_number'] = df['segment_number'].fillna('N/A').astype(str)
    if 'volume' in df.columns:
        df['volume'] = df['volume'].fillna(0).astype(int)
    if 'source' in df.columns:
        df['source'] = df['source'].fillna('Manual Entry').astype(str) # Default updated
    if 'patient_id' in df.columns:
        df['patient_id'] = df['patient_id'].fillna('None').astype(str)
        
    # Ensure the dataframe has the correct final column order
    df = df.reindex(columns=MASTER_COLUMNS, fill_value=None)
    return df

def update_inventory_status(df):
    """Checks expiry dates and updates unit status."""
    today_date_only = datetime.today().date()
    
    expirable_statuses = ['Available', 'Crossmatched']
    
    # Mark as 'Expired'
    df.loc[(df['status'].isin(expirable_statuses)) & (df['expiry'].dt.date <= today_date_only), 'status'] = 'Expired'
    
    return df

def save_data(df):
    """Saves the current DataFrame back to the CSV file."""
    
    # Convert dates to string format
    df['collected'] = df['collected'].dt.strftime('%Y-%m-%d')
    df['expiry'] = df['expiry'].dt.strftime('%Y-%m-%d')
    
    # Replace NaT in crossmatched_date with 'None' before saving
    df['crossmatched_date'] = df['crossmatched_date'].apply(
        lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else 'None'
    )
    
    df.to_csv(INVENTORY_FILE, index=False)
    
# --- Application Initialization ---

if 'inventory_df' not in st.session_state:
    st.session_state['inventory_df'] = load_data()

# Ensure the status is up to date on load
st.session_state['inventory_df'] = update_inventory_status(st.session_state['inventory_df'].copy())

# --- Streamlit UI ---
st.set_page_config(layout="wide", page_title="Blood Unit Management System")

# --- Live Clock Implementation Placeholder ---
clock_placeholder = st.empty()

# --- Header ---
st.title("🏥 Blood Unit Inventory Dashboard")
st.write("---")

# --- Sidebar Filters ---
st.sidebar.header("🔍 Filter Inventory")

all_groups = st.session_state['inventory_df']['blood_group'].dropna().unique().tolist()
all_components = st.session_state['inventory_df']['component'].dropna().unique().tolist()

selected_group = st.sidebar.selectbox("Blood Group", ['All'] + sorted(all_groups))
selected_component = st.sidebar.selectbox("Component", ['All'] + sorted(all_components))

filtered_df = st.session_state['inventory_df'].copy()

if selected_group != 'All':
    filtered_df = filtered_df[filtered_df['blood_group'] == selected_group]
if selected_component != 'All':
    filtered_df = filtered_df[filtered_df['component'] == selected_component]

# --- Metrics (Top of Page) ---
col1, col2, col3, col4 = st.columns(4)

total_units = filtered_df.shape[0]
available_units = filtered_df[filtered_df['status'] == 'Available'].shape[0]
expired_units = filtered_df[filtered_df['status'] == 'Expired'].shape[0]

col1.metric("Total Units", total_units)
col2.metric("Available", available_units)
col3.metric("Expired", expired_units)
col4.metric("Used/Discarded", filtered_df[filtered_df['status'].isin(['Discarded', 'Transfused'])].shape[0])

st.write("---")

# --- Main Tabs for Inventory Views ---
tab1, tab2, tab3, tab4 = st.tabs(["Active Inventory (Edit/Delete)", "Add New Unit", "History (Transfused/Discarded)", "Summary Report"])

with tab1:
    st.header("Active Inventory & Management")
    st.info("The 'Source' field is now free-text input for flexibility.")
    
    active_inventory_df = filtered_df[filtered_df['status'].isin(['Available', 'Crossmatched', 'Expired'])].copy()

    active_inventory_df = active_inventory_df.sort_values(by=['status', 'expiry'], ascending=[False, True])
    
    original_indices = active_inventory_df.index 
    active_inventory_df_display = active_inventory_df.reset_index(drop=True)

    # 1. Use st.data_editor for viewing and allowing editing/deletion
    edited_df_display = st.data_editor(
        active_inventory_df_display,
        key="active_inventory_editor",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "unit_id": st.column_config.Column("Unit ID", disabled=True),
            "segment_number": st.column_config.Column("Segment No."),
            "blood_group": st.column_config.SelectboxColumn("Blood Group", options=sorted(all_groups)),
            "component": st.column_config.SelectboxColumn("Component", options=sorted(all_components)),
            "collected": st.column_config.DateColumn("Collected Date"),
            "expiry": st.column_config.DateColumn("Expiry Date"),
            "volume": st.column_config.NumberColumn("Volume (mL)"),
            "source": st.column_config.Column("Source"), # FIX: Changed to standard Column for free text
            "status": st.column_config.SelectboxColumn("Status", options=['Available', 'Crossmatched', 'Transfused', 'Discarded', 'Expired']),
            "patient_id": st.column_config.Column("Patient ID", help="Required if status is Crossmatched or Transfused."),
            "crossmatched_date": st.column_config.DateColumn("X-match Date"),
        }
    )

    st.write("")
    
    # 2. Save Button Logic
    if st.button("💾 Save All Changes (Updates & Deletions)", type="primary"):
        try:
            edited_df_display.index = original_indices[:len(edited_df_display)]
            df_to_keep = st.session_state['inventory_df'][~st.session_state['inventory_df'].index.isin(original_indices)]
            final_df = pd.concat([df_to_keep, edited_df_display])
            
            final_df['collected'] = pd.to_datetime(final_df['collected'], errors='coerce')
            final_df['expiry'] = pd.to_datetime(final_df['expiry'], errors='coerce')
            final_df['crossmatched_date'] = pd.to_datetime(final_df['crossmatched_date'], errors='coerce')
            
            st.session_state['inventory_df'] = update_inventory_status(final_df)
            save_data(st.session_state['inventory_df'])
            
            st.success("Inventory changes saved successfully!")
            st.experimental_rerun()
            
        except Exception as e:
            st.error(f"An error occurred during save in Active Inventory. Error: {e}")


with tab2:
    st.header("Add New Unit")
    st.write("Use this form to add a new unit to the inventory.")
    
    with st.form("new_unit_form", clear_on_submit=True):
        st.subheader("Unit Details")
        col_id, col_seg, col_vol = st.columns(3)
        unit_id = col_id.text_input("Unit ID (e.g., 251210-A)")
        segment_number = col_seg.text_input("Segment Number")
        volume = col_vol.number_input("Volume (mL)", min_value=1, value=450, step=10)

        col_group, col_comp, col_src = st.columns(3)
        blood_group = col_group.selectbox("Blood Group", sorted(all_groups) if all_groups else ['A+', 'O-', 'AB+'])
        component = col_comp.selectbox("Component", sorted(all_components) if all_components else ['Whole Blood', 'PRBC', 'FFP', 'Platelets'])
        source = col_src.text_input("Source (e.g., Main Hospital, Donor Bus)") # FIX: Changed to text_input
        
        col_coll, col_exp = st.columns(2)
        
        default_collected = datetime.today().date()
        default_expiry = (datetime.today() + timedelta(days=42)).date()
        
        collected_date = col_coll.date_input("Collection Date", value=default_collected)
        expiry_date = col_exp.date_input("Expiry Date", value=default_expiry)
        
        st.write("---")
        st.subheader("Optional: Allocation Details (Unit Status will default to 'Available')")
        
        col_pat, col_xm = st.columns(2)
        patient_id = col_pat.text_input("Allocate to Patient ID (Optional)")
        crossmatch_date = col_xm.date_input("Crossmatch Date (Optional)", value=None)
        
        initial_status = 'Available'
        if patient_id:
            initial_status = 'Crossmatched'

        st.write("---")
        submit_button = st.form_submit_button("➕ Add New Unit to Inventory", type="primary")
        
        if submit_button:
            if not unit_id:
                st.error("Please enter a Unit ID.")
            elif unit_id in st.session_state['inventory_df']['unit_id'].values:
                st.error(f"Unit ID {unit_id} already exists in the inventory.")
            else:
                new_data_dict = {
                    'unit_id': unit_id,
                    'segment_number': segment_number if segment_number else 'N/A',
                    'blood_group': blood_group,
                    'component': component,
                    'collected': collected_date, 
                    'expiry': expiry_date,
                    'volume': volume, 
                    'source': source if source else 'Manual Entry', # Use free text input
                    'status': initial_status,
                    'patient_id': patient_id if patient_id else 'None',
                    'crossmatched_date': crossmatch_date if crossmatch_date else np.datetime64('NaT')
                }

                new_unit_df = pd.DataFrame([new_data_dict], columns=MASTER_COLUMNS)
                
                st.session_state['inventory_df'] = pd.concat([st.session_state['inventory_df'], new_unit_df], ignore_index=True)

                save_data(st.session_state['inventory_df'])

                st.success(f"Unit {unit_id} successfully added and saved! Status: {initial_status}")
                st.experimental_rerun()


with tab3:
    st.header("History: Transfused and Discarded Units")
    st.write("Historical records of units that have left the active inventory.")
    
    transfused_df = filtered_df[filtered_df['status'] == 'Transfused'].copy()
    discarded_df = filtered_df[filtered_df['status'] == 'Discarded'].copy()
    
    st.subheader("✅ Transfused Units")
    if transfused_df.empty:
        st.info("No units have been recorded as Transfused.")
    else:
        st.dataframe(transfused_df, use_container_width=True)

    st.subheader("❌ Discarded Units")
    if discarded_df.empty:
        st.info("No units have been recorded as Discarded.")
    else:
        st.dataframe(discarded_df, use_container_width=True)


with tab4:
    st.header("Inventory Summary Report")
    st.write("High-level overview of available inventory counts by Blood Group and Component.")
    
    summary = filtered_df[filtered_df['status'] == 'Available'].groupby('blood_group')['component'].value_counts().unstack(fill_value=0)
    
    if summary.empty:
        st.info("No available units to generate a summary.")
    else:
        st.dataframe(summary)
        
        
# --- Final Clock Loop ---
# This loop runs forever and updates the clock_placeholder every second.
while True:
    with clock_placeholder:
        current_time = datetime.now().strftime("%A, %B %d, %Y | %I:%M:%S %p")
        st.markdown(f"#### ⏱️ Current Time: **{current_time}**")
    time.sleep(1)
