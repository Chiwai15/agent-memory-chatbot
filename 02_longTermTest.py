import os
import asyncio
import uuid
from dotenv import load_dotenv
from langchain_core.tools import tool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage, trim_messages
from langchain.chat_models import init_chat_model
from typing import Dict, List, Any
from langgraph.store.postgres.aio import AsyncPostgresStore

# Load environment variables from .env file
load_dotenv()

# Initialize the LLM using LangGraph's recommended approach
llm = init_chat_model(
    model=os.getenv("LLM_MODEL", "openai:gpt-4"),
    temperature=0,
    base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
    api_key=os.getenv("OPENAI_API_KEY", "your-api-key-here")
)


@tool("book_hotel", description="Book a hotel reservation")
def book_hotel(hotel_name: str):
    """
    Simulates booking a hotel reservation.

    Args:
        hotel_name: Name of the hotel to book

    Returns:
        Confirmation message with booking details
    """
    return f"Successfully booked accommodation at {hotel_name}."


def parse_messages(messages: List[Any]) -> None:
    """
    Parse and display detailed information about conversation messages.

    Prints comprehensive details for HumanMessage, AIMessage, and ToolMessage types
    including content, metadata, tool calls, and token usage.

    Args:
        messages: List of message objects from the conversation
    """
    print("=== Message Parsing Results ===")
    for idx, msg in enumerate(messages, 1):
        print(f"\nMessage {idx}:")

        # Get message type
        msg_type = msg.__class__.__name__
        print(f"Type: {msg_type}")

        # Extract message content
        content = getattr(msg, 'content', '')
        print(f"Content: {content if content else '<empty>'}")

        # Process additional information
        additional_kwargs = getattr(msg, 'additional_kwargs', {})
        if additional_kwargs:
            print("Additional Information:")
            for key, value in additional_kwargs.items():
                if key == 'tool_calls' and value:
                    print("  Tool Calls:")
                    for tool_call in value:
                        print(f"    - ID: {tool_call['id']}")
                        print(f"      Function: {tool_call['function']['name']}")
                        print(f"      Arguments: {tool_call['function']['arguments']}")
                else:
                    print(f"  {key}: {value}")

        # Handle ToolMessage specific fields
        if msg_type == 'ToolMessage':
            tool_name = getattr(msg, 'name', '')
            tool_call_id = getattr(msg, 'tool_call_id', '')
            print(f"Tool Name: {tool_name}")
            print(f"Tool Call ID: {tool_call_id}")

        # Handle AIMessage tool calls and metadata
        if msg_type == 'AIMessage':
            tool_calls = getattr(msg, 'tool_calls', [])
            if tool_calls:
                print("Tool Calls:")
                for tool_call in tool_calls:
                    print(f"  - Name: {tool_call['name']}")
                    print(f"    Arguments: {tool_call['args']}")
                    print(f"    ID: {tool_call['id']}")

            # Extract metadata
            metadata = getattr(msg, 'response_metadata', {})
            if metadata:
                print("Metadata:")
                token_usage = metadata.get('token_usage', {})
                print(f"  Token Usage: {token_usage}")
                print(f"  Model Name: {metadata.get('model_name', 'Unknown')}")
                print(f"  Finish Reason: {metadata.get('finish_reason', 'Unknown')}")

        # Print message ID
        msg_id = getattr(msg, 'id', 'Unknown')
        print(f"Message ID: {msg_id}")
        print("-" * 50)


def save_graph_visualization(graph, filename: str = "graph.png") -> None:
    """
    Save a visual representation of the agent's state graph.

    Exports the graph as a PNG image using Mermaid format.

    Args:
        graph: The agent graph instance
        filename: Output file path for the visualization
    """
    try:
        with open(filename, "wb") as f:
            f.write(graph.get_graph().draw_mermaid_png())
        print(f"Graph visualization saved as {filename}")
    except IOError as e:
        print(f"Failed to save graph visualization: {e}")


