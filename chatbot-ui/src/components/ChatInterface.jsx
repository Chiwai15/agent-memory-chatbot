import { useState, useRef, useEffect } from 'react';
import samplePersonasData from '../data/samplePersonas.json';

// Use environment variable for API URL, with fallback
// For Vercel/production: VITE_API_URL should be set
// For development: defaults to localhost:8000
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Natural Green & Yellow Color Palette - Flat Design (No Gradients)
const colors = {
  primary: '#165c33',      // Dark green (main theme)
  secondary: '#0d3d22',    // Very dark green
  accent: '#259855',       // Medium green (accent)
  background: '#fbf7ec',   // Matching yellow rgb(251, 247, 236)
  surface: '#ffffff',      // Pure white
  text: '#2d3436',         // Dark gray (for light backgrounds)
  textLight: '#636e72',    // Medium gray (for light backgrounds)
  textOnDark: '#ffffff',   // White text (for dark backgrounds)
  border: '#e8e6e1',       // Subtle border
  hover: '#e8f5e9',        // Very light green hover
  selected: '#165c33',     // Dark green selected
};

function ChatInterface() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [memorySource, setMemorySource] = useState('both'); // 'short', 'long', 'both'
  const [debugData, setDebugData] = useState(null);
  const [debugLoading, setDebugLoading] = useState(false);
  const [viewingFile, setViewingFile] = useState(null); // State for viewing individual file
  const [penseiveView, setPenseiveView] = useState('short'); // 'short' or 'long' - for tabs in Memory Pensieve
  const [messageLimit, setMessageLimit] = useState(30); // Default 30, will be fetched from backend config

  // Demo persona states
  const [selectedPersona, setSelectedPersona] = useState('');
  const [isPlaying, setIsPlaying] = useState(false);
  const [playProgress, setPlayProgress] = useState({ current: 0, total: 0 });

  // Session management - completely rebuilt for reliability
  // STEP 1: Initialize sessions first (single source of truth for session list)
  const [sessions, setSessions] = useState(() => {
    console.debug('[SESSION INIT] Initializing sessions from localStorage...');

    const stored = localStorage.getItem('memorybank_sessions');
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        console.debug('[SESSION INIT] ✅ Found stored sessions:', parsed);
        return parsed;
      } catch (e) {
        console.error('[SESSION INIT] ❌ Failed to parse stored sessions:', e);
      }
    }

    // Create initial session
    const initialSession = {
      id: 'user_' + Math.random().toString(36).substr(2, 9),
      name: 'Session 1',
      createdAt: new Date().toISOString()
    };
    console.debug('[SESSION INIT] 🆕 Creating new initial session:', initialSession);
    return [initialSession];
  });

  // STEP 2: Initialize active session ID (must exist in sessions array)
  const [activeSessionId, setActiveSessionId] = useState(() => {
    console.debug('[SESSION INIT] Initializing active session ID...');

    const storedActiveId = localStorage.getItem('memorybank_active_session');
    const storedSessions = localStorage.getItem('memorybank_sessions');

    // Parse stored sessions to validate
    let parsedSessions = sessions; // Use the sessions state we just initialized
    if (storedSessions) {
      try {
        parsedSessions = JSON.parse(storedSessions);
      } catch (e) {
        console.error('[SESSION INIT] ❌ Failed to parse sessions for validation:', e);
      }
    }

    // Validate that stored active ID exists in sessions
    if (storedActiveId) {
      const exists = parsedSessions.some(s => s.id === storedActiveId);
      if (exists) {
        console.debug('[SESSION INIT] ✅ Using stored active session:', storedActiveId);
        return storedActiveId;
      } else {
        console.warn('[SESSION INIT] ⚠️ Stored active session not found in sessions, using first session');
      }
    }

    // Default to first session
    const firstSessionId = parsedSessions[0]?.id;
    console.debug('[SESSION INIT] 🔄 Defaulting to first session:', firstSessionId);
    return firstSessionId;
  });

  const userId = activeSessionId;
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // STEP 3: Persist sessions to localStorage whenever they change
  useEffect(() => {
    console.debug('[SESSION PERSIST] 💾 Saving sessions to localStorage:', sessions);
    localStorage.setItem('memorybank_sessions', JSON.stringify(sessions));
  }, [sessions]); // Only depend on sessions, not activeSessionId

  // STEP 3b: Validate activeSessionId exists in sessions (separate effect)
  useEffect(() => {
    const exists = sessions.some(s => s.id === activeSessionId);
    if (!exists && sessions.length > 0) {
      console.error('[SESSION VALIDATION] ❌ Active session not found! Fixing...', {
        activeSessionId,
        availableSessions: sessions.map(s => s.id)
      });
      setActiveSessionId(sessions[0].id);
    }
  }, [sessions, activeSessionId]);

  // STEP 4: Persist active session ID to localStorage whenever it changes
  useEffect(() => {
    console.debug('[SESSION PERSIST] 💾 Saving active session to localStorage:', activeSessionId);
    localStorage.setItem('memorybank_active_session', activeSessionId);
  }, [activeSessionId]);

  // STEP 5: On component mount, log the session state for debugging
  useEffect(() => {
    console.debug('=== 🚀 SESSION STATE ON MOUNT ===');
    console.debug('📋 Sessions:', sessions);
    console.debug('✨ Active Session ID:', activeSessionId);
    console.debug('👤 User ID:', userId);
    console.debug('🔍 localStorage sessions:', localStorage.getItem('memorybank_sessions'));
    console.debug('🔍 localStorage activeSessionId:', localStorage.getItem('memorybank_active_session'));
    console.debug('=====================================');

    // Debug: Log if component remounts
    return () => {
      console.debug('⚠️ COMPONENT UNMOUNTING - This should not happen frequently!');
    };
  }, []); // Only run once on mount

  // STEP 6: Watch for unexpected activeSessionId changes
  useEffect(() => {
    console.debug('[SESSION WATCH] 👀 Active session changed to:', activeSessionId);
  }, [activeSessionId]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Fetch debug data based on memory source - ALWAYS REFRESH
  const fetchDebugData = async () => {
    setDebugLoading(true);
    try {
      const result = {
        longTerm: {
          total: 0,
          memories: []
        }
      };

      // Fetch long-term memories (PostgreSQL store)
      if (memorySource === 'long' || memorySource === 'both') {
        console.log('🔍 [Memory Pensieve] Fetching memories for userId:', userId);
        console.log('🔍 [Memory Pensieve] API URL:', `${API_URL}/memories/all/inspect?user_id=${userId}`);

        const response = await fetch(`${API_URL}/memories/all/inspect?user_id=${userId}`);
        if (response.ok) {
          const data = await response.json();
          console.log('✅ [Memory Pensieve] API Response:', data);
          console.log('✅ [Memory Pensieve] Total memories:', data.total);
          console.log('✅ [Memory Pensieve] Memories array:', data.memories);

          result.longTerm = {
            total: data.total || 0,
            memories: data.memories || []
          };
        } else {
          console.error('❌ [Memory Pensieve] API request failed:', response.status, response.statusText);
        }
      }

      // Note: Short-term memory (conversation history) is managed by checkpoints
      // and is automatically used during chat - no separate fetch needed for debug

      console.log('🎯 [Memory Pensieve] Setting debugData:', result);
      console.log('🎯 [Memory Pensieve] Long-term memories count:', result.longTerm.memories.length);
      setDebugData(result);
    } catch (error) {
      console.error('❌ [Memory Pensieve] Error fetching debug data:', error);
      // Set empty data on error
      setDebugData({
        longTerm: {
          total: 0,
          memories: []
        }
      });
    } finally {
      setDebugLoading(false);
    }
  };

  // Fetch conversation history from PostgreSQL checkpoints
  const fetchConversationHistory = async () => {
    try {
      console.log('🔄 [Conversation] Fetching history for userId:', userId);
      const response = await fetch(`${API_URL}/conversation/${userId}`);
      if (response.ok) {
        const data = await response.json();
        console.log('✅ [Conversation] Loaded history:', data);
        if (data.messages && data.messages.length > 0) {
          setMessages(data.messages);
        } else {
          // No history found, keep messages empty
          setMessages([]);
        }
      } else {
        console.error('❌ [Conversation] Failed to load history:', response.status);
        setMessages([]);
      }
    } catch (error) {
      console.error('❌ [Conversation] Error loading history:', error);
      setMessages([]);
    }
  };

  // Fetch backend configuration (message limit)
  const fetchConfig = async () => {
    try {
      console.log('🔄 [Config] Fetching backend configuration...');
      const response = await fetch(`${API_URL}/api/config`);
      if (response.ok) {
        const data = await response.json();
        console.log('✅ [Config] Loaded configuration:', data);
        if (data.short_term_message_limit) {
          setMessageLimit(data.short_term_message_limit);
          console.log(`📊 [Config] Message limit set to: ${data.short_term_message_limit}`);
        }
      } else {
        console.error('❌ [Config] Failed to load configuration:', response.status);
      }
    } catch (error) {
      console.error('❌ [Config] Error loading configuration:', error);
    }
  };

  // Fetch config on mount
  useEffect(() => {
    fetchConfig();
  }, []);

  // Auto-fetch debug data on mount and when memory source changes
  useEffect(() => {
    fetchDebugData();
  }, [memorySource, activeSessionId]);

  // Refetch debug data when switching between long/short tabs in pensieve (when mode is 'both')
  useEffect(() => {
    if (memorySource === 'both') {
      console.log('🔄 [Memory Pensieve] Tab switched to:', penseiveView);
      fetchDebugData();
    }
  }, [penseiveView]);

  // Load conversation history when session changes
  useEffect(() => {
    fetchConversationHistory();
  }, [activeSessionId]);

  const sendMessage = async (e) => {
    e.preventDefault();

    // Show feedback instead of silently returning
    if (!input.trim()) {
      alert('Please enter a message first');
      return;
    }

    if (loading) {
      alert('Please wait for the current message to complete');
      return;
    }

    const userMessage = {
      role: 'user',
      content: input,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    // Refocus input after clearing for better UX
    setTimeout(() => inputRef.current?.focus(), 0);

    try {
      const response = await fetch(`${API_URL}/chat/v2`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: input,
          user_id: userId,
          memory_source: memorySource, // Send memory source preference
          messages: messages.map(msg => ({
            role: msg.role,
            content: msg.content
          }))
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to get response');
      }

      const data = await response.json();

      const botMessage = {
        role: 'assistant',
        content: data.response,
        timestamp: new Date().toISOString(),
        memories_used: data.memories_used,
        facts_extracted: data.facts_extracted,
        complexity_level: data.complexity_level,
        mode_transitions: data.mode_transitions,
        thinking_process: data.thinking_process,
        quality_score: data.quality_score
      };

      setMessages((prev) => [...prev, botMessage]);

      // Auto-refresh debug panel after message
      fetchDebugData();
    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage = {
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please make sure the backend is running.',
        timestamp: new Date().toISOString(),
        isError: true,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const clearChat = async () => {
    if (!confirm('⚠️ WARNING: This will delete ALL memories from ALL users!\n\nThis action cannot be undone. Are you sure?')) {
      return;
    }

    try {
      // Clear ALL memories for ALL users (PostgreSQL store + checkpoints)
      const response = await fetch(`${API_URL}/memories/all/clear`, {
        method: 'DELETE'
      });

      if (response.ok) {
        const data = await response.json();
        console.log('All memories cleared:', data);

        // Show detailed clear results
        const storeCount = data.cleared?.store_entries || 0;
        const checkpointCount = data.cleared?.checkpoint_entries || 0;
        alert(`✅ Successfully cleared all data!\n\n` +
              `Long-term memories: ${storeCount} entries\n` +
              `Conversation history: ${checkpointCount} entries\n\n` +
              `Database is now clean for public testing.`);

        fetchDebugData(); // Refresh debug panel

        // Also clear all local sessions and localStorage
        const newSession = {
          id: 'user_' + Math.random().toString(36).substr(2, 9),
          name: 'Session 1',
          createdAt: new Date().toISOString()
        };
        setSessions([newSession]);
        setActiveSessionId(newSession.id);
        setMessages([]); // Clear messages in UI
        localStorage.clear(); // Clear ALL localStorage for thorough cleanup

        // Reinitialize sessions in localStorage
        localStorage.setItem('memorybank_sessions', JSON.stringify([newSession]));
        localStorage.setItem('memorybank_activeSessionId', newSession.id);
      } else {
        throw new Error('Failed to clear backend memories');
      }
    } catch (error) {
      console.error('Error clearing memories:', error);
      alert('❌ Error: Failed to clear backend memories.');
    }

    // Clear frontend messages
    setMessages([]);
  };

  const createNewSession = () => {
    const newSession = {
      id: 'user_' + Math.random().toString(36).substr(2, 9),
      name: `Session ${sessions.length + 1}`,
      createdAt: new Date().toISOString()
    };
    console.debug('[SESSION] 🆕 Creating new session:', newSession);
    setSessions([...sessions, newSession]);
    setActiveSessionId(newSession.id);
    setMessages([]);
    console.debug('[SESSION] ✅ New session created and activated');
  };

  const switchSession = (sessionId) => {
    console.debug('[SESSION] 🔄 Switching to session:', sessionId);
    setActiveSessionId(sessionId);
    setMessages([]);
    fetchDebugData();
    console.debug('[SESSION] ✅ Session switched');
  };

  const deleteSession = async (sessionId) => {
    const isLastSession = sessions.length === 1;

    const confirmMessage = isLastSession
      ? 'Clear all memories for this session? The session will remain but all conversation history and saved facts will be deleted.'
      : 'Delete this session? All conversation history and saved facts for this user will be removed.';

    if (confirm(confirmMessage)) {
      try {
        // Delete backend memories from PostgreSQL
        const response = await fetch(`${API_URL}/memories/${sessionId}`, {
          method: 'DELETE'
        });

        if (response.ok) {
          const data = await response.json();
          console.log('Session memories deleted:', data);
          fetchDebugData(); // Refresh debug panel
        } else {
          throw new Error('Failed to delete backend memories');
        }
      } catch (error) {
        console.error('Error deleting session memories:', error);
        alert('Warning: Failed to delete backend memories. Session will still be removed from frontend.');
      }

      // Handle session removal
      if (isLastSession) {
        // Keep the session but clear messages
        setMessages([]);
        alert('Session data cleared! The session remains active but all memories have been deleted.');
      } else {
        // Remove session from frontend
        const newSessions = sessions.filter(s => s.id !== sessionId);
        setSessions(newSessions);

        if (sessionId === activeSessionId) {
          setActiveSessionId(newSessions[0].id);
          setMessages([]);
        }
      }
    }
  };

  const handleStarterPrompt = (promptText) => {
    setInput(promptText);
  };

  // Auto-play persona messages
  const playPersonaDemo = async () => {
    if (!selectedPersona || isPlaying) return;

    const persona = samplePersonasData.personas.find(p => p.id === selectedPersona);
    if (!persona) return;

    setIsPlaying(true);
    setPlayProgress({ current: 0, total: persona.messages.length });

    for (let i = 0; i < persona.messages.length; i++) {
      const messageText = persona.messages[i];

      // Update progress
      setPlayProgress({ current: i + 1, total: persona.messages.length });

      // Add user message to UI
      const userMessage = {
        role: 'user',
        content: messageText,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);

      // Wait a bit before sending to backend
      await new Promise(resolve => setTimeout(resolve, 500));

      // Add typing indicator
      const typingIndicator = {
        role: 'assistant',
        content: '...',
        timestamp: new Date().toISOString(),
        isTyping: true
      };
      setMessages((prev) => [...prev, typingIndicator]);

      try {
        // Send to backend
        const response = await fetch(`${API_URL}/chat/v2`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            message: messageText,
            user_id: userId,
            memory_source: memorySource,
            messages: messages
              .filter(msg => !msg.isTyping)
              .map(msg => ({
                role: msg.role,
                content: msg.content
              }))
          }),
        });

        if (!response.ok) {
          throw new Error('Failed to get response');
        }

        const data = await response.json();

        const botMessage = {
          role: 'assistant',
          content: data.response,
          timestamp: new Date().toISOString(),
          memories_used: data.memories_used,
          facts_extracted: data.facts_extracted,
          complexity_level: data.complexity_level,
          mode_transitions: data.mode_transitions,
          thinking_process: data.thinking_process,
          quality_score: data.quality_score
        };

        // Remove typing indicator and add real response
        setMessages((prev) => prev.filter(msg => !msg.isTyping).concat(botMessage));

        // Refresh debug panel
        await fetchDebugData();

        // Wait before next message
        await new Promise(resolve => setTimeout(resolve, 1500));

      } catch (error) {
        console.error('Error in persona demo:', error);
        // Remove typing indicator on error
        setMessages((prev) => prev.filter(msg => !msg.isTyping));
        setIsPlaying(false);
        return;
      }
    }

    setIsPlaying(false);
    setPlayProgress({ current: 0, total: 0 });
  };

  const starterPrompts = [
    {
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
      ),
      text: "Introduce yourself and share your interests"
    },
    {
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      ),
      text: "What do you remember about me?"
    },
    {
      icon: (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      ),
      text: "Update or modify existing information"
    }
  ];

  return (
    <div className="h-screen flex flex-col overflow-hidden" style={{ backgroundColor: colors.background }}>
      {/* Announcement Bar */}
      <div className="w-full py-2 px-4 sm:px-6 flex-shrink-0" style={{ backgroundColor: colors.primary }}>
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          {/* Warning Message */}
          <div className="flex items-center gap-2 text-white text-xs sm:text-sm">
            <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span className="flex-1">Demo Mode: Your data is shared and may be modified or deleted by others.</span>
          </div>

          {/* Demo Controls */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <select
              value={selectedPersona}
              onChange={(e) => {
                if (isPlaying) {
                  alert('Cannot change persona while demo is playing');
                  return;
                }
                setSelectedPersona(e.target.value);
              }}
              className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 hover:scale-105"
              style={{
                backgroundColor: colors.surface,
                color: colors.text,
                borderWidth: '1px',
                borderStyle: 'solid',
                borderColor: colors.border
              }}
            >
              <option value="">Select Demo Persona</option>
              {samplePersonasData.personas.map(persona => (
                <option key={persona.id} value={persona.id}>{persona.name}</option>
              ))}
            </select>

            <button
              onClick={() => {
                if (!selectedPersona) {
                  alert('Please select a demo persona first');
                  return;
                }
                if (isPlaying) {
                  alert('Demo is already playing. Please wait for it to finish.');
                  return;
                }
                playPersonaDemo();
              }}
              className="px-4 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 hover:scale-105 active:scale-95 flex items-center gap-2"
              style={{
                backgroundColor: isPlaying ? colors.secondary : colors.surface,
                color: isPlaying ? 'white' : colors.text,
                borderWidth: '1px',
                borderStyle: 'solid',
                borderColor: isPlaying ? colors.secondary : colors.border
              }}
            >
              {isPlaying ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  <span>{playProgress.current}/{playProgress.total}</span>
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>Play Demo</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 flex flex-col lg:flex-row p-3 sm:p-4 lg:p-6 gap-3 sm:gap-4 lg:gap-6 overflow-hidden">
      {/* Sidebar */}
      <div className="w-full lg:w-80 flex flex-col gap-3 sm:gap-4 lg:gap-6 h-auto lg:h-full">
        {/* Logo Card */}
        <div className="rounded-2xl sm:rounded-3xl p-4 sm:p-6 lg:p-8 flex-shrink-0" style={{ backgroundColor: colors.surface }}>
          <div className="flex items-center gap-3 sm:gap-4">
            <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-xl sm:rounded-2xl flex items-center justify-center" style={{ backgroundColor: colors.primary }}>
              <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold" style={{ color: colors.text }}>Memorybank</h1>
              <p className="text-xs" style={{ color: colors.textLight }}>AI with Memory</p>
            </div>
          </div>
        </div>

        {/* Sessions Card */}
        <div className="rounded-2xl sm:rounded-3xl p-4 sm:p-5 lg:p-6 flex-1 flex flex-col overflow-hidden" style={{ backgroundColor: colors.surface }}>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider" style={{ color: colors.text }}>Sessions</h2>
            <button
              onClick={createNewSession}
              className="w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center transition-all duration-200 hover:scale-110 active:scale-95 hover:shadow-lg"
              style={{ backgroundColor: colors.primary }}
            >
              <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
          </div>

          <div className="space-y-2 flex-1 overflow-y-auto overflow-x-visible pr-2 min-h-0 px-1" style={{ maxHeight: '420px' }}>
            {sessions.map((session) => (
              <div
                key={session.id}
                onClick={() => switchSession(session.id)}
                className="group relative rounded-xl p-3 cursor-pointer transition-all duration-200 hover:scale-[1.01] active:scale-[0.99] hover:shadow-md"
                style={{
                  backgroundColor: colors.surface,
                  borderWidth: '1px',
                  borderStyle: 'solid',
                  borderColor: session.id === activeSessionId ? colors.primary : colors.border
                }}
              >
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0" style={{ backgroundColor: colors.primary }}>
                    <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" style={{ color: colors.text }}>{session.name}</p>
                    <p className="text-xs font-mono truncate" style={{ color: colors.textLight }}>{session.id}</p>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      e.preventDefault();
                      deleteSession(session.id);
                    }}
                    className="w-7 h-7 rounded-lg flex items-center justify-center transition-all duration-200 hover:scale-110 active:scale-90 hover:opacity-100 hover:shadow-sm cursor-pointer"
                    style={{
                      backgroundColor: colors.hover,
                      opacity: 0.6
                    }}
                    aria-label="Delete session"
                  >
                    <svg className="w-4 h-4 pointer-events-none" style={{ color: colors.primary }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>

          <button
            onClick={clearChat}
            className="mt-4 w-full py-3 px-4 rounded-xl text-sm font-medium transition-all duration-200 flex items-center justify-center gap-2 flex-shrink-0 hover:scale-[1.02] active:scale-[0.98] hover:shadow-md"
            style={{ backgroundColor: colors.surface, borderWidth: '1px', borderStyle: 'solid', borderColor: colors.border, color: colors.text }}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            Clear Chat
          </button>
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col rounded-3xl overflow-hidden h-full" style={{ backgroundColor: colors.surface }}>
        {/* Messages Container */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 md:p-8 lg:p-10 min-h-0">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center animate-fade-in">
              <div className="w-16 h-16 sm:w-20 sm:h-20 md:w-24 md:h-24 rounded-2xl sm:rounded-3xl flex items-center justify-center mb-6 sm:mb-8" style={{ backgroundColor: colors.primary }}>
                <svg className="w-12 h-12 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
              </div>
              <h2 className="text-3xl font-bold mb-4" style={{ color: colors.text }}>Welcome to Memorybank</h2>
              <p className="mb-12 text-center max-w-md" style={{ color: colors.textLight }}>
                AI assistant with persistent memory powered by vector embeddings
              </p>

              <div className="grid grid-cols-1 2xl:grid-cols-3 gap-5 w-full max-w-3xl">
                {starterPrompts.map((prompt, index) => (
                  <button
                    key={index}
                    onClick={() => handleStarterPrompt(prompt.text)}
                    className="group p-5 2xl:p-7 rounded-2xl transition-all duration-200 hover:scale-105 active:scale-95 hover:shadow-lg text-left flex 2xl:flex-col items-center 2xl:items-start gap-4 2xl:gap-0"
                    style={{ backgroundColor: colors.surface, borderWidth: '1px', borderStyle: 'solid', borderColor: colors.border }}
                  >
                    <div className="w-10 h-10 2xl:w-14 2xl:h-14 rounded-xl 2xl:rounded-2xl flex items-center justify-center flex-shrink-0 2xl:mb-5 group-hover:scale-110 transition-transform duration-300" style={{ backgroundColor: colors.hover }}>
                      {prompt.icon}
                    </div>
                    <p className="text-sm font-medium flex-1" style={{ color: colors.text }}>{prompt.text}</p>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-6 max-w-4xl mx-auto">
              {messages.map((message, index) => (
                <div
                  key={index}
                  className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} animate-slide-up`}
                >
                  <div
                    className={`max-w-[75%] rounded-lg p-3 ${
                      message.role === 'user'
                        ? 'ml-auto'
                        : ''
                    }`}
                    style={{
                      backgroundColor: message.role === 'user' ? colors.primary : colors.surface,
                      color: message.role === 'user' ? 'white' : colors.text,
                      borderWidth: '1px',
                      borderStyle: 'solid',
                      borderColor: message.role === 'user' ? colors.primary : colors.border
                    }}
                  >
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className={`text-xs font-semibold opacity-70 uppercase tracking-wide`}>
                        {message.role === 'user' ? 'You' : 'Assistant'}
                      </span>
                      <span className={`text-xs opacity-50`}>
                        {message.timestamp ? new Date(message.timestamp).toLocaleTimeString() : ''}
                      </span>
                    </div>
                    <div className="text-sm leading-relaxed whitespace-pre-wrap">
                      {message.isTyping ? (
                        <div className="flex items-center gap-1">
                          <span className="inline-block w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: colors.text, animationDelay: '0ms' }}></span>
                          <span className="inline-block w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: colors.text, animationDelay: '150ms' }}></span>
                          <span className="inline-block w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: colors.text, animationDelay: '300ms' }}></span>
                        </div>
                      ) : (
                        /* Strip out [STORED MEMORIES...] context from chat display */
                        message.content.split('[STORED MEMORIES')[0].trim()
                      )}
                    </div>

                    {message.facts_extracted && message.facts_extracted.length > 0 && (
                      <div className="mt-3 p-2.5 rounded-lg" style={{ backgroundColor: message.role === 'user' ? 'rgba(255,255,255,0.2)' : '#e8f5e9' }}>
                        <div className="flex items-center gap-2 mb-2">
                          <svg className={`w-4 h-4`} style={{ color: message.role === 'user' ? 'white' : colors.primary }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          <span className={`text-xs font-semibold`} style={{ color: message.role === 'user' ? 'white' : colors.primary }}>Memory Learned</span>
                        </div>
                        <ul className="space-y-1">
                          {message.facts_extracted.map((fact, i) => (
                            <li key={i} className={`text-xs`} style={{ color: message.role === 'user' ? 'rgba(255,255,255,0.9)' : '#2d3436' }}>• {fact}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {message.memories_used && message.memories_used.length > 0 && (
                      <div className="mt-5 p-4 rounded-xl" style={{ backgroundColor: message.role === 'user' ? 'rgba(255,255,255,0.2)' : '#e8f5e9' }}>
                        <div className="flex items-center gap-2 mb-3">
                          <svg className={`w-4 h-4`} style={{ color: message.role === 'user' ? 'white' : colors.primary }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                          </svg>
                          <span className={`text-xs font-semibold`} style={{ color: message.role === 'user' ? 'white' : colors.primary }}>Memory Recalled</span>
                        </div>
                        <ul className="space-y-1">
                          {message.memories_used.map((memory, i) => (
                            <li key={i} className={`text-xs`} style={{ color: message.role === 'user' ? 'rgba(255,255,255,0.9)' : '#2d3436' }}>• {memory.text}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="flex justify-start animate-slide-up">
                  <div className="rounded-2xl p-6" style={{ backgroundColor: colors.surface, borderWidth: '1px', borderStyle: 'solid', borderColor: colors.border }}>
                    <div className="flex items-center gap-2">
                      <div className="flex gap-1">
                        <div className="w-2 h-2 rounded-full animate-bounce" style={{ backgroundColor: colors.primary }}></div>
                        <div className="w-2 h-2 rounded-full animate-bounce" style={{ backgroundColor: colors.primary, animationDelay: '0.1s' }}></div>
                        <div className="w-2 h-2 rounded-full animate-bounce" style={{ backgroundColor: colors.primary, animationDelay: '0.2s' }}></div>
                      </div>
                      <span className="text-xs" style={{ color: colors.textLight }}>Assistant is typing...</span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input Container with Memory Source Selection */}
        <div className="p-4 sm:p-6 lg:p-8 flex-shrink-0" style={{ borderTopWidth: '1px', borderTopStyle: 'solid', borderTopColor: colors.border }}>
          {/* Memory Source Buttons */}
          <div className="max-w-4xl mx-auto mb-5">
            <div className="flex items-center gap-3">
              <span className="text-xs font-semibold" style={{ color: colors.textLight }}>Memory Mode:</span>
              <div className="flex gap-3">
                <button
                  onClick={() => setMemorySource('short')}
                  className="px-3 py-1.5 rounded-xl text-xs font-medium transition-all duration-200 hover:scale-105 active:scale-95"
                  style={{
                    backgroundColor: memorySource === 'short' ? colors.primary : colors.surface,
                    color: memorySource === 'short' ? 'white' : colors.text,
                    borderWidth: '1px',
                    borderStyle: 'solid',
                    borderColor: memorySource === 'short' ? colors.primary : colors.border
                  }}
                >
                  Short-term
                </button>
                <button
                  onClick={() => setMemorySource('long')}
                  className="px-3 py-1.5 rounded-xl text-xs font-medium transition-all duration-200 hover:scale-105 active:scale-95"
                  style={{
                    backgroundColor: memorySource === 'long' ? colors.secondary : colors.surface,
                    color: memorySource === 'long' ? 'white' : colors.text,
                    borderWidth: '1px',
                    borderStyle: 'solid',
                    borderColor: memorySource === 'long' ? colors.secondary : colors.border
                  }}
                >
                  Long-term
                </button>
                <button
                  onClick={() => setMemorySource('both')}
                  className="px-3 py-1.5 rounded-xl text-xs font-medium transition-all duration-200 hover:scale-105 active:scale-95"
                  style={{
                    backgroundColor: memorySource === 'both' ? colors.primary : colors.surface,
                    color: memorySource === 'both' ? 'white' : colors.text,
                    borderWidth: '1px',
                    borderStyle: 'solid',
                    borderColor: memorySource === 'both' ? colors.primary : colors.border
                  }}
                >
                  Both
                </button>
              </div>
            </div>
          </div>

          <form onSubmit={sendMessage} className="max-w-4xl mx-auto">
            <div className="flex gap-4">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask me anything..."
                disabled={loading}
                className="flex-1 px-5 py-3 rounded-full focus:outline-none focus:ring-2 transition-all duration-300"
                style={{
                  backgroundColor: colors.surface,
                  borderWidth: '1px',
                  borderStyle: 'solid',
                  borderColor: colors.border,
                  color: colors.text,
                  focusRingColor: colors.primary
                }}
              />
              <button
                type="submit"
                className="px-4 sm:px-5 py-2 sm:py-3 rounded-xl sm:rounded-2xl font-medium transition-all duration-200 hover:scale-105 active:scale-95 hover:shadow-lg flex items-center gap-2"
                style={{ backgroundColor: colors.primary, color: 'white' }}
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
                Send
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Debug Panel - ALWAYS VISIBLE */}
      <div className="w-full lg:w-96 rounded-2xl sm:rounded-3xl overflow-hidden h-auto lg:h-full flex flex-col" style={{ backgroundColor: colors.surface }}>
        <div className="p-4 sm:p-6 lg:p-8 flex-shrink-0" style={{ borderBottomWidth: '1px', borderBottomStyle: 'solid', borderBottomColor: colors.border }}>
          <h2 className="text-base sm:text-lg font-bold" style={{ color: colors.text }}>Memory Pensieve ⛲️</h2>
          <p className="text-xs mt-1" style={{ color: colors.textLight }}>Mode: {memorySource === 'short' ? 'Short-term only' : memorySource === 'long' ? 'Long-term only' : 'Both'}</p>
          <p className="text-xs mt-1" style={{ color: colors.textLight }}>User ID: {userId}</p>
          <div className="mt-3 p-2 rounded-lg" style={{ backgroundColor: colors.hover }}>
            <p className="text-xs" style={{ color: colors.text }}>
              💡 Conversation compacting happens every 30 messages for long-term memory
            </p>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          {debugLoading ? (
            <div className="flex items-center justify-center h-full">
              <div className="flex gap-1">
                <div className="w-2 h-2 rounded-full animate-bounce" style={{ backgroundColor: colors.primary }}></div>
                <div className="w-2 h-2 rounded-full animate-bounce" style={{ backgroundColor: colors.primary, animationDelay: '0.1s' }}></div>
                <div className="w-2 h-2 rounded-full animate-bounce" style={{ backgroundColor: colors.primary, animationDelay: '0.2s' }}></div>
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Tabs - only show when mode is "both" */}
              {memorySource === 'both' && (
                <div className="flex gap-2 p-1 rounded-lg" style={{ backgroundColor: colors.hover }}>
                  <button
                    onClick={() => setPenseiveView('short')}
                    className="flex-1 py-2 px-3 rounded-md text-xs font-medium transition-all duration-200 hover:scale-105 active:scale-95"
                    style={{
                      backgroundColor: penseiveView === 'short' ? colors.primary : 'transparent',
                      color: penseiveView === 'short' ? 'white' : colors.text
                    }}
                  >
                    💬 Short-term
                  </button>
                  <button
                    onClick={() => setPenseiveView('long')}
                    className="flex-1 py-2 px-3 rounded-md text-xs font-medium transition-all duration-200 hover:scale-105 active:scale-95"
                    style={{
                      backgroundColor: penseiveView === 'long' ? colors.primary : 'transparent',
                      color: penseiveView === 'long' ? 'white' : colors.text
                    }}
                  >
                    💾 Long-term
                  </button>
                </div>
              )}

              {/* Determine which view to show */}
              {(() => {
                const showShort = memorySource === 'short' || (memorySource === 'both' && penseiveView === 'short');
                const showLong = memorySource === 'long' || (memorySource === 'both' && penseiveView === 'long');

                return (
                  <>
                    {/* Short-term Memory - Actual Messages */}
                    {showShort && (
                      <div className="space-y-4">
                        <div className="flex items-center justify-between">
                          <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: colors.text }}>
                            Short-term Memory
                          </div>
                          <div className="text-xs" style={{ color: colors.textLight }}>
                            {messages.slice(-messageLimit).length} / {messageLimit} messages
                          </div>
                        </div>

                        {messages.slice(-messageLimit).length > 0 ? (
                          <div className="space-y-3">
                            {messages.slice(-messageLimit).reverse().map((msg, idx) => (
                              <div key={idx} className="rounded-xl p-3" style={{ backgroundColor: colors.surface, borderWidth: '1px', borderStyle: 'solid', borderColor: colors.border }}>
                                <div className="flex items-center gap-2 mb-2">
                                  <span className={`px-2 py-1 rounded text-xs font-medium ${msg.role === 'user' ? 'bg-blue-100 text-blue-700' : 'bg-green-100 text-green-700'}`}>
                                    {msg.role === 'user' ? '👤 User' : '🤖 Assistant'}
                                  </span>
                                  <span className="text-xs" style={{ color: colors.textLight }}>
                                    #{messages.length - idx}
                                  </span>
                                </div>
                                <p className="text-xs leading-relaxed" style={{ color: colors.text }}>
                                  {msg.content}
                                </p>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="rounded-xl p-4 text-center" style={{ backgroundColor: colors.surface, borderWidth: '1px', borderStyle: 'solid', borderColor: colors.border }}>
                            <p className="text-xs" style={{ color: colors.textLight }}>
                              No messages yet. Start chatting to see conversation history.
                            </p>
                          </div>
                        )}

                        <div className="rounded-lg p-3" style={{ backgroundColor: colors.hover }}>
                          <div className="flex items-center gap-2 text-xs">
                            <span className="px-2 py-1 rounded" style={{ backgroundColor: colors.surface, color: colors.text }}>
                              Checkpoints
                            </span>
                            <span style={{ color: colors.textLight }}>
                              (binary msgpack)
                            </span>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Long-term Memories (PostgreSQL Store) */}
                    {showLong && (
                      <div className="space-y-4">
                        <div className="flex items-center justify-between">
                          <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: colors.text }}>
                            Long-term Memory (Entities)
                          </div>
                        </div>

                        {debugData && debugData.longTerm && debugData.longTerm.memories && debugData.longTerm.memories.length > 0 ? (
                          <div className="space-y-3">
                            {debugData.longTerm.memories.map((memory, idx) => (
                              <div key={idx} className="rounded-xl p-4" style={{ backgroundColor: colors.surface, borderWidth: '1px', borderStyle: 'solid', borderColor: colors.border }}>
                                <p className="text-xs mb-2 font-semibold" style={{ color: colors.text }}>{memory.text}</p>
                                {memory.metadata && memory.metadata.reference_sentence && (
                                  <p className="text-xs mb-3 italic" style={{ color: colors.textLight, opacity: 0.85 }}>
                                    Reference: "{memory.metadata.reference_sentence}"
                                  </p>
                                )}
                                <div className="flex items-center gap-2 text-xs">
                                  <span className="px-2 py-1 rounded" style={{ backgroundColor: colors.hover, color: colors.text }}>
                                    Store
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="rounded-xl p-4 text-center" style={{ backgroundColor: colors.surface, borderWidth: '1px', borderStyle: 'solid', borderColor: colors.border }}>
                            <p className="text-xs mb-2 font-medium" style={{ color: colors.textLight }}>
                              No entities extracted yet
                            </p>
                            <p className="text-xs mb-2" style={{ color: colors.textLight }}>
                              LLM automatically extracts:
                            </p>
                            <div className="text-xs space-y-1" style={{ color: colors.textLight }}>
                              <p>• Names, ages, professions</p>
                              <p>• Locations (with past/current/future)</p>
                              <p>• Preferences, facts, relationships</p>
                            </div>
                            <p className="text-xs mt-2" style={{ color: colors.textLight, opacity: 0.7 }}>
                              Confidence ≥ 0.5 | Temporal awareness enabled
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
          )}
        </div>

        <div className="p-6 flex-shrink-0" style={{ borderTopWidth: '1px', borderTopStyle: 'solid', borderTopColor: colors.border }}>
          <button
            onClick={fetchDebugData}
            disabled={debugLoading}
            className="w-full py-3 sm:py-4 px-4 sm:px-5 rounded-xl sm:rounded-2xl disabled:opacity-50 font-medium transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] hover:shadow-lg flex items-center justify-center gap-2"
            style={{ backgroundColor: colors.primary, color: 'white' }}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>
      </div>
    </div>
  </div>
  );
}

export default ChatInterface;
