#!/usr/bin/env python3
"""
Orchestrate the complete pipeline: sync, load, normalize, enrich, validate.
Run this weekly to keep the database updated.
"""

import os
import sys
import logging
import subprocess
from datetime import datetime
from pathlib import Path

# Configure logging
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"orchestrate_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).parent

def run_step(step_num, script_name, description):
    """Run a pipeline step script."""
    script_path = SCRIPTS_DIR / script_name
    
    logger.info("=" * 70)
    logger.info(f"[{step_num}/6] {description}")
    logger.info("=" * 70)
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(SCRIPTS_DIR.parent),
            capture_output=False
        )
        
        if result.returncode != 0:
            logger.error(f"✗ Step {step_num} failed with exit code {result.returncode}")
            return False
        
        logger.info(f"✓ Step {step_num} completed")
        return True
    
    except Exception as e:
        logger.error(f"✗ Step {step_num} error: {e}")
        return False

def main():
    logger.info("=" * 70)
    logger.info("REWATCHABLES PIPELINE: FULL ORCHESTRATION")
    logger.info(f"Started: {datetime.utcnow().isoformat()}")
    logger.info("=" * 70)
    
    steps = [
        (1, '01_sync_sheets.py', 'Sync Google Sheets → master.xlsx'),
        (2, '02_load_raw.py', 'Load raw zone from master.xlsx'),
        (3, '03_normalize_and_resolve.py', 'Normalize and resolve movie keys'),
        (4, '04_enrich.py', 'Enrich from APIs (TMDB, Wiki, Wikidata)'),
        (5, '05_validate.py', 'Validate data quality'),
    ]
    
    results = []
    for step_num, script, desc in steps:
        success = run_step(step_num, script, desc)
        results.append((step_num, desc, success))
        
        if not success:
            logger.error(f"\n✗ Pipeline halted at step {step_num}")
            break
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("PIPELINE SUMMARY")
    logger.info("=" * 70)
    
    for step_num, desc, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        logger.info(f"Step {step_num}: {status} - {desc}")
    
    overall_success = all(s[2] for s in results)
    
    if overall_success:
        logger.info("\n✓ PIPELINE COMPLETED SUCCESSFULLY")
        logger.info(f"Log file: {log_file}")
        return 0
    else:
        logger.error("\n✗ PIPELINE FAILED")
        logger.info(f"Log file: {log_file}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
