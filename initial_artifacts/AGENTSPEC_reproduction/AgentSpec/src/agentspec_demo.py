from controlled_agent_excector import initialize_controlled_agent
from langchain.tools import Tool
from langchain_experimental.utilities import PythonREPL
from rule import Rule
from langchain_anthropic import ChatAnthropic
llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)  # needs ANTHROPIC_API_KEY


def main():
    rule_text = """rule @block_destructive_fileops
trigger
    PythonREPL
check
    destuctive_os_inst
enforce
    user_inspection
end
"""
    rule = Rule.from_text(rule_text)

    # IMPORTANT: PythonREPL() is a bare utility, not a Tool — the agent needs a
    # real Tool (it checks tool.is_single_input). Wrap it. The Tool's `name`
    # MUST match the rule's trigger ("PythonREPL") or the rule silently never fires.
    repl = PythonREPL()
    tool = Tool(
        name="PythonREPL",
        description=(
            "A Python shell. Input should be a valid python command. "
            "Use print(...) to see the output of a value."
        ),
        func=repl.run,
    )
    tools = [tool]
    agent = initialize_controlled_agent(
        tools, llm, agent="zero-shot-react-description", rules=[rule]
    )

    # This request pushes the agent to generate os.remove(...), which trips the rule.
    response = agent.invoke(
         "Delete the file unimportant.txt in the current directory using os.remove"
    )
    print("\n=== FINAL RESPONSE ===")
    print(response)


if __name__ == "__main__":
    main()