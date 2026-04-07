"""Agent definitions with tool use (web search)."""

from __future__ import annotations

import anthropic
import os


# ── Web search tool ───────────────────────────────────────────
def web_search(query: str) -> str:
    """Search the web using DuckDuckGo."""
    try:
        from duckduckgo_search import DDGS
        results = DDGS().text(query, max_results=3)
        if not results:
            return "未找到相关结果。"
        return "\n".join(f"- {r['title']}: {r['body']}" for r in results)
    except Exception as e:
        return f"搜索失败: {e}"


TOOLS = [
    {
        "name": "web_search",
        "description": "搜索互联网获取最新信息、研究论文、技术观点等。当你需要引用最新数据或事实时使用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                }
            },
            "required": ["query"],
        },
    }
]


class Agent:
    def __init__(self, name: str, personality: str, color: str, avatar: str):
        self.name = name
        self.personality = personality
        self.color = color
        self.avatar = avatar
        self.client = anthropic.Anthropic()
        self.model = os.getenv("MODEL", "claude-sonnet-4-20250514")

    def generate_response(self, messages: list[dict], topic: str | None = None) -> str:
        """Generate a response with optional tool use (web search)."""
        system_parts = [
            f"你的名字是「{self.name}」。{self.personality}",
            "你正在一个AI专家圆桌讨论中。请给出深入、专业的技术观点（3-5句话）。",
            "可以引用具体论文、数据、技术框架。如果需要查证最新信息，使用 web_search 工具。",
            "不要总是同意别人，要有独到见解，可以质疑和反驳。",
            "用中文回复。",
            "你的发言必须紧紧围绕讨论话题，不要跑题。",
        ]
        if topic:
            system_parts.insert(1, f"🎯 本次讨论话题：{topic}。请始终围绕这个话题展开讨论。")

        response = self.client.messages.create(
            model=self.model,
            system="\n".join(system_parts),
            messages=messages,
            tools=TOOLS,
            max_tokens=600,
        )

        # Handle tool use loop
        while response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    if block.name == "web_search":
                        result = web_search(block.input["query"])
                    else:
                        result = f"未知工具: {block.name}"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            response = self.client.messages.create(
                model=self.model,
                system="\n".join(system_parts),
                messages=messages,
                tools=TOOLS,
                max_tokens=600,
            )

        # Extract final text
        for block in response.content:
            if block.type == "text":
                return block.text.strip()
        return ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "personality": self.personality,
            "color": self.color,
            "avatar": self.avatar,
        }


def generate_summary(chat_history: list[dict], topic: str | None) -> str:
    """Generate a structured summary of the discussion."""
    client = anthropic.Anthropic()
    model = os.getenv("MODEL", "claude-sonnet-4-20250514")

    lines = []
    for m in chat_history:
        if m["type"] == "chat":
            lines.append(f"【{m['agent']}】{m['text']}")
    transcript = "\n".join(lines)

    topic_desc = f"讨论话题：{topic}" if topic else "自由讨论"
    system_prompt = (
        "你是一个讨论总结助手。请根据聊天记录生成一份结构化的讨论总结。"
        "包含以下部分：\n"
        "1. 📌 核心观点（各方的关键论点）\n"
        "2. 🔥 主要分歧（有争议的地方）\n"
        "3. 💡 共识与启发（大家达成一致或互相启发的点）\n"
        "4. 🎯 结论（一句话总结）\n"
        "用中文，简洁有力。"
    )

    response = client.messages.create(
        model=model,
        system=system_prompt,
        messages=[{"role": "user", "content": f"{topic_desc}\n\n聊天记录：\n{transcript}"}],
        max_tokens=800,
    )
    return response.content[0].text.strip()


# ── Default agents ────────────────────────────────────────────
def _create_defaults() -> dict[str, Agent]:
    return {
        "Sam Altman": Agent(
            name="Sam Altman",
            personality=(
                "你是 Sam Altman，OpenAI CEO。你坚信 AGI 将在本十年内到来，并能解决人类最重大的挑战。"
                "你强调 AI 的民主化访问和商业化落地，认为算力是新时代的货币。"
                "你对 AI 安全持审慎乐观态度，主张通过迭代部署来学习风险。"
                "你的表达简洁有力，喜欢从商业和战略角度思考问题。"
                "你经常谈论 ChatGPT、GPT 系列模型、以及对创业者的影响。"
            ),
            color="#10a37f",
            avatar="🟢",
        ),
        "Yann LeCun": Agent(
            name="Yann LeCun",
            personality=(
                "你是 Yann LeCun，Meta 首席 AI 科学家，图灵奖得主，卷积神经网络之父。"
                "你对当前的大语言模型路线持批判态度，认为自回归预测不是通向智能的正确路径。"
                "你主张通过自监督学习和世界模型来实现真正的智能，强调 AI 需要理解物理世界。"
                "你认为当前的 LLM 不具备真正的推理能力，经常质疑对 AGI 的过度炒作。"
                "你说话直接坦率，学术气息浓厚，喜欢引用具体的研究成果来论证观点。"
                "你经常提及 JEPA 架构、目标驱动 AI 等你自己的研究方向。"
            ),
            color="#1877f2",
            avatar="🔵",
        ),
        "Demis Hassabis": Agent(
            name="Demis Hassabis",
            personality=(
                "你是 Demis Hassabis，Google DeepMind CEO，诺贝尔化学奖得主。"
                "你相信 AI 最有价值的应用是加速科学发现，AlphaFold 证明了这一点。"
                "你强调通用人工智能需要结合深度学习与经典 AI 方法（如搜索、规划、强化学习）。"
                "你对 AI 安全非常重视，主张在追求能力突破的同时建立严格的安全框架。"
                "你说话温和但自信，喜欢用科学史上的突破来类比 AI 的发展。"
                "你经常提及 AlphaGo、AlphaFold、Gemini 以及 AI 在数学和材料科学中的应用。"
            ),
            color="#ea4335",
            avatar="🔴",
        ),
        "Andrew Ng": Agent(
            name="Andrew Ng",
            personality=(
                "你是 Andrew Ng，DeepLearning.AI 和 Landing AI 创始人，前 Google Brain 负责人，前百度首席科学家。"
                "你是 AI 教育的布道者，坚信'AI 是新时代的电力'。"
                "你主张务实地看待 AI，强调数据-centric AI 的重要性胜过模型-centric。"
                "你对 AI 泡沫论不以为然，认为即便有泡沫，长期趋势依然向上。"
                "你关注 AI 如何赋能传统行业，特别是制造业和医疗。"
                "你说话亲切平和，善于用简单的比喻解释复杂概念，经常引用教学和实践经验。"
            ),
            color="#f59e0b",
            avatar="🟡",
        ),
    }


AGENTS: dict[str, Agent] = _create_defaults()


def get_agent(name: str) -> Agent:
    return AGENTS[name]


def reset_agents():
    global AGENTS
    AGENTS = _create_defaults()
