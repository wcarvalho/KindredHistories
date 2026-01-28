import React, { useState, useEffect } from 'react';

// Strip markdown formatting from text
const stripMarkdown = (text) => {
  if (!text) return '';
  return text
    .replace(/^#{1,6}\s*/gm, '')  // Remove heading markers
    .replace(/\*\*([^*]+)\*\*/g, '$1')  // Remove bold **text**
    .replace(/\*([^*]+)\*/g, '$1')  // Remove italic *text*
    .replace(/__([^_]+)__/g, '$1')  // Remove bold __text__
    .replace(/_([^_]+)_/g, '$1')  // Remove italic _text_
    .trim();
};

const ResultsView = ({ figures = [] }) => {
  const [activeFacets, setActiveFacets] = useState(new Set());
  const [availableFacets, setAvailableFacets] = useState({});

  useEffect(() => {
    // Extract facets from figures
    const facets = {};
    figures.forEach(fig => {
      Object.entries(fig.tags).forEach(([key, values]) => {
        if (!facets[key]) facets[key] = new Set();
        // Filter out empty/falsy values
        values.forEach(v => {
          if (v && typeof v === 'string' && v.trim()) {
            facets[key].add(v);
          }
        });
      });
    });
    setAvailableFacets(facets);
  }, [figures]);

  const toggleFacet = (category, value) => {
    const facetId = `${category}:${value}`;
    const newActive = new Set(activeFacets);
    if (newActive.has(facetId)) {
      newActive.delete(facetId);
    } else {
      newActive.add(facetId);
    }
    setActiveFacets(newActive);
  };

  const filteredFigures = figures.filter(fig => {
    if (activeFacets.size === 0) return true;
    // Check if figure matches ANY active facet
    // User instructions: "Rows where ANY matches should show, not where ALL matches."
    // Wait, actually user says: "I want every individual piece of the social model to define a facet and a person can turn facets off and then all people who don't fit the facet are removed."
    // Re-reading: "rows where ANY matches should show" vs "all people who don't fit the facet are removed" is contradictory.
    // Usually facets are AND between categories, OR within categories.
    // But user said: "Turn facets off and then all people who don't fit the facet are removed." -> This implies filtering IN those who match the remaining.
    // Let's assume standard faceted search: If I select "Mexico", I only see "Mexico".
    // If I select "Mexico" AND "Scientist", I see people who are both? Or either?
    // User: "Rows where ANY matches should show, not where ALL matches" suggests OR logic.
    // But "turn facets off... removed" suggests standard filtering.
    // I'll implement OR logic for now as requested.
    
    for (const [key, values] of Object.entries(fig.tags)) {
      for (const val of values) {
        if (activeFacets.has(`${key}:${val}`)) return true;
      }
    }
    return false;
  });
  
  // BUT logic above is "If active facets > 0, only show matches".
  // If 0 active facets, show all.
  
  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* Sidebar */}
      <div style={{ width: '300px', background: '#131315', padding: '1rem', overflowY: 'auto', borderRight: '1px solid #333' }}>
        <h2 style={{ fontSize: '1.2rem', marginBottom: '1rem' }}>Facets</h2>
        {Object.entries(availableFacets).map(([category, values]) => (
          <div key={category} style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ fontSize: '0.9rem', color: '#888', textTransform: 'uppercase', marginBottom: '0.5rem' }}>{category}</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
              {Array.from(values).map(val => {
                const isActive = activeFacets.has(`${category}:${val}`);
                return (
                  <button
                    key={val}
                    onClick={() => toggleFacet(category, val)}
                    style={{
                      background: isActive ? 'var(--accent-color)' : '#252529',
                      color: isActive ? 'white' : '#aaa',
                      border: 'none',
                      padding: '4px 8px',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '0.8rem'
                    }}
                  >
                    {val}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Main Content */}
      <div style={{ flex: 1, padding: '2rem', overflowY: 'auto', background: '#0f0f11' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1.5rem' }}>
          {filteredFigures.map((fig) => (
            <div key={fig.name} className="fade-in" style={{ background: '#1a1a1d', borderRadius: '12px', overflow: 'hidden', border: '1px solid #333' }}>
              <div style={{ height: '200px', background: '#222', overflow: 'hidden' }}>
                {fig.image_url ? (
                  <img src={fig.image_url} alt={fig.name} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                ) : (
                  <div style={{ width: '100%', height: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', color: '#444' }}>No Image</div>
                )}
              </div>
              <div style={{ padding: '1.5rem' }}>
                <h3 style={{ marginTop: 0, fontSize: '1.4rem' }}>{stripMarkdown(fig.name)}</h3>
                <p style={{ fontSize: '0.9rem', color: '#ccc', lineHeight: '1.5' }}>{stripMarkdown(fig.marginalization_context)}</p>
                <div style={{ marginTop: '1rem', fontSize: '0.8rem', color: '#888' }}>
                  <strong>Achievement:</strong> {stripMarkdown(fig.achievement)}
                </div>
              </div>
            </div>
          ))}
          {filteredFigures.length === 0 && (
            <p style={{ gridColumn: '1/-1', textAlign: 'center', color: '#666', marginTop: '2rem' }}>
              {figures.length === 0 ? "Searching history... One moment." : "No matches found for selected filters."}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default ResultsView;
