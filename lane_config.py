"""
Lane configuration for multi-Appium architecture.

Each lane represents an isolated posting "worker" with:
- Its own Appium server instance
- Its own systemPort range (to avoid conflicts)
- Optionally its own state file

This enables running N phones in parallel without cross-talk or port collisions.
"""

# Default lanes configuration
# Each lane MUST have a distinct appium_url and system_port_base
LANES = [
    {
        "name": "lane1",
        "appium_url": "http://127.0.0.1:4723",
        "system_port_base": 8200,
        "appium_port": 4723,
    },
    {
        "name": "lane2",
        "appium_url": "http://127.0.0.1:4725",
        "system_port_base": 8300,
        "appium_port": 4725,
    },
    {
        "name": "lane3",
        "appium_url": "http://127.0.0.1:4727",
        "system_port_base": 8400,
        "appium_port": 4727,
    },
]


def get_lane_config(lane_name: str) -> dict:
    """Get configuration for a specific lane by name.

    Args:
        lane_name: Name of the lane (e.g., "lane1", "lane2")

    Returns:
        Lane configuration dict with appium_url, system_port_base, etc.

    Raises:
        ValueError: If lane_name is not found in LANES
    """
    for lane in LANES:
        if lane["name"] == lane_name:
            return lane

    available = [l["name"] for l in LANES]
    raise ValueError(f"Lane '{lane_name}' not found. Available lanes: {available}")


def get_all_lane_names() -> list:
    """Get list of all configured lane names."""
    return [lane["name"] for lane in LANES]


def get_system_port_for_lane(lane_name: str, worker_index: int = 1) -> int:
    """Get the systemPort for a specific lane and worker.

    Args:
        lane_name: Name of the lane
        worker_index: Worker index within the lane (1-based, default 1)

    Returns:
        systemPort value (e.g., 8201 for lane1 worker 1)
    """
    lane = get_lane_config(lane_name)
    return lane["system_port_base"] + worker_index


def validate_lanes_no_overlap():
    """Validate that no two lanes have overlapping port ranges.

    Each lane reserves 100 ports starting from system_port_base.
    Also validates Appium ports are unique.

    Raises:
        ValueError: If overlapping ports detected
    """
    appium_ports = set()
    port_ranges = []

    for lane in LANES:
        # Check Appium port uniqueness
        appium_port = lane["appium_port"]
        if appium_port in appium_ports:
            raise ValueError(f"Duplicate Appium port {appium_port} in lanes config")
        appium_ports.add(appium_port)

        # Check systemPort range overlaps (each lane reserves 100 ports)
        base = lane["system_port_base"]
        range_start = base
        range_end = base + 100

        for other_name, other_start, other_end in port_ranges:
            if not (range_end <= other_start or range_start >= other_end):
                raise ValueError(
                    f"Port range overlap between {lane['name']} ({range_start}-{range_end}) "
                    f"and {other_name} ({other_start}-{other_end})"
                )

        port_ranges.append((lane["name"], range_start, range_end))

    return True


# Validate on import
try:
    validate_lanes_no_overlap()
except ValueError as e:
    import warnings
    warnings.warn(f"Lane configuration error: {e}")


if __name__ == "__main__":
    # Print lane configuration for debugging
    print("Lane Configuration:")
    print("-" * 50)
    for lane in LANES:
        print(f"  {lane['name']}:")
        print(f"    Appium URL: {lane['appium_url']}")
        print(f"    Appium Port: {lane['appium_port']}")
        print(f"    systemPort base: {lane['system_port_base']}")
        print()

    print("Validation: ", end="")
    try:
        validate_lanes_no_overlap()
        print("PASSED - No port overlaps detected")
    except ValueError as e:
        print(f"FAILED - {e}")
