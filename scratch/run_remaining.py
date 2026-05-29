import sys
import os

# Set UTF-8 encoding for Windows console to handle Vietnamese characters
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("============================================================")
print("GraphRAG Resume Pipeline — Steps 7 & 8 Only")
print("============================================================")

# 1. Community detection
print("\n[1/2] Detecting communities...")
from community.detector import detect_communities
detect_communities()

# 2. Community summarization
print("\n[2/2] Summarizing communities...")
from community.summarizer import summarize_all_communities
summarize_all_communities()

print("\n============================================================")
print("✅ Resume pipeline finished successfully!")
print("============================================================")
