import os
import json
import time
import urllib.request
import urllib.error
import socket
from pathlib import Path

def call_gemini_rest_api(prompt_text, model_name="gemini-3.5-flash-lite", timeout=30):
    """
    Minimal standard-library REST client for Gemini API connectivity testing
    and diagnostic requests without requiring third-party SDK installation.
    Reads GEMINI_API_KEY from environment securely.
    Enforces bounded exponential backoff retries (max 3 attempts: 1s, 2s delays)
    specifically for HTTP 503, direct socket/read timeouts, and URLError-wrapped timeouts.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"success": False, "error": "Missing GEMINI_API_KEY environment variable"}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt_text}]
        }]
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    max_attempts = 3
    backoff_delays = [1.0, 2.0]

    last_error_result = {"success": False, "error": "Unknown error"}

    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                resp_bytes = response.read()
                if len(resp_bytes) > 500_000:
                    return {"success": False, "error": "Response exceeded maximum size limit"}
                
                result_json = json.loads(resp_bytes.decode("utf-8", errors="replace"))
                # Extract text from standard Gemini REST response structure
                candidates = result_json.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        text_output = parts[0].get("text", "")
                        return {"success": True, "text": text_output}
                
                return {"success": False, "error": "No candidates returned in response", "raw": result_json}
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="replace") if he.fp else ""
            err_result = {"success": False, "error": f"HTTPError {he.code}: {he.reason}", "details": err_body}
            # Retry only on HTTP 503
            if he.code == 503 and attempt < max_attempts:
                last_error_result = err_result
                time.sleep(backoff_delays[attempt - 1])
                continue
            return err_result
        except (socket.timeout, TimeoutError):
            err_result = {"success": False, "error": "TimeoutError: Request timed out"}
            if attempt < max_attempts:
                last_error_result = err_result
                time.sleep(backoff_delays[attempt - 1])
                continue
            return err_result
        except urllib.error.URLError as ue:
            if isinstance(ue.reason, (socket.timeout, TimeoutError)):
                err_result = {"success": False, "error": "TimeoutError: Request timed out"}
                if attempt < max_attempts:
                    last_error_result = err_result
                    time.sleep(backoff_delays[attempt - 1])
                    continue
                return err_result
            return {"success": False, "error": f"URLError: {ue.reason}"}
        except Exception as ex:
            return {"success": False, "error": f"Exception: {str(ex)}"}

    return last_error_result

if __name__ == "__main__":
    print("Gemini REST client module loaded.")
