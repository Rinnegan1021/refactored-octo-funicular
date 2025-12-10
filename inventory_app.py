import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date 
import os
import time 
import numpy as np 

# --- Configuration ---
INVENTORY_FILE = 'df.csv'
DATE_FORMAT_STRING = '%m/%d/%Y' # Standard Date Format: MM/DD/YYYY
DATE_DISPLAY_FORMAT = 'MM/DD/YYYY' # Streamlit Display Format
# Define the master column order for consistency
MASTER_COLUMNS = [
    'unit_id', 'segment_number', 'blood_group', 'component', 'collected', 'expiry', 
    'volume', 'source', 
    'status', 'patient_id', 'crossmatched_date' 
]

# --- Utility Functions ---

def calculate_expiry_date(collected_date, component):
    """Calculates the expiry date based on the component and collected date."""
    if collected_date is None:
        return datetime.today().date()
    
    if isinstance(collected_date, datetime):
        collected_date = collected_date.date()
    
    if component in ['PRBC', 'Whole Blood']:
        return collected_date + timedelta(days=35)
    elif component == 'Platelets':
        return collected_date + timedelta(days=5)
    elif component == 'FFP':
        return collected_date + timedelta(days=7 * 365 + 1)
    else:
        return collected_date + timedelta(days=42)

def load_data():
    """Loads or initializes the inventory DataFrame."""
    if os.path.exists(INVENTORY_FILE):
        df = pd.read_csv(INVENTORY_FILE)
    else:
        df = pd.DataFrame(columns=MASTER_COLUMNS)
    
    try:
        df['collected'] = pd.to_datetime(df['collected'], format=DATE_FORMAT_STRING, errors='coerce')
        df['expiry'] = pd.to_datetime(df['expiry'], format=DATE_FORMAT_STRING, errors='coerce')
        df['crossmatched_date'] = df['crossmatched_date'].replace('None', np.nan)
        df['crossmatched_date'] = pd.to_datetime(df['crossmatched_date'], format=DATE_FORMAT_STRING, errors='coerce')
    except Exception as e:
        st.warning(f"Error loading dates: {e}. Defaulting to empty dates.")
        df['collected'] = pd.NaT
        df['expiry'] = pd.NaT
        df['crossmatched_date'] = pd.NaT

    if 'segment_number' in df.columns:
        df['segment_number'] = df['segment_number'].fillna('N/A').astype(str)
    if 'volume' in df.columns:
        df['volume'] = df['volume'].fillna(0).astype(int)
    if 'source' in df.columns:
        df['source'] = df['source'].fillna('Manual Entry').astype(str)
    if 'patient_id' in df.columns:
        df['patient_id'] = df['patient_id'].fillna('None').astype(str)
        
    df = df.reindex(columns=MASTER_COLUMNS, fill_value=None)
    return df

def update_inventory_status(df):
    """Checks expiry dates and updates unit status."""
    today_date_only = datetime.today().date()
    expirable_statuses = ['Available', 'Crossmatched']
    df.loc[(df['status'].isin(expirable_statuses)) & (df['expiry'].dt.date <= today_date_only), 'status'] = 'Expired'
    return df

def save_data(df):
    """Saves the current DataFrame back to the CSV file using the specified format."""
    
    # CRITICAL FIX 1: Explicitly handle NaT values to 'None' string before saving
    def date_to_string(d):
        if pd.isna(d):
            return 'None'
        try:
            return d.strftime(DATE_FORMAT_STRING)
        except:
            return 'None' # Fallback for non-datetime objects that are also not NaT
    
    df['collected'] = df['collected'].apply(date_to_string)
    df['expiry'] = df['expiry'].apply(date_to_string)
    df['crossmatched_date'] = df['crossmatched_date'].apply(date_to_string)
    
    df.to_csv(INVENTORY_FILE, index=False)
    
# --- Application Initialization ---

