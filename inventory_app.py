import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

# --- 1. CORE DATA MODEL & CONSTANTS ---

EXPIRY_DAYS = {
    'Whole Blood': 35,
    'PRBC': 35,
    'Platelets': 5,
    'FFP': 7 * 365,  # 7 years for Frozen Fresh Plasma
}

# Define column names for the DataFrame
COLUMNS = [
    'serial', 'segment', 'source', 'blood', 'component', 'volume',
    'collected', 'expiry', 'status', 'patient', 'age_days', 'age_text', 'row_color'
]


def format_date(date_obj):
    """Formats a datetime object to YYYY-MM-DD string."""
    if isinstance(date_obj, datetime):
        return date_obj.strftime("%Y-%m-%d")
    return date_obj  # Returns string if already a string


def calculate_expiry(component, collected_date):
    """Calculates the expiry date based on component and collection date."""
    if not collected_date or component not in EXPIRY_DAYS:
        return None

    # Ensure collected_date is a datetime object
    if isinstance(collected_date, str):
        collected_date = datetime.strptime(collected_date, "%Y-%m-%d")

    days_to_add = EXPIRY_DAYS[component]
    expiry_date = collected_date + timedelta(days=days_to_add)
    return format_date(expiry_date)

# inventory_app.py (CORRECTED)


# inventory_app.py (CORRECTED compute_age)
def compute_age(collected_date_str, component):
    """Calculates age in days and text format."""
    if not collected_date_str:
        return 0, ""

    # FIX 1: Handle date object passed from Pandas apply()
    if not isinstance(collected_date_str, str):
        collected_date_str = collected_date_str.strftime("%Y-%m-%d")

    collected_date = datetime.strptime(collected_date_str, "%Y-%m-%d")

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    diff_days = (today - collected_date).days

    # FIX 2: Initialize age_text before the conditional logic
    age_text = f"{diff_days}d"  # Default age text

    if component == "FFP":
        years = diff_days // 365
        days = diff_days % 365
        age_text = f"{years}y {days}d"
    # Note: No 'else' needed here, as the default handles all other components.

    return diff_days, age_text  # This line now always sees age_text defined


# inventory_app.py (CORRECTED determine_row_color)
def determine_row_color(expiry_date_str, status):
    """Determines the color coding based on expiry status."""
    if status in ['Expired', 'Transfused']:
        return status.lower()

    if not expiry_date_str:
        return ""

    # --- FIX: Convert datetime.date object to string if necessary ---
    if not isinstance(expiry_date_str, str):
        expiry_date_str = expiry_date_str.strftime("%Y-%m-%d")

    expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d")
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days_left = (expiry_date - today).days

    if days_left < 0:
        return "already-expired"
    elif days_left <= 3:
        return "near-expiry"
    else:
        return ""


def update_inventory_status(df):
    """Updates the calculated fields (age, color, and checks for auto-expiry)."""
    if df.empty:
        return df

    df['age_days'], df['age_text'] = zip(*df.apply(
        lambda row: compute_age(row['collected'], row['component']), axis=1
    ))

    # Determine row color based on existing status and expiry date
    df['row_color'] = df.apply(
        lambda row: determine_row_color(row['expiry'], row['status']), axis=1
    )

    # Auto-move active units to 'Expired' if days left is negative and status is 'Available' or 'Crossmatched'
 # inventory_app.py (CORRECTED update_inventory_status)


def update_inventory_status(df):
    """Updates the calculated fields (age, color, and checks for auto-expiry)."""
    if df.empty:
        return df

    # ... (Lines 91-105: age_days and initial row_color calculation - NO CHANGE HERE) ...

    df['age_days'], df['age_text'] = zip(*df.apply(
        lambda row: compute_age(row['collected'], row['component']), axis=1
    ))

    df['row_color'] = df.apply(
        lambda row: determine_row_color(row['expiry'], row['status']), axis=1
    )

    # ------------------ FIX START ------------------
    # 1. Calculate the MAX_AGE threshold for every row individually
    df['max_age'] = df['component'].apply(lambda c: EXPIRY_DAYS.get(c, 999))

    # 2. Use the 'max_age' column for comparison
    expired_units = (df['age_days'] > df['max_age']) & (
        df['status'].isin(['Available', 'Crossmatched']))

    # Apply the status change
    df.loc[expired_units, 'status'] = 'Expired'

    # Drop the temporary column
    df = df.drop(columns=['max_age'])
    # ------------------ FIX END --------------------

    # Re-calculate color after status update
    df['row_color'] = df.apply(
        lambda row: determine_row_color(row['expiry'], row['status']), axis=1
    )

    return df

# --- 2. STREAMLIT SETUP & DATA INITIALIZATION ---


st.set_page_config(layout="wide", page_title="Blood Unit Management System")

