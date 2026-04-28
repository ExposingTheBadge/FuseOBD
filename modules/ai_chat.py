"""AI Mechanic Chat — interactive diagnostic assistant with web search capability."""
import os
import json
import urllib.request
import urllib.parse
import urllib.error
import ssl
import re
import anthropic

AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", "")
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
MODEL = (
    os.environ.get("ANTHROPIC_MODEL")
    or os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL")
    or "claude-opus-4-7"
)

SYSTEM_PROMPT = """You are a master automotive diagnostician with 30 years of hands-on experience across ALL vehicle makes — Ford, GM, Toyota, Honda, BMW, Mercedes, VW, Hyundai, Kia, Nissan, Chrysler, Subaru, Mazda, Volvo, Land Rover, and everything else. You work on cars every day. You think like a mechanic, not a computer.

## Your tools:
You can use these tools to gather information before answering:
- **search_web(query)** — Search the internet for TSBs, forum discussions, repair guides, common fixes for specific DTCs. Use this before giving diagnostic advice — real mechanics look things up constantly.
- **fetch_page(url)** — Fetch content from a specific web page (forum post, repair guide, TSB). Use this when search results look promising and you want details.

## How you diagnose:
1. Look at the fault codes AS A SYSTEM, not individually. A single bad ground or weak battery can throw 20 codes across 8 modules.
2. Check for CAN bus communication errors (U-codes) — these often trace to one module going offline, which cascades to every module that talks to it.
3. Look at freeze frame data (if available) — what were the conditions when the fault set?
4. Consider the vehicle's age, mileage, known issues for that make/model/year.
5. Search for TSBs and common fixes for the specific codes on the specific vehicle.

## Response style:
- Talk like a real mechanic — plain English, no corporate speak
- Tell the owner what's actually wrong and what's just noise
- Give repair difficulty estimates (driveway job vs. need a lift vs. dealer-only)
- Mention if something is safe to drive or needs immediate attention
- If you search the web, incorporate what you find into your diagnosis
- Be honest when something needs a professional — don't pretend everything is DIY

## When answering:
- Reference specific fault codes by number
- Explain the "why" behind your diagnosis
- If multiple codes trace to one root cause, explain the cascade
- Give the owner a prioritized list: fix this first, then this, then this"""


def _fetch_text(url: str, timeout: float = 8.0) -> str:
    """Fetch text content from a URL."""
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
            # Try to decode
            content_type = resp.headers.get("Content-Type", "")
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].split(";")[0].strip()
            try:
                text = raw.decode(charset, errors="replace")
            except Exception:
                text = raw.decode("utf-8", errors="replace")
            # Strip HTML tags for Claude consumption
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:8000]  # Limit to 8K chars
    except Exception as e:
        return f"Error fetching {url}: {str(e)}"


def _search_web(query: str) -> str:
    """Search the web using DuckDuckGo and return results."""
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        html = _fetch_text(url, timeout=10)

        # Extract result snippets
        results = []
        # Match DDG result blocks
        for match in re.finditer(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL):
            results.append(re.sub(r"<[^>]+>", "", match.group(1)).strip())

        if not results:
            # Try alternate extraction
            for match in re.finditer(r'class="result__body"[^>]*>(.*?)</a>', html, re.DOTALL):
                results.append(re.sub(r"<[^>]+>", "", match.group(1)).strip())

        if not results:
            # Try generic snippet extraction
            snippets = re.findall(r'class="[^"]*snippet[^"]*"[^>]*>(.*?)</', html, re.DOTALL)
            results = [re.sub(r"<[^>]+>", "", s).strip() for s in snippets if len(s) > 50]

        if not results:
            return f"No search results found for: {query}"

        return "\n\n".join(results[:5])  # Top 5 results
    except Exception as e:
        return f"Search error: {str(e)}"


# Tool definitions for Claude API
TOOLS = [
    {
        "name": "search_web",
        "description": "Search the internet for automotive diagnostic information, TSBs, forum discussions, repair guides, and common fixes. Use this to find real-world repair data for specific DTCs, vehicle issues, and diagnostic procedures.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query. Be specific — include the DTC code, vehicle make/model/year, and symptom. Example: 'P0420 Toyota Camry 2018 catalytic converter TSB' or 'Ford F150 P0300 misfire common causes forum'"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "fetch_page",
        "description": "Fetch and read the content of a specific web page. Use this when search results show a promising forum post, repair guide article, or TSB page that you want to read in detail.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL of the page to fetch"
                }
            },
            "required": ["url"]
        }
    }
]


