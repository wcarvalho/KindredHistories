/**
 * Sidebar component showing user's past searches.
 * Replaces facet filters when "Searches" tab is active.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { API_URL } from '../config';

const SearchHistorySidebar = ({ onSearchSelect }) => {
  const { user, getValidToken } = useAuth();
  const [searches, setSearches] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchSearchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const token = await getValidToken();
      if (!token) {
        setLoading(false);
        return;
      }

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
    setLoading(false);
  }, [getValidToken]);

  useEffect(() => {
    if (!user) {
      setLoading(false);
      return;
    }

    fetchSearchHistory();
  }, [user, fetchSearchHistory]);

  const handleSearchClick = async (search) => {
    // Re-run this search
    try {
      const token = await getValidToken();
      if (!token) return;

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
        onSearchSelect(data);
      }
    } catch (error) {
      console.error('Failed to rerun search:', error);
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
        // Refresh the search list
        fetchSearchHistory();
      }
    } catch (error) {
      console.error('Failed to delete search:', error);
    }
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return '';
    const date = timestamp.toDate ? timestamp.toDate() : new Date(timestamp._seconds * 1000);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  };

  return (
    <div style={{
      width: '320px',
      background: 'rgba(19, 19, 21, 0.65)',
      padding: '1.5rem',
      overflowY: 'auto',
      borderRight: '1px solid #333'
    }}>
      <h2 style={{ fontSize: '1.56rem', marginBottom: '0.5rem', marginTop: 0 }}>
        Your Searches
      </h2>
      <p style={{ fontSize: '1.02rem', color: '#888', marginBottom: '1.5rem' }}>
        Click to re-run a past search
      </p>

      {loading ? (
        <p style={{ color: '#666' }}>Loading...</p>
      ) : searches.length === 0 ? (
        <p style={{ color: '#666' }}>No search history yet</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {searches.map((search) => (
            <div
              key={search.id}
              onClick={() => handleSearchClick(search)}
              style={{
                padding: '1rem',
                background: 'rgba(26, 26, 29, 0.55)',
                borderRadius: '8px',
                border: '1px solid #333',
                cursor: 'pointer',
                transition: 'all 0.2s',
                position: 'relative'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(37, 37, 41, 0.7)';
                e.currentTarget.style.borderColor = '#7c4dff';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'rgba(26, 26, 29, 0.55)';
                e.currentTarget.style.borderColor = '#333';
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
                  padding: '0.25rem 0.5rem',
                  fontSize: '0.7rem',
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
                Delete
              </button>

              <div style={{
                fontSize: '0.9rem',
                color: '#fff',
                marginBottom: '0.5rem',
                lineHeight: '1.4',
                paddingRight: '4rem' // Make room for delete button
              }}>
                {search.search_text && search.search_text.slice(0, 100)}
                {search.search_text && search.search_text.length > 100 && '...'}
              </div>

              <div style={{
                fontSize: '0.75rem',
                color: '#888',
                marginBottom: '0.5rem'
              }}>
                {formatTimestamp(search.timestamp)}
              </div>

              {search.facets && search.facets.length > 0 && (
                <div style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '0.25rem',
                  marginTop: '0.5rem'
                }}>
                  {search.facets.slice(0, 5).map((facet, idx) => (
                    <span
                      key={idx}
                      style={{
                        fontSize: '0.7rem',
                        padding: '0.15rem 0.4rem',
                        background: 'rgba(42, 42, 45, 0.6)',
                        borderRadius: '4px',
                        color: '#aaa'
                      }}
                    >
                      {facet}
                    </span>
                  ))}
                  {search.facets.length > 5 && (
                    <span style={{
                      fontSize: '0.7rem',
                      color: '#666'
                    }}>
                      +{search.facets.length - 5} more
                    </span>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default SearchHistorySidebar;
