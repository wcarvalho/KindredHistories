import React, { useState } from 'react';
import '../index.css';
import credits from '../credits.json';

const ChatInterface = ({ onSubmit }) => {
  const [text, setText] = useState('');
  const [loadingStage, setLoadingStage] = useState(null); // null | 'extracting' | 'analyzing' | 'loading_results'
  const [showWhy, setShowWhy] = useState(false);

  // Helper function to get loading text based on stage
  const getLoadingText = (stage) => {
    switch (stage) {
      case 'extracting': return 'Understanding your background...';
      case 'analyzing': return 'Finding matching figures...';
      case 'loading_results': return 'Loading results...';
      default: return 'Processing...';
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    setLoadingStage('extracting');
    await onSubmit(text, setLoadingStage);
    setLoadingStage(null);
  };

  return (
    <>
      {/* Contributors Credit - Bottom Right Corner */}
      {credits.contributors && credits.contributors.length > 0 && (
        <div style={{
          position: 'fixed',
          bottom: '1rem',
          right: '1rem',
          fontSize: '0.85rem',
          color: 'rgba(255,255,255,0.6)',
          display: 'flex',
          gap: '0.3rem',
          flexWrap: 'wrap',
          justifyContent: 'flex-end',
          alignItems: 'center',
          textAlign: 'right',
          zIndex: 1000,
          maxWidth: '300px'
        }}>
          <span>with help from</span>
          {credits.contributors.map((person, index) => (
            <span key={index}>
              <a
                href={person.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: '#69B1E3', textDecoration: 'none' }}
              >
                {person.name}
              </a>
              {index < credits.contributors.length - 1 && ', '}
            </span>
          ))}
        </div>
      )}

      <div className="container" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: '80vh' }}>
        <div className="fade-in" style={{ width: '100%', maxWidth: '700px', textAlign: 'center' }}>
        <h1 style={{ fontSize: '2.5rem', marginBottom: '1rem', background: 'linear-gradient(45deg, #7c4dff, #ff4081)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
          {/*A Portal to <em style={{ fontFamily: 'Georgia, "Times New Roman", serif', fontStyle: 'italic' }}>Kindred</em> but Forgotten Histories*/}
          A Portal to Forgotten Histories
        </h1>
        {/*<p style={{ marginBottom: '1rem', color: '#aaa', fontSize: '1.2rem' }}>
          Discover forgotten historical figures who share your story.
        </p>*/}

        {/* Creator Credit - Below Title */}
        <div style={{
          marginBottom: '0.5rem',
          fontSize: '1rem',
          color: 'rgba(255,255,255,0.7)',
          textAlign: 'center'
        }}>
          with <span style={{ color: '#ff4d4d' }}> ❤️</span>, by {' '}
          <a
            href={credits.creator.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#69B1E3', textDecoration: 'none' }}
          >
            {credits.creator.name}
          </a>
        </div>

        {/* Why Section */}
        <div style={{ marginBottom: '.5rem', position: 'relative' }}>
          <button
            onClick={() => setShowWhy(!showWhy)}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#7c4dff',
              cursor: 'pointer',
              fontSize: '0.9rem',
              textDecoration: 'underline',
              padding: 0,
              margin: '0 auto'
            }}
          >
            why?
          </button>

          {showWhy && (
            <div style={{
              position: 'absolute',
              top: '100%',
              left: '50%',
              transform: 'translateX(-50%)',
              marginTop: '1rem',
              padding: '1.5rem',
              background: 'rgba(26, 26, 30, 0.98)',
              borderRadius: '8px',
              border: '1px solid rgba(124, 77, 255, 0.3)',
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.5)',
              color: '#ddd',
              fontSize: '0.95rem',
              lineHeight: '1.6',
              textAlign: 'left',
              maxWidth: '600px',
              width: '90%',
              zIndex: 100
            }}>
              <p style={{ margin: 0 }}>
                If you come from a marginalized or disenfranchised background, there are people who share your identity who have done incredible things. <b>Many of their stories were never taught or widely shared.</b> Maybe you're Bolivian-American, like I am, and you've never heard about the scientists, politicians, lawyers, or athletes who come from your background.              </p>
              <p style={{ marginTop: '1rem', marginBottom: 0 }}>
                What we believe is possible is shaped by what we see. When we see people like us doing remarkable things, new futures start to feel real. <b>This tool helps surface those stories, so people can see themselves in them—and imagine what they might become.</b>              </p>
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <textarea
            className="input-field"
            rows="6"
            placeholder="Describe yourself and your aspirations... e.g. 'I am a Bolivian New Yorker that wants to help more people get into STEM' 
            
            
and learn about amazing historical figures who share your identity."
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <button type="submit" className="btn" disabled={!!loadingStage} style={{ alignSelf: 'center', minWidth: '200px' }}>
            {loadingStage ? getLoadingText(loadingStage) : 'Begin Journey'}
          </button>
        </form>
      </div>
    </div>
    </>
  );
};

export default ChatInterface;
