#!/usr/bin/env python3
"""
Phase 1: Sync Google Sheets to local master.xlsx
Downloads the public Google Sheet and saves it as master.xlsx for version control.
"""

import os
import sys
import logging
import hashlib
from datetime import datetime
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv('config/.env')

# Configure logging
logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

def sync_sheets_to_xlsx(sheet_id, gid, output_path):
    """
    Download Google Sheet and save to xlsx.
    
    Args:
        sheet_id: Google Sheets document ID
        gid: Specific sheet ID within the document (gid=0 for first sheet)
        output_path: Path to write master.xlsx
    
    Returns:
        DataFrame of synced data
    """
    # Google Sheets export URL (CSV format)
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    
    logger.info(f"Fetching Google Sheet: {sheet_id} (gid={gid})")
    
    try:
        df = pd.read_csv(url)
        logger.info(f"Downloaded {len(df)} rows, {len(df.columns)} columns")
        
        # Save to xlsx
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(output_path, index=False)
        logger.info(f"Saved to {output_path}")
        
        return df
    except Exception as e:
        logger.error(f"Failed to sync Google Sheet: {e}")
        raise

def compute_row_fingerprint(row):
    """Generate MD5 hash of row for change detection."""
    row_str = '|'.join([str(v) for v in row])
    return hashlib.md5(row_str.encode()).hexdigest()

def detect_changes(old_df, new_df):
    """Detect added, modified, and deleted rows between two dataframes."""
    added = new_df[~new_df.index.isin(old_df.index)]
    deleted = old_df[~old_df.index.isin(new_df.index)]
    
    # Simplified: rows with same index but different values
    common_idx = old_df.index.intersection(new_df.index)
    modified = new_df.loc[common_idx][~new_df.loc[common_idx].eq(old_df.loc[common_idx]).all(axis=1)]
    
    return {
        'added': len(added),
        'modified': len(modified),
        'deleted': len(deleted)
    }

def main():
    sheet_id = os.getenv('GOOGLE_SHEETS_WORKSHEET_ID')
    gid = os.getenv('GOOGLE_SHEET_GID', '637738347')
    output_path = 'data/master.xlsx'
    
    if not sheet_id:
        logger.error("GOOGLE_SHEETS_WORKSHEET_ID not set in environment")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("Phase 1: Sync Google Sheets → master.xlsx")
    logger.info("=" * 60)
    
    df = sync_sheets_to_xlsx(sheet_id, gid, output_path)
    
    logger.info(f"✓ Synced {len(df)} episodes")
    logger.info("=" * 60)

if __name__ == '__main__':
    main()
