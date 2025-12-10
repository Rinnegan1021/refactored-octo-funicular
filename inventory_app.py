import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

# --- Configuration ---
# Use the current directory for the CSV file
INVENTORY_FILE = 'df.csv'

# --- Utility Functions ---

def load_data():
    """Loads or initializes the inventory DataFrame."""
    if os.path.exists(INVENTORY_FILE):
        df = pd.read_csv(INVENTORY_FILE)
    else:
        # Initialize with required columns if file doesn't exist
        df = pd.DataFrame(columns=[
            'unit_id', 'blood_group', 'component', 'collected', 'expiry', 
            'status', 'patient_id', 'crossmatched_date'
        ])
    
    # Ensure date columns are proper datetime objects
    df['collected'] = pd.to_datetime(df['collected'], errors='coerce')
    df['expiry'] = pd.to_datetime(df['expiry'], errors='coerce')
    
    return df

def update_inventory_status(df):
    """Checks expiry dates and updates unit status."""
    today = datetime.now()
    
    # Mark as 'Expired'
    # Units must be Available or Crossmatched to expire (not already Discarded/Transfused)
    expirable_statuses = ['Available', 'Crossmatched']
    df.loc[(df['status'].isin(expirable_statuses)) & (df['expiry'] < today), 'status'] = 'Expired'
    
    return df

def save_data(df):
    """Saves the current DataFrame back to the CSV file."""
    # Ensure dates are in YYYY-MM-DD string format before saving
    df['collected'] = df['collected'].dt.strftime('%Y-%m-%d')
    df['expiry'] = df['expiry'].dt.strftime('%Y-%m-%d')
    df.to_csv(INVENTORY_FILE, index=False)
    
# --- Application Initialization ---

# Load data and store it in Streamlit's session state
if 'inventory_df' not in st.session_state:
    st.session_state['inventory_df'] = load_data()

# Update statuses whenever the app runs
st.session_state['inventory_df'] = update_inventory_status(st.session_state['inventory_df'].copy())

# --- Streamlit UI ---
st.set_page_config(layout="wide", page_title="Blood Unit Management System")
st.title("🏥 Blood Unit Inventory Dashboard")
st.write("---")

# --- Sidebar Filters ---
st.sidebar.header("🔍 Filter Inventory")

# Get unique, sorted lists for filters (handle case where no data exists yet)
all_groups = st.session_state['inventory_df']['blood_group'].dropna().unique().tolist()
all_components = st.session_state['inventory_df']['component'].dropna().unique().tolist()

selected_group = st.sidebar.selectbox("Blood Group", ['All'] + sorted(all_groups))
selected_component = st.sidebar.selectbox("Component", ['All'] + sorted(all_components))

# Apply filters
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
col4.metric("Discarded/Used", filtered_df[filtered_df['status'].isin(['Discarded', 'Transfused'])].shape[0])

st.write("---")

# --- Main Tabs for Inventory Views ---
tab1, tab2, tab3, tab4 = st.tabs(["Active Inventory (Edit/Delete)", "Add New Unit", "Discarded/Used", "Summary Report"])

