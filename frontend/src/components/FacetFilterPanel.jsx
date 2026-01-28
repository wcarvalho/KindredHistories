/**
 * Shared component for displaying facet filter checkboxes.
 * Used by both FacetedResultsView and AuthenticatedApp.
 */
import React from 'react';

// Category groupings
const BACKGROUND_CATEGORIES = ['race', 'ethnicity', 'cultural_background', 'location', 'gender', 'sexuality'];
const GOALS_CATEGORIES = ['interests', 'aspirations'];

const FacetFilterPanel = ({
  facets = [], // Now array of { category, value }
  enabledFacets = new Set(), // Now Set of { category, value }
  onToggleFacet, // Signature: (category, value) => void
  matchCount = 0,
  isPolling = false,
  isAutoSearching = false, // NEW
  onRefresh = null,
  onCheckAll = null,
  onUncheckAll = null,
  filterMode = 'or', // 'and' or 'or'
  onModeChange = null // Signature: (mode) => void
}) => {
  return (
    <>
      <h2 style={{
        fontSize: '1.2rem',
        color: '#fff',
        marginBottom: '0.5rem',
        marginTop: 0,
        fontWeight: '700'
      }}>
        Filter by Facets
      </h2>
      <p style={{
      }}>
        Check/uncheck boxes to show people who share these properties
      </p>
      {/* Check All / Uncheck All buttons */}
      {(onCheckAll || onUncheckAll) && (
        <div style={{
          display: 'flex',
          gap: '0.5rem',
          marginBottom: '1rem'
        }}>
          {onCheckAll && (
            <button
              onClick={onCheckAll}
              style={{
                flex: 1,
                padding: '0.5rem',
                background: '#52b788',
                border: 'none',
                borderRadius: '6px',
                color: '#fff',
                cursor: 'pointer',
                fontSize: '0.85rem',
                fontWeight: '600',
                transition: 'background 0.2s'
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#40916c'}
              onMouseLeave={(e) => e.currentTarget.style.background = '#52b788'}
            >
              Check All
            </button>
          )}
          {onUncheckAll && (
            <button
              onClick={onUncheckAll}
              style={{
                flex: 1,
                padding: '0.5rem',
                background: '#d4a373',
                border: 'none',
                borderRadius: '6px',
                color: '#fff',
                cursor: 'pointer',
                fontSize: '0.85rem',
                fontWeight: '600',
                transition: 'background 0.2s'
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#b88e5f'}
              onMouseLeave={(e) => e.currentTarget.style.background = '#d4a373'}
            >
              Uncheck All
            </button>
          )}
        </div>
      )}

      {/* AND/OR Toggle */}
      {onModeChange && (
        <div style={{
          display: 'flex',
          gap: '0',
          marginBottom: '1rem',
          background: '#2a2a2d',
          borderRadius: '6px',
          padding: '2px',
          border: '1px solid #444'
        }}>
          <button
            onClick={() => onModeChange('or')}
            style={{
              flex: 1,
              padding: '0.5rem 0.75rem',
              background: filterMode === 'or' ? '#7c4dff' : 'transparent',
              border: 'none',
              borderRadius: '4px',
              color: filterMode === 'or' ? '#fff' : '#888',
              cursor: 'pointer',
              fontSize: '0.85rem',
              fontWeight: '600',
              transition: 'all 0.2s'
            }}
            title="Show figures matching ANY selected facet"
          >
            OR (Any)
          </button>
          <button
            onClick={() => onModeChange('and')}
            style={{
              flex: 1,
              padding: '0.5rem 0.75rem',
              background: filterMode === 'and' ? '#7c4dff' : 'transparent',
              border: 'none',
              borderRadius: '4px',
              color: filterMode === 'and' ? '#fff' : '#888',
              cursor: 'pointer',
              fontSize: '0.85rem',
              fontWeight: '600',
              transition: 'all 0.2s'
            }}
            title="Show figures matching ALL selected facets"
          >
            AND (All)
          </button>
        </div>
      )}

      <div style={{ marginBottom: '1rem', fontSize: '1.08rem', color: '#aaa' }}>
        <strong>{enabledFacets.size}</strong> facets enabled
      </div>

      {/* Facet Checkboxes - Split into Background and Goals */}
      {(() => {
        const backgroundFacets = facets.filter(f => BACKGROUND_CATEGORIES.includes(f.category));
        const goalsFacets = facets.filter(f => GOALS_CATEGORIES.includes(f.category));

        const renderFacetList = (facetList) => (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {facetList.map((facet) => {
              const isChecked = Array.from(enabledFacets).some(
                ef => ef.category === facet.category && ef.value === facet.value
              );

              return (
                <label
                  key={`${facet.category}:${facet.value}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    cursor: 'pointer',
                    fontSize: '1.08rem',
                    color: isChecked ? '#fff' : '#666',
                    transition: 'color 0.2s'
                  }}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => onToggleFacet(facet.category, facet.value)}
                    style={{
                      marginRight: '0.5rem',
                      cursor: 'pointer',
                      accentColor: '#7c4dff'
                    }}
                  />
                  {facet.value}
                </label>
              );
            })}
          </div>
        );

        const sectionHeaderStyle = {
          fontSize: '1rem',
          color: '#aaa',
          marginBottom: '0.5rem',
          marginTop: '0.75rem',
          fontWeight: '600',
          textTransform: 'uppercase',
          letterSpacing: '0.5px'
        };

        return (
          <div style={{ marginBottom: '1rem' }}>
            {backgroundFacets.length > 0 && (
              <>
                <h3 style={sectionHeaderStyle}>Background</h3>
                {renderFacetList(backgroundFacets)}
              </>
            )}
            {goalsFacets.length > 0 && (
              <>
                <h3 style={{ ...sectionHeaderStyle, marginTop: '1.25rem' }}>Goals</h3>
                {renderFacetList(goalsFacets)}
              </>
            )}
          </div>
        );
      })()}

      {facets.length === 0 && (
        <p style={{ color: '#666', fontSize: '1.08rem' }}>Loading facets...</p>
      )}

      {/* Match Count - Moved to bottom */}
      <div style={{
        marginTop: '1rem',
        fontSize: '1.08rem',
        color: '#fff',
        fontWeight: 'bold',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <span>
          {matchCount} Matches
          {isAutoSearching && ' (searching...)'}
          {!isAutoSearching && isPolling && ' (discovering...)'}
        </span>
        {onRefresh && (
          <button
            onClick={onRefresh}
            style={{
              padding: '0.4rem 0.75rem',
              background: '#2a2a2d',
              border: '1px solid #444',
              borderRadius: '6px',
              color: '#fff',
              cursor: 'pointer',
              fontSize: '0.75rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem'
            }}
            title="Refresh results"
          >
            🔄 Refresh
          </button>
        )}
      </div>
    </>
  );
};

export default FacetFilterPanel;
