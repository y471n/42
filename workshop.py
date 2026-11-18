import sys

from langgraph.types import Command
from museum.graph import build_graph

question = " ".join(sys.argv[1:]) or "What makes a life meaningful?"
graph = build_graph()
config = {"configurable": {"thread_id": "workshop"}}
result = graph.invoke({"question": question}, config)
for key in ("response", "option_a", "option_b", "future_a", "future_b", "critique"):
    if result.get(key):
        print(f"\n{key.upper()}:\n{result[key]}")
if "__interrupt__" in result:
    print("\nPaused for human review.")
    choice = input("Approve? [y/n] ").strip().lower()
    if choice not in ("y", "n"):
        raise ValueError("Enter y or n.")
    result = graph.invoke(Command(resume={"approve": choice == "y"}), config)
    print("APPROVED:", result["approved"])
