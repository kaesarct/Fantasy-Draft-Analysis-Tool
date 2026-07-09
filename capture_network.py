import json
import os
import sys
from playwright.sync_api import sync_playwright

output_file = os.path.join(os.path.dirname(__file__), "network_log.json")
logs = []

def handle_response(response):
    request = response.request
    if request.resource_type in ["xhr", "fetch"]:
        try:
            try:
                response_text = response.text()
            except Exception:
                response_text = "<binary or failed to read body>"
                
            try:
                request_body = request.post_data
            except Exception:
                request_body = None

            log_entry = {
                "url": request.url,
                "method": request.method,
                "request_headers": dict(request.headers),
                "request_payload": request_body,
                "response_status": response.status,
                "response_headers": dict(response.headers),
                "response_payload": response_text
            }
            logs.append(log_entry)
            print(f"Captured: {request.method} {request.url}")
            
            # Save incrementally
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error logging response: {e}")

def main():
    print(f"Logging file will be saved at: {output_file}")
    with sync_playwright() as p:
        print("Launching browser in headful mode...")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # Intercept responses
        page.on("response", handle_response)
        
        url = "https://leghe.fantacalcio.it/fantacalcio-tamarros"
        print(f"Navigating to {url} ...")
        page.goto(url)
        
        print("\n" + "="*60)
        print("Browser is open and running.")
        print("Please log in and perform the actions you need.")
        print("All XHR/Fetch requests are being intercepted in the background.")
        print("Close the browser window when you are done to save and exit.")
        print("="*60 + "\n")
        
        try:
            page.wait_for_event("close", timeout=0)
        except KeyboardInterrupt:
            print("\nExiting due to keyboard interrupt...")
        except Exception as e:
            print(f"\nBrowser closed: {e}")
        finally:
            print("Closing browser...")
            browser.close()

if __name__ == "__main__":
    main()
