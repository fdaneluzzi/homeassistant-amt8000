"""Constants for the Intelbras AMT 8000 integration."""
DOMAIN = "amt8000"
DEFAULT_PORT = 9009
SCAN_INTERVAL_SECONDS = 5

# Partition index 0 is a read-only AND-aggregate: armed only when ALL user groups are armed.
# Real user groups start at index 1. Confirmed via live protocol observation on AMT 8000 fw 3.2.5.
AGGREGATE_PARTITION_IDX = 0

EVENT_ALARM_TRIGGERED = f"{DOMAIN}_alarm_triggered"
