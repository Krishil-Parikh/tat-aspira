"""
database/init_demo.py — Complete Demo Environment Initialization for Aspira TAT System

This script performs a complete reset and initialization of the system for:
- Fresh testing
- Realistic client demo
- Webhook flow validation
- TAT/SLA validation
- Distributed lab testing
- Queue/routing validation
- Dashboard/KPI validation
- Reconciliation testing
- Split-processing testing

Usage:
    python database/init_demo.py

Prerequisites:
    - DATABASE_URL must be set in .env (Neon or local PostgreSQL)
    - Redis must be running
    - .env file must be configured

This script:
1. Drops and recreates the entire schema
2. Inserts realistic lab network (GHK, NM, Shobha, Kharghar, Chembur, HOC, Truecare, SSO, OS)
3. Creates admin and lab manager accounts
4. Initializes master EDOS (test catalog)
5. Initializes lab-wise EDOS distribution
6. Seeds realistic test data
7. Configures batch schedules
8. Sets up routing rules
"""

from __future__ import annotations
import os
import sys
import logging
import asyncio
from datetime import datetime, timedelta, time
from typing import Dict, List, Any

# Try to import asyncpg for Neon support
try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("init_demo")

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "")

def _is_neon_database():
    """Check if DATABASE_URL is a Neon database"""
    return "neon.tech" in DATABASE_URL or "localhost" in DATABASE_URL or "127.0.0.1" in DATABASE_URL or "postgres" in DATABASE_URL


# ====================================================================
# REALISTIC LAB NETWORK CONFIGURATION
# ====================================================================

