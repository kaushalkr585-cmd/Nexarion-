import json
import time
import urllib.request

from code_review.config import get_settings


def benchmark_nvidia():
    s = get_settings()
    url = f"{s.nvidia_base_url}/chat/completions"
    payload = {
        "model": s.nvidia_model,
        "messages": [{"role": "user", "content": "What is Python in 1 sentence?"}],
        "stream": True,
        "max_tokens": 128,
    }
    t0 = time.time()
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {s.nvidia_api_key}",
            "Content-Type": "application/json",
        },
    )
    ttft = None
    chunks = 0
    full_text = ""
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            for line in resp:
                line_str = line.decode().strip()
                if line_str.startswith("data: ") and line_str != "data: [DONE]":
                    if ttft is None:
                        ttft = time.time() - t0
                    data = json.loads(line_str[6:])
                    content = data["choices"][0]["delta"].get("content", "")
                    full_text += content
                    chunks += 1
        total_time = time.time() - t0
        msg = (
            f"[NVIDIA] TTFT: {ttft:.3f}s | Total: {total_time:.3f}s | "
            f"Chunks: {chunks} | Text: {full_text[:60]}..."
        )
        print(msg)
    except Exception as e:
        print(f"[NVIDIA] Error: {e}")


def benchmark_ollama():
    s = get_settings()
    url = f"{s.ollama_base_url}/api/chat"
    payload = {
        "model": s.ollama_model,
        "messages": [{"role": "user", "content": "What is Python in 1 sentence?"}],
        "stream": True,
    }
    t0 = time.time()
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    ttft = None
    chunks = 0
    full_text = ""
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            for line in resp:
                line_str = line.decode().strip()
                if line_str:
                    if ttft is None:
                        ttft = time.time() - t0
                    data = json.loads(line_str)
                    content = data.get("message", {}).get("content", "")
                    full_text += content
                    chunks += 1
                    if data.get("done", False):
                        break
        total_time = time.time() - t0
        msg = (
            f"[OLLAMA] TTFT: {ttft:.3f}s | Total: {total_time:.3f}s | "
            f"Chunks: {chunks} | Text: {full_text[:60]}..."
        )
        print(msg)
    except Exception as e:
        print(f"[OLLAMA] Error: {e}")

if __name__ == "__main__":
    benchmark_nvidia()
    benchmark_ollama()
