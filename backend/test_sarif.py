import json
from app.sarif_translator import SarifTranslator

def run_test():
    print("🔄 Reading semgrep_out.json...")
    try:
        with open("semgrep_out.json", "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        
        # Get the findings array
        triage_elements = raw_data.get("results", [])
        print(f"📋 Found {len(triage_elements)} raw vulnerability elements.")
        
        # Translate
        print("⚙️ Running data through SarifTranslator pipeline...")
        translator = SarifTranslator(triage_elements)
        sarif_payload = translator.generate_payload()
        
        # Print a snippet of the result to verify structure
        print("\n✅ Success! Here is a preview of your generated SARIF payload:")
        print(json.dumps(sarif_payload, indent=2)[:600] + "\n\n... [truncated preview] ...")
        
    except FileNotFoundError:
        print("❌ Error: Could not find 'semgrep_out.json' in the backend root directory.")
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")

if __name__ == "__main__":
    run_test()