LABS = [
    {
        "lab_name": "GHK - Main Hybrid Lab",
        "lab_code": "GHK",
        "lab_type": 0,  # Main hybrid processing lab
        "max_concurrent_samples": 10,
        "processing_mode": "max",
        "default_processing_mins": 90,
        "is_fallback": 1,
        "is_active": 1,
        "timezone": "Asia/Kolkata",
        "capabilities": [
            {"department_id": 906, "department_name": "HAEMATOLOGY"},
            {"department_id": 913, "department_name": "BIOCHEMISTRY"},
            {"department_id": 915, "department_name": "CLINICAL PATHOLOGY"},
            {"department_id": 917, "department_name": "THYROID"},
            {"department_id": 918, "department_name": "LIPID"},
        ],
        "edos_tests": ["CBC", "ESR", "LFT", "KFT", "THYROID", "LIPID"],
    },
    {
        "lab_name": "NM - Specialized Processing Lab",
        "lab_code": "NM",
        "lab_type": 1,  # Specialized processing lab
        "max_concurrent_samples": 5,
        "processing_mode": "max",
        "default_processing_mins": 120,
        "is_fallback": 0,
        "is_active": 1,
        "timezone": "Asia/Kolkata",
        "capabilities": [
            {"department_id": 917, "department_name": "THYROID"},
            {"department_id": 919, "department_name": "HORMONAL"},
            {"department_id": 920, "department_name": "SPECIALIZED BIOCHEMISTRY"},
        ],
        "edos_tests": ["THYROID", "HORMONAL", "SPECIALIZED_BIOCHEM"],
    },
    {
        "lab_name": "Shobha - Hybrid Lab",
        "lab_code": "SHOBHA",
        "lab_type": 0,  # Hybrid lab
        "max_concurrent_samples": 8,
        "processing_mode": "max",
        "default_processing_mins": 75,
        "is_fallback": 0,
        "is_active": 1,
        "timezone": "Asia/Kolkata",
        "capabilities": [
            {"department_id": 906, "department_name": "HAEMATOLOGY"},
            {"department_id": 915, "department_name": "CLINICAL PATHOLOGY"},
        ],
        "edos_tests": ["CBC", "ESR", "BASIC_PATHOLOGY"],
    },
    {
        "lab_name": "Kharghar - Diagnostic Hub",
        "lab_code": "KHARGHAR",
        "lab_type": 0,  # Hybrid diagnostic hub
        "max_concurrent_samples": 6,
        "processing_mode": "max",
        "default_processing_mins": 60,
        "is_fallback": 0,
        "is_active": 1,
        "timezone": "Asia/Kolkata",
        "capabilities": [
            {"department_id": 906, "department_name": "HAEMATOLOGY"},
            {"department_id": 913, "department_name": "BIOCHEMISTRY"},
        ],
        "edos_tests": ["CBC", "BASIC_BIOCHEM"],
    },
    {
        "lab_name": "Chembur - Collection Center",
        "lab_code": "CHEMBUR",
        "lab_type": 2,  # Collection-focused center
        "max_concurrent_samples": 3,
        "processing_mode": "max",
        "default_processing_mins": 45,
        "is_fallback": 0,
        "is_active": 1,
        "timezone": "Asia/Kolkata",
        "capabilities": [
            {"department_id": 906, "department_name": "HAEMATOLOGY"},
        ],
        "edos_tests": ["CBC"],
    },
    {
        "lab_name": "HOC - Collection Hub",
        "lab_code": "HOC",
        "lab_type": 2,  # Collection-heavy center
        "max_concurrent_samples": 2,
        "processing_mode": "max",
        "default_processing_mins": 30,
        "is_fallback": 0,
        "is_active": 1,
        "timezone": "Asia/Kolkata",
        "capabilities": [],
        "edos_tests": [],
    },
    {
        "lab_name": "Truecare - Collection Lab",
        "lab_code": "TRUECARE",
        "lab_type": 2,  # Collection-focused lab
        "max_concurrent_samples": 2,
        "processing_mode": "max",
        "default_processing_mins": 30,
        "is_fallback": 0,
        "is_active": 1,
        "timezone": "Asia/Kolkata",
        "capabilities": [],
        "edos_tests": [],
    },
    {
        "lab_name": "SSO - Limited Processing Center",
        "lab_code": "SSO",
        "lab_type": 0,  # Hybrid/limited processing
        "max_concurrent_samples": 4,
        "processing_mode": "max",
        "default_processing_mins": 60,
        "is_fallback": 0,
        "is_active": 1,
        "timezone": "Asia/Kolkata",
        "capabilities": [
            {"department_id": 906, "department_name": "HAEMATOLOGY"},
        ],
        "edos_tests": ["CBC"],
    },
    {
        "lab_name": "OS - Outsource Reference Lab",
        "lab_code": "OS",
        "lab_type": 3,  # Outsource reference lab
        "max_concurrent_samples": 15,
        "processing_mode": "max",
        "default_processing_mins": 180,
        "is_fallback": 0,
        "is_active": 1,
        "timezone": "Asia/Kolkata",
        "capabilities": [
            {"department_id": 920, "department_name": "SPECIALIZED BIOCHEMISTRY"},
            {"department_id": 921, "department_name": "MOLECULAR"},
        ],
        "edos_tests": ["SPECIALIZED_BIOCHEM", "MOLECULAR"],
    },
]


# ====================================================================
# USER ACCOUNT CONFIGURATION
# ====================================================================

