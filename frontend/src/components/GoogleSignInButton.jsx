/**
 * Google Sign-In button component.
 */
import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';

const GoogleSignInButton = () => {
  const { user, signInWithGoogle, signOut } = useAuth();
  const [loading, setLoading] = useState(false);

  const handleSignIn = async () => {
    setLoading(true);
    try {
      await signInWithGoogle();
    } catch (error) {
      console.error('Sign-in failed:', error);
    }
    setLoading(false);
  };

  if (user) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        padding: '0.5rem 1rem',
        background: '#2a2a2d',
        borderRadius: '8px',
        border: '1px solid #444'
      }}>
        {user.photoURL && (
          <img
            src={user.photoURL}
            alt={user.displayName}
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '50%'
            }}
          />
        )}
        <span style={{ color: '#fff', fontSize: '0.9rem' }}>
          {user.displayName || user.email}
        </span>
        <button
          onClick={signOut}
          style={{
            padding: '0.25rem 0.75rem',
            background: 'transparent',
            border: '1px solid #666',
            borderRadius: '4px',
            color: '#aaa',
            cursor: 'pointer',
            fontSize: '0.8rem'
          }}
        >
          Sign Out
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={handleSignIn}
      disabled={loading}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        padding: '0.5rem 1rem',
        background: '#4a5568',
        border: '1px solid #5a6a7a',
        borderRadius: '8px',
        cursor: 'pointer',
        fontSize: '0.9rem',
        fontWeight: '500',
        color: '#e2e8f0'
      }}
    >
      <svg width="18" height="18" viewBox="0 0 18 18">
        <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
        <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/>
        <path fill="#FBBC05" d="M3.964 10.707c-.18-.54-.282-1.117-.282-1.707 0-.593.102-1.17.282-1.707V4.961H.957C.347 6.175 0 7.55 0 9s.348 2.825.957 4.039l3.007-2.332z"/>
        <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.961L3.964 7.293C4.672 5.163 6.656 3.58 9 3.58z"/>
      </svg>
      {loading ? 'Signing in...' : 'Sign in with Google'}
    </button>
  );
};

export default GoogleSignInButton;
