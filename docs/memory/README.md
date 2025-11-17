# Memory System - Complete Guide

## Overview

The Memory Chat system uses a **two-layer memory architecture** combining short-term conversation context with long-term persistent storage.

## Two Types of Memory

### 1. Short-Term Memory (Conversation Checkpoints)
### 2. Long-Term Memory (Persistent Store)

---

## 📋 Short-Term Memory (Checkpoints)

### What It Stores:
- **Recent conversation messages** in the current session
- Both user messages and AI responses
- Stored in PostgreSQL `checkpoints` table

### How Long It Lasts:
- ✅ **Persists across page refreshes** (as long as you stay in the same session)
- ✅ **Survives browser restart** (stored in PostgreSQL, not just in RAM)
- ❌ **Does NOT transfer between sessions** (Session 1 can't see Session 2's messages)

### How Many Messages:
**The AI sees the last 30 messages from the conversation**

From `server.py` line 228:
```python
for msg in request.messages[-30:]:  # Keep last 30 messages for context
```

And line 95:
```python
max_tokens=30,  # Keep last 30 messages
```

### Example:
```
You: Hello!
AI: Hi there!
You: My favorite color is blue
AI: Got it!
You: What's the weather?
AI: I don't have weather data
...
[After 30 messages]
You: What's my favorite color?
AI: Blue! (retrieved from short-term memory)
```

**After 31+ messages:** The first messages start getting dropped, but important facts should be in long-term memory.

---

## 🧠 Long-Term Memory (Store)

### What It Stores:
- **Important facts** triggered by specific phrases
- Personal information, preferences, relationships
- Stored in PostgreSQL `store` table

### How Long It Lasts:
- ✅ **Forever** (until explicitly deleted)
- ✅ **Across all sessions** (any session with the same user_id can access it)
- ✅ **Survives browser restart, server restart, everything**

### How Many Memories Are Recalled:
**ALL of them!**

From `server.py` line 204:
```python
memories = await global_store.asearch(namespace, query="")
```

The empty query `""` means "get all memories for this user".

Then line 211:
```python
memories_context = " ".join([d.value.get("data", "") for d in memories])
```

All memories are concatenated and injected into your prompt!

### Trigger Phrases (What Gets Stored):

From `server.py` line 257:
```python
if any(phrase in request.message.lower() for phrase in [
    "my name is",
    "i am",
    "i like",
    "i love",
    "i prefer"
]):
    # Store in long-term memory
```

**Only messages containing these phrases get stored:**
- "My name is..."
- "I am..."
- "I like..."
- "I love..."
- "I prefer..."

### Example:
```
Session 1:
You: "My name is Alice and I love pizza"
     ↓
AI: Stores in long-term: "My name is Alice and I love pizza"

[Later, different session or after refresh]

Session 2 (same user_id):
You: "What do you remember about me?"
     ↓
AI: Retrieves ALL long-term memories
    Sees: "My name is Alice and I love pizza"
    Responds: "Your name is Alice and you love pizza!"
```

---

## 🔄 How Both Work Together

When you send a message, here's what happens:

### Step 1: Retrieve Long-Term Memories
```python
# Get ALL stored memories for this user
memories = await global_store.asearch(namespace, query="")
memories_context = " ".join([d.value.get("data", "") for d in memories])
```

**Result:** All long-term memories are joined into one text block.

### Step 2: Augment Your Message
```python
augmented_input = (
    f"{request.message}\n\n"
    f"[STORED MEMORIES from previous conversations:\n{memories_context}\n"
    f"Use these memories to answer the user's question if relevant.]"
)
```

**Your message becomes:**
```
What's my name?

[STORED MEMORIES from previous conversations:
My name is Alice and I love pizza
I prefer technical explanations
My friend is Sarah who works at Google
Use these memories to answer the user's question if relevant.]
```

### Step 3: Add Short-Term Context
```python
for msg in request.messages[-30:]:  # Last 30 messages
    message_history.append(msg)
```

**The AI sees:**
- Last 30 conversation messages
- Your current message (augmented with long-term memories)
- System prompt

### Step 4: Generate Response
The AI processes all this context and responds.

### Step 5: Check If New Memory Should Be Stored
```python
if any(phrase in request.message.lower() for phrase in [
    "my name is", "i am", "i like", "i love", "i prefer"
]):
    await global_store.aput(namespace, memory_id, {"data": request.message})
```

If your message contains trigger phrases, it's stored in long-term memory.

---

## 📊 Memory Limits

### Short-Term Memory:
| Metric | Limit | Why |
|--------|-------|-----|
| Messages recalled | **30** | To keep context manageable and avoid token limits |
| Storage duration | **Forever** (in PostgreSQL) | But only last 30 are used per request |
| Scope | **Single session only** | Each session has its own conversation thread |