USERS = [
    {
        "email": "admin@aspira.com",
        "full_name": "System Administrator",
        "role": "admin",
        "lab_id": None,
        "is_active": 1,
    },
    {
        "email": "logistics@aspira.com",
        "full_name": "Logistics Coordinator",
        "role": "logistics",
        "lab_id": None,
        "is_active": 1,
    },
    {
        "email": "doctor@aspira.com",
        "full_name": "Medical Officer",
        "role": "doctor",
        "lab_id": None,
        "is_active": 1,
    },
    # Lab managers (will be mapped after lab insertion)
    {"email": "ghk.manager@aspira.com", "full_name": "GHK Lab Manager", "role": "lab", "lab_code": "GHK", "is_active": 1},
    {"email": "nm.manager@aspira.com", "full_name": "NM Lab Manager", "role": "lab", "lab_code": "NM", "is_active": 1},
    {"email": "shobha.manager@aspira.com", "full_name": "Shobha Lab Manager", "role": "lab", "lab_code": "SHOBHA", "is_active": 1},
    {"email": "kharghar.manager@aspira.com", "full_name": "Kharghar Lab Manager", "role": "lab", "lab_code": "KHARGHAR", "is_active": 1},
    {"email": "chembur.manager@aspira.com", "full_name": "Chembur Lab Manager", "role": "lab", "lab_code": "CHEMBUR", "is_active": 1},
    {"email": "hoc.manager@aspira.com", "full_name": "HOC Lab Manager", "role": "lab", "lab_code": "HOC", "is_active": 1},
    {"email": "truecare.manager@aspira.com", "full_name": "Truecare Lab Manager", "role": "lab", "lab_code": "TRUECARE", "is_active": 1},
    {"email": "sso.manager@aspira.com", "full_name": "SSO Lab Manager", "role": "lab", "lab_code": "SSO", "is_active": 1},
    {"email": "os.manager@aspira.com", "full_name": "OS Lab Manager", "role": "lab", "lab_code": "OS", "is_active": 1},
]


# ====================================================================
# MASTER EDOS (TEST CATALOG)
# ====================================================================

MASTER_EDOS = [
    {"external_test_id": 230964, "test_code": "CBC", "test_name": "Complete Blood Count", "department_id": 906, "department_name": "HAEMATOLOGY", "test_category": "Routine", "processing_time_mins": 45, "is_parallel_capable": 1, "default_priority": 5, "is_critical": 0, "predefined_tat_hours": 3.0},
    {"external_test_id": 231001, "test_code": "ESR", "test_name": "Erythrocyte Sedimentation Rate", "department_id": 906, "department_name": "HAEMATOLOGY", "test_category": "Routine", "processing_time_mins": 30, "is_parallel_capable": 1, "default_priority": 5, "is_critical": 0, "predefined_tat_hours": 2.0},
    {"external_test_id": 234978, "test_code": "LFT", "test_name": "Liver Function Test", "department_id": 913, "department_name": "BIOCHEMISTRY", "test_category": "Profile", "processing_time_mins": 90, "is_parallel_capable": 1, "default_priority": 5, "is_critical": 0, "predefined_tat_hours": 6.0},
    {"external_test_id": 234986, "test_code": "KFT", "test_name": "Kidney Function Test", "department_id": 913, "department_name": "BIOCHEMISTRY", "test_category": "Profile", "processing_time_mins": 75, "is_parallel_capable": 1, "default_priority": 5, "is_critical": 0, "predefined_tat_hours": 6.0},
    {"external_test_id": 236290, "test_code": "CREATININE", "test_name": "Creatinine", "department_id": 913, "department_name": "BIOCHEMISTRY", "test_category": "Biochemistry", "processing_time_mins": 45, "is_parallel_capable": 1, "default_priority": 5, "is_critical": 0, "predefined_tat_hours": 4.0},
    {"external_test_id": 231107, "test_code": "HBA1C", "test_name": "Glycated Haemoglobin", "department_id": 906, "department_name": "HAEMATOLOGY", "test_category": "Special Bio", "processing_time_mins": 120, "is_parallel_capable": 0, "default_priority": 5, "is_critical": 0, "predefined_tat_hours": 8.0},
    {"external_test_id": 231287, "test_code": "URINE", "test_name": "Routine Examination Urine", "department_id": 915, "department_name": "CLINICAL PATHOLOGY", "test_category": "Clin Path", "processing_time_mins": 30, "is_parallel_capable": 1, "default_priority": 5, "is_critical": 0, "predefined_tat_hours": 2.0},
    {"external_test_id": 237001, "test_code": "THYROID", "test_name": "Thyroid Profile", "department_id": 917, "department_name": "THYROID", "test_category": "Endocrine", "processing_time_mins": 120, "is_parallel_capable": 0, "default_priority": 5, "is_critical": 0, "predefined_tat_hours": 8.0},
    {"external_test_id": 237002, "test_code": "TSH", "test_name": "TSH", "department_id": 917, "department_name": "THYROID", "test_category": "Endocrine", "processing_time_mins": 90, "is_parallel_capable": 1, "default_priority": 5, "is_critical": 0, "predefined_tat_hours": 6.0},
    {"external_test_id": 237003, "test_code": "LIPID", "test_name": "Lipid Profile", "department_id": 918, "department_name": "LIPID", "test_category": "Profile", "processing_time_mins": 90, "is_parallel_capable": 1, "default_priority": 5, "is_critical": 0, "predefined_tat_hours": 6.0},
    {"external_test_id": 238001, "test_code": "HORMONAL", "test_name": "Hormonal Panel", "department_id": 919, "department_name": "HORMONAL", "test_category": "Endocrine", "processing_time_mins": 150, "is_parallel_capable": 0, "default_priority": 5, "is_critical": 0, "predefined_tat_hours": 10.0},
    {"external_test_id": 238002, "test_code": "SPECIALIZED_BIOCHEM", "test_name": "Specialized Biochemistry", "department_id": 920, "department_name": "SPECIALIZED BIOCHEMISTRY", "test_category": "Specialized", "processing_time_mins": 180, "is_parallel_capable": 0, "default_priority": 3, "is_critical": 1, "predefined_tat_hours": 12.0},
    {"external_test_id": 238003, "test_code": "MOLECULAR", "test_name": "Molecular Testing", "department_id": 921, "department_name": "MOLECULAR", "test_category": "Specialized", "processing_time_mins": 240, "is_parallel_capable": 0, "default_priority": 2, "is_critical": 1, "predefined_tat_hours": 24.0},
    {"external_test_id": 239001, "test_code": "BASIC_PATHOLOGY", "test_name": "Basic Pathology", "department_id": 915, "department_name": "CLINICAL PATHOLOGY", "test_category": "Pathology", "processing_time_mins": 60, "is_parallel_capable": 1, "default_priority": 5, "is_critical": 0, "predefined_tat_hours": 4.0},
    {"external_test_id": 239002, "test_code": "BASIC_BIOCHEM", "test_name": "Basic Biochemistry", "department_id": 913, "department_name": "BIOCHEMISTRY", "test_category": "Biochemistry", "processing_time_mins": 60, "is_parallel_capable": 1, "default_priority": 5, "is_critical": 0, "predefined_tat_hours": 4.0},
]


