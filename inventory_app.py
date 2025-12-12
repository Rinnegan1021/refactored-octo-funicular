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
    """Calculates the expiry date based on the component and collected date."""
    if collected_date is None or pd.isna(collected_date):
        return None
    
    if isinstance(collected_date, datetime):
        collected_date = collected_date.date()
    
    if component in ['PRBC', 'Whole Blood']:
        return collected_date + timedelta(days=42) 
    elif component == 'Platelets':
        return collected_date + timedelta(days=5)
    elif component == 'FFP':
        # FFP has a long shelf life, e.g., 7 years + 1 day
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
        else:
            df = pd.DataFrame(columns=COLUMN_NAMES)
    except Exception as e:
        # Fallback to empty DataFrame on read error
        df = pd.DataFrame(columns=COLUMN_NAMES)
        
    # 1. ENFORCE COLUMN STRUCTURE
    # Add missing columns with default values and remove unknown columns
    df = df.reindex(columns=COLUMN_NAMES)
    
    # 2. DATA CLEANUP & TYPE COERCION
    
    # Text Columns Cleanup (Fill NaNs with 'None', convert to string)
    for col in ['serial', 'segment', 'source', 'blood_type', 'component', 'status', 'patient', 'age']:
        if col in df.columns:
            # Replace common bad values with NaN, then fill NaN with 'None'
            df[col] = df[col].replace(['', 'None', 'nan', 'NaN'], np.nan).fillna('None').astype(str)
        
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
    
    # 3. RE-CALCULATE AGE and STATUS
    df['age'] = df.apply(lambda row: compute_age_text(row['collected'], row['component']), axis=1)
    df = update_inventory_status(df)
        
    return df

def update_inventory_status(df):
    """Checks expiry dates and updates unit status."""
    today_date_only = datetime.today().date()
    expirable_statuses = ['Available', 'Crossmatched']
    
    if 'expiry' in df.columns and not df['expiry'].isnull().all():
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
    
    return [''] * len(
