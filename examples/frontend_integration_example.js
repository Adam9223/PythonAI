// Frontend Integration Example for clone.ulap.biz
// This shows how to connect your existing frontend auth to the Python AI backend

class AIBackendClient {
  constructor(backendUrl = 'http://localhost:8000') {
    this.backendUrl = backendUrl;
    this.apiAccessToken = null; // Token for THIS backend
  }

  // Step 1: Authenticate with the Python AI backend
  async authenticate() {
    // Generate API key
    const keyResponse = await fetch(`${this.backendUrl}/api/auth/generate-key`, {
      method: 'POST'
    });
    const { api_key } = await keyResponse.json();

    // Get access token
    const tokenResponse = await fetch(`${this.backendUrl}/api/auth/token?api_key=${api_key}`, {
      method: 'POST'
    });
    const { access_token } = await tokenResponse.json();
    
    this.apiAccessToken = access_token;
    return access_token;
  }

  // Step 2: Get inventory using YOUR frontend auth context
  // authContext supports:
  // - userToken (jwt)
  // - userCookie (raw cookie header string)
  // - csrfToken
  // - authHeaderName (e.g. Authorization, x-access-token)
  // - csrfHeaderName
  // - extraHeaders (object)
  async getInventory(authContext = {}) {
    if (!this.apiAccessToken) {
      await this.authenticate();
    }

    const {
      userToken = null,
      userCookie = null,
      csrfToken = null,
      authHeaderName = 'Authorization',
      csrfHeaderName = 'X-CSRF-Token',
      extraHeaders = null,
    } = authContext;

    const response = await fetch(`${this.backendUrl}/api/inventory`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiAccessToken}`, // Auth for Python backend
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        category: 'all',
        user_auth_token: userToken,
        user_cookie: userCookie,
        csrf_token: csrfToken,
        auth_header_name: authHeaderName,
        csrf_header_name: csrfHeaderName,
        extra_headers: extraHeaders
      })
    });

    return await response.json();
  }

  // Step 3: Chat with context from protected API
  async chat(message, userToken) {
    if (!this.apiAccessToken) {
      await this.authenticate();
    }

    const response = await fetch(`${this.backendUrl}/api/chat`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiAccessToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        message: message,
        user_auth_token: userToken
      })
    });

    return await response.json();
  }

  // Step 4: Get balance data
  async getBalance(userToken) {
    if (!this.apiAccessToken) {
      await this.authenticate();
    }

    const response = await fetch(`${this.backendUrl}/api/balance`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiAccessToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        data_source: 'general_ledger',
        user_auth_token: userToken
      })
    });

    return await response.json();
  }
}

// USAGE EXAMPLE:
// ===============

// In your frontend, after the user logs into clone.ulap.biz:
async function example() {
  // Your existing login code gets this token
  const userTokenForUlap = localStorage.getItem('ulap_token'); // or however you store it
  const csrfToken = localStorage.getItem('csrf_token');
  const userCookie = document.cookie; // if frontend request relies on session cookie
  
  // Create AI client
  const aiClient = new AIBackendClient('http://localhost:8000');
  
  // Use the AI backend with your token
  try {
    // Get inventory
    const inventory = await aiClient.getInventory({
      userToken: userTokenForUlap,
      userCookie,
      csrfToken,
      authHeaderName: 'Authorization',
      csrfHeaderName: 'X-CSRF-Token'
    });
    console.log('Inventory:', inventory);
    
    // Chat about the data
    const chatResponse = await aiClient.chat(
      'What inventory do we have?',
      userTokenForUlap
    );
    console.log('AI Response:', chatResponse);
    
    // Get balance
    const balance = await aiClient.getBalance(userTokenForUlap);
    console.log('Balance:', balance);
    
  } catch (error) {
    console.error('Error:', error);
  }
}

// REACT EXAMPLE:
// ==============

function InventoryComponent() {
  const [inventory, setInventory] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  
  // Get user token from your auth context/state
  const { userToken } = useAuth(); // Your existing auth hook
  
  const fetchInventory = async () => {
    setLoading(true);
    try {
      const aiClient = new AIBackendClient('http://localhost:8000');
      const result = await aiClient.getInventory({
        userToken,
        userCookie: document.cookie,
        csrfToken: localStorage.getItem('csrf_token')
      });
      setInventory(result);
    } catch (error) {
      console.error('Failed to fetch inventory:', error);
    } finally {
      setLoading(false);
    }
  };
  
  React.useEffect(() => {
    if (userToken) {
      fetchInventory();
    }
  }, [userToken]);
  
  if (loading) return <div>Loading...</div>;
  
  return (
    <div>
      <h2>Inventory</h2>
      <pre>{JSON.stringify(inventory, null, 2)}</pre>
    </div>
  );
}

export { AIBackendClient };