### Long-Term Memory:
| Metric | Limit | Why |
|--------|-------|-----|
| Memories recalled | **ALL** | No limit - every stored memory is retrieved |
| Storage duration | **Forever** | Until manually deleted |
| Scope | **Cross-session** | Any session with same user_id can access |
| Storage trigger | **Specific phrases only** | "my name is", "i am", "i like", "i love", "i prefer" |

---

## 💡 Special Commands

The system prompt includes special commands to force memory checking:

### "Check your memory"
Forces the AI to list all stored facts about you.

**Example:**
```
You: Check your memory
AI: Looking at my stored memories, I have:
    - "My name is Alice and I love pizza"
    - "I prefer technical explanations"
    Your name is Alice!
```

### "What do you remember about me?"
Gets a summary of all long-term memories.

**Example:**
```
You: What do you remember about me?
AI: Here's what I have in my stored memories:
    1. Your name is Alice
    2. You love pizza
    3. You prefer technical explanations
```

### "That's wrong, check again"
Forces the AI to re-read stored memories and correct itself.

**Example:**
```
You: What's my name?
AI: I don't have that information.
You: That's wrong, check again
AI: I apologize! Checking my stored memories, I see your name is Alice.
```

---

## 🧪 Testing Memory

### Test 1: Short-Term Limit (30 messages)
```
1. You: Message 1
2. AI: Response 1
3. You: Message 2
4. AI: Response 2
...
60. You: Message 30
61. AI: Response 30
62. You: "What did I say in message 1?"
    AI: (Should NOT remember - it's beyond the 30 message limit)
```

### Test 2: Long-Term (Unlimited)
```
Session 1:
You: "My name is Alice"
You: "I love pizza"
You: "I prefer casual conversations"
You: "My friend is Sarah"
You: "I work at Google"
[All 5 stored in long-term memory]

[Refresh or new session]

You: "What do you know about me?"
AI: (Should recall ALL 5 facts)
```

### Test 3: Both Together
```
You: "My name is Alice"  [Stored in long-term]
You: "Hello!"
You: "How are you?"
...
[30 more messages - filling short-term]
...
You: "What's my name?"
AI: "Alice!"
    ↑ Retrieved from long-term memory
      (even though "My name is Alice" is no longer in the last 30 messages)
```

---

## 🔍 Checking Memory Usage

### In Backend Logs:
When you send a message, look for:
```
🧠 Retrieved 3 memories for user user_abc123
📝 Memory context: My name is Alice and I love pizza...
```

This shows:
- How many long-term memories were retrieved
- What the memory context looks like

### In Frontend Debug Panel (Memory Pensieve ⛲️):
The right sidebar shows:
- **Short-term Memories** - Info card explaining 30-message limit
- **Stored Facts** - Long-term persistent memories

### Via API:
```bash
# Check all long-term memories for a user
curl "http://localhost:8000/memories/all/inspect?user_id=user_xxx"

# Check memory bank
curl "http://localhost:8000/memory-bank/user_xxx"
```

---

## ⚙️ Tuning Memory Limits

If you want to change the limits, edit `server.py`:

### Change Short-Term Limit:
**Line 95** - Change `max_tokens=30` to your desired number:
```python
max_tokens=50,  # Now keeps last 50 messages
```

**Line 228** - Also update this:
```python
for msg in request.messages[-50:]:  # Keep last 50 messages for context
```

### Change Long-Term Retrieval:
**Line 204** - Currently retrieves ALL memories:
```python
memories = await global_store.asearch(namespace, query="")
```

To limit to top N most relevant:
```python
memories = await global_store.asearch(namespace, query=request.message, limit=5)
```

This would retrieve only the 5 most relevant memories based on semantic similarity to your query.

---

## 📝 Summary Table

| Feature | Short-Term (Checkpoints) | Long-Term (Store) |
|---------|-------------------------|-------------------|
| **Storage** | Last 30 messages | ALL triggered messages |
| **Trigger** | Automatic (every message) | Specific phrases only |
| **Retrieval** | Last 30 messages | ALL memories |
| **Duration** | Forever in DB, but only last 30 used | Forever |
| **Scope** | Single session | Cross-session (same user_id) |
| **Use Case** | Recent conversation context | Persistent facts about user |

---

## 🎯 Best Practices

1. **For important info**: Use trigger phrases
   - ✅ "My name is Alice"
   - ❌ "Call me Alice" (won't be stored)

2. **For recent context**: Just chat normally
   - The last 30 messages are always available

3. **Use "Both" mode**: Gets best of both worlds
   - Recent conversation flow (short-term)
   - Persistent facts (long-term)

4. **Check the Memory Pensieve**: See what's actually stored

5. **Stay in one session**: For continuous conversations

---

**Bottom Line:**
- Short-term = last **30 messages**
- Long-term = **ALL stored facts** (triggered by specific phrases)
- Combined = Best user experience with both context and persistence
