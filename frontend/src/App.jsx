import React, { useState, useEffect } from 'react';
import ChatInterface from './components/ChatInterface';
import FacetedResultsView from './components/FacetedResultsView';
import StarryBackground from './components/StarryBackground';
import AuthenticatedApp from './components/AuthenticatedApp';

import GoogleSignInButton from './components/GoogleSignInButton';
import { useAuth } from './context/AuthContext';
import { dummyUserFacets, exampleData } from './dummyData';
import { API_URL } from './config';

const ServerLoadingBanner = () => (
  <div style={{
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    background: 'linear-gradient(90deg, #7c4dff 0%, #536dfe 100%)',
    color: '#fff',
    padding: '0.75rem 1rem',
    textAlign: 'center',
    zIndex: 9999,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.75rem',
    fontSize: '0.9rem',
    fontWeight: 500,
    boxShadow: '0 2px 8px rgba(0,0,0,0.3)'
  }}>
    <div style={{
      width: '16px',
      height: '16px',
      border: '2px solid rgba(255,255,255,0.3)',
      borderTopColor: '#fff',
      borderRadius: '50%',
      animation: 'spin 1s linear infinite'
    }} />
    <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    Starting server...
  </div>
);

function App() {
  const { user, getValidToken } = useAuth();
  const [view, setView] = useState('chat');
  const [userFacets, setUserFacets] = useState(null);
  const [searchText, setSearchText] = useState(''); // Store the original search prompt
  const [initialFigures, setInitialFigures] = useState(null); // Store immediate results

  const [isTestMode, setIsTestMode] = useState(false);
  const [selectedExample, setSelectedExample] = useState(null);
  const [isRedoing, setIsRedoing] = useState(false);
  const [serverConnected, setServerConnected] = useState(false);

  // Check server connectivity on mount
  useEffect(() => {
    let cancelled = false;

    const checkServer = async () => {
      try {
        const response = await fetch(`${API_URL}/health`, {
          method: 'GET',
          signal: AbortSignal.timeout(5000)
        });
        if (!cancelled && response.ok) {
          setServerConnected(true);
        }
      } catch (error) {
        if (!cancelled) {
          // Retry after 2 seconds
          setTimeout(checkServer, 2000);
        }
      }
    };

    checkServer();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    // Check if we are in the test route
    if (window.location.pathname === '/test') {
      setView('results');
      setIsTestMode(true);

      // Check if we have generated examples
      const hasExamples = exampleData && Object.keys(exampleData).length > 0;
      
      if (hasExamples) {
        const firstKey = Object.keys(exampleData)[0];
        handleExampleChange(firstKey);
      } else {
        // Fallback to static dummy data
        setUserFacets(dummyUserFacets);
      }
    }
  }, []);

  const handleExampleChange = (key) => {
    if (exampleData && exampleData[key]) {
      setSelectedExample(key);
      // Load the preset facets immediately
      // This will trigger FacetedResultsView to fetch figures from backend based on these facets
      setUserFacets(exampleData[key].userFacets);
      setSearchText(exampleData[key].description || '');
    }
  };

  const handleRedoSearch = async () => {
    if (!searchText) return;
    
    setIsRedoing(true);
    try {
      // Run the full search pipeline (Extract -> Analyze -> Fetch)
      // This ensures we are testing the backend's current extraction logic too
      await handleSearch(searchText);
    } catch (error) {
      console.error("Error during redo:", error);
    }
    setIsRedoing(false);
  };

  const handleSearch = async (text, setProgress) => {
    try {
      // Store the search text
      setSearchText(text);

      // Stage 1: extracting (already set by ChatInterface before calling)
      // First, extract user's facets from their description
      const extractResponse = await fetch(`${API_URL}/api/extract-facets`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ text }),
      });

      if (!extractResponse.ok) {
        console.error("Failed to extract facets");
        return;
      }

      const extractData = await extractResponse.json();
      setUserFacets(extractData);

      // Stage 2: analyzing
      if (setProgress) setProgress('analyzing');

      // Then start the analysis with pre-extracted facets (with optional auth header)
      const headers = {
        'Content-Type': 'application/json',
      };

      // Get a fresh token if user is authenticated
      const token = await getValidToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      // Pass pre-extracted facets to avoid re-extraction
      let analyzeResponse = await fetch(`${API_URL}/api/analyze`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          text,
          facets: extractData.facets,
          social_model: extractData.social_model
        }),
      });

      // If we get 401 with auth token, retry without token (fallback to anonymous)
      if (analyzeResponse.status === 401 && token) {
        console.log('Token rejected, retrying as anonymous user');
        delete headers['Authorization'];
        analyzeResponse = await fetch(`${API_URL}/api/analyze`, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            text,
            facets: extractData.facets,
            social_model: extractData.social_model
          }),
        });
      }

      if (analyzeResponse.ok) {
        const analyzeData = await analyzeResponse.json();

        // Stage 3: loading_results
        if (setProgress) setProgress('loading_results');

        // Set initial figures if provided (immediate results)
        if (analyzeData.initial_figures) {
          setInitialFigures(analyzeData.initial_figures);
          console.log(`Showing ${analyzeData.initial_figures.length} existing matches immediately`);
        }

        // Check if cache hit
        if (analyzeData.status === 'cache_hit') {
          console.log('Cache hit! Showing cached results');
        }

        setView('results');
      } else {
        console.error("Failed to start analysis");
      }

      // Return the extracted data for AuthenticatedApp
      return extractData;
    } catch (error) {
      console.error("Error connecting to backend", error);
      return null;
    }
  };

  // If user is logged in and not in test mode, show AuthenticatedApp
  if (user && !isTestMode) {
    return (
      <>
        {!serverConnected && <ServerLoadingBanner />}
        <StarryBackground />
        <AuthenticatedApp onSearch={handleSearch} />
      </>
    );
  }

  // If in test mode, show sidebar + results
  if (isTestMode) {
    return (
      <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
        {!serverConnected && <ServerLoadingBanner />}
        <StarryBackground />
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <FacetedResultsView
            userFacets={userFacets}
            searchText={searchText}
            initialFigures={initialFigures}
            testFigures={null} // Always fetch from backend in test mode
            showDebugColumns={true}
            showSidebar={true}
            testMode={true}
            testExamples={exampleData}
            selectedTestExample={selectedExample}
            onTestExampleSelect={handleExampleChange}
            onTestRedo={handleRedoSearch}
            isTestRedoing={isRedoing}
          />
        </div>
      </div>
    );
  }

  // Handler for starting a new search (anonymous mode)
  const handleNewSearch = () => {
    setView('chat');
    setUserFacets(null);
    setSearchText('');
    setInitialFigures(null);
  };

  // Otherwise show the normal flow (for anonymous users)
  return (
    <>
      {!serverConnected && <ServerLoadingBanner />}
      <StarryBackground />

      {/* Top Right Corner - New Search + Sign In */}
      <div style={{
        position: 'fixed',
        top: '1rem',
        right: '1rem',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem'
      }}>
        {view === 'results' && (
          <button
            onClick={handleNewSearch}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              padding: '0.5rem 0.75rem',
              background: 'rgba(255, 255, 255, 0.08)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              borderRadius: '6px',
              color: 'rgba(255, 255, 255, 0.8)',
              fontSize: '0.85rem',
              fontWeight: '500',
              cursor: 'pointer',
              backdropFilter: 'blur(8px)',
              transition: 'all 0.15s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.12)';
              e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.25)';
              e.currentTarget.style.color = 'rgba(255, 255, 255, 0.95)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)';
              e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.15)';
              e.currentTarget.style.color = 'rgba(255, 255, 255, 0.8)';
            }}
          >
            <span style={{ fontSize: '0.9rem', fontWeight: '400' }}>+</span>
            New Search
          </button>
        )}
        <GoogleSignInButton />
      </div>

      {view === 'chat' ? (
        <ChatInterface onSubmit={handleSearch} />
      ) : (
        <FacetedResultsView
          userFacets={userFacets}
          searchText={searchText}
          initialFigures={initialFigures}
          testFigures={null} // Anonymous user flow doesn't use test figures
          showDebugColumns={false}
        />
      )}
    </>
  );
}

export default App;