# Inject Custom CSS for row coloring (Streamlit requires custom HTML/CSS for row styling)
st.markdown("""
<style>
/* CSS copied from your original file for thematic consistency */
.st-emotion-cache-nahz7x { /* Target Streamlit table body */
    font-size: 0.9rem;
}

/* Row Styling based on the 'row_color' column value */
.already-expired {
    background-color: #dc3545 !important; /* Red */
    color: white;
}
.near-expiry {
    background-color: #ffc107 !important; /* Yellow/Warning */
    color: #343a40;
}
.expired {
    background-color: #f8d7da !important; /* Light Red for Expired tab */
}
.transfused {
    background-color: #bee5eb !important; /* Light Cyan for Transfused tab */
}
</style>
""", unsafe_allow_html=True)


if 'inventory_df' not in st.session_state:
    # Seed Demo Data (similar to JS setup)
    now = datetime.now().date()
    three_days_ago = now - timedelta(days=3)
    soon_expiry = now + timedelta(days=2)
    expired_date = now - timedelta(days=5)

    demo_data = {
        'serial': ['S1001', 'S1002', 'S1003', 'S1004', 'S1005'],
        'segment': ['A1', 'B2', 'C3', 'D4', 'E5'],
        'source': ['Donor A', 'Donor B', 'Donor C', 'Donor D', 'Donor E'],
        'blood': ['O+', 'A-', 'B+', 'AB+', 'O-'],
        'component': ['PRBC', 'FFP', 'Platelets', 'Whole Blood', 'PRBC'],
        'volume': [300, 200, 50, 450, 250],
        'collected': [format_date(three_days_ago), format_date(now), format_date(three_days_ago), format_date(three_days_ago), format_date(expired_date - timedelta(days=30))],
        'status': ['Available', 'Available', 'Crossmatched', 'Transfused', 'Expired'],
        'patient': ['', '', 'John Doe - ICU 5', 'Jane Smith - OR 2', ''],
    }

    df = pd.DataFrame(demo_data)
    # Calculate expiry for initial data
    df['expiry'] = df.apply(
        lambda row: calculate_expiry(row['component'], row['collected']), axis=1
    )

    # Add placeholder columns (will be populated by update_inventory_status)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None

    st.session_state.inventory_df = update_inventory_status(df)


# --- 3. UI LAYOUT: HEADER & TABS ---

