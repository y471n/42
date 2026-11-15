import sys
from museum.graph import build_graph

question = " ".join(sys.argv[1:]) or "What makes a life meaningful?"
result = build_graph().invoke({"question": question})

print(result)