class MechanicChat:
    """Interactive AI mechanic with web search and tool use."""

    def __init__(self):
        self.messages = []
        self.vehicle_info = {}
        self.dtc_data = []
        self._client = None

    def _get_client(self):
        if self._client is None:
            kwargs = {"api_key": AUTH_TOKEN, "timeout": 120.0}
            if BASE_URL:
                kwargs["base_url"] = BASE_URL
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def start_session(self, vehicle_info: dict, dtc_data: list):
        """Start a new diagnostic session with vehicle context."""
        self.vehicle_info = vehicle_info
        self.dtc_data = dtc_data

        fault_text = ""
        for mod in dtc_data:
            for dtc in mod.get("dtcs", []):
                desc = dtc.get("description", "") or "No description"
                status = dtc.get("status_text", "") or dtc.get("status", "") or "Unknown"
                fault_text += f"  [{mod['module_abbrev']}] {dtc['code']} — {desc}  [{status}]\n"

        vehicle_text = ""
        if vehicle_info:
            vehicle_text = "\n".join([
                f"  Year: {vehicle_info.get('year','?')}",
                f"  Make: {vehicle_info.get('make','?')}",
                f"  Model: {vehicle_info.get('model','?')}",
                f"  Engine: {vehicle_info.get('engine','?')} ({vehicle_info.get('displacement_l','?')}L {vehicle_info.get('cylinders','?')}cyl)",
                f"  Transmission: {vehicle_info.get('transmission','?')}",
                f"  Body: {vehicle_info.get('body_class','?')}",
                f"  Built: {vehicle_info.get('built_at','?')}",
                f"  VIN: {vehicle_info.get('vin','?')}",
            ])

        self.messages = [{
            "role": "user",
            "content": f"""I need you to diagnose my vehicle. Here's what I know:

VEHICLE INFO:
{vehicle_text or 'No vehicle info available yet'}

FAULT CODES:
{fault_text or 'No fault codes read yet'}

Please start by giving me your initial assessment. What do you see? What should I check first?"""
        }]

    def send_message(self, user_text: str) -> str:
        """Send a message to the AI mechanic and get the response. Handles tool use loop."""
        self.messages.append({"role": "user", "content": user_text})

        try:
            return self._run_tool_loop()
        except anthropic.RateLimitError:
            return "The AI service is rate limited right now. Give it a minute and try again."
        except anthropic.APIStatusError as e:
            return f"AI service error: {e.message}"
        except Exception as e:
            return f"AI chat error: {str(e)}"

    def _run_tool_loop(self, max_turns: int = 5) -> str:
        """Run the Claude tool use loop — Claude can call tools multiple times before responding."""
        current_messages = list(self.messages)

        for _ in range(max_turns):
            response = self._get_client().messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=current_messages,
            )

            # Check for tool use
            tool_uses = []
            text_blocks = []

            for block in response.content:
                if block.type == "tool_use":
                    tool_uses.append(block)
                elif block.type == "text":
                    text_blocks.append(block.text)

            # If Claude provided text and no tool use, we're done
            if text_blocks and not tool_uses:
                final_text = "\n".join(text_blocks)
                self.messages.append({"role": "assistant", "content": final_text})
                return final_text

            # If Claude wants to use tools
            if tool_uses:
                # Build assistant content with tool use blocks
                assistant_content = []
                for b in response.content:
                    if b.type == "text":
                        assistant_content.append({"type": "text", "text": b.text})
                    elif b.type == "tool_use":
                        assistant_content.append({
                            "type": "tool_use",
                            "id": b.id,
                            "name": b.name,
                            "input": b.input,
                        })

                current_messages.append({"role": "assistant", "content": assistant_content})

                # Execute tools and build results
                tool_results = []
                for tu in tool_uses:
                    if tu.name == "search_web":
                        result_text = _search_web(tu.input.get("query", ""))
                    elif tu.name == "fetch_page":
                        result_text = _fetch_text(tu.input.get("url", ""))
                    else:
                        result_text = f"Unknown tool: {tu.name}"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": result_text[:6000],
                    })

                current_messages.append({"role": "user", "content": tool_results})
                continue

            # No tool use and no text = unexpected; return whatever we have
            if text_blocks:
                return "\n".join(text_blocks)
            return "I'm not sure how to respond to that. Could you rephrase?"

        return "I've done several rounds of research but I'm going in circles. Let me give you what I have so far:\n\n" + "\n".join(text_blocks) if text_blocks else "I couldn't reach a conclusion. Let me start fresh — what would you like to know?"