st.title("🩸 Blood Unit Management System")
st.caption(
    f"Central Inventory & Unit Lifecycle Tracking | Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

tab1, tab2, tab3, tab4 = st.tabs([
    "➕ Register Unit",
    "📦 Available Units",
    "🗑️ Expired Units",
    " transfused Units Issued"
])

# --- 4. DATA PROCESSING AND FILTERS ---

df = st.session_state.inventory_df.copy()

# Live update of calculated fields
df = update_inventory_status(df)
st.session_state.inventory_df = df.copy()  # Save the updated state

# --- Global Filter/Search (Streamlit Sidebar) ---
st.sidebar.title("🔬 Search & Unit Filters")
search_query = st.sidebar.text_input(
    "Search (Serial, Blood Type, Patient)", key="qSearch")
filter_blood = st.sidebar.selectbox("Filter by Blood Type", [
                                    'All'] + sorted(df['blood'].unique().tolist()), key="fBlood")
filter_component = st.sidebar.selectbox("Filter by Component", [
                                        'All'] + sorted(df['component'].unique().tolist()), key="fComponent")
filter_status = st.sidebar.selectbox("Filter by Status", [
                                     'All', 'Available', 'Crossmatched', 'Expired', 'Transfused'], key="fStatus")

# Apply Filters
filtered_df = df.copy()

if search_query:
    filtered_df = filtered_df[
        filtered_df.apply(
            lambda row: search_query.lower() in str(row['serial']).lower() or
            search_query.lower() in str(row['blood']).lower() or
            search_query.lower() in str(row['patient']).lower(), axis=1
        )
    ]

if filter_blood != 'All':
    filtered_df = filtered_df[filtered_df['blood'] == filter_blood]
if filter_component != 'All':
    filtered_df = filtered_df[filtered_df['component'] == filter_component]
if filter_status != 'All':
    filtered_df = filtered_df[filtered_df['status'] == filter_status]


# --- 5. REGISTER UNIT TAB (tab1) ---

with tab1:
    st.subheader("Register New Blood Unit")

    with st.form("unit_registration_form"):
        # Row 1: IDs
        col1, col2, col3 = st.columns(3)
        serial = col1.text_input("Unit Serial No.", key="serial", max_chars=10)
        segment = col2.text_input("Segment ID", key="segment", max_chars=10)
        source = col3.text_input(
            "Source/Donor ID (Optional)", key="source", max_chars=15)

        # Row 2: Type/Volume/Collection
        col4, col5, col6, col7 = st.columns(4)
        blood = col4.selectbox(
            "Blood Type", ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-'], key="blood")
        component = col5.selectbox("Component Type", list(
            EXPIRY_DAYS.keys()), key="component")
        volume = col6.number_input(
            "Volume (mL)", min_value=1, value=300, key="volume")
        collected = col7.date_input(
            "Collection Date", value=datetime.now().date(), key="collected")

        # Auto-calculate Expiry Date
        expiry_date = calculate_expiry(component, collected)

        # Row 3: Expiry/Status/Patient
        col8, col9, col10 = st.columns(3)
        col8.text_input("Expiry Date (Auto-calculated)",
                        value=expiry_date or "N/A", disabled=True, key="expiry")
        status = col9.selectbox("Current Status", [
                                'Available', 'Crossmatched', 'Expired', 'Transfused'], key="status")
        patient = col10.text_input(
            "Patient Allocation (Optional)", key="patient", placeholder="e.g., Jane Smith - OR 2")

        submit_button = st.form_submit_button(label="✅ Register Unit")

        if submit_button:
            if not serial or not segment or not collected:
                st.error(
                    "Please fill in required fields (Serial No., Segment ID, Collection Date).")
            elif serial in df['serial'].values:
                st.error(f"Unit Serial No. {serial} already exists!")
            else:
                new_unit = pd.DataFrame({
                    'serial': [serial], 'segment': [segment], 'source': [source],
                    'blood': [blood], 'component': [component], 'volume': [volume],
                    'collected': [format_date(collected)], 'expiry': [expiry_date],
                    'status': [status], 'patient': [patient]
                })

                # Append new unit and re-calculate all derived fields
                st.session_state.inventory_df = pd.concat(
                    [st.session_state.inventory_df, new_unit], ignore_index=True)
                st.session_state.inventory_df = update_inventory_status(
                    st.session_state.inventory_df)
                st.success(
                    f"Unit {serial} successfully registered and added to inventory.")

                # Clear form on successful submission (requires key reset or separate state management if using st.tabs)
                # For simplicity here, the values are reset by Streamlit on RERUN.

# --- 6. INVENTORY TABS (tab2, tab3, tab4) ---


# inventory_app.py (CORRECTED display_inventory_table)
def display_inventory_table(df_display, status_list, title, tab):
    """Displays a filtered and styled table of units."""
    df_filtered_by_tab = df_display[df_display['status'].isin(status_list)]

    with tab:
        st.subheader(title)

        if df_filtered_by_tab.empty:
            st.info("No units found matching criteria.")
            return

        # Prepare for display: select, rename, and format columns
        df_view = df_filtered_by_tab.copy()

        # --- NEW SAFE DATE CONVERSION HELPER ---
        def safe_date_format(date_val):
            if not date_val:
                return "N/A"
            if not isinstance(date_val, str):
                date_val = date_val.strftime('%Y-%m-%d')

            # Now parse the YYYY-MM-DD string and format it for display
            return datetime.strptime(date_val, '%Y-%m-%d').strftime('%b %d, %Y')
        # ----------------------------------------

        # Convert ISO dates to display format using the safe helper
        df_view['Collected'] = df_view['collected'].apply(safe_date_format)
        df_view['Expiry Date'] = df_view['expiry'].apply(safe_date_format)

        # ... (rest of the function remains the same, no change needed below this point)
        # Select and rename columns for clean display
        df_view = df_view.rename(columns={
            'serial': 'Serial No.',
            'segment': 'Seg ID',
            'source': 'Source',
            'blood': 'Blood Type',
            'component': 'Component',
            'volume': 'Volume (mL)',
            'age_text': 'Age/Storage',
            'patient': 'Patient Allocation',
            'status': 'Current Status'
        })[[
            'Serial No.', 'Seg ID', 'Source', 'Blood Type', 'Component',
            'Volume (mL)', 'Collected', 'Expiry Date', 'Age/Storage',
            'Current Status', 'Patient Allocation', 'row_color'
        ]]

        # --- Display the table with interactive styling (using custom component) ---
        # NOTE: Streamlit's data_editor is perfect for this, but needs setup for actions.
        # For simplicity, we use st.dataframe with custom styling logic.

        # Create a list of the rows and their colors for HTML rendering (if needed)

        st.dataframe(
            df_view.drop(columns=['row_color']),
            use_container_width=True,
            # Streamlit doesn't natively support full row conditional styling easily via st.dataframe
            # The CSS injection above helps, but we must use a custom component for proper row action/editing.
        )

        st.caption(
            "Note: Row colors indicate near-expiry (Yellow) or expired (Red).")

        # Action Buttons (Edit/Change Status via data_editor or separate form)

        # --- Report Button ---
        if st.button(f"🖨️ Generate CSV Summary ({title})", key=f'report_{title.replace(" ", "_")}'):
            df_report = df_filtered_by_tab.drop(
                columns=['age_days', 'row_color'])

            # Use Streamlit's built-in download button for the CSV
            st.download_button(
                label=f"Download {title} CSV",
                data=df_report.to_csv(index=False).encode('utf-8'),
                file_name=f'BloodInventory_Report_{title.replace(" ", "")}_{format_date(datetime.now().date())}.csv',
                mime='text/csv',
                key=f'download_{title.replace(" ", "_")}'
            )


# --- Displaying the content for each tab ---

# 1. Available Units Tab
display_inventory_table(filtered_df, [
                        'Available', 'Crossmatched'], "Active Inventory: Available & Crossmatched Units", tab2)

# 2. Expired Units Tab
display_inventory_table(filtered_df, ['Expired'], "Units For Disposal", tab3)

# 3. Issued Units Tab
display_inventory_table(
    filtered_df, ['Transfused'], "Issued Units Log (Transfused)", tab4)