# ====================================================================
# BATCH SCHEDULE CONFIGURATION
# ====================================================================

BATCH_SCHEDULES = [
    {"lab_code": "GHK", "batch_time": "08:00", "batch_day": None, "max_capacity": 50},
    {"lab_code": "GHK", "batch_time": "12:00", "batch_day": None, "max_capacity": 50},
    {"lab_code": "GHK", "batch_time": "16:00", "batch_day": None, "max_capacity": 50},
    {"lab_code": "NM", "batch_time": "09:00", "batch_day": None, "max_capacity": 30},
    {"lab_code": "NM", "batch_time": "15:00", "batch_day": None, "max_capacity": 30},
    {"lab_code": "SHOBHA", "batch_time": "08:00", "batch_day": None, "max_capacity": 40},
    {"lab_code": "SHOBHA", "batch_time": "14:00", "batch_day": None, "max_capacity": 40},
    {"lab_code": "KHARGHAR", "batch_time": "09:00", "batch_day": None, "max_capacity": 35},
    {"lab_code": "KHARGHAR", "batch_time": "15:00", "batch_day": None, "max_capacity": 35},
    {"lab_code": "CHEMBUR", "batch_time": "10:00", "batch_day": None, "max_capacity": 20},
    {"lab_code": "SSO", "batch_time": "11:00", "batch_day": None, "max_capacity": 25},
    {"lab_code": "OS", "batch_time": "10:00", "batch_day": None, "max_capacity": 100},
    {"lab_code": "OS", "batch_time": "16:00", "batch_day": None, "max_capacity": 100},
]


