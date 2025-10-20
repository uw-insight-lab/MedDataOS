"""
Logging and knowledge management utilities.
Handles console logging and XML-based shared knowledge storage.
"""
import json
import os
import xml.etree.ElementTree as ET
from xml.dom import minidom


def log_user(msg):
    """Log a user message to console."""
    print(f"🧑‍💬 {msg}")


def log_assistant(msg):
    """Log an assistant message to console."""
    print(f"🤖 {msg}")


def log_tool_call(name, input_data):
    """Log a tool call to console."""
    print(f"🛠️  {name}: {input_data}")


def log_tool_result(res):
    """Log a tool result to console."""
    print(f"📦 → {json.dumps(res, ensure_ascii=False)}")


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
