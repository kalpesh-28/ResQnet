import os, json
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    generation_config=genai.types.GenerationConfig(
        temperature=0.3,
        max_output_tokens=512,
        response_mime_type="application/json",
    ),
)
prompt = (
    'Return this exact JSON filled with real values:\n'
    '{\n'
    '  "overall_severity": "critical",\n'
    '  "total_affected": 5000,\n'
    '  "active_zones": ["Nashik", "Pune", "Aurangabad"],\n'
    '  "cross_incident_risk": "one sentence here",\n'
    '  "immediate_priorities": ["priority 1", "priority 2", "priority 3"],\n'
    '  "assessment_summary": "two sentences here"\n'
    '}\n'
    'Return ONLY the JSON, no extra text.'
)

r = model.generate_content(prompt)
raw = r.text or ""
print("RAW LEN:", len(raw))
print("RAW[:800]:", repr(raw[:800]))

first = raw.find("{")
last = raw.rfind("}")
if first != -1 and last != -1 and last > first:
    cleaned = raw[first:last + 1]
    print("CLEANED OK, len:", len(cleaned))
    try:
        parsed = json.loads(cleaned)
        print("PARSE SUCCESS:", list(parsed.keys()))
    except Exception as e:
        print("PARSE FAILED:", e)
        print("CLEANED:", repr(cleaned[:500]))
else:
    print("No JSON brackets found!")
