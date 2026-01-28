import React, { useState, useEffect, useRef } from 'react';
import PersonDetailModal from './PersonDetailModal';
import { useAuth } from '../context/AuthContext';
import SearchHistorySidebar from './SearchHistorySidebar';
import TestModeSidebar from './TestModeSidebar';
import FacetFilterPanel from './FacetFilterPanel';
import { API_URL } from '../config';

// Add spinner animation
const spinnerStyles = `
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
`;

// Strip markdown syntax for plain text display in table cells
const stripMarkdown = (text) => {
  if (!text) return '';
  return text
    .replace(/\*\*([^*]+)\*\*/g, '$1')  // **bold** -> bold
    .replace(/\*([^*]+)\*/g, '$1')       // *italic* -> italic
    .replace(/`([^`]+)`/g, '$1')         // `code` -> code
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')  // [link](url) -> link
    .replace(/^#{1,6}\s+/gm, '');        // # headers -> text
};

// Clean up malformed person names (remove descriptions, markdown, etc.)
const cleanPersonName = (name) => {
  if (!name) return 'Unknown';

  // First strip markdown
  let cleaned = stripMarkdown(name);

  // Remove descriptions after common separators
  cleaned = cleaned.split(' – ')[0];  // em dash
  cleaned = cleaned.split(' - ')[0];   // regular dash with spaces
  cleaned = cleaned.split(': ')[0];    // colon

  // Trim and check if we have something left
  cleaned = cleaned.trim();

  // If the name looks broken (too short, starts weird, etc.), flag it
  if (cleaned.length < 3 || cleaned.startsWith('is ') || cleaned.startsWith('the ')) {
    console.warn('[Data Quality] Malformed person name detected:', name);
    return 'Unknown Figure';
  }

  return cleaned;
};

const FacetedResultsView = ({
  userFacets,
  searchText: initialSearchText = '',
  initialFigures = null,
  testFigures = null,
  showDebugColumns = false,
  showSidebar = true,
  // New Test Mode Props
  testMode = false,
  testExamples = {},
  selectedTestExample = null,
  onTestExampleSelect = () => {},
  onTestRedo = () => {},
  isTestRedoing = false,
  // Authenticated Mode Props
  externalEnabledFacets = null,
  onExternalFacetsChange = null,  // Callback: (facets: Set) => void - for external state management
  refreshTrigger = 0,
  onFiguresUpdate = null,
  onFacetsReady = null,  // Callback: (facetObjects: {category, value}[]) => void
  // External filter mode props (for authenticated mode)
  externalFilterMode = null,      // 'or' | 'and' | null
  onFilterModeChange = null       // Callback: (mode) => void
}) => {
  const { user } = useAuth();
  // Default to 'searches' if logged in, 'examples' if test mode, otherwise 'facets'
  const [sidebarTab, setSidebarTab] = useState(
    user ? 'searches' : (testMode ? 'examples' : 'facets')
  ); 
  const [allFacets, setAllFacets] = useState({});
  const [enabledFacets, setEnabledFacets] = useState(new Set());
  const [figures, setFigures] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isFetching, setIsFetching] = useState(false);
  const [sortBy, setSortBy] = useState('overall');
  const [sortDirection, setSortDirection] = useState('desc');
  const [selectedPerson, setSelectedPerson] = useState(null);
  const [filterMode, setFilterMode] = useState('or'); // 'and' or 'or' - default to OR for more results

  // Use external filter mode if provided (authenticated mode)
  const effectiveFilterMode = externalFilterMode ?? filterMode;
  const handleFilterModeChange = onFilterModeChange ?? setFilterMode;
  const [searchText, setSearchText] = useState(initialSearchText);
  const [isPolling, setIsPolling] = useState(false);
  const [pollCount, setPollCount] = useState(0);

  // Auto-search state (for triggering searches when no results found)
  const [triggeredCombinations, setTriggeredCombinations] = useState(new Set());
  const [isAutoSearching, setIsAutoSearching] = useState(false);
  const [autoSearchAttempted, setAutoSearchAttempted] = useState(false);
  const [autoSearchError, setAutoSearchError] = useState(null);

  // AbortController refs to cancel in-flight requests
  const fetchAbortControllerRef = useRef(null);
  const pollAbortControllerRef = useRef(null);

  // Switch to searches tab when user logs in, or examples when test mode
  useEffect(() => {
    if (user) {
      setSidebarTab('searches');
    } else if (testMode) {
      setSidebarTab('examples');
    }
  }, [user, testMode]);

  // Update search text when prop changes
  useEffect(() => {
    setSearchText(initialSearchText);
  }, [initialSearchText]);

  // Initialize facets from user's social model (passed as prop)
  useEffect(() => {
    if (!userFacets || !userFacets.social_model) {
      return;
    }

    // Use the structured social_model to organize facets by field
    setAllFacets(userFacets.social_model);

    // Initialize with ALL facets enabled (all checked by default)
    // Dedupe by value to prevent same facet appearing multiple times
    const seenValues = new Set();
    const allFacetsSet = new Set();
    Object.entries(userFacets.social_model).forEach(([category, values]) => {
      if (Array.isArray(values)) {
        values.forEach(val => {
          if (!seenValues.has(val)) {
            seenValues.add(val);
            allFacetsSet.add({ category, value: val });
          }
        });
      }
    });

    // If external state management, notify parent to set all facets
    // Otherwise, manage internally
    if (onExternalFacetsChange) {
      onExternalFacetsChange(allFacetsSet);
    } else {
      setEnabledFacets(allFacetsSet);
    }
  }, [userFacets, onExternalFacetsChange]);

  // Initialize with provided initial figures immediately
  useEffect(() => {
    if (initialFigures && initialFigures.length > 0) {
      console.log(`[FacetedResultsView] Showing ${initialFigures.length} initial figures immediately`);
      setFigures(initialFigures);
      setLoading(false);

      // Start polling for new discoveries
      setIsPolling(true);
      setPollCount(0);
    }
  }, [initialFigures]);

  // Query figures whenever enabled facets change or refresh is triggered
  useEffect(() => {
    const fetchFigures = async () => {
      // Cancel previous request if it exists
      if (fetchAbortControllerRef.current) {
        fetchAbortControllerRef.current.abort();
      }

      // Create new AbortController for this request
      const controller = new AbortController();
      fetchAbortControllerRef.current = controller;

      // Use external facets if provided (authenticated mode), otherwise use internal state
      const facetsToUse = externalEnabledFacets || enabledFacets;

      if (facetsToUse.size === 0) {
        setFigures([]);
        setLoading(false);
        setIsFetching(false);
        setIsPolling(false);
        return;
      }

      // Don't show loading screen when refetching - load in background
      // Only show loading on initial load (when figures is empty)
      if (figures.length === 0) {
        setLoading(true);
      } else {
        // Show fetching indicator for background queries
        setIsFetching(true);
      }

      try {
        const facetArray = Array.from(facetsToUse).map(f => f.value);
        const params = new URLSearchParams();
        facetArray.forEach(f => params.append('facets', f));
        params.append('min_similarity', '0.2'); // Lower threshold - client-side filtering handles AND/OR logic

        const url = `${API_URL}/api/figures/semantic?${params}&limit=100`;
        const response = await fetch(url, { signal: controller.signal });

        if (response.ok) {
          const data = await response.json();
          setFigures(data.figures);

          // Start polling if we got 0 results (agent may still be processing)
          if (data.figures.length === 0 && !isPolling) {
            console.log('[FacetedResultsView] No results found');

            // If this is the first time with 0 results and we haven't attempted auto-search
            if (!autoSearchAttempted) {
              console.log('[FacetedResultsView] Triggering auto-search...');
              await triggerAutoSearch();
            } else {
              console.log('[FacetedResultsView] Auto-search already attempted, starting polling');
              setIsPolling(true);
              setPollCount(0);
            }
          } else if (data.figures.length > 0) {
            // Stop polling and auto-searching if we got results
            setIsPolling(false);
            setPollCount(0);
            setIsAutoSearching(false);
          }
        } else {
          console.error('[FacetedResultsView] Failed to fetch figures:', response.status);
        }
      } catch (error) {
        if (error.name === 'AbortError') {
          console.log('[FacetedResultsView] Fetch aborted');
          return; // Don't update state if aborted
        }
        console.error('Error fetching figures:', error);
      }
      setLoading(false);
      setIsFetching(false);
    };

    fetchFigures();

    // Cleanup: abort on unmount or dependency change
    return () => {
      if (fetchAbortControllerRef.current) {
        fetchAbortControllerRef.current.abort();
      }
    };
  }, [enabledFacets, externalEnabledFacets, testFigures, refreshTrigger]);

  // NOTE: onFiguresUpdate moved below filteredFigures definition

  // Polling effect - refetch results every 3 seconds when polling is active
  useEffect(() => {
    const facetsToUse = externalEnabledFacets || enabledFacets;

    if (!isPolling || facetsToUse.size === 0) return;

    const MAX_POLLS = 20; // Poll for up to 60 seconds (20 * 3s)

    if (pollCount >= MAX_POLLS) {
      console.log('[FacetedResultsView] Max poll attempts reached, stopping');
      setIsPolling(false);
      return;
    }

    const pollTimer = setTimeout(async () => {
      console.log(`[FacetedResultsView] Checking for new discoveries ${pollCount + 1}/${MAX_POLLS}`);

      // Cancel previous polling request if it exists
      if (pollAbortControllerRef.current) {
        pollAbortControllerRef.current.abort();
      }

      // Create new AbortController for this polling request
      const controller = new AbortController();
      pollAbortControllerRef.current = controller;

      try {
        const facetArray = Array.from(facetsToUse).map(f => f.value);
        const params = new URLSearchParams();
        facetArray.forEach(f => params.append('facets', f));
        params.append('min_similarity', '0.2');

        const url = `${API_URL}/api/figures/semantic?${params}&limit=100`;
        const response = await fetch(url, { signal: controller.signal });

        if (response.ok) {
          const data = await response.json();

          // Update if we found more figures than before
          if (data.figures.length > figures.length) {
            console.log(`[FacetedResultsView] Found ${data.figures.length - figures.length} new figures!`);
            setFigures(data.figures);
          }

          setPollCount(prev => prev + 1);
        }
      } catch (error) {
        if (error.name === 'AbortError') {
          console.log('[FacetedResultsView] Poll fetch aborted');
          return; // Don't update state if aborted
        }
        console.error('[FacetedResultsView] Poll error:', error);
        setPollCount(prev => prev + 1);
      }
    }, 3000);

    return () => {
      clearTimeout(pollTimer);
      // Abort polling request on cleanup
      if (pollAbortControllerRef.current) {
        pollAbortControllerRef.current.abort();
      }
    };
  }, [isPolling, pollCount, enabledFacets, externalEnabledFacets, figures.length]);

  // Helper functions for facet management with category information
  const facetKey = (facet) => `${facet.category}:${facet.value}`;

  const getCombinationKey = (facets) => {
    return Array.from(facets)
      .map(f => facetKey(f))
      .sort()
      .join('|');
  };

  const isFacetEnabled = (category, value) => {
    for (const facet of enabledFacets) {
      if (facet.category === category && facet.value === value) {
        return true;
      }
    }
    return false;
  };

  const toggleFacet = (category, value) => {
    const newEnabled = new Set(enabledFacets);

    // Find and remove if exists
    let found = false;
    for (const facet of newEnabled) {
      if (facet.category === category && facet.value === value) {
        newEnabled.delete(facet);
        found = true;
        break;
      }
    }

    // Add if not found
    if (!found) {
      newEnabled.add({ category, value });
    }

    setEnabledFacets(newEnabled);

    // Reset auto-search tracking when facets change
    setAutoSearchAttempted(false);
  };

  const handleCheckAll = () => {
    const allFacets = new Set();
    uniqueFacetsWithCategories.forEach(f => {
      allFacets.add({ category: f.category, value: f.value });
    });
    setEnabledFacets(allFacets);
    setAutoSearchAttempted(false);
  };

  const handleUncheckAll = () => {
    setEnabledFacets(new Set());
    setIsPolling(false);
    setIsAutoSearching(false);
    setAutoSearchAttempted(false);
  };

  const handleSort = (facet) => {
    if (sortBy === facet) {
      // Toggle direction
      setSortDirection(sortDirection === 'desc' ? 'asc' : 'desc');
    } else {
      setSortBy(facet);
      setSortDirection('desc');
    }
  };

  const handleSearchHistorySelect = (searchData) => {
    // When user clicks a past search, update the view with the results from that search

    // Show loading state
    setLoading(true);

    // Update facets to match the past search
    if (searchData.social_model) {
      setAllFacets(searchData.social_model);

      // Reconstruct facet objects with categories from social_model
      const facetObjects = new Set();
      if (searchData.facets) {
        // For each facet value, find its category in the social_model
        searchData.facets.forEach(facetValue => {
          for (const [category, values] of Object.entries(searchData.social_model)) {
            if (Array.isArray(values) && values.includes(facetValue)) {
              facetObjects.add({ category, value: facetValue });
              break; // Found the category, move to next facet
            }
          }
        });
      }
      setEnabledFacets(facetObjects);
    }

    // Update figures
    if (searchData.figures) {
      setFigures(searchData.figures);
    }

    // Update search text
    if (searchData.search_text) {
      setSearchText(searchData.search_text);
    }

    // Switch back to facets tab to show results
    setSidebarTab('facets');

    // Brief delay to show loading state, then turn it off
    setTimeout(() => {
      setLoading(false);
    }, 300);
  };

  // Auto-search trigger: constructs SocialModel from selected facets and triggers new search
  const triggerAutoSearch = async () => {
    const facetsToUse = externalEnabledFacets || enabledFacets;

    if (facetsToUse.size === 0) return;

    const combinationKey = getCombinationKey(facetsToUse);

    // Check if already triggered for this combination
    if (triggeredCombinations.has(combinationKey)) {
      console.log('[Auto-Search] Already triggered for this combination');
      return;
    }

    console.log('[Auto-Search] Triggering search for new figures...');
    setIsAutoSearching(true);
    setAutoSearchAttempted(true);

    // Mark this combination as triggered
    const newTriggered = new Set(triggeredCombinations);
    newTriggered.add(combinationKey);
    setTriggeredCombinations(newTriggered);

    try {
      // Build SocialModel from selected facets
      const socialModel = {
        race: [],
        ethnicity: [],
        cultural_background: [],
        location: [],
        gender: [],
        sexuality: [],
        interests: [],
        aspirations: []
      };

      // Populate from enabled facets
      for (const facet of facetsToUse) {
        if (socialModel.hasOwnProperty(facet.category)) {
          socialModel[facet.category].push(facet.value);
        }
      }

      // Build facets array (flat list of values)
      const facetsArray = Array.from(facetsToUse).map(f => f.value);

      console.log('[Auto-Search] Constructed SocialModel:', socialModel);

      // Call /api/analyze with social_model
      const response = await fetch(`${API_URL}/api/analyze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text: `Auto-search for facets: ${facetsArray.join(', ')}`,
          facets: facetsArray,
          social_model: socialModel
        }),
      });

      if (response.ok) {
        const data = await response.json();
        console.log('[Auto-Search] Search triggered successfully:', data);

        // Start polling for new results
        setIsPolling(true);
        setPollCount(0);
      } else {
        console.error('[Auto-Search] Failed to trigger search:', response.status);
        setIsAutoSearching(false);
        setAutoSearchError('Failed to start search. Please try again.');
      }
    } catch (error) {
      console.error('[Auto-Search] Error triggering search:', error);
      setIsAutoSearching(false);
      setAutoSearchError('Failed to trigger search. Please try again.');

      // Clear error after 5 seconds
      setTimeout(() => setAutoSearchError(null), 5000);
    }
  };

  // Client-side filtering based on AND/OR mode
  // Use external facets if provided (authenticated mode), otherwise use internal state
  const effectiveFacets = externalEnabledFacets || enabledFacets;

  const filteredFigures = React.useMemo(() => {
    if (!effectiveFacets.size) return figures;

    const enabledValues = Array.from(effectiveFacets).map(f => f.value);

    return figures.filter(fig => {
      if (!fig.facet_scores) return false;

      const scores = enabledValues.map(v => fig.facet_scores[v] ?? 0);

      if (scores.length === 0) return false;

      if (effectiveFilterMode === 'or') {
        // OR: At least one facet matches well (max >= threshold)
        return Math.max(...scores) >= 0.5;
      } else {
        // AND: All facets must match reasonably (mean >= threshold)
        const mean = scores.reduce((a, b) => a + b, 0) / scores.length;
        return mean >= 0.5;
      }
    });
  }, [figures, effectiveFacets, externalFilterMode, filterMode]);

  // Notify parent of FILTERED figures count (for authenticated mode sidebar)
  useEffect(() => {
    if (onFiguresUpdate) {
      onFiguresUpdate(filteredFigures.length, isPolling);
    }
  }, [filteredFigures.length, isPolling, onFiguresUpdate]);

  // Sort figures based on selected facet score
  const sortedFigures = React.useMemo(() => {
    if (!sortBy) return filteredFigures;

    return [...filteredFigures].sort((a, b) => {
      let scoreA, scoreB;
      if (sortBy === 'overall') {
        scoreA = a.similarity_score ?? 0;
        scoreB = b.similarity_score ?? 0;
      } else {
        scoreA = a.facet_scores?.[sortBy] ?? 0;
        scoreB = b.facet_scores?.[sortBy] ?? 0;
      }
      return sortDirection === 'desc' ? scoreB - scoreA : scoreA - scoreB;
    });
  }, [filteredFigures, sortBy, sortDirection]);

  // Column headers based on enabled facets (not results) - ensures columns stay visible
  // Dedupe to prevent React key collisions when same value appears in multiple categories
  // Use effectiveFacets to support authenticated mode where facets come from external state
  const columnsToShow = React.useMemo(() => {
    return [...new Set(Array.from(effectiveFacets).map(f => f.value))];
  }, [effectiveFacets]);

  // Extract unique facets from social model for filter panel (with categories)
  // Dedupe by value to prevent the same facet appearing in multiple categories
  const uniqueFacetsWithCategories = React.useMemo(() => {
    const seenValues = new Set();
    const facets = [];
    Object.entries(allFacets).forEach(([category, values]) => {
      if (Array.isArray(values)) {
        values.forEach(val => {
          // Only add if we haven't seen this value before
          if (!seenValues.has(val)) {
            seenValues.add(val);
            facets.push({ category, value: val });
          }
        });
      }
    });
    return facets.sort((a, b) => a.value.localeCompare(b.value));
  }, [allFacets]);

  // Notify parent when facet objects are ready
  useEffect(() => {
    if (onFacetsReady && uniqueFacetsWithCategories.length > 0) {
      onFacetsReady(uniqueFacetsWithCategories);
    }
  }, [uniqueFacetsWithCategories, onFacetsReady]);

  return (
    <>
      <style>{spinnerStyles}</style>
      <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
        {/* Tab Selector (only if user is logged in) */}
        {showSidebar && user && (
        <div style={{
          position: 'absolute',
          top: '1rem',
          left: '1rem',
          zIndex: 1000,
          display: 'flex',
          gap: '0.5rem',
          background: 'rgba(26, 26, 29, 0.65)',
          padding: '0.25rem',
          borderRadius: '8px',
          border: '1px solid #333'
        }}>
          <button
            onClick={() => setSidebarTab('facets')}
            style={{
              padding: '0.5rem 1rem',
              background: sidebarTab === 'facets' ? '#7c4dff' : 'transparent',
              border: 'none',
              borderRadius: '6px',
              color: sidebarTab === 'facets' ? '#fff' : '#aaa',
              cursor: 'pointer',
              fontSize: '0.9rem',
              fontWeight: '500'
            }}
          >
            Filter by Facets
          </button>
          <button
            onClick={() => setSidebarTab('searches')}
            style={{
              padding: '0.5rem 1rem',
              background: sidebarTab === 'searches' ? '#7c4dff' : 'transparent',
              border: 'none',
              borderRadius: '6px',
              color: sidebarTab === 'searches' ? '#fff' : '#aaa',
              cursor: 'pointer',
              fontSize: '0.9rem',
              fontWeight: '500'
            }}
          >
            Your Searches
          </button>
        </div>
      )}

      {/* Conditional Sidebar */}
      {showSidebar && (sidebarTab === 'facets' || testMode) ? (
        <div
          style={{
            width: '320px',
            background: 'rgba(19, 19, 21, 0.65)',
            padding: '1.5rem',
            overflowY: 'auto',
            borderRight: '1px solid #333',
            paddingTop: user ? '5rem' : '1.5rem' // Extra padding only if tabs are shown
          }}
        >
          <FacetFilterPanel
            facets={uniqueFacetsWithCategories}
            enabledFacets={enabledFacets}
            onToggleFacet={toggleFacet}
            matchCount={filteredFigures.length}
            isPolling={isPolling}
            isAutoSearching={isAutoSearching}
            onCheckAll={handleCheckAll}
            onUncheckAll={handleUncheckAll}
            filterMode={effectiveFilterMode}
            onModeChange={handleFilterModeChange}
          />

          {/* Test Mode Examples Embed */}
          {testMode && (
            <TestModeSidebar 
              examples={testExamples}
              selectedExample={selectedTestExample}
              onSelectExample={onTestExampleSelect}
              onRedo={onTestRedo}
              isRedoing={isTestRedoing}
            />
          )}
        </div>
      ) : showSidebar && sidebarTab === 'searches' ? (
        <div style={{ paddingTop: '5rem', width: '320px', background: 'rgba(19, 19, 21, 0.65)', borderRight: '1px solid #333' }}>
           <SearchHistorySidebar onSearchSelect={handleSearchHistorySelect} />
        </div>
      ) : null}

      {/* Main Content Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'transparent' }}>
        {/* Search Prompt Header */}
        {searchText && (
          <div style={{
            background: 'rgba(26, 26, 29, 0.75)',
            borderBottom: '1px solid #333',
            padding: '1.5rem 2rem',
            flexShrink: 0,
          }}>
            <div style={{ fontSize: '0.9rem', color: '#888', marginBottom: '0.5rem' }}>
              Your search:
            </div>
            <div style={{
              fontSize: '1.2rem',
              color: '#fff',
              lineHeight: '1.5',
              fontStyle: 'italic',
            }}>
              "{searchText}"
            </div>
          </div>
        )}

        {/* Fetching Indicator */}
        {isFetching && (
          <div style={{
            background: 'rgba(124, 77, 255, 0.1)',
            borderBottom: '1px solid rgba(124, 77, 255, 0.3)',
            padding: '0.75rem 2rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            flexShrink: 0,
          }}>
            <div style={{
              width: '16px',
              height: '16px',
              border: '2px solid rgba(124, 77, 255, 0.3)',
              borderTopColor: '#7c4dff',
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite',
            }} />
            <div style={{ fontSize: '0.95rem', color: '#b39dff' }}>
              Updating results...
            </div>
          </div>
        )}

        {/* Shared Horizontal Scroll Container */}
        <div style={{ flex: 1, overflowX: 'auto', display: 'flex', flexDirection: 'column', background: 'transparent' }}>
          {/* Inner container with actual content width */}
          <div style={{ display: 'flex', flexDirection: 'column', minWidth: 'min-content', flex: 1, background: 'transparent', overflow: 'hidden' }}>
            {/* Table Header - Sticky */}
            {!loading && sortedFigures.length > 0 && (
              <div
                style={{
                  background: 'rgba(26, 26, 29, 0.75)',
                  borderBottom: '2px solid #333',
                  padding: '1rem 2rem',
                  display: 'flex',
                  alignItems: 'center',
                  fontSize: '1.02rem',
                  fontWeight: '600',
                  color: '#aaa',
                  flexShrink: 0,
                }}
              >
                <div style={{ minWidth: '180px', width: '180px', textAlign: 'center', borderRight: '1px solid #333', paddingRight: '1rem', marginRight: '1rem' }}>Person</div>
                
                {/* Debug Column */}
                {showDebugColumns && (
                  <div style={{ minWidth: '200px', width: '200px', borderRight: '1px solid #333', paddingRight: '1rem', marginRight: '1rem', color: '#ffaaaa' }}>SEARCH SOURCE</div>
                )}

                <div style={{ minWidth: '250px', width: '250px', borderRight: '1px solid #333', paddingRight: '1rem', marginRight: '1rem' }}>Challenges</div>
                <div style={{ minWidth: '250px', width: '250px', borderRight: '1px solid #333', paddingRight: '1rem', marginRight: '1rem' }}>Overcoming</div>
                <div
                  onClick={() => handleSort('overall')}
                  style={{
                    minWidth: '80px',
                    width: '80px',
                    textAlign: 'center',
                    borderRight: '1px solid #333',
                    paddingRight: '1rem',
                    marginRight: '1rem',
                    cursor: 'pointer',
                    color: sortBy === 'overall' ? '#7c4dff' : '#aaa',
                    userSelect: 'none',
                  }}
                  title="Click to sort by Overall score"
                >
                  <div>Overall</div>
                  {sortBy === 'overall' && (
                    <div style={{ fontSize: '0.84rem' }}>
                      {sortDirection === 'desc' ? '▼' : '▲'}
                    </div>
                  )}
                </div>
                {columnsToShow.map((facet, index) => (
                  <div
                    key={facet}
                    onClick={() => handleSort(facet)}
                    style={{
                      minWidth: '100px',
                      width: '100px',
                      cursor: 'pointer',
                      textAlign: 'center',
                      color: sortBy === facet ? '#7c4dff' : '#aaa',
                      userSelect: 'none',
                      borderRight: index < columnsToShow.length - 1 ? '1px solid #333' : 'none',
                      paddingRight: '1rem',
                      marginRight: '1rem',
                    }}
                    title={`Click to sort by "${facet}"`}
                  >
                    <div style={{ fontSize: '0.9rem', marginBottom: '2px', wordBreak: 'break-word' }}>
                      {facet}
                    </div>
                    {sortBy === facet && (
                      <div style={{ fontSize: '0.84rem' }}>
                        {sortDirection === 'desc' ? '▼' : '▲'}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Table Rows - Only Vertical Scroll */}
            <div
              style={{
                flex: 1,
                overflowY: 'auto',
                background: 'transparent',
              }}
            >
          {loading ? (
            <div style={{ textAlign: 'center', color: '#888', marginTop: '3rem', padding: '0 2rem' }}>
              <div style={{ fontSize: '1.44rem', marginBottom: '0.5rem' }}>🔍 Searching...</div>
              <p style={{ fontSize: '1.2rem' }}>Finding kindred histories in the archives...</p>
            </div>
          ) : sortedFigures.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#888', marginTop: '3rem', padding: '0 2rem' }}>
              {isAutoSearching ? (
                // Auto-search in progress
                <>
                  <div style={{ fontSize: '1.44rem', marginBottom: '0.5rem' }}>🔍 No matches found</div>
                  <p style={{ fontSize: '1.2rem' }}>
                    Searching for new historical figures that match your selected facets...
                  </p>
                  <div style={{
                    marginTop: '1.5rem',
                    display: 'flex',
                    justifyContent: 'center',
                    alignItems: 'center',
                    gap: '1rem'
                  }}>
                    <div style={{
                      width: '24px',
                      height: '24px',
                      border: '3px solid rgba(124, 77, 255, 0.3)',
                      borderTopColor: '#7c4dff',
                      borderRadius: '50%',
                      animation: 'spin 0.8s linear infinite',
                    }} />
                    <span style={{ fontSize: '0.95rem', color: '#b39dff' }}>
                      Discovering figures...
                    </span>
                  </div>
                </>
              ) : isPolling ? (
                // Polling for results after auto-search triggered
                <>
                  <div style={{ fontSize: '1.44rem', marginBottom: '0.5rem' }}>🔍 Discovering new figures...</div>
                  <p style={{ fontSize: '1.2rem' }}>
                    The AI is researching historical figures that match your profile.
                    <br />
                    New results will appear here automatically.
                  </p>
                  <div style={{
                    marginTop: '1rem',
                    fontSize: '0.9rem',
                    color: '#666',
                    animation: 'pulse 2s ease-in-out infinite'
                  }}>
                    Checking... ({pollCount}/20)
                  </div>
                </>
              ) : autoSearchAttempted && pollCount >= 20 ? (
                // Exhausted polling attempts
                <>
                  <div style={{ fontSize: '1.44rem', marginBottom: '0.5rem' }}>🔍 No figures found</div>
                  <p style={{ fontSize: '1.2rem' }}>
                    We couldn't find historical figures matching this combination of facets.
                    <br />
                    Try selecting different facets or check back later.
                  </p>
                </>
              ) : (externalEnabledFacets || enabledFacets).size === 0 ? (
                // No facets selected
                <p style={{ fontSize: '1.2rem' }}>
                  Select facets above to discover historical figures who share these traits
                </p>
              ) : (
                // Fallback
                <p style={{ fontSize: '1.2rem' }}>
                  No matching figures found. The system is searching for new figures...
                </p>
              )}

              {/* Error display */}
              {autoSearchError && (
                <div style={{
                  marginTop: '1rem',
                  padding: '1rem',
                  background: 'rgba(255, 77, 77, 0.1)',
                  border: '1px solid rgba(255, 77, 77, 0.3)',
                  borderRadius: '8px',
                  color: '#ff9999'
                }}>
                  {autoSearchError}
                </div>
              )}
            </div>
          ) : (
            sortedFigures.map((fig) => (
              <div
                key={fig.name}
                className="fade-in"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  padding: '1.5rem 2rem',
                  borderBottom: '1px solid #2a2a2d',
                  background: 'rgba(26, 26, 29, 0.55)',
                  transition: 'background 0.2s',
                  cursor: 'pointer',
                }}
                onClick={() => setSelectedPerson(fig)}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(37, 37, 41, 0.7)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(26, 26, 29, 0.55)')}
              >
                {/* Person (Name + Image) */}
                <div
                  style={{
                    minWidth: '180px',
                    width: '180px',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '1rem',
                    borderRight: '1px solid #333',
                    paddingRight: '1rem',
                    marginRight: '1rem',
                  }}
                >
                  <div style={{ fontWeight: '600', fontSize: '1.2rem', textAlign: 'center', lineHeight: '1.2' }}>
                    {cleanPersonName(fig.name)}
                  </div>
                  
                  {fig.image_url ? (
                    <img
                      src={fig.image_url}
                      alt={fig.name}
                      style={{
                        width: '120px',
                        height: '120px',
                        borderRadius: '8px',
                        objectFit: 'cover',
                        border: '2px solid #333',
                      }}
                    />
                  ) : (
                    <div
                      style={{
                        width: '120px',
                        height: '120px',
                        borderRadius: '8px',
                        background: '#2a2a2d',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '3rem',
                        color: '#666',
                      }}
                    >
                      👤
                    </div>
                  )}
                </div>

                {/* Debug Column Data */}
                {showDebugColumns && (
                   <div
                    style={{
                      minWidth: '200px',
                      width: '200px',
                      fontSize: '0.9rem',
                      color: '#ffaaaa',
                      borderRight: '1px solid #333',
                      paddingRight: '1rem',
                      marginRight: '1rem',
                      overflowWrap: 'break-word',
                      alignSelf: 'flex-start'
                    }}
                  >
                    {fig.search_queries_used && fig.search_queries_used.length > 0 
                      ? fig.search_queries_used.join(', ')
                      : <span style={{opacity: 0.5}}>No info</span>
                    }
                  </div>
                )}

                {/* Challenges */}
                <div
                  style={{
                    minWidth: '250px',
                    width: '250px',
                    fontSize: '1.02rem',
                    color: '#ccc',
                    lineHeight: '1.4',
                    borderRight: '1px solid #333',
                    paddingRight: '1rem',
                    marginRight: '1rem',
                  }}
                >
                  {fig.challenges_faced ? (
                    stripMarkdown(fig.challenges_faced).slice(0, 100) + (fig.challenges_faced.length > 100 ? '...' : '')
                  ) : (
                    stripMarkdown(fig.marginalization_context)?.slice(0, 100) + '...'
                  )}
                </div>

                {/* Overcoming */}
                <div
                  style={{
                    minWidth: '250px',
                    width: '250px',
                    fontSize: '1.02rem',
                    color: '#ccc',
                    lineHeight: '1.4',
                    borderRight: '1px solid #333',
                    paddingRight: '1rem',
                    marginRight: '1rem',
                  }}
                >
                  {fig.how_they_overcame ? (
                    stripMarkdown(fig.how_they_overcame).slice(0, 100) + (fig.how_they_overcame.length > 100 ? '...' : '')
                  ) : (
                    <span style={{ color: '#666', fontStyle: 'italic' }}>View details...</span>
                  )}
                </div>

                {/* Overall Score */}
                <div
                  style={{
                    minWidth: '80px',
                    width: '80px',
                    textAlign: 'center',
                    fontSize: '1.2rem',
                    fontWeight: '700',
                    color: getScoreColor(fig.similarity_score),
                    borderRight: '1px solid #333',
                    paddingRight: '1rem',
                    marginRight: '1rem',
                  }}
                >
                  {(fig.similarity_score * 100).toFixed(0)}%
                </div>

                {/* Per-Facet Scores */}
                {columnsToShow.map((facet, index) => (
                  <div
                    key={facet}
                    style={{
                      minWidth: '100px',
                      width: '100px',
                      textAlign: 'center',
                      fontSize: '1.08rem',
                      fontWeight: '600',
                      color: getScoreColor(fig.facet_scores?.[facet] ?? 0),
                      borderRight: index < columnsToShow.length - 1 ? '1px solid #333' : 'none',
                      paddingRight: '1rem',
                      marginRight: '1rem',
                    }}
                  >
                    {fig.facet_scores?.[facet] !== undefined
                      ? (fig.facet_scores[facet] * 100).toFixed(0) + '%'
                      : '-'}
                  </div>
                ))}
              </div>
            ))
          )}
            </div>
          </div>
        </div>
      </div>
      
      {selectedPerson && (
        <PersonDetailModal
          person={selectedPerson}
          onClose={() => setSelectedPerson(null)}
        />
      )}
      </div>
    </>
  );
};

// Helper function to color-code similarity scores
const getScoreColor = (score) => {
  if (score >= 0.8) return '#4caf50'; // Green
  if (score >= 0.6) return '#8bc34a'; // Light green
  if (score >= 0.4) return '#ffc107'; // Yellow
  if (score >= 0.2) return '#ff9800'; // Orange
  return '#666'; // Gray
};

export default FacetedResultsView;
