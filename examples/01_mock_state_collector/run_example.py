#!/usr/bin/env python3
"""
Example 01: Mock State Collector — Create & Verify a Note

This example demonstrates how to use the MockXRClawDeviceManager to test
the Samsung Notes state collector without a physical device.

Flow:
  1. Create a MockXRClawDeviceManager
  2. Capture pre-state (no notes exist)
  3. Simulate the agent creating a note
  4. Run the state collector's verify() function
  5. Print the result

Run:
    python examples/01_mock_state_collector/run_example.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from test.mocks.mock_xrclaw import MockXRClawDeviceManager
from apps.samsung_notes.state_collector import capture_pre, verify


def main():
    print("=" * 60)
    print("Example 01: Mock State Collector — Samsung Notes Create")
    print("=" * 60)

    # 1. Create mock device manager
    dm = MockXRClawDeviceManager()
    print("\n[1] Created MockXRClawDeviceManager")

    # 2. Capture pre-state
    pre = capture_pre(dm)
    print(f"[2] Pre-state: {pre['count']} notes exist")

    # 3. Simulate agent creating a note
    dm.notes.create_note("Shopping List", "milk and eggs")
    print("[3] Agent created note: 'Shopping List' with content 'milk and eggs'")

    # 4. Verify
    gt_answer = "A note titled 'Shopping List' with content milk and eggs"
    result = verify(dm, "samsungnote", "create",
                    "Create a note titled 'Shopping List'", gt_answer, pre)

    # 5. Print result
    print(f"\n[4] Verification result:")
    print(f"    Method:   {result['method']}")
    print(f"    Verified: {result['verified']}")
    print(f"    Rating:   {result['rating']}")
    print(f"    Analysis: {result['analysis']}")
    print(f"\n{'✓ PASS' if result['verified'] else '✗ FAIL'}")


if __name__ == "__main__":
    main()