if 'inventory_df' not in st.session_state:
    st.session_state['inventory_df'] = load_data()

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
    st.info("All dates are in MM/DD/YYYY format. Set sidebar filters to 'All' to see all units.")
    
    active_inventory_df = filtered_df[filtered_df['status'].isin(['Available', 'Crossmatched', 'Expired'])].copy()

    active_inventory_df = active_inventory_df.sort_values(by=['status', 'expiry'], ascending=[False, True])
    
    original_indices = active_inventory_df.index 
    active_inventory_df_display = active_inventory_df.reset_index(drop=True)

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
            "collected": st.column_config.DateColumn("Collected Date", format=DATE_DISPLAY_FORMAT),
            "expiry": st.column_config.DateColumn("Expiry Date", format=DATE_DISPLAY_FORMAT),
            "volume": st.column_config.NumberColumn("Volume (mL)"),
            "source": st.column_config.Column("Source"),
            "status": st.column_config.SelectboxColumn("Status", options=['Available', 'Crossmatched', 'Transfused', 'Discarded', 'Expired']),
            "patient_id": st.column_config.Column("Patient ID", help="Required if status is Crossmatched or Transfused."),
            "crossmatched_date": st.column_config.DateColumn("X-match Date", format=DATE_DISPLAY_FORMAT),
        }
    )

    st.write("")
    
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
            st.exception(e)


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
        
        selected_component_for_calc = col_comp.selectbox(
            "Component", 
            sorted(all_components) if all_components else ['Whole Blood', 'PRBC', 'FFP', 'Platelets'],
            key='add_unit_component_select'
        )
        source = col_src.text_input("Source (e.g., Main Hospital, Donor Bus)")
        
        col_coll, col_exp = st.columns(2)
        
        default_collected = datetime.today().date()
        
        collected_date = col_coll.date_input("Collection Date", value=default_collected, key='collected_date_input')
        
        calculated_expiry = calculate_expiry_date(collected_date, selected_component_for_calc)
        
        expiry_date = col_exp.date_input(
            "Expiry Date (Auto-calculated, Edit if necessary)", 
            value=calculated_expiry, 
            key='expiry_date_input'
        )
        
        st.write("---")
        st.subheader("Optional: Allocation Details")
        
        col_pat, col_xm = st.columns(2)
        patient_id = col_pat.text_input("Allocate to Patient ID (Optional)")
        crossmatch_date = col_xm.date_input("Crossmatch Date (Optional)", value=None)
        
        initial_status = 'Available'
        if patient_id:
            initial_status = 'Crossmatched'

        st.write("---")
        submit_button = st.form_submit_button("➕ Add New Unit to Inventory", type="primary")
        
        if submit_button:
            try:
                if not unit_id:
                    st.error("Please enter a Unit ID.")
                elif unit_id in st.session_state['inventory_df']['unit_id'].values:
                    st.error(f"Unit ID {unit_id} already exists in the inventory.")
                else:
                    # CRITICAL FIX 2: Define a robust string conversion for the form data
                    def date_input_to_string(d):
                        if d is None:
                            return 'None'
                        # Handle both date and datetime objects
                        if isinstance(d, datetime) or isinstance(d, date):
                             return d.strftime(DATE_FORMAT_STRING)
                        return 'None'
                        
                    new_data_dict = {
                        'unit_id': unit_id,
                        'segment_number': segment_number if segment_number else 'N/A',
                        'blood_group': blood_group,
                        'component': selected_component_for_calc,
                        'collected': date_input_to_string(collected_date), 
                        'expiry': date_input_to_string(expiry_date),
                        'volume': volume, 
                        'source': source if source else 'Manual Entry',
                        'status': initial_status,
                        'patient_id': patient_id if patient_id else 'None',
                        'crossmatched_date': date_input_to_string(crossmatch_date)
                    }

                    new_unit_df = pd.DataFrame([new_data_dict], columns=MASTER_COLUMNS)
                    
                    # Temporarily load the current state, ensuring all existing data is string formatted for clean concatenation
                    temp_current_df = st.session_state['inventory_df'].copy()
                    temp_current_df['collected'] = temp_current_df['collected'].apply(lambda x: x.strftime(DATE_FORMAT_STRING) if pd.notna(x) else 'None')
                    temp_current_df['expiry'] = temp_current_df['expiry'].apply(lambda x: x.strftime(DATE_FORMAT_STRING) if pd.notna(x) else 'None')
                    temp_current_df['crossmatched_date'] = temp_current_df['crossmatched_date'].apply(lambda x: x.strftime(DATE_FORMAT_STRING) if pd.notna(x) else 'None')
                    
                    final_concatenated_df = pd.concat([temp_current_df, new_unit_df], ignore_index=True)
                    
                    # Save the new, string-formatted DataFrame
                    save_data(final_concatenated_df) 
                    
                    st.success(f"Unit {unit_id} successfully added and saved! Status: {initial_status}")
                    st.experimental_rerun()
            except Exception as e:
                st.error(f"An error occurred while adding the unit. **Please check the full traceback below and send me the error message!**")
                st.exception(e) # Display full traceback
                
# ... (Tab 3 and Tab 4 remain unchanged)

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
while True:
    with clock_placeholder:
        st.markdown(f"#### ⏱️ Current Time: **{datetime.now().strftime(f'{DATE_FORMAT_STRING} | %I:%M:%S %p')}**")
    time.sleep(1)
