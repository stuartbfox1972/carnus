import React, { useState, useEffect } from 'react';
import { Authenticator } from '@aws-amplify/ui-react';
import { fetchAuthSession } from 'aws-amplify/auth';
import TagCloud from './components/TagCloud';
import GalleryGrid from './components/GalleryGrid';
import ImageModal from './components/ImageModal';
import '@aws-amplify/ui-react/styles.css';

const globalStyles = `
  .pill-bar-container { display: flex; overflow-x: auto; gap: 8px; padding: 15px 0; border-bottom: 1px solid #e2e8f0; scrollbar-width: none; }
  .ai-pill { white-space: nowrap; padding: 6px 16px; border-radius: 20px; font-size: 13px; background: #f1f5f9; cursor: pointer !important; transition: all 0.2s; }
  .ai-pill:hover { background: #e2e8f0; }
  .modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(15, 23, 42, 0.9); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 20px; backdrop-filter: blur(4px); }
  .pivot-link { cursor: pointer !important; color: #3b82f6; text-decoration: underline; font-weight: bold; }
  .status-pill { padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: bold; cursor: pointer !important; border: none; color: white; margin: 3px; background: #3b82f6; }
`;

function Dashboard() {
  const [tags, setTags] = useState([]);
  const [images, setImages] = useState([]);
  const [selectedTag, setSelectedTag] = useState(null);
  const [selectedImage, setSelectedImage] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [nextKey, setNextKey] = useState(null);
  const [loading, setLoading] = useState(false);

  // Fetch the main tag list for the TagCloud
  const fetchTags = async () => {
    try {
      const session = await fetchAuthSession();
      const response = await fetch('/tags', {
        headers: { 'Authorization': session.tokens?.idToken?.toString() }
      });
      const data = await response.json();
      // Normalized to match expected component props
      setTags(data.map(item => ({ 
        LabelName: item.Text, 
        Count: item.Count,
        SK: `TAG#${item.Text}` 
      })));
    } catch (e) {
      console.error("Error fetching tags:", e);
    }
  };

  // Main navigation and search handler
  const handleTagClick = async (tagValue, isLoadMore = false) => {
    const dbTag = tagValue.startsWith('TAG#') ? tagValue : `TAG#${tagValue}`;

    // UI resets: Close modal and set selection
    setSelectedTag(dbTag);
    setSelectedImage(null); 

    if (!isLoadMore) {
      setImages([]);
      setNextKey(null);
      setLoading(true);
    }

    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();
      let url = `/tags/${encodeURIComponent(dbTag)}?limit=50`;
      if (isLoadMore && nextKey) url += `&next_token=${encodeURIComponent(nextKey)}`;

      const response = await fetch(url, { headers: { 'Authorization': token } });
      const data = await response.json();

      if (data && data.items) {
        setImages(prev => isLoadMore ? [...prev, ...data.items] : data.items);
        setNextKey(data.next_token || null);
      }
    } catch (err) {
      console.error("Error fetching gallery:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchTags(); }, []);

  return (
    <div style={{ minHeight: '100vh', background: '#f8f9fa' }}>
      <style>{globalStyles}</style>

      <header style={{ background: '#232f3e', color: 'white', padding: '1rem 2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong
          onClick={() => { setSelectedTag(null); setImages([]); }}
          style={{ cursor: 'pointer', fontSize: '1.2rem', letterSpacing: '1px' }}
        >
          CARNUS CONSOLE
        </strong>
        <Authenticator>
          {({ signOut }) => <button onClick={signOut} style={{ cursor: 'pointer' }}>Sign Out</button>}
        </Authenticator>
      </header>

      <main style={{ padding: '40px', maxWidth: '1200px', margin: '0 auto' }}>

        {/* MODAL: Handles details and hardware pivots */}
        <ImageModal
          image={selectedImage}
          onClose={() => setSelectedImage(null)}
          onTagClick={handleTagClick}
        />

        {/* VIEW LOGIC: Cloud vs Gallery */}
        {!selectedTag ? (
          <TagCloud
            tags={tags}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            onTagClick={handleTagClick}
          />
        ) : (
          <div style={{ marginTop: '20px' }}>
            {loading && images.length === 0 ? (
              <div style={{ textAlign: 'center', marginTop: '100px' }}><h3>Loading items...</h3></div>
            ) : (
              <GalleryGrid
                images={images}
                selectedTag={selectedTag}
                onImageClick={setSelectedImage}
                onBack={() => { setSelectedTag(null); setImages([]); }}
                nextKey={nextKey}
                onLoadMore={() => handleTagClick(selectedTag, true)}
              />
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Authenticator.Provider>
      <Dashboard />
    </Authenticator.Provider>
  );
}
