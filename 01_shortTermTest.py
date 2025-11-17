import os
import asyncio
import asyncpg
from dotenv import load_dotenv
from langchain_core.tools import tool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langgraph")
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from langchain.chat_models import init_chat_model
from typing import Dict, List, Any
from langchain_core.messages.utils import count_tokens_approximately, trim_messages

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
    Main agent execution function demonstrating short-term memory.

    Creates a ReAct agent with PostgreSQL-backed conversation checkpointing
    for maintaining context within a conversation thread.

    Checkpoint metadata (step, source, writes) is automatically stored by LangGraph.
    """
    # Define custom tools list
    tools = [book_hotel]

    # Define system message to guide tool usage
    system_message = SystemMessage(content=(
        "You are an AI assistant."
    ))

    # PostgreSQL connection string for persistent short-term memory
    db_uri = "postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable"

    # Initialize PostgresSaver for short-term memory checkpointing
    async with AsyncPostgresSaver.from_conn_string(db_uri) as checkpointer:
        await checkpointer.setup()

        # Create ReAct-style agent
        agent = create_react_agent(
            model=llm,
            tools=tools,
            prompt=system_message,
            # Optional node to add processing before the agent node
            # pre_model_hook=pre_model_hook,
            checkpointer=checkpointer,
        )

        # Save agent graph visualization to local file
        save_graph_visualization(agent)

        # Define thread ID for conversation tracking
        config = {"configurable": {"thread_id": "1"}}

        # User input examples (uncomment to test different scenarios)
        user_input = "Book a Hilton Hotel"
        # user_input = "My name is Nelson"
        # user_input = "What is my name?"

        # 1. Non-streaming query processing
        agent_response = await agent.ainvoke(
            {"messages": [HumanMessage(content=user_input)]},
            config
        )

        # Format and display returned messages
        parse_messages(agent_response['messages'])
        agent_response_content = agent_response["messages"][-1].content
        print(f"\nFinal Response: {agent_response_content}")

        # Display checkpoint metadata stored in PostgreSQL by LangGraph
        print("\n" + "=" * 80)
        print("CHECKPOINT METADATA (Automatically stored by LangGraph)")
        print("=" * 80)

        # Get the latest checkpoint state
        state_snapshot = await agent.aget_state(config)
        if state_snapshot:
            checkpoint_metadata = state_snapshot.metadata
            checkpoint_values = state_snapshot.values
            checkpoint_id = state_snapshot.config.get('configurable', {}).get('checkpoint_id', 'N/A')

            print(f"\nCheckpoint ID: {checkpoint_id}")
            print(f"\nMetadata (from checkpoints.metadata column):")
            print(f"  step: {checkpoint_metadata.get('step', 'N/A')} (execution step number)")
            print(f"  source: {checkpoint_metadata.get('source', 'N/A')} (input/loop/update)")
            print(f"  parents: {checkpoint_metadata.get('parents', {})}")

            # Query checkpoint_writes table to get writes information
            print(f"\n  writes: (queried from checkpoint_writes table)")
            conn = await asyncpg.connect(
                host='localhost',
                port=5432,
                user='postgres',
                password='postgres',
                database='postgres'
            )

            # Get writes for this checkpoint
            writes = await conn.fetch(
                """
                SELECT task_id, channel, type
                FROM checkpoint_writes
                WHERE checkpoint_id = $1
                ORDER BY task_id
                """,
                checkpoint_id
            )

            if writes:
                # Group writes by task_id
                writes_by_task = {}
                for write in writes:
                    task_id = write['task_id']
                    if task_id not in writes_by_task:
                        writes_by_task[task_id] = []
                    writes_by_task[task_id].append({
                        'channel': write['channel'],
                        'type': write['type']
                    })

                for task_id, task_writes in writes_by_task.items():
                    print(f"    Task {task_id[:8]}...:")
                    for write in task_writes:
                        print(f"      - channel: {write['channel']}, type: {write['type']}")
            else:
                print(f"    (No writes for final checkpoint - this is normal)")

                # Get writes from the most recent checkpoints with writes
                print(f"\n  Recent checkpoints with writes (last 3):")
                recent_writes = await conn.fetch(
                    """
                    SELECT DISTINCT ON (cw.checkpoint_id)
                        c.checkpoint_id,
                        c.metadata->>'step' as step,
                        c.metadata->>'source' as source,
                        COUNT(*) OVER (PARTITION BY cw.checkpoint_id) as write_count
                    FROM checkpoint_writes cw
                    JOIN checkpoints c ON c.checkpoint_id = cw.checkpoint_id
                    WHERE c.thread_id = '1'
                    ORDER BY cw.checkpoint_id DESC, cw.task_id
                    LIMIT 3
                    """
                )

                for rec in recent_writes:
                    print(f"    Checkpoint (step={rec['step']}, source={rec['source']}): {rec['write_count']} write(s)")

                    # Get detailed writes for this checkpoint
                    checkpoint_writes = await conn.fetch(
                        """
                        SELECT channel, type
                        FROM checkpoint_writes
                        WHERE checkpoint_id = $1
                        ORDER BY channel
                        """,
                        rec['checkpoint_id']
                    )
                    for w in checkpoint_writes:
                        print(f"      - channel: {w['channel']}, type: {w['type']}")

            await conn.close()

            print(f"\nNext Actions: {state_snapshot.next}")

            # Show checkpoint values (the actual state data)
            print(f"\nCheckpoint Values (current state):")
            print(f"  Total messages in state: {len(checkpoint_values.get('messages', []))}")

        else:
            print("No checkpoint found")

        print("=" * 80)

        # Query PostgreSQL directly to show what's actually stored
        print("\n" + "=" * 80)
        print("VIEW STORED CHECKPOINTS IN DATABASE")
        print("=" * 80)
        print("Run 'python view_checkpoints.py' to see all checkpoint metadata")
        print("stored in the PostgreSQL tables (checkpoints, checkpoint_writes).")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_agent())