with tab1:
    st.header("Active Inventory & Management")
    st.info("Edit any cell or use the trash can icon on the left to delete rows. Click 'Save Changes' to finalize.")
    
    # Filter for active/expiring units only (Available, Crossmatched, Expired)
    active_inventory_df = filtered_df[filtered_df['status'].isin(['Available', 'Crossmatched', 'Expired'])].copy()

    # Sort to show Expired at the top for immediate attention
    active_inventory_df = active_inventory_df.sort_values(by=['status', 'expiry'], ascending=[False, True])
    
    # Temporarily reset index for clean display, but store the original indices
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
            "blood_group": st.column_config.SelectboxColumn("Blood Group", options=sorted(all_groups)),
            "component": st.column_config.SelectboxColumn("Component", options=sorted(all_components)),
            "collected": st.column_config.DateColumn("Collected Date"),
            "expiry": st.column_config.DateColumn("Expiry Date"),
            "status": st.column_config.SelectboxColumn("Status", options=['Available', 'Crossmatched', 'Transfused', 'Discarded', 'Expired'])
        }
    )

    st.write("") # Add space
    
    # 2. Save Button Logic
    if st.button("💾 Save All Changes (Updates & Deletions)", type="primary"):
        try:
            # Map the remaining edited rows back to their original index for merging
            # This handles deletions, as deleted rows won't be in edited_df_display
            edited_df_display.index = original_indices[:len(edited_df_display)]
            
            # Identify the rows NOT shown in this editor tab (e.g., 'Transfused', 'Discarded', or units filtered out)
            df_to_keep = st.session_state['inventory_df'][~st.session_state['inventory_df'].index.isin(original_indices)]
            
            # Combine the kept data with the newly edited/retained data from the editor
            final_df = pd.concat([df_to_keep, edited_df_display])
            
            # Re-ensure date formats are correct after editing
            final_df['collected'] = pd.to_datetime(final_df['collected'], errors='coerce')
            final_df['expiry'] = pd.to_datetime(final_df['expiry'], errors='coerce')
            
            # Update the status, save, and rerun
            st.session_state['inventory_df'] = update_inventory_status(final_df)
            save_data(st.session_state['inventory_df'])
            
            st.success("Inventory changes saved successfully!")
            st.experimental_rerun()
            
        except Exception as e:
            st.error(f"An error occurred during save. Please check your date formats or data integrity. Error: {e}")


with tab2:
    st.header("Add New Unit")
    st.write("Use this form to add a new unit to the inventory.")
    
    # Use st.form for grouping inputs and preventing excessive reruns
    with st.form("new_unit_form", clear_on_submit=True):
        col_id, col_group, col_comp = st.columns(3)
        
        unit_id = col_id.text_input("Unit ID (e.g., 251210-A)")
        blood_group = col_group.selectbox("Blood Group", sorted(all_groups) if all_groups else ['A+', 'O-', 'AB+'])
        component = col_comp.selectbox("Component", sorted(all_components) if all_components else ['Whole Blood', 'PRBC', 'FFP', 'Platelets'])
        
        col_coll, col_exp = st.columns(2)
        
        # Default collection date to today, default expiry 42 days later for PRBC (a common lifespan)
        default_collected = datetime.now().date()
        default_expiry = (datetime.now() + timedelta(days=42)).date()
        
        collected_date = col_coll.date_input("Collection Date", value=default_collected)
        expiry_date = col_exp.date_input("Expiry Date", value=default_expiry)
        
        st.write("---")
        submit_button = st.form_submit_button("➕ Add New Unit to Inventory", type="primary")
        
        if submit_button:
            # Simple validation check
            if not unit_id:
                st.error("Please enter a Unit ID.")
            elif unit_id in st.session_state['inventory_df']['unit_id'].values:
                st.error(f"Unit ID {unit_id} already exists in the inventory.")
            else:
                # 1. Create the new row data
                new_data = {
                    'unit_id': unit_id,
                    'blood_group': blood_group,
                    'component': component,
                    'collected': collected_date, 
                    'expiry': expiry_date,
                    'status': 'Available',
                    'patient_id': 'None',
                    'crossmatched_date': pd.NaT 
                }

                # 2. Append to the main inventory DataFrame
                new_unit_df = pd.DataFrame([new_data])
                st.session_state['inventory_df'] = pd.concat([st.session_state['inventory_df'], new_unit_df], ignore_index=True)

                # 3. Save the updated DataFrame to the CSV file
                save_data(st.session_state['inventory_df'])

                st.success(f"Unit {unit_id} successfully added and saved!")
                st.experimental_rerun()


with tab3:
    st.header("Discarded & Transfused Units")
    st.write("Units in the 'Discarded' or 'Transfused' status are shown here for historical reference.")
    
    # Filter for used/discarded units
    history_df = filtered_df[filtered_df['status'].isin(['Discarded', 'Transfused'])].copy()
    
    # No editing/deleting here for data integrity
    st.dataframe(history_df, use_container_width=True)


with tab4:
    st.header("Inventory Summary Report")
    st.write("High-level overview of available inventory counts by Blood Group and Component.")
    
    # Pivot table to summarize counts by group and component
    summary = filtered_df[filtered_df['status'] == 'Available'].groupby('blood_group')['component'].value_counts().unstack(fill_value=0)
    
    st.dataframe(summary)
