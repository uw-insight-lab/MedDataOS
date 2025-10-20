"""
Logging and knowledge management utilities.
Handles console logging and XML-based shared knowledge storage.
Supports optional WebSocket broadcasting for web UI.
"""
import json
import os
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
from typing import Optional, Set
import asyncio

# Global WebSocket manager (will be set by web server)
_websocket_manager: Optional['WebSocketManager'] = None


class WebSocketManager:
    """Manages WebSocket connections and broadcasts log messages."""

    def __init__(self):
        self.active_connections: Set = set()
        self.loop = None

    def set_loop(self, loop):
        """Set the event loop for async operations."""
        self.loop = loop

    def connect(self, websocket):
        """Add a new WebSocket connection."""
        self.active_connections.add(websocket)

    def disconnect(self, websocket):
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return

        # Create tasks for all broadcasts
        tasks = []
        for connection in self.active_connections.copy():
            tasks.append(self._send_to_client(connection, message))

        # Wait for all broadcasts to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_to_client(self, connection, message: dict):
        """Send message to a single client."""
        try:
            await connection.send_json(message)
        except Exception:
            # Remove disconnected clients
            self.active_connections.discard(connection)


def set_websocket_manager(manager: WebSocketManager):
    """Set the global WebSocket manager."""
    global _websocket_manager
    _websocket_manager = manager


def _broadcast_log(log_type: str, message: str, metadata: dict = None, header: str = None):
    """Broadcast log to WebSocket clients if manager is available."""
    if _websocket_manager is None or _websocket_manager.loop is None:
        return

    log_data = {
        "type": log_type,
        "header": header or log_type.replace("_", " ").title(),
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "metadata": metadata or {}
    }

    # Schedule the broadcast in the event loop from any thread
    try:
        asyncio.run_coroutine_threadsafe(
            _websocket_manager.broadcast(log_data),
            _websocket_manager.loop
        )
    except Exception as e:
        # Silently fail if broadcast fails
        print(f"Broadcast error: {e}")


def log_user(msg):
    """Log a user message to console and broadcast to web UI."""
    print(f"🧑‍💬 {msg}")
    _broadcast_log("user", msg, header="User Query")


def log_assistant(msg):
    """Log an assistant message to console and broadcast to web UI."""
    print(f"🤖 {msg}")
    _broadcast_log("assistant", msg, header="System Response")


def log_tool_call(name, input_data):
    """Log a tool call to console and broadcast to web UI."""
    message = f"{input_data}"
    print(f"🛠️  {name}: {input_data}")

    # Create readable header from tool name
    header_map = {
        "prepare_data_for_analysis": "Data Preparation",
        "prepare_analysis": "Analysis Execution",
        "generate_analysis_report": "Report Generation",
        "classify_chest_xray": "Chest X-Ray Classification"
    }
    header = header_map.get(name, name.replace("_", " ").title())

    _broadcast_log("tool_call", message, {"tool_name": name, "input": str(input_data)}, header=header)


def log_tool_result(res):
    """Log a tool result to console and broadcast to web UI."""
    message = json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res
    print(f"📦 → {message}")
    _broadcast_log("tool_result", message, header="Execution Result")


def write_agent_summary(agent_name, summary):
    """
    Write execution summary for a specific agent to shared_knowledge.xml

    Args:
        agent_name (str): Name of the agent (preparation, analysis, report)
        summary (str): Summary text of what the agent accomplished
    """
    xml_file = "shared_knowledge.xml"

    try:
        # Try to parse existing XML file
        if os.path.exists(xml_file) and os.path.getsize(xml_file) > 0:
            tree = ET.parse(xml_file)
            root = tree.getroot()
        else:
            # Create new root element if file doesn't exist or is empty
            root = ET.Element("shared_knowledge")

        # Find existing agent element or create new one
        agent_element = root.find(agent_name)
        if agent_element is not None:
            # Update existing element
            agent_element.text = f"\n{summary}\n"
        else:
            # Create new agent element
            agent_element = ET.SubElement(root, agent_name)
            agent_element.text = f"\n{summary}\n"

        # Create ElementTree and write to file with pretty formatting
        tree = ET.ElementTree(root)

        # Convert to string for pretty printing
        rough_string = ET.tostring(root, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ")

        # Remove empty lines and write to file
        lines = [line for line in pretty_xml.split('\n') if line.strip()]
        with open(xml_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        print(f"📝 Updated {agent_name} summary in shared_knowledge.xml")

    except Exception as e:
        print(f"❌ Error writing to XML file: {str(e)}")


def read_agent_summary(agent_name):
    """
    Read execution summary for a specific agent from shared_knowledge.xml

    Args:
        agent_name (str): Name of the agent to read summary for

    Returns:
        str: Summary text or None if not found
    """
    xml_file = "shared_knowledge.xml"

    try:
        if not os.path.exists(xml_file):
            return None

        tree = ET.parse(xml_file)
        root = tree.getroot()

        agent_element = root.find(agent_name)
        if agent_element is not None:
            return agent_element.text.strip() if agent_element.text else None
        else:
            return None

    except Exception as e:
        print(f"❌ Error reading from XML file: {str(e)}")
        return None


def read_all_summaries():
    """
    Read all agent summaries from shared_knowledge.xml

    Returns:
        dict: Dictionary with agent names as keys and summaries as values
    """
    xml_file = "shared_knowledge.xml"
    summaries = {}

    try:
        if not os.path.exists(xml_file):
            return summaries

        tree = ET.parse(xml_file)
        root = tree.getroot()

        for agent_element in root:
            if agent_element.text:
                summaries[agent_element.tag] = agent_element.text.strip()

        return summaries

    except Exception as e:
        print(f"❌ Error reading from XML file: {str(e)}")
        return summaries
