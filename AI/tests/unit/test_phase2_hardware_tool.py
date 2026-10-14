"""Unit tests for SystemHardwareTool telemetry and safety clamping."""

import pytest

from nani.tools.system_hardware import SystemHardwareTool


@pytest.mark.asyncio
async def test_system_hardware_resource_inspection():
    tool = SystemHardwareTool()
    res = await tool.run(operation="get_system_resources")
    assert res.success is True
    assert "load_avg" in res.data
    assert "cpu_count" in res.data
    assert res.data["cpu_count"] >= 1


@pytest.mark.asyncio
async def test_system_hardware_battery_inspection():
    tool = SystemHardwareTool()
    res = await tool.run(operation="get_battery")
    assert res.success is True
    assert "battery_present" in res.data


@pytest.mark.asyncio
async def test_system_hardware_volume_query():
    tool = SystemHardwareTool()
    res = await tool.run(operation="get_volume")
    assert res.success is True
    assert "volume_percent" in res.data


@pytest.mark.asyncio
async def test_system_hardware_parameter_validation():
    tool = SystemHardwareTool()
    # Missing operation
    res = await tool.run()
    assert res.success is False

    # Missing value for set_volume
    res_vol = await tool.run(operation="set_volume")
    assert res_vol.success is False
    assert "Missing required parameter 'value'" in res_vol.error

    # Missing value for set_brightness
    res_bright = await tool.run(operation="set_brightness")
    assert res_bright.success is False
    assert "Missing required parameter 'value'" in res_bright.error
