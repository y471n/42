import sys

from museum.graph import build_graph

question = " ".join(sys.argv[1:]) or "What makes a life meaningful?"
result = build_graph().invoke({"question": question})
print(f"\nRESPONSE:\n{result['response']}")
for key in ("option_a", "option_b", "future_a", "future_b"):
    if result.get(key):
        print(f"This: \n{key.upper()}:\n{result[key]}")
