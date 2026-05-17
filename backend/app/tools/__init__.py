"""
ASTRA OS — Tool Registration v3.0
====================================
Registers all available tools with the central registry.
Each tool is tagged with a risk level for the approval gate:

  🟢 SAFE:     Auto-execute (search, read, memory, system info)
  🟡 MODERATE: Execute with logging (Python executor)
  🔴 RISKY:    Requires human approval (file writes)

Import this module to populate the tool registry.
"""

from app.core.tool_registry import tool_registry, Tool
from app.agent.schemas import RiskLevel

# ──────────────────────────────────────────────
#  Import all tools
# ──────────────────────────────────────────────

from app.tools.python_executor import PythonExecutor
from app.tools.duckduckgo_search import DuckDuckGoSearchTool
from app.tools.doc_intelligence import DocIntelligenceTool
from app.tools.document_search import DocumentSearchTool
from app.tools.intelligence_tool import LongTermMemoryTool
from app.tools.recall_tool import MemoryRecallTool
from app.tools.vision_tool import run_vision_ocr
from app.tools.audio_tool import run_audio_transcription
from app.tools.filesystem_tool import FileReadTool, ListDirectoryTool, FileWriteTool
from app.tools.system_info_tool import SystemInfoTool


# ──────────────────────────────────────────────
#  Instantiate tools
# ──────────────────────────────────────────────

python_executor = PythonExecutor()
web_search = DuckDuckGoSearchTool()  # FREE — no API key needed
doc_intelligence = DocIntelligenceTool()
document_search = DocumentSearchTool()
long_term_memory = LongTermMemoryTool()
memory_recall = MemoryRecallTool()
file_read = FileReadTool()
list_directory = ListDirectoryTool()
file_write = FileWriteTool()
system_info = SystemInfoTool()


# ──────────────────────────────────────────────
#  Register tools with risk levels
# ──────────────────────────────────────────────

# 🟢 SAFE — Web search (DuckDuckGo, free, no API key)
tool_registry.register_tool(Tool(
    name=web_search.name,
    description=web_search.description,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to look up on the web"
            }
        },
        "required": ["query"]
    },
    func=web_search.execute,
    risk_level=RiskLevel.SAFE,
))

# 🟢 SAFE — System info (time, date, platform, disk)
tool_registry.register_tool(Tool(
    name=system_info.name,
    description=system_info.description,
    parameters={
        "type": "object",
        "properties": {
            "info_type": {
                "type": "string",
                "description": "Type of info: 'time', 'platform', 'disk', 'cwd', or 'all'",
                "enum": ["time", "platform", "disk", "cwd", "all"]
            }
        },
        "required": ["info_type"]
    },
    func=system_info.execute,
    risk_level=RiskLevel.SAFE,
))

# 🟢 SAFE — Read a file
tool_registry.register_tool(Tool(
    name=file_read.name,
    description=file_read.description,
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Full path to the file to read"
            }
        },
        "required": ["file_path"]
    },
    func=file_read.execute,
    risk_level=RiskLevel.SAFE,
))

# 🟢 SAFE — List directory contents
tool_registry.register_tool(Tool(
    name=list_directory.name,
    description=list_directory.description,
    parameters={
        "type": "object",
        "properties": {
            "directory_path": {
                "type": "string",
                "description": "Full path to the directory to list"
            }
        },
        "required": ["directory_path"]
    },
    func=list_directory.execute,
    risk_level=RiskLevel.SAFE,
))

# 🟢 SAFE — Document search (project knowledge base)
tool_registry.register_tool(Tool(
    name=document_search.name,
    description=document_search.description,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query for the knowledge base"
            },
            "project_id": {
                "type": "string",
                "description": "The project ID to search in"
            }
        },
        "required": ["query"]
    },
    func=document_search.execute,
    risk_level=RiskLevel.SAFE,
))

# 🟢 SAFE — Long-term memory (store facts)
tool_registry.register_tool(Tool(
    name=long_term_memory.name,
    description=long_term_memory.description,
    parameters={
        "type": "object",
        "properties": {
            "fact": {
                "type": "string",
                "description": "The piece of information to permanently retain"
            },
            "project_id": {
                "type": "string",
                "description": "Optional project ID, defaults to 'default'"
            }
        },
        "required": ["fact"]
    },
    func=long_term_memory.execute,
    risk_level=RiskLevel.SAFE,
))

# 🟢 SAFE — Memory recall (retrieve stored facts)
tool_registry.register_tool(Tool(
    name=memory_recall.name,
    description=memory_recall.description,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for in memory, e.g., 'user name' or 'preferences'"
            },
            "project_id": {
                "type": "string",
                "description": "Optional project ID, defaults to 'default'"
            }
        },
        "required": ["query"]
    },
    func=memory_recall.execute,
    risk_level=RiskLevel.SAFE,
))

# 🟡 MODERATE — Python code execution (sandboxed)
tool_registry.register_tool(Tool(
    name=python_executor.name,
    description=python_executor.description,
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The Python code to execute in the sandbox"
            }
        },
        "required": ["code"]
    },
    func=python_executor.execute,
    risk_level=RiskLevel.MODERATE,
))

# 🟡 MODERATE — Document generation (creates files)
tool_registry.register_tool(Tool(
    name=doc_intelligence.name,
    description=doc_intelligence.description,
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create_report", "create_presentation", "create_table"],
                "description": "Action to perform"
            },
            "content": {
                "type": "string",
                "description": "Content to write into the document"
            },
            "title": {
                "type": "string",
                "description": "Document title"
            },
            "format": {
                "type": "string",
                "enum": ["docx", "pptx", "xlsx"],
                "description": "Output format"
            }
        },
        "required": ["action", "content", "title"]
    },
    func=doc_intelligence.execute,
    risk_level=RiskLevel.MODERATE,
))

# 🔴 RISKY — File write (sandboxed but still creates files)
tool_registry.register_tool(Tool(
    name=file_write.name,
    description=file_write.description,
    parameters={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Name of the file to create (written to agent_output/ directory)"
            },
            "content": {
                "type": "string",
                "description": "Text content to write to the file"
            }
        },
        "required": ["filename", "content"]
    },
    func=file_write.execute,
    risk_level=RiskLevel.RISKY,
))

# 🟢 SAFE — Vision OCR
tool_registry.register_tool(Tool(
    name="vision_ocr",
    description="Extracts text from images (screenshots, photos) using local OCR.",
    parameters={
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "Path to the image file"
            }
        },
        "required": ["image_path"]
    },
    func=run_vision_ocr,
    risk_level=RiskLevel.SAFE,
))

# 🟢 SAFE — Audio transcription
tool_registry.register_tool(Tool(
    name="audio_transcription",
    description="Transcribes audio files (voice notes, WAV) into text.",
    parameters={
        "type": "object",
        "properties": {
            "audio_path": {
                "type": "string",
                "description": "Path to the audio file"
            }
        },
        "required": ["audio_path"]
    },
    func=run_audio_transcription,
    risk_level=RiskLevel.SAFE,
))
