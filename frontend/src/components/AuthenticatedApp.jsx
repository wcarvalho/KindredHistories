/**
 * Chat-app style interface for authenticated users.
 * Shows search history sidebar on left, and either chat input or results on right.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import ChatInterface from './ChatInterface';
import FacetedResultsView from './FacetedResultsView';
import FacetFilterPanel from './FacetFilterPanel';
import { API_URL } from '../config';

// Spinner animation styles
const spinnerStyles = `
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
`;

const AuthenticatedApp = ({ onSearch }) => {
  const { user, getValidToken, signOut } = useAuth();
  const [searches, setSearches] = useState([]);
  const [selectedSearch, setSelectedSearch] = useState(null);
  const [view, setView] = useState('new'); // 'new' | 'results'
  const [currentSearchData, setCurrentSearchData] = useState(null);
  const [currentSearchText, setCurrentSearchText] = useState('');
  const [enabledFacets, setEnabledFacets] = useState(new Set());
  const [facetObjects, setFacetObjects] = useState([]);  // Structured facets from FacetedResultsView
  const [filterMode, setFilterMode] = useState('or');  // 'or' | 'and' - filter mode for facets
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [figuresCount, setFiguresCount] = useState(0);
  const [isPolling, setIsPolling] = useState(false);
  const [sidebarTab, setSidebarTab] = useState('searches'); // 'facets' | 'searches'
  const [loadingSearchId, setLoadingSearchId] = useState(null); // ID of search being loaded

  const fetchSearchHistory = useCallback(async () => {
    try {
      const token = await getValidToken();
      if (!token) return;

      const response = await fetch(`${API_URL}/api/user/searches`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setSearches(data.searches);
      }
    } catch (error) {
      console.error('Failed to fetch search history:', error);
    }
  }, [getValidToken]);

  useEffect(() => {
    if (user) {
      fetchSearchHistory();
    }
  }, [user, fetchSearchHistory]);

  const handleNewSearch = () => {
    setSelectedSearch(null);
    setView('new');
    setCurrentSearchData(null);
    setCurrentSearchText('');
  };

  const handleSearchClick = async (search) => {
    setSelectedSearch(search.id);
    setLoadingSearchId(search.id);

    // Re-run the search
    try {
      const token = await getValidToken();
      if (!token) {
        setLoadingSearchId(null);
        return;
      }

      const response = await fetch(
        `${API_URL}/api/user/searches/${search.id}/rerun`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (response.ok) {
        const data = await response.json();

        // Set current search data with facets
        const searchData = {
          facets: data.facets || [],
          social_model: data.social_model || {}
        };
        setCurrentSearchData(searchData);
        setCurrentSearchText(search.search_text || '');

        setView('results');
        // Switch to facets tab to show the filters
        setSidebarTab('facets');
      }
    } catch (error) {
      console.error('Failed to rerun search:', error);
    } finally {
      setLoadingSearchId(null);
    }
  };

  const handleDeleteClick = async (e, searchId) => {
    e.stopPropagation(); // Prevent triggering the search click

    if (!confirm('Delete this search from your history?')) {
      return;
    }

    try {
      const token = await getValidToken();
      if (!token) return;

      const response = await fetch(
        `${API_URL}/api/user/searches/${searchId}`,
        {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );

      if (response.ok) {
        // If we deleted the currently selected search, reset to new search view
        if (selectedSearch === searchId) {
          handleNewSearch();
        }
        // Refresh the search list
        fetchSearchHistory();
      }
    } catch (error) {
      console.error('Failed to delete search:', error);
    }
  };

  const handleSearchSubmit = async (text, searchData) => {
    // Called when user submits a new search
    if (!searchData) {
      console.error('[AuthenticatedApp] No searchData provided to handleSearchSubmit');
      return;
    }

    setCurrentSearchData(searchData);
    setCurrentSearchText(text);

    setView('results');
    // Switch to facets tab to show the filters
    setSidebarTab('facets');

    // Refresh search history after a short delay
    setTimeout(() => {
      fetchSearchHistory();
    }, 1000);
  };

  const toggleFacet = (category, value) => {
    const newEnabled = new Set(enabledFacets);
    let found = false;
    for (const facet of newEnabled) {
      if (facet.category === category && facet.value === value) {
        newEnabled.delete(facet);
        found = true;
        break;
      }
    }
    if (!found) {
      newEnabled.add({ category, value });
    }
    setEnabledFacets(newEnabled);
  };

  const handleCheckAll = () => {
    setEnabledFacets(new Set(facetObjects));
  };

  const handleUncheckAll = () => {
    setEnabledFacets(new Set());
  };

  const handleRefresh = () => {
    setRefreshTrigger(prev => prev + 1);
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return '';
    const date = timestamp.toDate ? timestamp.toDate() : new Date(timestamp._seconds * 1000);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  return (
    <>
      <style>{spinnerStyles}</style>
      <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
        {/* Left Sidebar - Search History */}
      <div style={{
        width: '320px',
        background: 'rgba(19, 19, 21, 0.65)',
        borderRight: '1px solid #333',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden'
      }}>
        {/* User Profile Header */}
        <div style={{
          padding: '1rem',
          borderBottom: '1px solid #333',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem'
        }}>
          {user.photoURL && (
            <img
              src={user.photoURL}
              alt={user.displayName}
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '50%'
              }}
            />
          )}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              color: '#fff',
              fontSize: '0.9rem',
              fontWeight: '500',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap'
            }}>
              {user.displayName || user.email}
            </div>
            <button
              onClick={signOut}
              style={{
                padding: '0.15rem 0.5rem',
                background: 'transparent',
                border: '1px solid #555',
                borderRadius: '4px',
                color: '#aaa',
                cursor: 'pointer',
                fontSize: '0.75rem',
                marginTop: '0.25rem'
              }}
            >
              Sign Out
            </button>
          </div>
        </div>

        {/* New Search Button */}
        <div style={{ padding: '1rem', borderBottom: '1px solid #333' }}>
          <button
            onClick={handleNewSearch}
            style={{
              width: '100%',
              padding: '0.75rem',
              background: selectedSearch === null && view === 'new' ? '#7c4dff' : '#2a2a2d',
              border: '1px solid ' + (selectedSearch === null && view === 'new' ? '#7c4dff' : '#444'),
              borderRadius: '8px',
              color: '#fff',
              cursor: 'pointer',
              fontSize: '0.9rem',
              fontWeight: '500',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem'
            }}
          >
            <span style={{ fontSize: '1.2rem' }}>+</span>
            New Search
          </button>
        </div>

        {/* Tab Switcher - Only show when in results view */}
        {view === 'results' && currentSearchData && (
          <div style={{
            display: 'flex',
            gap: '0.5rem',
            padding: '1rem',
            borderBottom: '1px solid #333',
            background: 'rgba(26, 26, 29, 0.3)'
          }}>
            <button
              onClick={() => setSidebarTab('facets')}
              style={{
                flex: 1,
                padding: '0.5rem',
                background: sidebarTab === 'facets' ? '#7c4dff' : 'transparent',
                border: 'none',
                borderRadius: '6px',
                color: sidebarTab === 'facets' ? '#fff' : '#aaa',
                cursor: 'pointer',
                fontSize: '0.85rem',
                fontWeight: '500'
              }}
            >
              Filter by Facets
            </button>
            <button
              onClick={() => setSidebarTab('searches')}
              style={{
                flex: 1,
                padding: '0.5rem',
                background: sidebarTab === 'searches' ? '#7c4dff' : 'transparent',
                border: 'none',
                borderRadius: '6px',
                color: sidebarTab === 'searches' ? '#fff' : '#aaa',
                cursor: 'pointer',
                fontSize: '0.85rem',
                fontWeight: '500'
              }}
            >
              Your Searches
            </button>
          </div>
        )}

        {/* Current Search Facets - Full Filter UI */}
        {view === 'results' && currentSearchData && facetObjects.length > 0 && sidebarTab === 'facets' && (
          <div style={{
            padding: '1.5rem',
            borderBottom: '1px solid #333',
            flex: 1,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column'
          }}>
            <FacetFilterPanel
              facets={facetObjects}
              enabledFacets={enabledFacets}
              onToggleFacet={toggleFacet}
              matchCount={figuresCount}
              isPolling={isPolling}
              onCheckAll={handleCheckAll}
              onUncheckAll={handleUncheckAll}
              filterMode={filterMode}
              onModeChange={setFilterMode}
            />
          </div>
        )}

        {/* Search History List - Show when searches tab is active OR when not in results view */}
        {(sidebarTab === 'searches' || view !== 'results') && (
          <div style={{
            flex: 1,
            overflowY: 'auto',
            padding: '0.5rem'
          }}>


          {searches.length === 0 ? (
            <div style={{
              padding: '1rem',
              color: '#666',
              fontSize: '0.85rem',
              textAlign: 'center'
            }}>
              No searches yet
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              {searches.map((search) => (
                <div
                  key={search.id}
                  onClick={() => !loadingSearchId && handleSearchClick(search)}
                  style={{
                    padding: '0.75rem',
                    background: selectedSearch === search.id ? 'rgba(124, 77, 255, 0.15)' : 'transparent',
                    borderRadius: '8px',
                    cursor: loadingSearchId ? 'default' : 'pointer',
                    borderLeft: selectedSearch === search.id ? '3px solid #7c4dff' : '3px solid transparent',
                    transition: 'all 0.2s',
                    position: 'relative'
                  }}
                  onMouseEnter={(e) => {
                    if (selectedSearch !== search.id) {
                      e.currentTarget.style.background = 'rgba(42, 42, 45, 0.5)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (selectedSearch !== search.id) {
                      e.currentTarget.style.background = 'transparent';
                    }
                  }}
                >
                  {/* Delete button */}
                  <button
                    onClick={(e) => handleDeleteClick(e, search.id)}
                    style={{
                      position: 'absolute',
                      top: '0.5rem',
                      right: '0.5rem',
                      background: 'rgba(255, 64, 64, 0.8)',
                      border: 'none',
                      borderRadius: '4px',
                      color: '#fff',
                      cursor: 'pointer',
                      padding: '0.2rem 0.4rem',
                      fontSize: '0.65rem',
                      opacity: 0.7,
                      transition: 'opacity 0.2s'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.opacity = '1';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.opacity = '0.7';
                    }}
                  >
                    ×
                  </button>

                  <div
                    title={search.search_text}
                    style={{
                      fontSize: '1.05rem',
                      color: '#fff',
                      paddingRight: '1.5rem', // Make room for delete button
                      lineHeight: '1.4',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical'
                    }}
                  >
                    {search.search_text}
                  </div>

                  {/* Loading indicator */}
                  {loadingSearchId === search.id && (
                    <div style={{
                      marginTop: '0.5rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      color: '#7c4dff',
                      fontSize: '0.8rem'
                    }}>
                      <div style={{
                        width: '14px',
                        height: '14px',
                        border: '2px solid #7c4dff',
                        borderTopColor: 'transparent',
                        borderRadius: '50%',
                        animation: 'spin 1s linear infinite'
                      }} />
                      Loading search...
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          </div>
        )}
      </div>

      {/* Right Side - Main Content */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {view === 'new' ? (
          <ChatInterface
            onSubmit={async (text, setProgress) => {
              const data = await onSearch(text, setProgress);
              if (data) {
                handleSearchSubmit(text, data);
              }
            }}
            hideSignIn={true}
          />
        ) : (
          <FacetedResultsView
            userFacets={currentSearchData}
            searchText={currentSearchText}
            showSidebar={false}
            externalEnabledFacets={enabledFacets}
            onExternalFacetsChange={setEnabledFacets}
            externalFilterMode={filterMode}
            onFilterModeChange={setFilterMode}
            refreshTrigger={refreshTrigger}
            onFiguresUpdate={(count, polling) => {
              setFiguresCount(count);
              setIsPolling(polling);
            }}
            onFacetsReady={setFacetObjects}
          />
        )}
      </div>
      </div>
    </>
  );
};

export default AuthenticatedApp;