def pre_model_hook(state):
    """
    Pre-processing hook called before each LLM invocation.

    Trims the conversation history to manage token limits or message counts.
    This helps optimize context window usage and reduce costs.

    Args:
        state: Current agent state containing messages

    Returns:
        Dictionary with trimmed messages under 'llm_input_messages' key
    """
    trimmed_messages = trim_messages(
        messages=state["messages"],
        # Limit to 4 messages
        max_tokens=4,
        strategy="last",
        # Use len to count message quantity
        token_counter=len,
        start_on="human",
        include_system=True,
        allow_partial=False,
    )

    # Alternative token-based trimming approach (commented out)
    # trimmed_messages = trim_messages(
    #     messages=state["messages"],
    #     strategy="last",
    #     token_counter=count_tokens_approximately,
    #     max_tokens=20,
    #     start_on="human",
    #     end_on=("human", "tool"),
    # )

    # Return updated information under 'llm_input_messages' or 'messages' key
    return {"llm_input_messages": trimmed_messages}


async def run_agent():
    """
    Main agent execution function demonstrating both short-term and long-term memory.

    Creates a ReAct agent with:
    - PostgreSQL-backed conversation checkpointing (short-term memory)
    - PostgreSQL-backed persistent storage (long-term memory)

    Long-term memory enables the agent to remember user preferences and
    historical information across different conversation sessions.
    """
    # Define custom tools list
    tools = [book_hotel]

    # Define system message to guide tool usage
    system_message = SystemMessage(content=(
        "You are an AI assistant."
    ))

    # PostgreSQL connection string for persistent storage
    db_uri = "postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable"

    # Initialize both short-term (checkpointer) and long-term (store) memory
    async with (
        AsyncPostgresSaver.from_conn_string(db_uri) as checkpointer,
        AsyncPostgresStore.from_conn_string(db_uri) as store
    ):
        await store.setup()
        await checkpointer.setup()

        # Create ReAct-style agent with both memory types
        agent = create_react_agent(
            model=llm,
            tools=tools,
            prompt=system_message,
            # Optional node to add processing before the agent node
            pre_model_hook=pre_model_hook,
            checkpointer=checkpointer,
            store=store
        )

        # Save agent graph visualization to local file (optional)
        # save_graph_visualization(agent)

        # Define thread ID and user ID for dual-level memory management
        config = {"configurable": {"thread_id": "1", "user_id": "1"}}

        # Retrieve long-term memories (e.g., user preferences, settings)
        user_id = config["configurable"]["user_id"]
        namespace = ("memories", user_id)
        memories = await store.asearch(namespace, query="")
        info = " ".join([d.value["data"] for d in memories]) if memories else "No long-term memory information"
        print(f"Retrieved information: {info}")

        # Augment user input with retrieved long-term context
        user_input = f"Book a Hilton Hotel, my additional preferences are: {info}"

        # Custom storage logic - Store long-term memories
        # Uncomment to add new memories to the store
        # namespace = ("memories", config["configurable"]["user_id"])
        # memory1 = "My name is Nelson"
        # await store.aput(namespace, str(uuid.uuid4()), {"data": memory1})
        # memory2 = "My accommodation preferences: window seat, WiFi"
        # await store.aput(namespace, str(uuid.uuid4()), {"data": memory2})
        # print("Long-term memory stored!")

        # 1. Non-streaming query processing
        agent_response = await agent.ainvoke(
            {"messages": [HumanMessage(content=user_input)]},
            config
        )

        # Format and display returned messages
        parse_messages(agent_response['messages'])
        agent_response_content = agent_response["messages"][-1].content
        print(f"Final Response: {agent_response_content}")

        # 2. Streaming query processing (alternative approach)
        # async for message_chunk, metadata in agent.astream(
        #         input={"messages": [HumanMessage(content=user_input)]},
        #         config=config,
        #         stream_mode="messages"
        # ):
        #     # Test raw output
        #     # print(f"Token: {message_chunk}\n")
        #     # print(f"Metadata: {metadata}\n\n")
        #
        #     # Skip tool output
        #     # if metadata["langgraph_node"] == "tools":
        #     #     continue
        #
        #     # Output final result
        #     if message_chunk.content:
        #         print(message_chunk.content, end="|", flush=True)


if __name__ == "__main__":
    asyncio.run(run_agent())
