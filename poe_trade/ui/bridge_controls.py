"""Manual Streamlit controls for bridge helpers."""

from __future__ import annotations

import json

from poe_trade.bridge.local_bridge import BridgeResult

try:
    import streamlit as st
except ImportError:  # pragma: no cover - optional UI dependency
    st = None  # type: ignore[assignment]

from poe_trade.ui.client import LedgerApiClient


def _display_result(result: "BridgeResult") -> None:
    if st is None:
        return
    if result.success:
        st.success(result.message)
    else:
        st.error(result.message)
    with st.expander("Payload summary"):
        st.code(json.dumps(result.payload, default=str, indent=2), language="json")


def render_bridge_controls(client: LedgerApiClient) -> None:
    if st is None:
        raise RuntimeError("Streamlit required to render bridge controls")
    st.subheader("Bridge Controls")
    st.caption("Manual clipboard, OCR, and overlay helpers for diagnostics.")
    manual_trigger = st.checkbox("Confirm manual trigger", value=False)
    st.markdown(
        "- Manual trigger must be checked before any of these actions will execute.\n"
        "- Guardrail status is reported per action."
    )
    if not manual_trigger:
        st.warning("Manual trigger is disabled; actions will be blocked until confirmed.")

    with st.expander("Capture screen text"):
        st.write("Capture the active screen and OCR the payload (Tesseract + screenshot tool required).")
        if st.button("Capture screen", key="capture_screen", disabled=not manual_trigger):
            result = client.bridge_capture_screen(manual_trigger=manual_trigger)
            _display_result(result)

    with st.expander("Clipboard"):
        st.write("Read or write clipboard contents via wl-copy/xclip/xsel.")
        if st.button("Read clipboard", key="clipboard_read", disabled=not manual_trigger):
            result = client.bridge_clipboard_read(manual_trigger=manual_trigger)
            _display_result(result)
        clipboard_value = st.text_area("Clipboard write value", value="", key="clipboard_write_value")
        if st.button("Write clipboard", key="clipboard_write", disabled=not manual_trigger):
            result = client.bridge_clipboard_write(clipboard_value, manual_trigger=manual_trigger)
            _display_result(result)

    with st.expander("Overlay payload queue"):
        queue_path = st.text_input(
            "Queue path",
            value=LedgerApiClient.DEFAULT_OVERLAY_QUEUE_PATH,
        )
        payload_text = st.text_area("Payload JSON", value="{}", height=120)
        if st.button("Push overlay payload", key="overlay_payload", disabled=not manual_trigger):
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError as exc:
                st.error(f"Invalid JSON payload: {exc}")
            else:
                result = client.bridge_push_overlay_payload(
                    payload=payload,
                    manual_trigger=manual_trigger,
                    queue_path=queue_path,
                )
                _display_result(result)

    with st.expander("Item filter writer"):
        filter_path = st.text_input(
            "Filter path",
            value=LedgerApiClient.DEFAULT_FILTER_PATH,
            key="filter_path",
        )
        backup_path = st.text_input(
            "Backup path (optional)",
            value=LedgerApiClient.DEFAULT_FILTER_BACKUP_PATH,
            key="filter_backup",
        )
        contents = st.text_area("Filter contents", value="# manual filter", height=140)
        if st.button("Write filter", key="filter_write", disabled=not manual_trigger):
            result = client.bridge_write_item_filter(
                contents,
                manual_trigger=manual_trigger,
                filter_path=filter_path,
                backup_path=backup_path,
            )
            _display_result(result)
