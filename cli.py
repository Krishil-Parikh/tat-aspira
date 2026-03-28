"""CLI interface for the TAT & Batch Monitoring System.

Usage:
  python cli.py search <query>                    Search tests by name or code
  python cli.py info <test_code>                   Get test details
  python cli.py accession <test_code> [datetime]   Calculate ETA for a sample
  python cli.py miss-batch <test_code> [datetime]  Simulate missed batch
  python cli.py list-schedules                     Show all unique schedule formats

Examples:
  python cli.py search "Chromogranin"
  python cli.py info ELISA023
  python cli.py accession ELISA023
  python cli.py accession ELISA023 "2026-03-10 16:00"
  python cli.py miss-batch ELISA023 "2026-03-10 16:00"
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from app.csv_loader import search_tests, get_test_by_code, get_all_tests
from app.schedule_parser import parse_schedule, find_next_batch
from app.tat_parser import parse_tat, calculate_eta
from app.engine import calculate_eta_standalone, simulate_missed_batch_standalone


def fmt_dt(dt: datetime) -> str:
    """Format a datetime nicely."""
    if dt is None:
        return "N/A"
    return dt.strftime("%A %B %d, %Y %I:%M %p")


def cmd_search(query: str):
    """Search for tests."""
    results = search_tests(query)
    if not results:
        print(f"❌ No tests found matching '{query}'")
        return

    print(f"\n🔍 Found {len(results)} test(s) matching '{query}':\n")
    print(f"{'Code':<18} {'Test Name':<55} {'Schedule':<25} {'TAT'}")
    print("─" * 120)
    for t in results[:30]:
        name = t.test_name[:52] + "..." if len(t.test_name) > 55 else t.test_name
        print(f"{t.test_code:<18} {name:<55} {t.test_schedule:<25} {t.tat}")


def cmd_info(test_code: str):
    """Get detailed test information."""
    test = get_test_by_code(test_code)
    if not test:
        print(f"❌ Test code '{test_code}' not found")
        return

    slots = parse_schedule(test.test_schedule)
    tat_parsed = parse_tat(test.tat)
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    print(f"\n{'═' * 60}")
    print(f"  📋 TEST DETAILS: {test.test_code}")
    print(f"{'═' * 60}")
    print(f"  Name:          {test.test_name}")
    print(f"  Code:          {test.test_code}")
    print(f"  MRP:           ₹{test.mrp:,.2f}")
    print(f"  Group:         {test.group}")
    print(f"  Specimen:      {test.specimen_type}")
    print(f"  Method:        {test.method}")
    print(f"  Temperature:   {test.temp}")
    print(f"  Location:      {test.city}, {test.state}")
    print(f"{'─' * 60}")
    print(f"  Schedule:      {test.test_schedule}")
    print(f"  TAT:           {test.tat}")
    print(f"{'─' * 60}")

    if slots:
        print(f"  Parsed Schedule Slots:")
        for slot in slots:
            info = f"    → {day_names[slot.day_of_week]} at {slot.hour:02d}:{slot.minute:02d}"
            if slot.week_numbers:
                weeks = ", ".join([f"Week {w}" for w in slot.week_numbers])
                info += f" ({weeks} of month)"
            print(info)

    if tat_parsed:
        days, hour, minute = tat_parsed
        print(f"  Parsed TAT:    +{days} day(s), report at {hour:02d}:{minute:02d}")

    # Calculate from now
    now = datetime.now()
    next_batch = find_next_batch(now, test.test_schedule)
    if next_batch:
        eta = calculate_eta(next_batch, test.tat)
        print(f"{'─' * 60}")
        print(f"  📊 If accessioned NOW ({now.strftime('%A %I:%M %p')}):")
        print(f"     Next batch:  {fmt_dt(next_batch)}")
        print(f"     ETA:         {fmt_dt(eta)}")

    print(f"{'═' * 60}\n")


def cmd_accession(test_code: str, time_str: str = None):
    """Calculate ETA for a sample accession."""
    accession_time = None
    if time_str:
        try:
            accession_time = datetime.fromisoformat(time_str)
        except ValueError:
            print(f"❌ Invalid datetime format: '{time_str}'. Use ISO format (YYYY-MM-DD HH:MM)")
            return

    result = calculate_eta_standalone(test_code, accession_time)
    if not result:
        print(f"❌ Could not calculate ETA for test '{test_code}'")
        return

    print(f"\n{'═' * 60}")
    print(f"  🧪 SAMPLE ACCESSION")
    print(f"{'═' * 60}")
    print(f"  Test:          {result['test_name']} ({result['test_code']})")
    print(f"  Accession:     {fmt_dt(result['accession_time'])}")
    print(f"  Schedule:      {result['test_schedule']}")
    print(f"  TAT Rule:      {result['tat_rule']}")
    print(f"{'─' * 60}")
    print(f"  📦 Assigned Batch: {fmt_dt(result['assigned_batch'])}")
    print(f"  📄 Expected ETA:   {fmt_dt(result['eta'])}")
    print(f"{'═' * 60}\n")


def cmd_miss_batch(test_code: str, time_str: str = None):
    """Simulate a missed batch."""
    accession_time = None
    if time_str:
        try:
            accession_time = datetime.fromisoformat(time_str)
        except ValueError:
            print(f"❌ Invalid datetime format: '{time_str}'")
            return

    result = simulate_missed_batch_standalone(test_code, accession_time)
    if not result:
        print(f"❌ Could not simulate missed batch for test '{test_code}'")
        return

    print(f"\n{'═' * 60}")
    print(f"  ⚠️  MISSED BATCH SIMULATION")
    print(f"{'═' * 60}")
    print(f"  Test:              {result['test_name']} ({result['test_code']})")
    print(f"  Accession:         {fmt_dt(result['accession_time'])}")
    print(f"{'─' * 60}")
    print(f"  Original Batch:    {fmt_dt(result['original_batch'])}")
    print(f"  Original ETA:      {fmt_dt(result['original_eta'])}")
    print(f"{'─' * 60}")
    print(f"  ❌ Batch MISSED!")
    print(f"{'─' * 60}")
    print(f"  New Batch:         {fmt_dt(result['new_batch'])}")
    print(f"  New ETA:           {fmt_dt(result['new_eta'])}")
    print(f"{'─' * 60}")
    print(f"  📢 {result['message']}")
    print(f"{'═' * 60}\n")


def cmd_list_schedules():
    """List all unique schedule and TAT formats."""
    tests = get_all_tests()
    schedules = set()
    tats = set()
    for t in tests:
        if t.test_schedule:
            schedules.add(t.test_schedule)
        if t.tat:
            tats.add(t.tat)

    print(f"\n📅 Unique Schedule Formats ({len(schedules)}):")
    print("─" * 50)
    for s in sorted(schedules):
        slots = parse_schedule(s)
        parsed = "✅" if slots else "❌"
        print(f"  {parsed} {s}")

    print(f"\n⏱  Unique TAT Formats ({len(tats)}):")
    print("─" * 50)
    for t in sorted(tats):
        parsed_tat = parse_tat(t)
        parsed = "✅" if parsed_tat else "❌"
        print(f"  {parsed} {t}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower()

    if command == "search":
        if len(sys.argv) < 3:
            print("Usage: python cli.py search <query>")
            return
        cmd_search(" ".join(sys.argv[2:]))

    elif command == "info":
        if len(sys.argv) < 3:
            print("Usage: python cli.py info <test_code>")
            return
        cmd_info(sys.argv[2])

    elif command == "accession":
        if len(sys.argv) < 3:
            print("Usage: python cli.py accession <test_code> [datetime]")
            return
        time_str = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else None
        cmd_accession(sys.argv[2], time_str)

    elif command == "miss-batch":
        if len(sys.argv) < 3:
            print("Usage: python cli.py miss-batch <test_code> [datetime]")
            return
        time_str = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else None
        cmd_miss_batch(sys.argv[2], time_str)

    elif command == "list-schedules":
        cmd_list_schedules()

    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
