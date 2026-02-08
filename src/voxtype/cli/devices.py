"""Input device listing and configuration."""

from __future__ import annotations

import sys
from typing import Annotated, Any

import typer
from rich.table import Table

from voxtype.cli._helpers import console
from voxtype.config import set_config_value


def register(app: typer.Typer) -> None:
    """Register devices command on the main app."""

    @app.command()
    def devices(
        set_hotkey: Annotated[
            bool,
            typer.Option("--set-hotkey", "-k", help="Set selected device as hotkey device"),
        ] = False,
        hid: Annotated[
            bool,
            typer.Option("--hid", "-H", help="List HID devices (for device profiles)"),
        ] = False,
    ) -> None:
        """List input devices and optionally configure hotkey device.

        Shows all input devices. Use --hid to list HID devices with vendor/product IDs
        for creating device profiles.

        Example:
            voxtype devices                    # List input devices
            voxtype devices --hid              # List HID devices with IDs
            voxtype devices --set-hotkey       # Select device for hotkey
        """
        if hid:
            _list_hid_devices()
            return

        if sys.platform == "linux":
            _list_evdev_devices(set_hotkey)
        else:
            # macOS: show HID devices by default
            _list_hid_devices()


def _list_hid_devices() -> None:
    """List HID devices with vendor/product IDs."""
    try:
        import hid

        devices_list = hid.enumerate()
    except ImportError:
        try:
            # Try hidapi package (cython-based, bundles native lib)
            import hidapi

            devices_list = [
                {
                    "vendor_id": d.vendor_id,
                    "product_id": d.product_id,
                    "manufacturer_string": d.manufacturer_string,
                    "product_string": d.product_string,
                }
                for d in hidapi.enumerate()
            ]
        except ImportError:
            from voxtype.utils.install_info import get_feature_install_message

            console.print("[red]hidapi package not installed[/]")
            console.print("This should be installed automatically on macOS.")
            console.print(get_feature_install_message("hidapi"))
            raise typer.Exit(1)

    if not devices_list:
        console.print("[yellow]No HID devices found[/]")
        raise typer.Exit(1)

    # Group by vendor_id/product_id to deduplicate interfaces
    seen = set()
    unique_devices = []
    for dev in devices_list:
        key = (dev["vendor_id"], dev["product_id"])
        if key not in seen and key != (0, 0):
            seen.add(key)
            unique_devices.append(dev)

    # Sort by product name
    unique_devices.sort(key=lambda d: (d.get("product_string") or "").lower())

    table = Table(title="HID Devices", show_header=True, header_style="bold", expand=False)
    table.add_column("Vendor ID", style="cyan", width=10)
    table.add_column("Product ID", style="cyan", width=10)
    table.add_column("Manufacturer", width=20)
    table.add_column("Product", style="green", width=30)

    for dev in unique_devices:
        vendor_id = f"0x{dev['vendor_id']:04x}"
        product_id = f"0x{dev['product_id']:04x}"
        manufacturer = dev.get("manufacturer_string") or "[dim]—[/]"
        product = dev.get("product_string") or "[dim]Unknown[/]"

        table.add_row(vendor_id, product_id, manufacturer, product)

    console.print(table)
    console.print()
    console.print("[dim]To use a device, create ~/.config/voxtype/devices/<name>.toml:[/]")
    console.print()
    console.print('[dim]  vendor_id = 0x????[/]')
    console.print('[dim]  product_id = 0x????[/]')
    console.print('[dim]  [bindings][/]')
    console.print('[dim]  KEY_PAGEUP = "project-prev"[/]')
    console.print('[dim]  KEY_PAGEDOWN = "project-next"[/]')
    console.print('[dim]  KEY_B = "toggle-listening"[/]')


def _list_evdev_devices(set_hotkey: bool) -> None:
    """List evdev devices (Linux only)."""
    try:
        import evdev
    except ImportError:
        from voxtype.utils.install_info import get_feature_install_message

        console.print("[red]evdev not installed[/]")
        console.print(get_feature_install_message("evdev"))
        raise typer.Exit(1)

    # Collect all devices with their info
    devices_info: list[dict[str, Any]] = []
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
            caps = device.capabilities().get(evdev.ecodes.EV_KEY, [])
            has_scroll = evdev.ecodes.KEY_SCROLLLOCK in caps
            has_keys = len(caps) > 0
            name = device.name
            is_keyboard = "keyboard" in name.lower()
            device.close()

            devices_info.append({
                "path": path,
                "name": name,
                "has_keys": has_keys,
                "has_scroll": has_scroll,
                "is_keyboard": is_keyboard,
            })
        except Exception:
            continue

    # Sort: keyboards first, then by name
    devices_info.sort(key=lambda d: (not d["is_keyboard"], d["name"].lower()))

    if not devices_info:
        console.print("[yellow]No input devices found[/]")
        raise typer.Exit(1)

    # Display table
    table = Table(title="Input Devices", show_header=True, header_style="bold", expand=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("Device Name", style="cyan")
    table.add_column("Keys", justify="center", width=6)
    table.add_column("ScrollLock", justify="center", width=10)
    table.add_column("Type", width=12)

    # Add option 0 for auto-detect
    if set_hotkey:
        table.add_row("0", "[yellow](auto-detect)[/]", "—", "—", "—")

    for i, dev in enumerate(devices_info, 1):
        keys_icon = "[green]✓[/]" if dev["has_keys"] else "[dim]—[/]"
        scroll_icon = "[green]✓[/]" if dev["has_scroll"] else "[dim]—[/]"
        dev_type = "[cyan]Keyboard[/]" if dev["is_keyboard"] else "[dim]Other[/]"

        table.add_row(str(i), dev["name"], keys_icon, scroll_icon, dev_type)

    console.print(table)

    # If setting hotkey, prompt for selection
    if set_hotkey:
        console.print()
        prompt = f"Select device for hotkey [0=auto-detect, 1-{len(devices_info)}]"

        try:
            choice = typer.prompt(prompt, type=int)
            if choice < 0 or choice > len(devices_info):
                console.print("[red]Invalid selection[/]")
                raise typer.Exit(1)

            if choice == 0:
                set_config_value("hotkey.device", "")
                console.print("[green]✓[/] Hotkey device cleared (auto-detect)")
            else:
                selected = devices_info[choice - 1]
                set_config_value("hotkey.device", selected["name"])
                console.print(f"[green]✓[/] Hotkey device set to: [cyan]{selected['name']}[/]")

        except (ValueError, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled[/]")
            raise typer.Exit(0)
    else:
        console.print("\n[dim]Use --set-hotkey to configure a device[/]")
        console.print("[dim]Use --hid to list HID devices for device profiles[/]")