# ====================================================================
# ROUTING RULES CONFIGURATION
# ====================================================================

ROUTING_RULES = [
    {"test_code": None, "department_id": 906, "processing_lab_code": "GHK", "notes": "HAEMATOLOGY default → GHK"},
    {"test_code": None, "department_id": 913, "processing_lab_code": "GHK", "notes": "BIOCHEMISTRY default → GHK"},
    {"test_code": None, "department_id": 915, "processing_lab_code": "SHOBHA", "notes": "CLINICAL PATHOLOGY default → Shobha"},
    {"test_code": None, "department_id": 917, "processing_lab_code": "NM", "notes": "THYROID default → NM"},
    {"test_code": None, "department_id": 918, "processing_lab_code": "GHK", "notes": "LIPID default → GHK"},
    {"test_code": None, "department_id": 919, "processing_lab_code": "NM", "notes": "HORMONAL default → NM"},
    {"test_code": None, "department_id": 920, "processing_lab_code": "OS", "notes": "SPECIALIZED BIOCHEMISTRY default → OS"},
    {"test_code": None, "department_id": 921, "processing_lab_code": "OS", "notes": "MOLECULAR default → OS"},
    {"test_code": "SPECIALIZED_BIOCHEM", "department_id": None, "processing_lab_code": "OS", "notes": "SPECIALIZED_BIOCHEM override → OS"},
]


