
import requests
import json
import sseclient
import time

# Config
BASE_URL = "http://localhost:3080/api"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjY5OWY0Y2IxMzFkMDI4NTg1MmNlNzRlZSIsInVzZXJuYW1lIjoibWxhem8iLCJwcm92aWRlciI6ImxvY2FsIiwiZW1haWwiOiJtbGF6b0BtYWlsaW5hdG9yLmNvbSIsImlhdCI6MTc3MjA4NTc5OSwiZXhwIjoxNzcyMDg2Njk5fQ.i35Y8qcy1K6ug41xsJQOzz6MSp4uIqpCEWobyifiEO0"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    # CRITICAL: LibreChat requires a browser User-Agent header
    # The uaParser middleware blocks non-browser requests with "Illegal request" error
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 1. List available models
def list_models():
    response = requests.get(f"{BASE_URL}/models", headers=headers)
    models = response.json()
    print("Available models:", json.dumps(models, indent=2))
    return models

# 2. List available agents
def list_agents():
    """
    List all available agents with their IDs and details.
    
    Returns:
        dict: Contains list of agents with their agent_id, name, description, etc.
    """
    response = requests.get(f"{BASE_URL}/agents", headers=headers)
    if response.status_code != 200:
        print(f"Error listing agents: {response.status_code}", response.text)
        return None
    
    agents_data = response.json()
    print(f"\nAvailable Agents ({agents_data.get('total', 0)} total):")
    print("=" * 80)
    
    for agent in agents_data.get('data', []):
        agent_id = agent.get('id')
        name = agent.get('name', 'Unnamed')
        description = agent.get('description', 'No description')
        provider = agent.get('provider', 'unknown')
        model = agent.get('model', 'unknown')
        
        print(f"\n📋 Agent ID: {agent_id}")
        print(f"   Name: {name}")
        print(f"   Description: {description}")
        print(f"   Provider: {provider}")
        print(f"   Model: {model}")
    
    print("\n" + "=" * 80)
    return agents_data

def create_agent(name, description, provider, model, instructions, temperature=0.7, max_tokens=4096):
    """
    Create a new agent in the database.
    
    Args:
        name: Agent name
        description: Agent description
        provider: Provider name (e.g., "openai", "google", "deepseek")
        model: Model name (e.g., "gpt-4", "gemini-1.5-flash")
        instructions: System instructions for the agent
        temperature: Temperature setting (0.0-1.0)
        max_tokens: Maximum tokens
    
    Returns:
        dict: Created agent data including agent_id
    """
    agent_data = {
        "name": name,
        "description": description,
        "provider": provider,
        "model": model,
        "instructions": instructions,
        "model_parameters": {
            "temperature": temperature,
            "max_tokens": max_tokens
        }
    }
    
    response = requests.post(
        f"{BASE_URL}/agents",
        headers=headers,
        json=agent_data
    )
    
    if response.status_code == 201:
        agent = response.json()
        print(f"✅ Created agent: {agent['id']}")
        print(f"   Name: {agent['name']}")
        return agent
    else:
        print(f"❌ Error creating agent: {response.status_code}", response.text)
        return None

def create_agents():
    print("Creating agents in database...")
    agents = [
        dict(
            name="Google AI Assistant",
            description="Fast, general-purpose assistant powered by Google Gemini",
            provider="google",
            model="gemini-1.5-flash",
            instructions="You are a helpful assistant powered by Google Gemini. Provide fast, accurate responses.",
            temperature=0.7,
            max_tokens=2048
        ),
        dict(
            name="DeepSeek Coder",
            description="Specialized coding assistant optimized for programming",
            provider="deepseek",  # Note: This should match your custom endpoint name
            model="deepseek-coder",
            instructions="You are an expert programming assistant. Help with code review, debugging, optimization, and best practices.",
            temperature=0.3,
            max_tokens=4096
        ),
        dict(
            name="DeepSeek Chat",
            description="General purpose assistant using DeepSeek",
            provider="deepseek",
            model="deepseek-chat",
            instructions="You are a helpful AI assistant. Provide clear, accurate, and thoughtful responses.",
            temperature=0.7,
            max_tokens=4096
        ),
    ]
    for item in agents:
        created_agent = create_agent(**item)
    
