import { Authenticator } from '@aws-amplify/ui-react';
import '@aws-amplify/ui-react/styles.css';

function App() {
  return (
    <Authenticator>
      {({ signOut, user }) => (
        <main style={{ padding: '20px', fontFamily: 'sans-serif' }}>
          <h1>🪶 Carnus Dashboard</h1>
          <p>Logged in as: <strong>{user.username}</strong></p>
          
          <div style={{ marginTop: '20px', border: '1px solid #ccc', padding: '15px' }}>
            <h3>System Status</h3>
            <ul>
              <li>Backend Stack: Ready</li>
              <li>Processor Logic: Connected</li>
              <li>S3 Ingestion: Monitoring...</li>
            </ul>
          </div>

          <button onClick={signOut} style={{ marginTop: '20px', cursor: 'pointer' }}>
            Sign Out
          </button>
        </main>
      )}
    </Authenticator>
  );
}

export default App;
