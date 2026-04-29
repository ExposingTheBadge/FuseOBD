"""AI-powered fault code diagnostics — mechanic persona analyzing DTC relationships."""
import os
import json
import anthropic

# Read from Windows system environment variables (set via System Properties)
AUTH_TOKEN = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", "")
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
MODEL = (
    os.environ.get("ANTHROPIC_MODEL")
    or os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL")
    or "claude-opus-4-7"
)

SYSTEM_PROMPT = """You are a master Ford diagnostics technician with 30 years of experience. You think like a mechanic, not a computer.

Your job: analyze a set of diagnostic trouble codes (DTCs) from a vehicle and determine:
1. Which faults are the ROOT CAUSE — the original problem
2. Which faults are CASCADE EFFECTS — triggered by the root cause, not independent problems
3. Which faults are ISOLATED — genuinely separate issues

How mechanics think about cascading faults:
- A bad wheel speed sensor (ABS module) can trigger: ABS light, traction control fault, stability control fault, cruise control inop, AWD/4WD fault — because all those systems read wheel speed from the ABS module
- Low battery voltage can trigger: random misfire codes, CAN communication errors (U-codes), multiple sensor rationality faults — the modules aren't broken, they're under-volted
- A failed O2 sensor can trigger: O2 heater circuit code, fuel trim codes, catalyst efficiency code — they cascade from the sensor failure
- A stuck thermostat can trigger: coolant temp rationality code, P0128 (coolant temp below regulating temp), and if ignored, head gasket codes from overheating
- A clogged DPF can trigger: EGR flow codes, turbo underboost, exhaust pressure sensor codes — all downstream of the restriction
- CAN bus issues (U-codes): a single module going offline can trigger lost communication codes from every module that talks to it

Output your analysis as JSON:
{
  "summary": "Brief mechanic's overview of what's wrong with this vehicle (2-3 sentences, plain English, like you're explaining to the owner)",
  "root_causes": [
    {"code": "P0000", "module": "PCM", "description": "...", "explanation": "Why this is likely a root cause", "fix_first": true}
  ],
  "cascade_groups": [
    {
      "trigger_code": "P0000",
      "trigger_description": "The root cause",
      "affected_codes": ["P0001", "P0002"],
      "mechanism": "How the root cause creates these symptoms"
    }
  ],
  "isolated_faults": [
    {"code": "P0003", "module": "ABS", "description": "...", "explanation": "Why this appears unrelated"}
  ],
  "repair_priority": ["List codes in the order a mechanic should investigate/fix them"],
  "overall_severity": "green|yellow|red — green=nothing urgent, yellow=needs attention soon, red=stop driving and fix now",
  "estimated_repair_difficulty": "easy|moderate|hard — overall assessment"
}

Be specific. Reference actual Ford module names and known failure patterns. If you see CAN communication errors (U-codes), always check if they trace back to a single module going offline."""


def analyze_dtcs(module_dtcs: list, vehicle_info: str = "") -> dict:
    """Analyze fault codes using AI. Returns parsed JSON result or error dict."""
    if not AUTH_TOKEN:
        return {"error": "No AI auth token configured. Set ANTHROPIC_AUTH_TOKEN in Windows system environment."}

    # Build the fault list for the AI. Each `mod` is a dict with keys
    # 'module_abbrev' and 'dtcs', mirroring MechanicChat.start_session().
    fault_lines = []
    for mod in module_dtcs:
        for dtc in mod.get("dtcs", []):
            desc = dtc.get("description", "") or dtc.get("desc", "") or "No description available"
            status = dtc.get("status_text", "") or dtc.get("status", "")
            fault_lines.append(f"  [{mod['module_abbrev']}] {dtc['code']} — {desc}  [{status}]")

    fault_text = "\n".join(fault_lines)

    user_prompt = f"""Analyze these fault codes from a vehicle I'm diagnosing:

{fault_text}

{vehicle_info or "No additional vehicle info provided."}

Total faults: {len(fault_lines)}

Think step by step as a mechanic. Look at which modules are involved, whether communication codes (U-codes) point to a single module going offline, and whether sensor faults could cascade to other systems."""

    kwargs = {"api_key": AUTH_TOKEN, "timeout": 120.0}
    if BASE_URL:
        kwargs["base_url"] = BASE_URL

    try:
        client = anthropic.Anthropic(**kwargs)
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = response.content[0].text

        # Extract JSON from response (may be wrapped in ```json blocks)
        json_match = None
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            json_match = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            json_match = text[start:end].strip()
        elif "{" in text and "}" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            json_match = text[start:end]

        if json_match:
            parsed = json.loads(json_match)
            parsed["_raw_analysis"] = text
            return parsed
        else:
            return {"error": "Could not parse AI response", "_raw_analysis": text}

    except anthropic.RateLimitError:
        return {"error": "AI service rate limited. Try again in a moment."}
    except anthropic.APIStatusError as e:
        return {"error": f"AI API error: {e.message}"}
    except Exception as e:
        return {"error": f"AI analysis failed: {str(e)}"}