# 3. Send a message with SSE streaming support
def send_message(text, agent_id=None, conversation_id=None, stream=True):
    """
    Send a message to LibreChat using the resumable streaming architecture.
    
    Args:
        text: The message text to send
        agent_id: Optional agent ID to use (if None, uses default endpoint config)
        conversation_id: Optional conversation ID for continuing conversations
        stream: Whether to stream the response (default True)
    
    Returns:
        dict: Contains the full response with text content
    """
    # Build the payload with proper structure for LibreChat agents endpoint
    payload = {
        "text": text,
        "endpoint": "agents",  # Must be at top level, not in endpointOption
        "conversationId": conversation_id or "new",
        "parentMessageId": None,
    }
    
    # Add agent_id if provided (at top level for agents endpoint)
    if agent_id:
        payload["agent_id"] = agent_id
    
    # Step 1: POST to /api/agents/chat to create the generation job
    print(f"Sending message: {text}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    response = requests.post(
        f"{BASE_URL}/agents/chat",
        headers=headers,
        json=payload
    )
    
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.text[:500]}")  # First 500 chars
    
    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}", response.text)
        return None
    
    # Get the streamId from the response
    try:
        job_info = response.json()
    except json.JSONDecodeError:
        print(f"❌ Failed to parse JSON response: {response.text}")
        return None
    
    stream_id = job_info.get("streamId")
    conversation_id = job_info.get("conversationId")
    
    if not stream_id:
        print(f"❌ No streamId in response: {job_info}")
        return None
    
    print(f"✅ Generation job created: streamId={stream_id}, conversationId={conversation_id}")
    
    return job_info
    
    
def get_responses(stream_id: str, conversation_id: str):

    # Step 2: Connect to the SSE stream to get the actual response
    print("Connecting to SSE stream...")
    
    # Check if job exists first (optional debug step)
    status_url = f"{BASE_URL}/agents/chat/status/{stream_id}"
    status_response = requests.get(status_url, headers=headers)
    print(f"Job status check: {status_response.status_code}")
    if status_response.status_code == 200:
        status_data = status_response.json()
        print(f"Job status: {json.dumps(status_data, indent=2)}")
    
    # Small delay to let job initialize
    time.sleep(0.3)
    
    stream_url = f"{BASE_URL}/agents/chat/stream/{stream_id}"
    print(f"Stream URL: {stream_url}")
    
    response = requests.get(stream_url, headers=headers, stream=True)
    
    print(f"Stream response status: {response.status_code}")
    
    if response.status_code != 200:
        error_text = response.text
        print(f"❌ Error connecting to stream: {response.status_code}")
        print(f"Error response: {error_text}")
        try:
            error_json = response.json()
            print(f"Error details: {json.dumps(error_json, indent=2)}")
        except:
            pass
        return {"streamId": stream_id, "conversationId": conversation_id, "error": "Stream connection failed", "details": error_text}
    
    # Parse SSE events
    client = sseclient.SSEClient(response)
    
    full_text = ""
    message_parts = []
    completed = False
    
    print("\nAI Response:")
    print("-" * 50)
    
    try:
        for event in client.events():
            if event.data:
                try:
                    data = json.loads(event.data)
                    
                    # Handle different event types
                    if data.get("type") == "textCreatedEvent":
                        # New text part started
                        pass
                    
                    elif data.get("type") == "textDeltaEvent":
                        # Text delta - append to current text
                        delta = data.get("text", "")
                        full_text += delta
                        print(delta, end="", flush=True)
                    
                    elif data.get("type") == "textDoneEvent":
                        # Text part completed
                        text_content = data.get("text", "")
                        if text_content:
                            message_parts.append({
                                "type": "text",
                                "text": text_content
                            })
                    
                    elif data.get("type") == "finalEvent":
                        # Generation completed
                        completed = True
                        print("\n" + "-" * 50)
                        break
                    
                    elif data.get("error"):
                        # Error occurred
                        print(f"\nError: {data.get('error')}")
                        break
                        
                except json.JSONDecodeError:
                    # Handle non-JSON data (like [DONE] marker)
                    if event.data == "[DONE]":
                        completed = True
                        break
                    continue
    
    except KeyboardInterrupt:
        print("\n\nStream interrupted by user")
    
    return {
        "streamId": stream_id,
        "conversationId": conversation_id,
        "text": full_text,
        "parts": message_parts,
        "completed": completed
    }

# 4. Get conversations
def get_conversations():
    response = requests.get(f"{BASE_URL}/convos", headers=headers)
    return response.json()

# Test it
if __name__ == "__main__":
    # Option 1: Create database agents (will show in list_agents)
    import ipdb
    ipdb.set_trace()
    
    # # Now list all agents (should show the 3 we just created)
    # print("\n" + "="*80)
    # agents = list_agents()
    # default_agent = None
    # if not agents:
    #     create_agents()
    #     agents = list_agents()

    # if agents:
    #     default_agent = agents.get("first_id")

    # # Test with one of the agents
    # if default_agent:
    #     print(f"\nTesting with Google Assistant (agent_id: {default_agent})")
    #     result = send_message(
    #         "Hello! Tell me a fun fact about AI.",
    #         agent_id=default_agent,
    #     )
    #     print(f"\n\nJob Info: {result}")
    #     # print("\n\nResponse received!")
    
    #     # list_models()
    #     # print(agents)
    #     # print("Conversations:", get_conversations())
    
    #     get_responses(
    #         stream_id=result.get("streamId"),
    #         conversation_id=result.get("conversationId"),
    #     )

    get_responses(
        stream_id='baf094d3-2401-4c0c-b406-8c3d78e4103d',
        conversation_id='baf094d3-2401-4c0c-b406-8c3d78e4103d',
    )