/**
 * Authentication context for managing user state globally.
 *
 * Test Mode: Add ?testAuth=true to URL to simulate a logged-in test user
 * without requiring Google OAuth. Useful for automated testing with Puppeteer.
 */
import React, { createContext, useContext, useState, useEffect } from 'react';
import {
  signInWithPopup,
  signOut as firebaseSignOut,
  onAuthStateChanged
} from 'firebase/auth';
import { auth, googleProvider } from '../firebase';
import { API_URL } from '../config';

const AuthContext = createContext();

// Test user for automated testing (when ?testAuth=true is in URL)
const TEST_USER = {
  uid: 'test-user-puppeteer-001',
  email: 'test@kindredhistories.test',
  displayName: 'Test User',
  photoURL: 'https://ui-avatars.com/api/?name=Test+User&background=7c4dff&color=fff'
};

// Check if test auth mode is enabled via URL parameter
const isTestAuthMode = () => {
  if (typeof window === 'undefined') return false;
  const params = new URLSearchParams(window.location.search);
  return params.get('testAuth') === 'true';
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [idToken, setIdToken] = useState(null);
  const [isTestMode, setIsTestMode] = useState(false);

  useEffect(() => {
    // Check for test auth mode first
    if (isTestAuthMode()) {
      console.log('[AuthContext] Test auth mode enabled - using mock user');
      setIsTestMode(true);
      setUser(TEST_USER);
      setIdToken('test-token-for-puppeteer');
      setLoading(false);
      return; // Skip Firebase auth listener in test mode
    }

    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      if (firebaseUser) {
        // Get ID token for backend auth
        const token = await firebaseUser.getIdToken();
        setIdToken(token);
        setUser({
          uid: firebaseUser.uid,
          email: firebaseUser.email,
          displayName: firebaseUser.displayName,
          photoURL: firebaseUser.photoURL
        });

        // Notify backend of login
        try {
          await fetch(`${API_URL}/api/auth/login`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            }
          });
        } catch (error) {
          console.error('Failed to sync user with backend:', error);
        }
      } else {
        setUser(null);
        setIdToken(null);
      }
      setLoading(false);
    });

    return unsubscribe;
  }, []);

  const signInWithGoogle = async () => {
    // In test mode, just set the test user
    if (isTestMode) {
      console.log('[AuthContext] Test mode sign-in');
      setUser(TEST_USER);
      setIdToken('test-token-for-puppeteer');
      return;
    }

    try {
      await signInWithPopup(auth, googleProvider);
    } catch (error) {
      console.error('Error signing in:', error);
      throw error;
    }
  };

  const signOut = async () => {
    // In test mode, just clear the user
    if (isTestMode) {
      console.log('[AuthContext] Test mode sign-out');
      setUser(null);
      setIdToken(null);
      return;
    }

    try {
      await firebaseSignOut(auth);
    } catch (error) {
      console.error('Error signing out:', error);
      throw error;
    }
  };

  // Helper to get a fresh token (refreshes if needed)
  const getValidToken = async () => {
    // In test mode, return the test token
    if (isTestMode) {
      return 'test-token-for-puppeteer';
    }

    if (!auth.currentUser) {
      return null;
    }

    try {
      // force=true will refresh if token is expired
      const token = await auth.currentUser.getIdToken(true);
      setIdToken(token);
      return token;
    } catch (error) {
      console.error('Error refreshing token:', error);
      return idToken; // Fallback to existing token
    }
  };

  const value = {
    user,
    loading,
    idToken,
    getValidToken,
    signInWithGoogle,
    signOut
  };

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        background: '#0f0f11',
        color: '#e0e0e0'
      }}>
        <div style={{
          textAlign: 'center',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '1rem'
        }}>
          <div style={{
            width: '40px',
            height: '40px',
            border: '3px solid rgba(124, 77, 255, 0.3)',
            borderTop: '3px solid #7c4dff',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite'
          }} />
          <div style={{ fontSize: '0.9rem', color: '#888' }}>Loading...</div>
          <style>{`
            @keyframes spin {
              0% { transform: rotate(0deg); }
              100% { transform: rotate(360deg); }
            }
          `}</style>
        </div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
