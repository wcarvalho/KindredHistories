import React from 'react';
import ReactMarkdown from 'react-markdown';

const PersonDetailModal = ({ person, onClose }) => {
  if (!person) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.85)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 1000,
        backdropFilter: 'blur(5px)',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '90%',
          maxWidth: '800px',
          maxHeight: '90vh',
          backgroundColor: 'rgba(26, 26, 29, 0.85)',
          border: '1px solid #333',
          borderRadius: '12px',
          overflowY: 'auto',
          position: 'relative',
          boxShadow: '0 20px 50px rgba(0,0,0,0.5)',
          display: 'flex',
          flexDirection: 'column',
          animation: 'fadeIn 0.2s ease-out',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          style={{
            position: 'absolute',
            top: '1rem',
            right: '1rem',
            background: 'transparent',
            border: 'none',
            color: '#aaa',
            fontSize: '1.5rem',
            cursor: 'pointer',
            padding: '0.5rem',
            zIndex: 10,
          }}
        >
          ✕
        </button>

        <div style={{ padding: '2.5rem' }}>
          {/* Header Section */}
          <div style={{ display: 'flex', gap: '2rem', marginBottom: '2rem', alignItems: 'flex-start' }}>
            <img
              src={person.image_url}
              alt={person.name}
              style={{
                width: '200px',
                height: '200px',
                objectFit: 'cover',
                borderRadius: '8px',
                border: '1px solid #333',
                flexShrink: 0,
              }}
            />
            <div>
              <h2 style={{
                margin: '0 0 1rem 0',
                fontSize: '2.5rem',
                color: '#fff',
                lineHeight: '1.1'
              }}>
                {person.name}
              </h2>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            {/* Biography / Context */}
            {person.marginalization_context && (
              <section>
                <h3 style={{ color: '#7c4dff', marginBottom: '0.8rem', marginTop: 0 }}>Context</h3>
                <ReactMarkdown
                  components={{
                    p: ({node, ...props}) => <p style={{ fontSize: '1.1rem', lineHeight: '1.6', color: '#ddd', margin: 0 }} {...props} />,
                    strong: ({node, ...props}) => <strong style={{ color: '#fff', fontWeight: '600' }} {...props} />
                  }}
                >
                  {person.marginalization_context}
                </ReactMarkdown>
              </section>
            )}

            {/* Challenges */}
            <section>
              <h3 style={{ color: '#ff5252', marginBottom: '0.8rem', marginTop: 0 }}>Challenges Faced</h3>
              {person.challenges_faced ? (
                <ReactMarkdown
                  components={{
                    p: ({node, ...props}) => <p style={{ fontSize: '1.1rem', lineHeight: '1.6', color: '#ddd', margin: 0 }} {...props} />,
                    strong: ({node, ...props}) => <strong style={{ color: '#fff', fontWeight: '600' }} {...props} />
                  }}
                >
                  {person.challenges_faced}
                </ReactMarkdown>
              ) : (
                <p style={{ fontSize: '1.1rem', lineHeight: '1.6', color: '#666', fontStyle: 'italic', margin: 0 }}>
                  Specific details about challenges faced are being researched...
                </p>
              )}
            </section>

            {/* How they Overcame */}
            <section>
              <h3 style={{ color: '#4caf50', marginBottom: '0.8rem', marginTop: 0 }}>How They Overcame</h3>
              {person.how_they_overcame ? (
                <ReactMarkdown
                  components={{
                    p: ({node, ...props}) => <p style={{ fontSize: '1.1rem', lineHeight: '1.6', color: '#ddd', margin: 0 }} {...props} />,
                    strong: ({node, ...props}) => <strong style={{ color: '#fff', fontWeight: '600' }} {...props} />
                  }}
                >
                  {person.how_they_overcame}
                </ReactMarkdown>
              ) : (
                <p style={{ fontSize: '1.1rem', lineHeight: '1.6', color: '#666', fontStyle: 'italic', margin: 0 }}>
                  Specific details about how they overcame these challenges are being researched...
                </p>
              )}
            </section>

            {/* Achievements */}
            <section>
              <h3 style={{ color: '#ffca28', marginBottom: '0.8rem', marginTop: 0 }}>Achievements</h3>
              <ReactMarkdown
                components={{
                  p: ({node, ...props}) => <p style={{ fontSize: '1.1rem', lineHeight: '1.6', color: '#ddd', margin: 0 }} {...props} />,
                  strong: ({node, ...props}) => <strong style={{ color: '#fff', fontWeight: '600' }} {...props} />
                }}
              >
                {person.achievement}
              </ReactMarkdown>
            </section>
          </div>
        </div>
      </div>
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: scale(0.95); }
          to { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  );
};

export default PersonDetailModal;
