/**
 * Sidebar component for Test Mode.
 * Lists available examples and allows re-running searches.
 */
import React from 'react';

const TestModeSidebar = ({ 
  examples, 
  selectedExample, 
  onSelectExample, 
  onRedo, 
  isRedoing 
}) => {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      marginTop: '2rem',
      paddingTop: '2rem',
      borderTop: '1px solid #333'
    }}>
      <h3 style={{ fontSize: '1.2rem', color: '#fff', marginBottom: '1rem', marginTop: 0 }}>
        Test Examples
      </h3>
      {/* Redo Button */}
      <div style={{ marginBottom: '1.5rem' }}>
        <button
          onClick={onRedo}
          disabled={!selectedExample || isRedoing}
          style={{
            width: '100%',
            padding: '0.75rem',
            background: isRedoing ? '#444' : '#7c4dff',
            border: 'none',
            borderRadius: '8px',
            color: '#fff',
            cursor: (!selectedExample || isRedoing) ? 'not-allowed' : 'pointer',
            fontSize: '0.9rem',
            fontWeight: '500',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.5rem',
            transition: 'background 0.2s'
          }}
        >
          {isRedoing ? 'Running Analysis...' : 'Redo Search Analysis'}
        </button>
      </div>

      {/* Example List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', overflowY: 'auto' }}>
        {Object.keys(examples).map((key) => {
          const example = examples[key];
          const isSelected = selectedExample === key;
          
          return (
            <div
              key={key}
              onClick={() => onSelectExample(key)}
              style={{
                padding: '0.75rem',
                background: isSelected ? 'rgba(124, 77, 255, 0.15)' : 'rgba(26, 26, 29, 0.55)',
                borderRadius: '6px',
                border: isSelected ? '1px solid #7c4dff' : '1px solid #333',
                cursor: 'pointer',
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => {
                if (!isSelected) {
                  e.currentTarget.style.background = 'rgba(37, 37, 41, 0.7)';
                  e.currentTarget.style.borderColor = '#7c4dff';
                }
              }}
              onMouseLeave={(e) => {
                if (!isSelected) {
                  e.currentTarget.style.background = 'rgba(26, 26, 29, 0.55)';
                  e.currentTarget.style.borderColor = '#333';
                }
              }}
            >
              <div style={{
                fontSize: '0.9rem',
                color: isSelected ? '#fff' : '#ccc',
                lineHeight: '1.4',
                // Limit lines if text is very long?
                display: '-webkit-box',
                WebkitLineClamp: isSelected ? 'none' : '3',
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden'
              }}>
                {example.description}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default TestModeSidebar;
