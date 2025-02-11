# Langchain Genezio Code Interpreter

The Langchain Genezio Code Interpreter allows you to add code execution functionality into the LLMs. The code is executed in a secured environment on Genezio Cloud Platform. 

## Installation

```
pip install langchain-genezio
```

## Usage

```
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain-genezio import GenezioPythonInterpreter

tools = [
    GenezioPythonInterpreter(
        url=os.getenv("GENEZIO_PROJECT_URL"),
    )
]

llm = ChatAnthropic(model="claude-3-haiku-20240307", temperature=0)

prompt_template = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a helpful assistant. Make sure to use a tool if you need to solve a problem.",
        ),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)

agent = create_tool_calling_agent(llm, tools, prompt_template)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
# Ask a tough question
result = agent_executor.invoke({"input": "What is the 888th prime number?"})
print(result["output"][0]["text"])
```
