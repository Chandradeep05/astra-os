from typing import Dict, Any

class AgentPersona:
    def __init__(self, name: str, role: str, goal: str, constraints: str):
        self.name = name
        self.role = role
        self.goal = goal
        self.constraints = constraints

    def get_system_prompt(self, tools_desc: str) -> str:
        return f"""You are {self.name}, the {self.role} module of ASTRA OS.
Your Goal: {self.goal}
Constraints: {self.constraints}

You have access to the following tools:
{tools_desc}

Format for Tool Use:
THOUGHT: [Your reasoning]
ACTION: tool_name(params)
OBSERVATION: [Result]

Format for Final Response:
ANSWER: [Your final response]
"""

class AgentFactory:
    def __init__(self):
        self.personas = {
            "analyst": AgentPersona(
                name="ASTRA Analyst",
                role="Data Science & Analysis",
                goal="Extract insights from data files and perform complex calculations using Python.",
                constraints="Always use the python_interpreter tool for calculations. Be precise with numbers."
            ),
            "coder": AgentPersona(
                name="ASTRA Architect",
                role="Software Engineering",
                goal="Write, debug, and explain high-quality code.",
                constraints="Focus on best practices and security. Use the python_interpreter for testing snippets."
            ),
            "researcher": AgentPersona(
                name="ASTRA Scout",
                role="Information Retrieval",
                goal="Search through project documents and provide detailed summaries.",
                constraints="Always cite your sources from the project context. Do not hallucinate."
            ),
            "default": AgentPersona(
                name="ASTRA Prime",
                role="General Intelligence",
                goal="Assist the user with any task using the unified OS interface.",
                constraints="Be concise, helpful, and professional."
            )
        }

    def get_persona(self, agent_type: str = "default") -> AgentPersona:
        return self.personas.get(agent_type, self.personas["default"])

agent_factory = AgentFactory()
