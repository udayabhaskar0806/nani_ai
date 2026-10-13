"""N.A.N.I. Web Command Deck Launcher
Starts the FastAPI web server and opens the futuristic J.A.R.V.I.S. Command Center in your browser.
"""

import webbrowser
import threading
import time
import uvicorn
from nani.web.server import app

def open_browser():
    time.sleep(1.2)
    print("🌐 Opening N.A.N.I. Command Deck in your browser: http://localhost:8000")
    webbrowser.open("http://localhost:8000")

def main():
    print("\n" + "=" * 60)
    print("  ⚡ N.A.N.I. WEB COMMAND CENTER ⚡")
    print("  Neural Analytical Network Intelligence")
    print("  Full Laptop Control • Screen Vision • Multi-AI Council")
    print("=" * 60 + "\n")
    
    # Launch browser automatically on Linux desktop
    threading.Thread(target=open_browser, daemon=True).start()

    # Start FastAPI server
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

if __name__ == "__main__":
    main()