async def run_demo_init():
    """Run complete demo initialization."""
    if not HAS_ASYNCPG:
        logger.error("asyncpg is required for database initialization. Install with: pip install asyncpg")
        sys.exit(1)
    
    if not DATABASE_URL:
        logger.error("DATABASE_URL not found in environment variables")
        sys.exit(1)
    
    logger.info("=== Aspira TAT Demo Environment Initialization ===")
    logger.info("Connecting to database...")
    
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    
    try:
        # Step 1: Drop and recreate schema
        logger.info("Step 1: Dropping and recreating schema...")
        # await conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        # await conn.execute("CREATE SCHEMA public")
        
        # Read and execute full schema.sql (includes default seed data)
        # schema_file = os.path.join(os.path.dirname(__file__), "schema.sql")
        # with open(schema_file, "r", encoding="utf-8") as f:
        #     schema_sql = f.read()
        
        # Execute full schema (broken view is now commented out in schema.sql)
        # await conn.execute(schema_sql)
        # logger.info("  ✓ Schema applied successfully")
        
        # RECONNECT to clear Postgres cache for custom types (Enums)
        # await conn.close()
        # conn = await asyncpg.connect(DATABASE_URL)
        # logger.info("  ✓ Reconnected to clear type cache")
        
        # Delete default seed data to replace with our custom data
        logger.info("Step 1.5: Removing default seed data...")
        await conn.execute("DELETE FROM tat_lab_edos")
        await conn.execute("DELETE FROM tat_lab_capability")
        await conn.execute("DELETE FROM tat_lab_batch_schedule")
        await conn.execute("DELETE FROM tat_test_routing")
        await conn.execute("DELETE FROM tat_user")
        await conn.execute("DELETE FROM tat_test_type_config")
        await conn.execute("DELETE FROM tat_lab")
        logger.info("✅ Default seed data removed")
        
        # Step 2: Insert labs
        logger.info("Step 2: Inserting realistic lab network...")
        lab_code_to_id = {}
        for lab in LABS:
            lab_id = await conn.fetchval("""
                INSERT INTO tat_lab (lab_name, lab_code, lab_type, max_concurrent_samples, processing_mode, 
                                     default_processing_mins, is_fallback, is_active, timezone)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
            """, lab["lab_name"], lab["lab_code"], lab["lab_type"], lab["max_concurrent_samples"],
                lab["processing_mode"], lab["default_processing_mins"], lab["is_fallback"], lab["is_active"],
                lab["timezone"])
            lab_code_to_id[lab["lab_code"]] = lab_id
            logger.info(f"  ✓ Created lab: {lab['lab_code']} - {lab['lab_name']} (id={lab_id})")
        
        # Step 3: Insert users
        logger.info("Step 3: Creating admin and lab manager accounts...")
        for user in USERS:
            lab_id = None
            if "lab_code" in user:
                lab_id = lab_code_to_id.get(user["lab_code"])
            
            await conn.execute("""
                INSERT INTO tat_user (email, full_name, role, lab_id, is_active)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (email) DO UPDATE
                SET full_name = EXCLUDED.full_name,
                    role = EXCLUDED.role,
                    lab_id = EXCLUDED.lab_id,
                    is_active = EXCLUDED.is_active,
                    updated_at = CURRENT_TIMESTAMP
            """, user["email"], user["full_name"], user["role"], lab_id, user["is_active"])
            
            lab_info = f" (lab={user.get('lab_code', 'N/A')})" if lab_id else ""
            logger.info(f"  ✓ Created user: {user['email']} - {user['role']}{lab_info}")
        
        # Step 4: Insert master EDOS
        logger.info("Step 4: Initializing master EDOS (test catalog)...")
        test_code_to_id = {}
        for test in MASTER_EDOS:
            test_id = await conn.fetchval("""
                INSERT INTO tat_test_type_config (external_test_id, test_code, test_name, department_id, department_name, 
                                                 test_category, processing_time_mins, is_parallel_capable, default_priority, 
                                                 is_critical, predefined_tat_hours)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING id
            """, test["external_test_id"], test["test_code"], test["test_name"], test["department_id"],
                test["department_name"], test["test_category"], test["processing_time_mins"],
                test["is_parallel_capable"], test["default_priority"], test["is_critical"],
                test["predefined_tat_hours"])
            test_code_to_id[test["test_code"]] = test_id
            logger.info(f"  ✓ Created test: {test['test_code']} - {test['test_name']} (dept={test['department_name']})")
        
        # Step 5: Insert lab capabilities and lab EDOS
        logger.info("Step 5: Initializing lab-wise EDOS distribution...")
        for lab in LABS:
            lab_id = lab_code_to_id[lab["lab_code"]]
            
            # Insert capabilities
            for cap in lab["capabilities"]:
                await conn.execute("""
                    INSERT INTO tat_lab_capability (lab_id, department_id, department_name)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (lab_id, department_id, test_code) DO NOTHING
                """, lab_id, cap["department_id"], cap["department_name"])
            
            # Insert lab EDOS (only for tests in the lab's edos_tests list)
            for test_code in lab["edos_tests"]:
                if test_code in test_code_to_id:
                    test = next(t for t in MASTER_EDOS if t["test_code"] == test_code)
                    await conn.execute("""
                        INSERT INTO tat_lab_edos (lab_id, test_code, department_id, department_name, 
                                                 processing_time_mins, committed_tat_hours, processing_mode, 
                                                 is_outsourced, outsource_buffer_mins, is_active, notes)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                        ON CONFLICT (lab_id, test_code) DO NOTHING
                    """, lab_id, test["test_code"], test["department_id"], test["department_name"],
                        test["processing_time_mins"], test["predefined_tat_hours"], "max", 0, 0, 1,
                        f"Lab EDOS for {lab['lab_code']}")
            
            logger.info(f"  ✓ Initialized EDOS for {lab['lab_code']} ({len(lab['edos_tests'])} tests)")
        
        # Step 6: Insert batch schedules
        logger.info("Step 6: Configuring batch schedules...")
        for schedule in BATCH_SCHEDULES:
            lab_id = lab_code_to_id[schedule["lab_code"]]
            # Convert batch_time string to time object
            hour, minute = map(int, schedule["batch_time"].split(':'))
            batch_time_obj = time(hour, minute)
            await conn.execute("""
                INSERT INTO tat_lab_batch_schedule (lab_id, batch_time, batch_day, max_capacity)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (lab_id, batch_time, batch_day) DO NOTHING
            """, lab_id, batch_time_obj, schedule["batch_day"], schedule["max_capacity"])
            logger.info(f"  ✓ Batch schedule: {schedule['lab_code']} @ {schedule['batch_time']} (cap={schedule['max_capacity']})")
        
        # Step 7: Insert routing rules
        logger.info("Step 7: Configuring routing rules...")
        for rule in ROUTING_RULES:
            lab_id = lab_code_to_id[rule["processing_lab_code"]]
            await conn.execute("""
                INSERT INTO tat_test_routing (test_code, department_id, processing_lab_id, notes)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (test_code, department_id) DO NOTHING
            """, rule["test_code"], rule["department_id"], lab_id, rule["notes"])
            
            rule_desc = f"{rule['test_code'] if rule['test_code'] else rule['department_id']} → {rule['processing_lab_code']}"
            logger.info(f"  ✓ Routing rule: {rule_desc}")
        
        # Step 8: Verify initialization
        logger.info("Step 8: Verifying initialization...")
        
        lab_count = await conn.fetchval("SELECT COUNT(*) FROM tat_lab")
        user_count = await conn.fetchval("SELECT COUNT(*) FROM tat_user")
        test_count = await conn.fetchval("SELECT COUNT(*) FROM tat_test_type_config")
        capability_count = await conn.fetchval("SELECT COUNT(*) FROM tat_lab_capability")
        edos_count = await conn.fetchval("SELECT COUNT(*) FROM tat_lab_edos")
        batch_count = await conn.fetchval("SELECT COUNT(*) FROM tat_lab_batch_schedule")
        routing_count = await conn.fetchval("SELECT COUNT(*) FROM tat_test_routing")
        
        logger.info("")
        logger.info("=== Initialization Summary ===")
        logger.info(f"  Labs: {lab_count}")
        logger.info(f"  Users: {user_count}")
        logger.info(f"  Master EDOS Tests: {test_count}")
        logger.info(f"  Lab Capabilities: {capability_count}")
        logger.info(f"  Lab EDOS Entries: {edos_count}")
        logger.info(f"  Batch Schedules: {batch_count}")
        logger.info(f"  Routing Rules: {routing_count}")
        logger.info("")
        logger.info("✅ Demo environment initialized successfully!")
        logger.info("")
        logger.info("=== Generated Credentials ===")
        logger.info("MASTER ADMIN:")
        logger.info("  Email: admin@aspira.com")
        logger.info("  Password: [Set via auth system]")
        logger.info("")
        logger.info("LAB MANAGERS:")
        for user in USERS:
            if user["role"] == "lab":
                logger.info(f"  {user['email']} - {user['full_name']} (lab={user.get('lab_code', 'N/A')})")
        logger.info("")
        logger.info("=== Next Steps ===")
        logger.info("1. Start backend: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
        logger.info("2. Start worker: celery -A app.workers.celery_app worker --loglevel=info -P solo --queues=queue:webhook-processing,projection")
        logger.info("3. Start beat: celery -A app.workers.celery_app beat --loglevel=info")
        logger.info("4. Start frontend: npm run dev")
        logger.info("5. Access dashboard: http://localhost:3000")
        logger.info("6. Run webhook tests using the generated PowerShell commands")
        
    except Exception as e:
        logger.error(f"❌ Initialization failed: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    if _is_neon_database():
        try:
            asyncio.run(run_demo_init())
        except Exception as e:
            logger.error(f"❌ Demo initialization failed: {e}")
            sys.exit(1)
    else:
        # Allow local development even if not Neon
        logger.warning("DATABASE_URL does not appear to be a Neon database. Proceeding with local initialization...")
        try:
            asyncio.run(run_demo_init())
        except Exception as e:
            logger.error(f"❌ Demo initialization failed: {e}")
            sys.exit(1)
